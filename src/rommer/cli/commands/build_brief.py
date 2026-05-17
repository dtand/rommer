"""rommer build-brief - generate a condensed game brief from project data."""

import json
from pathlib import Path

from rommer.config import Project


def handler(args):
    project = Project(args.project)
    if not project.exists():
        print(f"Error: project '{args.project}' not found")
        raise SystemExit(1)

    brief = build_game_brief(project)

    # Save to project
    output_path = project.src_dir / "game_brief.md"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(brief)
    print(brief)
    print(f"\nSaved to {output_path}")


def build_game_brief(project: Project) -> str:
    """Generate a condensed game brief from all available project data."""
    parts = []

    # ROM metadata
    meta = project.project_json
    rom = meta.get("rom", {})
    parts.append(f"# Game Brief: {meta.get('game_title', project.name)}")
    parts.append("")
    if rom:
        parts.append(f"- Platform: {meta.get('platform', 'unknown').upper()}")
        parts.append(f"- Developer: {rom.get('maker_name', 'unknown')}")
        parts.append(f"- Game Code: {rom.get('game_code', '?')}")
        parts.append(f"- Region: {rom.get('region', '?')}")
        parts.append(f"- ROM Size: {rom.get('rom_size_mb', '?')} MB")
        parts.append("")

    # Game systems from pass 2
    conn = project.get_db()
    try:
        systems = conn.execute("SELECT name, description FROM game_system ORDER BY name").fetchall()
        if systems:
            parts.append("## Game Systems")
            parts.append("")
            for s in systems:
                desc = s["description"][:150] if s["description"] else ""
                parts.append(f"- **{s['name']}**: {desc}")
            parts.append("")
    except Exception:
        pass

    # Discoveries grouped by system/category
    try:
        discoveries = conn.execute(
            "SELECT label, address, data_type, tier, notes, metadata FROM discovery ORDER BY address"
        ).fetchall()
        if discoveries:
            parts.append(f"## Known Memory Addresses ({len(discoveries)} discoveries)")
            parts.append("")

            golden = [d for d in discoveries if d["tier"] == "golden"]
            scratch = [d for d in discoveries if d["tier"] == "scratch"]

            if golden:
                parts.append(f"### Confirmed ({len(golden)})")
                parts.append("")
                for d in golden:
                    meta_str = ""
                    if d["metadata"]:
                        try:
                            m = json.loads(d["metadata"]) if isinstance(d["metadata"], str) else d["metadata"]
                            if m.get("kind"):
                                fields = len(m.get("fields", []))
                                entries = len(m.get("entries", []))
                                meta_str = f" [{m['kind']}"
                                if m.get("stride"):
                                    meta_str += f", stride={m['stride']}"
                                if m.get("count"):
                                    meta_str += f", count={m['count']}"
                                if fields:
                                    meta_str += f", {fields} fields"
                                if entries:
                                    meta_str += f", {entries} entries"
                                meta_str += "]"
                        except Exception:
                            pass
                    notes = f" — {d['notes'][:80]}" if d["notes"] else ""
                    parts.append(f"- `{d['address']}` **{d['label']}** ({d['data_type']}){meta_str}{notes}")
                parts.append("")

            if scratch:
                parts.append(f"### Unverified ({len(scratch)})")
                parts.append("")
                for d in scratch:
                    parts.append(f"- `{d['address']}` {d['label']} ({d['data_type']})")
                parts.append("")
    except Exception:
        pass

    # Data tables from pass 3 (item names, medal names, etc.)
    try:
        tables = conn.execute("SELECT id, table_name, column_names FROM game_data_table").fetchall()
        if tables:
            parts.append("## Game Data")
            parts.append("")
            for t in tables:
                row_count = conn.execute(
                    "SELECT COUNT(*) as cnt FROM game_data_row WHERE table_id = %s" if hasattr(conn, '_conn') else
                    "SELECT COUNT(*) as cnt FROM game_data_row WHERE table_id = ?",
                    (t["id"],)
                ).fetchone()
                count = row_count["cnt"] if row_count else 0
                cols = json.loads(t["column_names"]) if t["column_names"] else []
                parts.append(f"- **{t['table_name']}**: {count} entries")
                if cols:
                    parts.append(f"  Columns: {', '.join(cols[:8])}")

                # Show first few entries for context
                if count > 0 and count <= 50:
                    rows = conn.execute(
                        "SELECT row_data FROM game_data_row WHERE table_id = %s ORDER BY row_index LIMIT 5" if hasattr(conn, '_conn') else
                        "SELECT row_data FROM game_data_row WHERE table_id = ? ORDER BY row_index LIMIT 5",
                        (t["id"],)
                    ).fetchall()
                    for r in rows:
                        row_data = json.loads(r["row_data"]) if isinstance(r["row_data"], str) else r["row_data"]
                        # Show first value as sample
                        if isinstance(row_data, dict):
                            first_val = list(row_data.values())[0] if row_data else ""
                            parts.append(f"    e.g., {first_val}")
                            break
            parts.append("")
    except Exception:
        pass

    # Control mappings
    try:
        controls = conn.execute(
            "SELECT context, button, action FROM control_mapping ORDER BY context, button"
        ).fetchall()
        if controls:
            parts.append("## Controls")
            parts.append("")
            by_context: dict[str, list[str]] = {}
            for c in controls:
                ctx = c["context"] or "default"
                by_context.setdefault(ctx, []).append(f"{c['button']}: {c['action']}")
            for ctx, mappings in sorted(by_context.items()):
                parts.append(f"**{ctx}**: {', '.join(mappings[:6])}")
            parts.append("")
    except Exception:
        pass

    # Call graph stats if available
    call_graph_path = project.src_dir / "call_graph.json"
    if call_graph_path.exists():
        try:
            cg = json.loads(call_graph_path.read_text())
            parts.append("## Codebase")
            parts.append("")
            parts.append(f"- Functions: {cg['total_functions']}")
            parts.append(f"- Call tree depth: {cg['max_depth']} levels")
            parts.append(f"- Leaf functions: {cg['leaf_count']}")

            # Count augmented
            disc_funcs = sum(1 for f in cg["functions"].values() if f.get("discovery_refs"))
            io_funcs = sum(1 for f in cg["functions"].values() if f.get("io_registers"))
            parts.append(f"- Functions with discovery refs: {disc_funcs}")
            parts.append(f"- Functions with IO register access: {io_funcs}")

            # Key functions
            disc_entries = [(n, f) for n, f in cg["functions"].items() if f.get("discovery_refs")]
            if disc_entries:
                disc_entries.sort(key=lambda x: len(x[1]["discovery_refs"]), reverse=True)
                parts.append("")
                parts.append("### Key Functions")
                parts.append("")
                for name, f in disc_entries[:10]:
                    refs = [r["label"] for r in f["discovery_refs"]]
                    parts.append(f"- `{f['address']}` {name} (level {f.get('level', '?')}): {', '.join(refs)}")
            parts.append("")
        except Exception:
            pass

    conn.close()
    return "\n".join(parts)
