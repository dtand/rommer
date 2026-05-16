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
        self._db = project.get_db()

    @property
    def db(self) -> sqlite3.Connection:
        return self._db

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
        """Start a job by spawning its worker in a background thread."""
        self.db.execute(
            "UPDATE job SET status = 'running', started_at = ? WHERE id = ?",
            (datetime.now(timezone.utc).isoformat(), job_id),
        )
        self.db.commit()

        _broadcast({"type": "job_started", "job_id": job_id, "project": self.project.name})

        # Run worker in background thread
        thread = threading.Thread(target=self._run_worker, args=(job_id,), daemon=True)
        thread.start()

    def cancel_job(self, job_id: str) -> bool:
        """Cancel a running job."""
        proc = self._processes.get(job_id)
        if proc and proc.poll() is None:
            proc.terminate()

        self.db.execute(
            "UPDATE job SET status = 'cancelled', completed_at = ? WHERE id = ?",
            (datetime.now(timezone.utc).isoformat(), job_id),
        )
        self.db.commit()
        _broadcast({"type": "job_cancelled", "job_id": job_id, "project": self.project.name})
        return True

    def get_status(self, job_id: str) -> dict | None:
        """Get current job status."""
        row = self.db.execute(
            "SELECT * FROM job WHERE id = ?", (job_id,)
        ).fetchone()
        if not row:
            return None
        return {
            "id": row["id"],
            "type": row["type"],
            "status": row["status"],
            "progress": json.loads(row["progress"]) if row["progress"] else None,
            "config": json.loads(row["config"]) if row["config"] else {},
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
        """Update job progress and broadcast to WebSocket."""
        progress = {"step": step, "percent": percent, "message": message}
        self.db.execute(
            "UPDATE job SET progress = ? WHERE id = ?",
            (json.dumps(progress), job_id),
        )
        self.db.execute(
            "INSERT INTO job_event (job_id, type, data) VALUES (?, 'progress', ?)",
            (job_id, json.dumps(progress)),
        )
        self.db.commit()

        _broadcast({
            "type": "job_progress",
            "job_id": job_id,
            "project": self.project.name,
            "data": progress,
        })

    def complete_job(self, job_id: str, summary: str = ""):
        """Mark job as completed."""
        self.db.execute(
            "UPDATE job SET status = 'completed', completed_at = ? WHERE id = ?",
            (datetime.now(timezone.utc).isoformat(), job_id),
        )
        self.db.execute(
            "INSERT INTO job_event (job_id, type, data) VALUES (?, 'result', ?)",
            (job_id, json.dumps({"summary": summary})),
        )
        self.db.commit()
        self._processes.pop(job_id, None)

        _broadcast({
            "type": "job_complete",
            "job_id": job_id,
            "project": self.project.name,
            "data": {"summary": summary},
        })

    def fail_job(self, job_id: str, error: str):
        """Mark job as failed."""
        self.db.execute(
            "UPDATE job SET status = 'failed', completed_at = ?, error = ? WHERE id = ?",
            (datetime.now(timezone.utc).isoformat(), error, job_id),
        )
        self.db.execute(
            "INSERT INTO job_event (job_id, type, data) VALUES (?, 'error', ?)",
            (job_id, json.dumps({"error": error})),
        )
        self.db.commit()
        self._processes.pop(job_id, None)

        _broadcast({
            "type": "job_failed",
            "job_id": job_id,
            "project": self.project.name,
            "error": error,
        })

    def _run_worker(self, job_id: str):
        """Execute the job's worker function."""
        from rommer.jobs.worker import WORKERS

        status = self.get_status(job_id)
        if not status:
            return

        job_type = status["type"]
        config = status["config"]
        worker_fn = WORKERS.get(job_type)

        if not worker_fn:
            self.fail_job(job_id, f"Unknown job type: {job_type}")
            return

        try:
            worker_fn(self, job_id, self.project, config)
        except Exception as e:
            self.fail_job(job_id, str(e))

    def _get_project_id(self) -> int:
        row = self.db.execute("SELECT id FROM project LIMIT 1").fetchone()
        return row[0] if row else 0
