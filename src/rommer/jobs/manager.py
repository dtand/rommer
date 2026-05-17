"""Job manager - creates, tracks, and runs background jobs."""

import json
import sqlite3
import subprocess
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from rommer.config import Project


# Global callback for WebSocket broadcasting (set by backend on startup)
_broadcast_fn: Callable[[dict], None] | None = None


def set_broadcast(fn: Callable[[dict], None]):
    """Set the WebSocket broadcast function (called by backend startup)."""
    global _broadcast_fn
    _broadcast_fn = fn


def _broadcast(event: dict):
    """Emit an event to connected WebSocket clients."""
    if _broadcast_fn:
        _broadcast_fn(event)


class JobManager:
    """Manages background jobs for a project."""

    # Track running subprocesses by job_id
    _processes: dict[str, subprocess.Popen] = {}

    def __init__(self, project: Project):
        self.project = project
        self._db: sqlite3.Connection | None = None

    @property
    def db(self) -> sqlite3.Connection:
        """Get a thread-local DB connection."""
        # Create new connection per access to handle threading
        # SQLite with WAL mode supports concurrent readers
        if self._db is None:
            self._db = self.project.get_db()
        return self._db

    def _fresh_db(self) -> sqlite3.Connection:
        """Get a fresh connection (for use in worker threads)."""
        return self.project.get_db()

    def create_job(self, job_type: str, config: dict | None = None) -> str:
        """Create a new pending job. Returns job_id."""
        job_id = str(uuid.uuid4())[:12]
        project_id = self._get_project_id()

        self.db.execute(
            """INSERT INTO job (id, project_id, type, status, config, created_at)
               VALUES (?, ?, ?, 'pending', ?, ?)""",
            (job_id, project_id, job_type, json.dumps(config or {}),
             datetime.now(timezone.utc).isoformat()),
        )
        self.db.commit()
        return job_id

    def start_job(self, job_id: str) -> None:
        """Queue a job for execution by the worker daemon.

        Sets status to 'pending' — the daemon picks it up and runs it
        as a subprocess. No threads spawned here.
        """
        # Job is already created as 'pending' by create_job().
        # If called explicitly, ensure it's pending so daemon picks it up.
        self.db.execute(
            "UPDATE job SET status = 'pending' WHERE id = %s" if hasattr(self.db, '_conn') else
            "UPDATE job SET status = 'pending' WHERE id = ?",
            (job_id,),
        )
        self.db.commit()

    def cancel_job(self, job_id: str) -> bool:
        """Cancel a running job by killing its process."""
        # Try to kill by PID from DB
        status = self.get_status(job_id)
        if status and status.get("pid"):
            try:
                import os, signal
                os.kill(status["pid"], signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                pass

        self.db.execute(
            "UPDATE job SET status = 'cancelled', completed_at = ? WHERE id = ?",
            (datetime.now(timezone.utc).isoformat(), job_id),
        )
        self.db.commit()
        _broadcast({"type": "job_cancelled", "job_id": job_id, "project": self.project.name})
        return True

    def get_status(self, job_id: str) -> dict | None:
        """Get current job status."""
        placeholder = "%s" if hasattr(self.db, '_conn') else "?"
        row = self.db.execute(
            f"SELECT * FROM job WHERE id = {placeholder}", (job_id,)
        ).fetchone()
        if not row:
            return None
        return {
            "id": row["id"],
            "type": row["type"],
            "status": row["status"],
            "progress": json.loads(row["progress"]) if row["progress"] else None,
            "config": json.loads(row["config"]) if row["config"] else {},
            "pid": row.get("pid"),
            "created_at": row["created_at"],
            "started_at": row["started_at"],
            "completed_at": row["completed_at"],
            "error": row["error"],
        }

    def list_jobs(self) -> list[dict]:
        """List all jobs for this project."""
        project_id = self._get_project_id()
        rows = self.db.execute(
            "SELECT * FROM job WHERE project_id = ? ORDER BY created_at DESC", (project_id,)
        ).fetchall()
        return [
            {
                "id": r["id"],
                "type": r["type"],
                "status": r["status"],
                "progress": json.loads(r["progress"]) if r["progress"] else None,
                "created_at": r["created_at"],
                "started_at": r["started_at"],
                "completed_at": r["completed_at"],
                "error": r["error"],
            }
            for r in rows
        ]

    def emit_progress(self, job_id: str, step: str, percent: int, message: str = ""):
        """Update job progress — DB only (Postgres NOTIFY handles broadcast)."""
        progress = {"step": step, "percent": percent, "message": message}
        p = "%s" if hasattr(self.db, '_conn') else "?"
        self.db.execute(
            f"UPDATE job SET progress = {p} WHERE id = {p}",
            (json.dumps(progress), job_id),
        )
        self.db.execute(
            f"INSERT INTO job_event (job_id, type, data) VALUES ({p}, 'progress', {p})",
            (job_id, json.dumps(progress)),
        )
        self.db.commit()

    def complete_job(self, job_id: str, summary: str = ""):
        """Mark job as completed — DB only."""
        p = "%s" if hasattr(self.db, '_conn') else "?"
        self.db.execute(
            f"UPDATE job SET status = 'completed', completed_at = {p} WHERE id = {p}",
            (datetime.now(timezone.utc).isoformat(), job_id),
        )
        self.db.execute(
            f"INSERT INTO job_event (job_id, type, data) VALUES ({p}, 'result', {p})",
            (job_id, json.dumps({"summary": summary})),
        )
        self.db.commit()

    def fail_job(self, job_id: str, error: str):
        """Mark job as failed — DB only."""
        p = "%s" if hasattr(self.db, '_conn') else "?"
        self.db.execute(
            f"UPDATE job SET status = 'failed', completed_at = {p}, error = {p} WHERE id = {p}",
            (datetime.now(timezone.utc).isoformat(), error, job_id),
        )
        self.db.execute(
            f"INSERT INTO job_event (job_id, type, data) VALUES ({p}, 'error', {p})",
            (job_id, json.dumps({"error": error})),
        )
        self.db.commit()

    def _run_worker(self, job_id: str):
        """Execute the job's worker function in a background thread.

        Creates a NEW JobManager instance per thread to avoid
        shared DB connection issues with SQLite threading.
        """
        from rommer.jobs.worker import WORKERS

        # Each thread gets its own JobManager with its own DB connection
        thread_mgr = JobManager(self.project)
        thread_mgr._db = thread_mgr._fresh_db()

        status = thread_mgr.get_status(job_id)
        if not status:
            return

        job_type = status["type"]
        config = status["config"]
        worker_fn = WORKERS.get(job_type)

        if not worker_fn:
            thread_mgr.fail_job(job_id, f"Unknown job type: {job_type}")
            return

        try:
            worker_fn(thread_mgr, job_id, self.project, config)
        except Exception as e:
            thread_mgr.fail_job(job_id, str(e))

    def create_parallel_jobs(
        self, job_type: str, config: dict, parallel: int, merge_strategy: str = "union"
    ) -> list[str]:
        """Create and start N parallel jobs with a merge step on completion.

        Each job runs independently. When all complete, discoveries are merged
        using the specified strategy.

        Returns list of job IDs.
        """
        group_id = str(uuid.uuid4())[:12]
        job_ids = []

        for i in range(parallel):
            job_config = {
                **config,
                "parallel_group": group_id,
                "parallel_index": i,
                "parallel_total": parallel,
                "merge_strategy": merge_strategy,
                "stage_discoveries": True,  # Write to job_discovery instead of discovery
            }
            job_id = self.create_job(job_type, job_config)
            job_ids.append(job_id)

        # Start all jobs
        for job_id in job_ids:
            self.start_job(job_id)

        # Start a watcher thread that merges when all complete
        watcher = threading.Thread(
            target=self._watch_parallel_group,
            args=(group_id, job_ids, merge_strategy),
            daemon=True,
        )
        watcher.start()

        return job_ids

    def _watch_parallel_group(self, group_id: str, job_ids: list[str], merge_strategy: str):
        """Wait for all parallel jobs to complete, then merge."""
        import time
        conn = self._fresh_db()

        while True:
            time.sleep(5)
            statuses = []
            for jid in job_ids:
                row = conn.execute("SELECT status FROM job WHERE id = ?", (jid,)).fetchone()
                statuses.append(row["status"] if row else "unknown")

            # Check if all done (completed or failed)
            if all(s in ("completed", "failed", "cancelled") for s in statuses):
                break

        # Only merge if at least one succeeded
        completed = [jid for jid, s in zip(job_ids, statuses) if s == "completed"]
        if not completed:
            return

        from rommer.jobs.merge import merge_discoveries
        result = merge_discoveries(self.project, completed, merge_strategy)

        # Broadcast merge result
        _broadcast({
            "type": "job_complete",
            "job_id": f"merge-{group_id}",
            "project": self.project.name,
            "data": {
                "summary": f"Merged {result['inserted']} discoveries from {len(completed)} agents ({merge_strategy})",
            },
        })

        conn.close()

    def _get_project_id(self) -> int:
        row = self.db.execute("SELECT id FROM project LIMIT 1").fetchone()
        return row[0] if row else 0
