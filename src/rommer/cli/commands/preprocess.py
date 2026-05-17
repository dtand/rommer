"""rommer preprocess - run deterministic preprocessing scripts on decompiled code."""

from rommer.config import Project


def handler(args):
    project = Project(args.project)
    if not project.exists():
        print(f"Error: project '{args.project}' not found")
        raise SystemExit(1)

    src_dir = project.src_dir
    funcs_dir = src_dir / "functions"

    if not funcs_dir.exists() or not any(funcs_dir.glob("*.c")):
        print("Error: no decompiled function files found. Run ghidra-decompile first.")
        raise SystemExit(1)

    print(f"Preprocessing {args.project}...")
    print()

    # Step 1: Resolve types
    print("=== Step 1: Type Resolution ===")
    from rommer.scripts.resolve_types import resolve_types
    result = resolve_types(src_dir)
    print(f"  Files modified: {result.get('files_modified', 0)}")
    print(f"  Total replacements: {result.get('total_replacements', 0)}")
    for typ, count in result.get("replacements", {}).items():
        print(f"    {typ}: {count}")
    print()

    # Step 2: Resolve literal pool
    print("=== Step 2: Literal Pool Resolution ===")
    from rommer.scripts.resolve_literals import resolve_literals

    # Load discoveries for cross-referencing
    discoveries = []
    try:
        conn = project.get_db()
        rows = conn.execute("SELECT label, address, data_type FROM discovery").fetchall()
        discoveries = [dict(r) for r in rows]
        conn.close()
    except Exception:
        pass

    result = resolve_literals(src_dir, project.rom_path, discoveries)
    print(f"  Literals resolved: {result.get('resolved', 0)}")
    print(f"  Files modified: {result.get('files_modified', 0)}")
    print(f"  ROM pointers: {result.get('pointers_to_rom', 0)}")
    print(f"  IWRAM pointers: {result.get('pointers_to_iwram', 0)}")
    print(f"  EWRAM pointers: {result.get('pointers_to_ewram', 0)}")
    print(f"  Constants: {result.get('constants', 0)}")
    print(f"  Discovery labels matched: {result.get('with_discovery_labels', 0)}")
    print()

    # Step 3: Generate headers
    print("=== Step 3: Forward Declarations ===")
    from rommer.scripts.generate_headers import generate_headers
    result = generate_headers(src_dir)
    print(f"  Prototypes generated: {result.get('prototypes_generated', 0)}")
    print()

    # Step 4: Refresh game brief
    print("=== Step 4: Game Brief ===")
    from rommer.cli.commands.build_brief import build_game_brief
    brief = build_game_brief(project)
    brief_path = src_dir / "game_brief.md"
    brief_path.write_text(brief)
    print(f"  Written to {brief_path}")

    print()
    print("Preprocessing complete.")
