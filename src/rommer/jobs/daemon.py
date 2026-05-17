"""Worker daemon — picks up pending jobs and executes them as subprocesses.

Usage:
    rommer worker start [--max-workers 4]
    rommer worker stop
    rommer worker status

The daemon polls the job table for pending jobs, claims them atomically,
and spawns each as a subprocess via runner.py. It monitors running
workers and reaps finished/crashed ones.
"""

import json
import os
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


class WorkerDaemon:
    """Manages job execution as subprocesses."""

    def __init__(self, max_workers: int = 4):
        self.max_workers = max_workers
        self.running: dict[str, subprocess.Popen] = {}  # job_id -> process
        self.should_stop = False

        signal.signal(signal.SIGTERM, self._handle_signal)
        signal.signal(signal.SIGINT, self._handle_signal)

    def _handle_signal(self, signum, frame):
        print(f"\nReceived signal {signum}, shutting down gracefully...")
        self.should_stop = True

    def run(self):
        """Main daemon loop."""
        print(f"Rommer worker daemon started (max_workers={self.max_workers}, pid={os.getpid()})")
        print(f"Polling for pending jobs...")

        while not self.should_stop:
            self.reap_finished()

            if len(self.running) < self.max_workers:
                job = self.pick_next_job()
                if job:
                    self.start_worker(job)

            time.sleep(2)

        # Graceful shutdown
        self.shutdown()

    def pick_next_job(self) -> dict | None:
        """Atomically claim the next pending job."""
        from rommer.db.connection import is_postgres, get_postgres_connection

        if is_postgres():
            conn = get_postgres_connection()
            cur = conn.cursor()
            try:
                # Atomic claim with FOR UPDATE SKIP LOCKED
                cur.execute("""
                    UPDATE job SET status = 'running', pid = %s, started_at = %s
                    WHERE id = (
                        SELECT id FROM job
                        WHERE status = 'pending'
                        ORDER BY created_at
                        LIMIT 1
                        FOR UPDATE SKIP LOCKED
                    )
                    RETURNING id, type, config, project_id
                """, (os.getpid(), datetime.now(timezone.utc).isoformat()))

                row = cur.fetchone()
                conn.commit()

                if not row:
                    return None

                # Get project name
                cur.execute("SELECT game_id FROM project WHERE id = %s", (row[3],))
                project_row = cur.fetchone()
                project_name = project_row[0] if project_row else None

                conn.close()
                return {
                    "id": row[0],
                    "type": row[1],
                    "config": json.loads(row[2]) if row[2] else {},
                    "project_name": project_name,
                }
            except Exception as e:
                conn.rollback()
                conn.close()
                return None
        else:
            # SQLite fallback — no SKIP LOCKED but single-machine so OK
            from rommer.config import Project
            for name in Project.list_projects():
                p = Project(name)
                conn = p.get_db()
                try:
                    row = conn.execute(
                        "SELECT id, type, config FROM job WHERE status = 'pending' ORDER BY created_at LIMIT 1"
                    ).fetchone()
                    if row:
                        conn.execute(
                            "UPDATE job SET status = 'running', pid = ?, started_at = ? WHERE id = ?",
                            (os.getpid(), datetime.now(timezone.utc).isoformat(), row["id"]),
                        )
                        conn.commit()
                        conn.close()
                        return {
                            "id": row["id"],
                            "type": row["type"],
                            "config": json.loads(row["config"]) if row["config"] else {},
                            "project_name": name,
                        }
                except Exception:
                    pass
                conn.close()
            return None

    def start_worker(self, job: dict):
        """Spawn a worker subprocess for a job."""
        job_id = job["id"]
        project_name = job["project_name"]

        if not project_name:
            print(f"  ERROR: No project for job {job_id}")
            return

        cmd = [
            sys.executable, "-m", "rommer.jobs.runner",
            "--job-id", job_id,
            "--project", project_name,
        ]

        print(f"  Starting {job['type']} ({job_id}) for {project_name}")

        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )

        self.running[job_id] = proc

    def reap_finished(self):
        """Check for completed or crashed workers."""
        for job_id, proc in list(self.running.items()):
            rc = proc.poll()
            if rc is None:
                continue  # Still running

            # Read any output
            output = ""
            try:
                output = proc.stdout.read()
            except Exception:
                pass

            del self.running[job_id]

            if rc == 0:
                print(f"  Completed: {job_id}")
                if output:
                    print(f"    {output.strip()[:200]}")
            else:
                print(f"  Failed: {job_id} (exit code {rc})")
                if output:
                    print(f"    {output.strip()[:500]}")
                # Mark as failed if not already
                self._mark_failed(job_id, f"Worker process exited with code {rc}")

    def _mark_failed(self, job_id: str, error: str):
        """Mark a job as failed in the DB."""
        from rommer.db.connection import is_postgres, get_postgres_connection
        if is_postgres():
            conn = get_postgres_connection()
            cur = conn.cursor()
            cur.execute(
                "UPDATE job SET status = 'failed', error = %s, completed_at = %s WHERE id = %s AND status = 'running'",
                (error, datetime.now(timezone.utc).isoformat(), job_id),
            )
            conn.commit()
            conn.close()

    def shutdown(self):
        """Gracefully stop all running workers."""
        if not self.running:
            print("No running workers.")
            return

        print(f"Stopping {len(self.running)} workers...")
        for job_id, proc in self.running.items():
            proc.terminate()

        # Wait up to 10s for graceful exit
        deadline = time.time() + 10
        for job_id, proc in list(self.running.items()):
            remaining = max(0, deadline - time.time())
            try:
                proc.wait(timeout=remaining)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
            print(f"  Stopped: {job_id}")

        self.running.clear()
        print("All workers stopped.")

    def status(self):
        """Print daemon status."""
        print(f"Running workers: {len(self.running)}/{self.max_workers}")
        for job_id, proc in self.running.items():
            print(f"  {job_id}: pid={proc.pid}")
