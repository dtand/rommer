"""rommer ghidra-decompile - full Ghidra decompilation workflow."""

from rommer.config import Project


def handler(args):
    project = Project(args.project)
    if not project.exists():
        print(f"Error: project '{args.project}' not found")
        raise SystemExit(1)

    if args.dry_run:
        print(f"ghidra-decompile: {args.project} (dry-run)")
        print("  Step 1: Create Ghidra project")
        print("  Step 2: Import ROM (ARM:LE:32:v4t, base 0x08000000)")
        print("  Step 3: Add memory regions (IWRAM, EWRAM, VRAM, IO, OAM)")
        print("  Step 4: Run auto-analysis")
        print("  Step 5: Export golden discoveries as labels")
        print("  Step 6: Import labels into Ghidra")
        print("  Step 7: Decompile all functions → src/functions/")
        print("  Step 8: Export function_index.json, label_xrefs.json")
        print("  Step 9: Generate src/CLAUDE.md with memory map")
        return

    # TODO: Import and run ghidra scripts
    print("Error: ghidra-decompile execution not yet implemented")
    raise SystemExit(1)
