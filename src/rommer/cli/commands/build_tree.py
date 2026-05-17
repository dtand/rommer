"""rommer build-tree - build the function call graph from decompiled code."""

import json
import re
import time
from collections import defaultdict
from pathlib import Path

from rommer.config import Project


def handler(args):
    project = Project(args.project)
    if not project.exists():
        print(f"Error: project '{args.project}' not found")
        raise SystemExit(1)

    src_dir = project.src_dir
    funcs_dir = src_dir / "functions"
    index_path = src_dir / "function_index.json"

    if not index_path.exists():
        print("Error: function_index.json not found. Run ghidra-decompile first.")
        raise SystemExit(1)

    if not funcs_dir.exists() or not any(funcs_dir.glob("*.c")):
        print("Error: no decompiled function files found. Run ghidra-decompile first.")
        raise SystemExit(1)

    graph = build_call_graph(src_dir)

    # Save
    output_path = src_dir / "call_graph.json"
    output_path.write_text(json.dumps(graph, indent=2))
    print(f"\nSaved to {output_path} ({output_path.stat().st_size / 1024 / 1024:.1f} MB)")

    # Summary
    print(f"\nCall Graph Summary:")
    print(f"  Total functions: {graph['total_functions']}")
    print(f"  Leaf functions:  {graph['leaf_count']}")
    print(f"  Root functions:  {graph['root_count']}")
    print(f"  Max depth:       {graph['max_depth']}")
    print(f"  Cyclic:          {graph['cycle_count']}")
    print(f"\n  Level distribution:")
    for level, count in sorted(graph["level_counts"].items(), key=lambda x: int(x[0])):
        print(f"    Level {level}: {count} functions")


def build_call_graph(src_dir: Path) -> dict:
    """Build a function call graph from decompiled source files.

    Returns a dict with graph metadata and per-function data including
    callees, callers, and level in the call tree.
    """
    index_path = src_dir / "function_index.json"
    funcs_dir = src_dir / "functions"

    idx = json.loads(index_path.read_text())
    all_funcs = {f["name"] for f in idx}

    print(f"Building call graph for {len(idx)} functions...")
    start = time.time()

    # Build caller/callee relationships
    callees: dict[str, set[str]] = {}
    callers: dict[str, set[str]] = defaultdict(set)
    call_pattern = re.compile(r'\b(FUN_[0-9a-f]{8}|thunk_FUN_[0-9a-f]{8})\s*\(')

    processed = 0
    for f in funcs_dir.glob("*.c"):
        parts = f.stem.split("_", 1)
        if len(parts) < 2:
            continue
        func_name = parts[1]

        content = f.read_text()
        calls = set(call_pattern.findall(content))
        calls.discard(func_name)  # Remove self-calls
        valid_calls = calls & all_funcs

        callees[func_name] = valid_calls
        for callee in valid_calls:
            callers[callee].add(func_name)

        processed += 1
        if processed % 2000 == 0:
            print(f"  Processed {processed}...")

    elapsed = time.time() - start
    print(f"  Done in {elapsed:.1f}s")

    # Compute levels (BFS from leaves upward)
    levels: dict[str, int] = {}
    queue = []
    for name in all_funcs:
        if not callees.get(name):
            levels[name] = 0
            queue.append(name)

    visited = set(queue)
    while queue:
        next_queue = []
        for func in queue:
            for caller in callers.get(func, set()):
                if caller in visited:
                    continue
                child_levels = [levels.get(c, 0) for c in callees.get(caller, set()) if c in levels]
                if len(child_levels) == len(callees.get(caller, set())):
                    levels[caller] = max(child_levels) + 1
                    visited.add(caller)
                    next_queue.append(caller)
        queue = next_queue

    unassigned = all_funcs - set(levels.keys())

    # Level counts
    level_counts: dict[str, int] = defaultdict(int)
    for l in levels.values():
        level_counts[str(l)] += 1

    # Augment with discovery references
    # (will be done at analysis time, not here)

    # Build output
    max_level = max(levels.values()) if levels else 0
    leaf_count = sum(1 for name in all_funcs if not callees.get(name))
    root_count = sum(1 for name in all_funcs if not callers.get(name))

    graph_data = {
        "total_functions": len(idx),
        "leaf_count": leaf_count,
        "root_count": root_count,
        "max_depth": max_level,
        "cycle_count": len(unassigned),
        "level_counts": dict(level_counts),
        "functions": {},
    }

    for f in idx:
        name = f["name"]
        graph_data["functions"][name] = {
            "address": f["address"],
            "size": f.get("size", 0),
            "callees": sorted(callees.get(name, set())),
            "callers": sorted(callers.get(name, set())),
            "level": levels.get(name),
        }

    return graph_data
