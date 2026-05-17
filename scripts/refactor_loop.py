#!/usr/bin/env python3
"""Refactor loop - runs static analysis agents sequentially in a loop.

Monitors Ghidra job if running, then cycles through:
1. static_analysis
2. type_resolver
3. literal_pool
4. struct_annotator
5. forward_decl
6. system_tracer

Repeats until killed (Ctrl+C).

Usage:
    python scripts/refactor_loop.py --project robattle
    python scripts/refactor_loop.py --project robattle --wait-for-ghidra
"""

import argparse
import json
import sys
import time
import urllib.request

API = "http://localhost:8000/api"

STAGES = [
    ("static_analysis", "Static Analysis"),
    ("type_resolver", "Type Resolver"),
    ("literal_pool", "Literal Pool Resolver"),
    ("struct_annotator", "Struct Annotator"),
    ("forward_decl", "Forward Declarations"),
    ("system_tracer", "System Tracer"),
]


def api_get(path):
    req = urllib.request.Request(f"{API}{path}")
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def api_post(path, data):
    body = json.dumps(data).encode()
    req = urllib.request.Request(f"{API}{path}", data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def wait_for_job(job_id, label):
    """Poll until job completes or fails."""
    print(f"  Waiting for {label} ({job_id})...", flush=True)
    while True:
        status = api_get(f"/jobs/{job_id}")
        s = status.get("status", "unknown")
        progress = status.get("progress") or {}
        msg = progress.get("message", "")

        if s == "completed":
            print(f"  ✓ {label} completed", flush=True)
            return True
        elif s in ("failed", "cancelled"):
            err = status.get("error", "unknown error")
            print(f"  ✗ {label} {s}: {err}", flush=True)
            return False

        # Show progress
        pct = progress.get("percent", "")
        step = progress.get("step", "")
        if step:
            print(f"    [{pct}%] {step}: {msg[:60]}", end="\r", flush=True)

        time.sleep(10)


def wait_for_ghidra(project):
    """Wait for any running Ghidra job to complete."""
    print("Checking for running Ghidra jobs...", flush=True)
    jobs = api_get(f"/jobs?project={project}")
    ghidra_jobs = [j for j in jobs.get("jobs", []) if j["type"] == "ghidra_decompile" and j["status"] == "running"]

    if not ghidra_jobs:
        print("No running Ghidra jobs.", flush=True)
        return

    for j in ghidra_jobs:
        wait_for_job(j["id"], "Ghidra Decompile")


def kick_off_stage(project, stage_type, label):
    """Start a refactor stage job and wait for it."""
    if stage_type == "static_analysis":
        result = api_post("/jobs/static-analysis", {"project": project, "model": "opus"})
    else:
        result = api_post(f"/jobs/refactor/{stage_type}", {"project": project, "model": "opus"})

    job_id = result.get("job_id")
    if not job_id:
        print(f"  ✗ Failed to start {label}: {result}", flush=True)
        return False

    return wait_for_job(job_id, label)


def main():
    parser = argparse.ArgumentParser(description="Run refactor agents in a loop")
    parser.add_argument("--project", required=True)
    parser.add_argument("--wait-for-ghidra", action="store_true", help="Wait for Ghidra to finish first")
    args = parser.parse_args()

    if args.wait_for_ghidra:
        wait_for_ghidra(args.project)

    iteration = 0
    while True:
        iteration += 1
        print(f"\n{'='*60}", flush=True)
        print(f"REFACTOR LOOP - Iteration {iteration}", flush=True)
        print(f"{'='*60}", flush=True)

        for stage_type, label in STAGES:
            print(f"\n[{iteration}.{STAGES.index((stage_type, label)) + 1}] {label}", flush=True)
            success = kick_off_stage(args.project, stage_type, label)
            if not success:
                print(f"  Skipping to next stage...", flush=True)
                time.sleep(5)

        print(f"\nIteration {iteration} complete. Starting next loop...", flush=True)
        time.sleep(10)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nLoop stopped.", flush=True)
        sys.exit(0)
