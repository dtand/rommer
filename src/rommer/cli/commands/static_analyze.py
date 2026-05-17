"""rommer static-analyze — bottom-up function analysis pipeline.

Walks the call tree from leaves to root, analyzing functions level by level.
At each level, chunks of functions are distributed to parallel agents.
"""

import json
import math
import time
import urllib.request
from pathlib import Path

from rommer.config import Project

API = "http://localhost:8000/api"


def handler(args):
    project = Project(args.project)
    if not project.exists():
        print(f"Error: project '{args.project}' not found")
        raise SystemExit(1)

    num_nodes = args.num_nodes
    parallel = args.parallel
    model = args.model

    # Load call graph
    call_graph_path = project.src_dir / "call_graph.json"
    if not call_graph_path.exists():
        print("Error: call_graph.json not found. Run 'rommer build-tree' first.")
        raise SystemExit(1)

    call_graph = json.loads(call_graph_path.read_text())
    functions = call_graph["functions"]
    max_depth = call_graph["max_depth"]

    print(f"Static Analysis Pipeline: {call_graph['total_functions']} functions, {max_depth + 1} levels")
    print(f"  num_nodes={num_nodes}, parallel={parallel}, model={model}")
    print()

    # Check preprocessing
    ghidra_types = project.src_dir / "include" / "ghidra_types.h"
    if not ghidra_types.exists():
        print("Running preprocessing first...")
        from rommer.cli.commands.preprocess import handler as preprocess_handler

        class PreprocessArgs:
            pass
        pa = PreprocessArgs()
        pa.project = args.project
        preprocess_handler(pa)
        print()

    # Load already-analyzed functions
    analyzed = _get_analyzed_addresses(project)
    print(f"Already analyzed: {len(analyzed)} functions")
    print()

    # Walk levels bottom-up
    for level in range(0, max_depth + 1):
        # Get functions at this level that haven't been analyzed
        level_funcs = [
            {"address": f["address"], "name": name}
            for name, f in functions.items()
            if f.get("level") == level and f["address"] not in analyzed
        ]

        if not level_funcs:
            print(f"Level {level}: all {_count_at_level(functions, level)} functions already analyzed, skipping")
            continue

        total_at_level = _count_at_level(functions, level)
        print(f"Level {level}: {len(level_funcs)} to analyze ({total_at_level} total)")

        # Split into chunks
        chunks = [level_funcs[i:i + num_nodes] for i in range(0, len(level_funcs), num_nodes)]
        print(f"  {len(chunks)} chunks of up to {num_nodes} functions")

        # Distribute chunks across parallel workers
        job_ids = []
        for i, chunk in enumerate(chunks):
            config = {
                "model": model,
                "chunk": chunk,
                "level": level,
            }
            try:
                result = _api_post("/jobs/function-analysis", {
                    "project": args.project,
                    "config": config,
                })
                job_id = result.get("job_id")
                if job_id:
                    job_ids.append(job_id)
                    print(f"  Started job {job_id} ({len(chunk)} functions)")
            except Exception as e:
                print(f"  Failed to start job: {e}")

            # Limit concurrent jobs
            if len(job_ids) >= parallel:
                print(f"  Waiting for {len(job_ids)} jobs to complete...")
                _wait_for_jobs(job_ids)
                # Update analyzed set
                analyzed = _get_analyzed_addresses(project)
                job_ids = []

        # Wait for remaining jobs at this level
        if job_ids:
            print(f"  Waiting for {len(job_ids)} remaining jobs...")
            _wait_for_jobs(job_ids)
            analyzed = _get_analyzed_addresses(project)

        print(f"  Level {level} complete. Total analyzed: {len(analyzed)}")
        print()

    # Handle cyclic functions
    cycle_funcs = [
        {"address": f["address"], "name": name}
        for name, f in functions.items()
        if f.get("level") is None and f["address"] not in analyzed
    ]
    if cycle_funcs:
        print(f"Cyclic functions: {len(cycle_funcs)} remaining")
        chunks = [cycle_funcs[i:i + num_nodes] for i in range(0, len(cycle_funcs), num_nodes)]
        job_ids = []
        for chunk in chunks:
            config = {"model": model, "chunk": chunk, "level": -1}
            try:
                result = _api_post("/jobs/function-analysis", {
                    "project": args.project,
                    "config": config,
                })
                job_id = result.get("job_id")
                if job_id:
                    job_ids.append(job_id)
            except Exception:
                pass
            if len(job_ids) >= parallel:
                _wait_for_jobs(job_ids)
                job_ids = []
        if job_ids:
            _wait_for_jobs(job_ids)
        print()

    analyzed = _get_analyzed_addresses(project)
    print(f"Analysis complete. {len(analyzed)} / {call_graph['total_functions']} functions analyzed.")


def _get_analyzed_addresses(project: Project) -> set[str]:
    """Get set of already-analyzed function addresses."""
    try:
        conn = project.get_db()
        rows = conn.execute("SELECT address FROM function_analysis").fetchall()
        conn.close()
        return {r["address"] for r in rows}
    except Exception:
        return set()


def _count_at_level(functions: dict, level: int) -> int:
    return sum(1 for f in functions.values() if f.get("level") == level)


def _api_post(path: str, data: dict) -> dict:
    body = json.dumps(data).encode()
    req = urllib.request.Request(
        f"{API}{path}",
        data=body,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def _wait_for_jobs(job_ids: list[str]):
    """Poll until all jobs complete or fail."""
    remaining = set(job_ids)
    while remaining:
        time.sleep(5)
        done = set()
        for job_id in remaining:
            try:
                req = urllib.request.Request(f"{API}/jobs/{job_id}")
                with urllib.request.urlopen(req) as resp:
                    status = json.loads(resp.read())
                s = status.get("status", "unknown")
                if s in ("completed", "failed", "cancelled"):
                    done.add(job_id)
                    result = status.get("progress", {}).get("message", "")
                    print(f"    {job_id}: {s} {result[:60]}")
            except Exception:
                pass
        remaining -= done
