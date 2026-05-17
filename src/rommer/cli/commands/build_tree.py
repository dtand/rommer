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

    # Augmentation summary
    funcs = graph["functions"]
    disc_funcs = {n: f for n, f in funcs.items() if f.get("discovery_refs")}
    io_funcs = {n: f for n, f in funcs.items() if f.get("io_registers")}

    if disc_funcs:
        print(f"\n  Functions referencing discoveries ({len(disc_funcs)}):")
        # Sort by number of discovery refs
        for name, f in sorted(disc_funcs.items(), key=lambda x: len(x[1]["discovery_refs"]), reverse=True)[:20]:
            refs = f["discovery_refs"]
            labels = [r["label"] for r in refs]
            print(f"    {f['address']} {name} (level {f.get('level', '?')}): {', '.join(labels)}")
        if len(disc_funcs) > 20:
            print(f"    ... and {len(disc_funcs) - 20} more")

    if io_funcs:
        print(f"\n  Functions accessing IO registers ({len(io_funcs)}):")
        for name, f in sorted(io_funcs.items(), key=lambda x: len(x[1]["io_registers"]), reverse=True)[:10]:
            regs = list(f["io_registers"].values())
            print(f"    {f['address']} {name}: {', '.join(regs[:3])}")
        if len(io_funcs) > 10:
            print(f"    ... and {len(io_funcs) - 10} more")


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

    # GBA IO register patterns
    IO_REGISTERS = {
        "0x04000000": "REG_DISPCNT (display control)",
        "0x04000004": "REG_DISPSTAT (display status)",
        "0x04000006": "REG_VCOUNT (vertical counter)",
        "0x04000008": "REG_BG0CNT",
        "0x0400000a": "REG_BG1CNT",
        "0x0400000c": "REG_BG2CNT",
        "0x0400000e": "REG_BG3CNT",
        "0x04000010": "REG_BG0HOFS",
        "0x04000040": "REG_WIN0H",
        "0x04000050": "REG_BLDCNT (blend control)",
        "0x04000060": "REG_SOUND1CNT_L",
        "0x04000080": "REG_SOUNDCNT_L",
        "0x040000b0": "REG_DMA0SAD",
        "0x040000bc": "REG_DMA1SAD",
        "0x040000c8": "REG_DMA2SAD",
        "0x040000d4": "REG_DMA3SAD",
        "0x04000100": "REG_TM0CNT_L (timer 0)",
        "0x04000104": "REG_TM1CNT_L (timer 1)",
        "0x04000108": "REG_TM2CNT_L (timer 2)",
        "0x0400010c": "REG_TM3CNT_L (timer 3)",
        "0x04000130": "REG_KEYINPUT (key input)",
        "0x04000200": "REG_IE (interrupt enable)",
        "0x04000202": "REG_IF (interrupt flags)",
        "0x04000208": "REG_IME (interrupt master)",
    }
    io_pattern = re.compile(r'0x0400[0-9a-fA-F]{4}')

    # Memory region patterns
    iwram_pattern = re.compile(r'0x0300[0-9a-fA-F]{4}')
    ewram_pattern = re.compile(r'0x0200[0-9a-fA-F]{4}')
    vram_pattern = re.compile(r'0x0600[0-9a-fA-F]{4}')
    oam_pattern = re.compile(r'0x0700[0-9a-fA-F]{4}')

    # Per-function augmentation data
    func_augments: dict[str, dict] = {}

    processed = 0
    for f in funcs_dir.glob("*.c"):
        parts = f.stem.split("_", 1)
        if len(parts) < 2:
            continue
        func_name = parts[1]

        content = f.read_text()

        # Call graph
        calls = set(call_pattern.findall(content))
        calls.discard(func_name)
        valid_calls = calls & all_funcs

        callees[func_name] = valid_calls
        for callee in valid_calls:
            callers[callee].add(func_name)

        # Augment: IO registers (match both DAT_04000xxx and 0x04000xxx)
        io_refs = set(io_pattern.findall(content.lower()))
        dat_io = re.findall(r'DAT_(0400[0-9a-fA-F]{4})', content)
        io_refs.update(f"0x{m.lower()}" for m in dat_io)
        io_named = {addr: IO_REGISTERS[addr] for addr in io_refs if addr in IO_REGISTERS}

        # Augment: memory regions touched (match DAT_ references too)
        regions = set()
        if iwram_pattern.search(content) or "DAT_0300" in content:
            regions.add("IWRAM")
        if ewram_pattern.search(content) or "DAT_0200" in content:
            regions.add("EWRAM")
        if vram_pattern.search(content) or "DAT_0600" in content:
            regions.add("VRAM")
        if oam_pattern.search(content) or "DAT_0700" in content:
            regions.add("OAM")

        # Store augmentation
        augment = {}
        if io_named:
            augment["io_registers"] = io_named
        if regions:
            augment["memory_regions"] = sorted(regions)
        if augment:
            func_augments[func_name] = augment

        processed += 1
        if processed % 2000 == 0:
            print(f"  Processed {processed}...")

    elapsed = time.time() - start
    print(f"  Parsed in {elapsed:.1f}s")

    # Augment: discovery references via literal pool resolution
    print("  Augmenting with discoveries (via literal pool)...")
    discovery_refs: dict[str, list[dict]] = {}
    try:
        from rommer.db.connection import is_postgres
        if is_postgres():
            from rommer.db.connection import get_postgres_connection, PostgresConnectionWrapper
            conn = PostgresConnectionWrapper(get_postgres_connection())
        else:
            import sqlite3 as _sqlite3
            db_path = src_dir.parent / "db" / "rommer.db"
            conn = None
            if db_path.exists():
                conn = _sqlite3.connect(str(db_path))
                conn.row_factory = _sqlite3.Row

        if conn:
            discoveries = conn.execute("SELECT label, address, data_type, tier FROM discovery").fetchall()
            conn.close()

            if discoveries:
                import struct
                rom_path = src_dir.parent / "rom"
                rom_files = list(rom_path.iterdir()) if rom_path.exists() else []
                rom_file = rom_files[0] if rom_files else None

                if rom_file and rom_file.exists():
                    rom_data = rom_file.read_bytes()
                    print(f"  Resolving literal pool for {len(discoveries)} addresses in {len(rom_data)} byte ROM...")

                    # Step 1: Find DAT_ labels for each discovery address
                    dat_to_discovery: dict[str, dict] = {}
                    for d in discoveries:
                        addr_int = int(d["address"], 16)
                        addr_bytes = struct.pack("<I", addr_int)
                        pos = 0
                        while True:
                            pos = rom_data.find(addr_bytes, pos)
                            if pos == -1:
                                break
                            dat_label = f"DAT_{0x08000000 + pos:08x}"
                            dat_to_discovery[dat_label] = {
                                "label": d["label"], "address": d["address"],
                                "data_type": d["data_type"], "tier": d["tier"],
                            }
                            pos += 1

                    print(f"  Found {len(dat_to_discovery)} DAT_ labels for {len(discoveries)} discoveries")

                    # Step 2: Grep functions for these DAT_ labels
                    for f in funcs_dir.glob("*.c"):
                        fname = f.stem.split("_", 1)
                        if len(fname) < 2:
                            continue
                        func_name = fname[1]
                        content = f.read_text()

                        refs = []
                        seen_labels = set()
                        for dat, disc in dat_to_discovery.items():
                            if dat in content and disc["label"] not in seen_labels:
                                refs.append(disc)
                                seen_labels.add(disc["label"])

                        if refs:
                            if func_name not in func_augments:
                                func_augments[func_name] = {}
                            func_augments[func_name]["discovery_refs"] = refs
                            discovery_refs[func_name] = refs
                else:
                    print(f"  ROM not found, skipping literal pool resolution")
    except Exception as e:
        print(f"  Discovery augmentation failed: {e}")

    augmented_count = len(func_augments)
    disc_func_count = len(discovery_refs)
    io_func_count = sum(1 for a in func_augments.values() if "io_registers" in a)
    region_func_count = sum(1 for a in func_augments.values() if "memory_regions" in a)
    print(f"  Augmented {augmented_count} functions:")
    print(f"    Discovery refs: {disc_func_count} functions")
    print(f"    IO registers:   {io_func_count} functions")
    print(f"    Memory regions: {region_func_count} functions")

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
        entry = {
            "address": f["address"],
            "size": f.get("size", 0),
            "callees": sorted(callees.get(name, set())),
            "callers": sorted(callers.get(name, set())),
            "level": levels.get(name),
        }
        # Merge augmentation data
        if name in func_augments:
            entry.update(func_augments[name])
        graph_data["functions"][name] = entry

    return graph_data
