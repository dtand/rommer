"""rommer worker - manage the job worker daemon."""

import os
import signal
import sys


def handler(args):
    action = args.action

    if action == "start":
        _start(args)
    elif action == "stop":
        _stop()
    elif action == "status":
        _status()
    else:
        print(f"Unknown action: {action}")
        raise SystemExit(1)


def _start(args):
    """Start the worker daemon."""
    from rommer.jobs.daemon import WorkerDaemon

    max_workers = getattr(args, "max_workers", 4)
    daemon = WorkerDaemon(max_workers=max_workers)
    daemon.run()


def _stop():
    """Stop the worker daemon by sending SIGTERM to the PID file."""
    pid_file = "/tmp/rommer-worker.pid"
    if not os.path.exists(pid_file):
        print("No worker daemon running (no PID file)")
        return

    pid = int(open(pid_file).read().strip())
    try:
        os.kill(pid, signal.SIGTERM)
        print(f"Sent SIGTERM to worker daemon (pid {pid})")
    except ProcessLookupError:
        print(f"Worker daemon not running (stale PID {pid})")
        os.unlink(pid_file)


def _status():
    """Show worker daemon status."""
    pid_file = "/tmp/rommer-worker.pid"
    if os.path.exists(pid_file):
        pid = int(open(pid_file).read().strip())
        try:
            os.kill(pid, 0)  # Check if alive
            print(f"Worker daemon running (pid {pid})")
        except ProcessLookupError:
            print(f"Worker daemon not running (stale PID {pid})")
    else:
        print("Worker daemon not running")
