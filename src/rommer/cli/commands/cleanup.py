"""rommer cleanup — agent-driven Ghidra artifact cleanup.

Walk 0 of the bottom-up pipeline. Cleans Ghidra-specific constructs
(in_lr, CONCAT, SUB, DAT_, etc.) using AI agents that understand context.
Same tree-walking algorithm as static-analyze.
"""

import json
import time
import urllib.request

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

    # Load already-cleaned functions
    cleaned = _get_cleaned_addresses(project)

    print(f"Code Cleanup Pipeline: {call_graph['total_functions']} functions, {max_depth + 1} levels")
    print(f"  Already cleaned: {len(cleaned)}")
    print(f"  num_nodes={num_nodes}, parallel={parallel}, model={model}")
    print()

    # Walk levels bottom-up (same as static-analyze)
    for level in range(0, max_depth + 1):
        level_funcs = [
            {"address": f["address"], "name": name}
            for name, f in functions.items()
            if f.get("level") == level and f["address"] not in cleaned
        ]

        total_at_level = sum(1 for f in functions.values() if f.get("level") == level)
        if not level_funcs:
            print(f"Level {level}: all {total_at_level} functions already cleaned, skipping")
            continue

        print(f"Level {level}: {len(level_funcs)} to clean ({total_at_level} total)")

        chunks = [level_funcs[i:i + num_nodes] for i in range(0, len(level_funcs), num_nodes)]
        print(f"  {len(chunks)} chunks of up to {num_nodes}")

        job_ids = []
        for chunk in chunks:
            config = {"model": model, "chunk": chunk, "level": level}
            try:
                result = _api_post("/jobs/code-cleanup", {
                    "project": args.project,
                    "config": config,
                })
                job_id = result.get("job_id")
                if job_id:
                    job_ids.append(job_id)
            except Exception as e:
                print(f"  Failed to start job: {e}")

            if len(job_ids) >= parallel:
                print(f"  Waiting for {len(job_ids)} jobs...")
                _wait_for_jobs(job_ids)
                job_ids = []

        if job_ids:
            print(f"  Waiting for {len(job_ids)} remaining...")
            _wait_for_jobs(job_ids)

        cleaned = _get_cleaned_addresses(project)
        print(f"  Level {level} complete. Total cleaned: {len(cleaned)}")
        print()

    # Cyclic functions
    cycle_funcs = [
        {"address": f["address"], "name": name}
        for name, f in functions.items()
        if f.get("level") is None and f["address"] not in cleaned
    ]
    if cycle_funcs:
        print(f"Cyclic: {len(cycle_funcs)} functions")
        chunks = [cycle_funcs[i:i + num_nodes] for i in range(0, len(cycle_funcs), num_nodes)]
        job_ids = []
        for chunk in chunks:
            config = {"model": model, "chunk": chunk, "level": -1}
            try:
                result = _api_post("/jobs/code-cleanup", {"project": args.project, "config": config})
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

    cleaned = _get_cleaned_addresses(project)
    print(f"Cleanup complete. {len(cleaned)} / {call_graph['total_functions']} functions cleaned.")


def _get_cleaned_addresses(project) -> set[str]:
    """Get set of already-cleaned function addresses."""
    try:
        conn = project.get_db()
        rows = conn.execute("SELECT address FROM function_cleanup").fetchall()
        conn.close()
        return {r["address"] for r in rows}
    except Exception:
        return set()


def _api_post(path: str, data: dict) -> dict:
    body = json.dumps(data).encode()
    req = urllib.request.Request(f"{API}{path}", data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def _wait_for_jobs(job_ids: list[str]):
    remaining = set(job_ids)
    while remaining:
        time.sleep(5)
        done = set()
        for job_id in remaining:
            try:
                req = urllib.request.Request(f"{API}/jobs/{job_id}")
                with urllib.request.urlopen(req) as resp:
                    status = json.loads(resp.read())
                if status.get("status") in ("completed", "failed", "cancelled"):
                    done.add(job_id)
                    print(f"    {job_id}: {status['status']}")
            except Exception:
                pass
        remaining -= done
