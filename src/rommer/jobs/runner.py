"""Standalone job runner — executes a single job as its own process.

Usage:
    python -m rommer.jobs.runner --job-id <id> --project <name>

Reads job config from DB, runs the appropriate worker function,
writes all events/progress to DB. Exits with code 0 on success, 1 on failure.
No WebSocket or FastAPI dependency.
"""

import argparse
import json
import os
import sys
import traceback


def main():
    parser = argparse.ArgumentParser(description="Run a single rommer job")
    parser.add_argument("--job-id", required=True, help="Job ID to execute")
    parser.add_argument("--project", required=True, help="Project name")
    args = parser.parse_args()

    # Import rommer to load .env
    import rommer
    from rommer.config import Project
    from rommer.jobs.manager import JobManager
    from rommer.jobs.worker import WORKERS

    project = Project(args.project)
    if not project.exists():
        print(f"Error: project '{args.project}' not found", file=sys.stderr)
        sys.exit(1)

    mgr = JobManager(project)
    status = mgr.get_status(args.job_id)
    if not status:
        print(f"Error: job '{args.job_id}' not found", file=sys.stderr)
        sys.exit(1)

    job_type = status["type"]
    config = status["config"]

    worker_fn = WORKERS.get(job_type)
    if not worker_fn:
        mgr.fail_job(args.job_id, f"Unknown job type: {job_type}")
        sys.exit(1)

    # Update PID
    mgr.db.execute(
        "UPDATE job SET pid = %s WHERE id = %s" if hasattr(mgr.db, '_conn') else
        "UPDATE job SET pid = ? WHERE id = ?",
        (os.getpid(), args.job_id),
    )
    mgr.db.commit()

    try:
        worker_fn(mgr, args.job_id, project, config)
    except Exception as e:
        mgr.fail_job(args.job_id, f"{type(e).__name__}: {e}")
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)

    # Check if runner should trigger parallel merge
    _check_parallel_merge(mgr, args.job_id, project, config)

    sys.exit(0)


def _check_parallel_merge(mgr, job_id, project, config):
    """If this job is part of a parallel group, check if we're the last one."""
    group = config.get("parallel_group")
    if not group:
        return

    merge_strategy = config.get("merge_strategy", "union")

    # Find all jobs in this group
    import json as _json
    all_jobs = mgr.list_jobs()
    group_jobs = [j for j in all_jobs if _json.loads(j.get("config") or "{}").get("parallel_group") == group
                  ] if isinstance(all_jobs, list) else []

    # For Postgres wrapper compatibility, re-query
    if not group_jobs:
        return

    statuses = [j["status"] for j in group_jobs]

    # All must be completed or failed
    if not all(s in ("completed", "failed", "cancelled") for s in statuses):
        return

    completed_ids = [j["id"] for j in group_jobs if j["status"] == "completed"]
    if not completed_ids:
        return

    from rommer.jobs.merge import merge_discoveries
    result = merge_discoveries(project, completed_ids, merge_strategy)
    print(f"Merged {result['inserted']} discoveries from {len(completed_ids)} agents ({merge_strategy})")


if __name__ == "__main__":
    main()
