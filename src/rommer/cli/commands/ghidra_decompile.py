"""rommer ghidra-decompile - full Ghidra decompilation workflow."""

import json
from pathlib import Path

from rommer.config import Project


SCRIPTS_DIR = Path(__file__).parent.parent.parent / "static_analysis" / "ghidra_scripts"


def handler(args):
    project = Project(args.project)
    if not project.exists():
        print(f"Error: project '{args.project}' not found")
        raise SystemExit(1)

    steps = [
        ("Create Ghidra project", f"analyzeHeadless {project.ghidra_dir} {args.project} -import {project.rom_path} -processor ARM:LE:32:v4t"),
        ("Setup GBA memory map", f"Run script: {SCRIPTS_DIR / 'setup_memory.py'}"),
        ("Run auto-analysis", "analyzeHeadless ... -process -noanalysis=false"),
        ("Export golden discoveries as labels", f"Generate {project.ghidra_dir / 'discovery_labels.json'} from DB"),
        ("Import labels", f"Run script: {SCRIPTS_DIR / 'import_labels.py'}"),
        ("Decompile all functions", f"Run script: {SCRIPTS_DIR / 'export_decompiled.py'}"),
        ("Export split functions", f"Run script: {SCRIPTS_DIR / 'export_split.py'}"),
        ("Generate src/CLAUDE.md", f"Write analysis instructions to {project.src_dir / 'CLAUDE.md'}"),
    ]

    if args.dry_run:
        print(f"ghidra-decompile: {args.project} (dry-run)")
        for i, (name, detail) in enumerate(steps, 1):
            print(f"  Step {i}: {name}")
            print(f"         {detail}")
        return

    # Export discoveries as labels for Ghidra import
    _export_labels(project)

    # TODO: Actually invoke Ghidra headless analysis
    print("Error: ghidra-decompile execution not yet implemented")
    print("Run manually:")
    for i, (name, detail) in enumerate(steps, 1):
        print(f"  {i}. {name}: {detail}")
    raise SystemExit(1)


def _export_labels(project: Project) -> Path:
    """Export golden discoveries from DB as Ghidra label JSON."""
    import sqlite3
    conn = project.get_db()
    labels_path = project.ghidra_dir / "discovery_labels.json"

    try:
        rows = conn.execute(
            "SELECT label, address, data_type, notes FROM discovery WHERE tier = 'golden'"
        ).fetchall()
        labels = [
            {"label": r["label"], "address": r["address"],
             "data_type": r["data_type"], "notes": r["notes"]}
            for r in rows
        ]
    except sqlite3.OperationalError:
        labels = []

    labels_path.parent.mkdir(parents=True, exist_ok=True)
    labels_path.write_text(json.dumps(labels, indent=2))
    print(f"  Exported {len(labels)} labels to {labels_path}")
    conn.close()
    return labels_path
