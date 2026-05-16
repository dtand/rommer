"""rommer init-project - scaffold a new project workspace from a ZIP.

Uses a Claude agent to intelligently classify files from the ZIP into
a meaningful project structure.
"""

import json
import shutil
import tempfile
import zipfile
from pathlib import Path

from rommer.config import Project


CLASSIFICATION_PROMPT = """\
You are setting up a game reverse engineering project. I've extracted a ZIP file
containing game resources. Your job is to classify each file and decide where it
belongs in the project workspace.

## Project Structure

The workspace has this layout:
```
rom/              — The game ROM file (exactly one)
knowledge/        — All supplementary resources, organized meaningfully
  guides/         — Walkthroughs, manuals, strategy guides
  maps/           — Map layouts, area diagrams, room screenshots
  codes/          — Action Replay, CodeBreaker, GameShark codes
  sprites/        — Character sprites, tilesets, animation frames
  saves/          — Save files, save states
  reference/      — Data tables, item lists, enemy stats, formulae
  misc/           — Anything that doesn't fit elsewhere
save_states/      — Save states for the emulator (working copies)
```

You may create additional subdirectories under knowledge/ if the content warrants it
(e.g., knowledge/screenshots/, knowledge/audio/, knowledge/symbols/).

## Files to Classify

{file_listing}

## Instructions

For each file, decide:
1. Which directory it belongs in
2. Whether to rename it for clarity (optional, keep original if already clear)

Consider:
- File content and purpose, not just extension
- .png/.gif could be maps, sprites, screenshots, or random images
- .txt could be walkthroughs, code lists, notes, or data dumps
- Group related files together
- A ROM is usually the largest binary file with a game platform extension (.gba, .gb, .nes, etc.)
- Save states (.ss0, .xps, .sav) go in save_states/ for emulator use

Output JSON:
{{
  "classification": [
    {{
      "source": "original_filename.ext",
      "destination": "knowledge/maps/overworld_map.png",
      "reason": "Map layout image showing game overworld"
    }},
    ...
  ],
  "notes": "Any observations about the resource collection"
}}
"""


def handler(args):
    if Project(args.name).exists():
        print(f"Error: project '{args.name}' already exists")
        raise SystemExit(1)

    project = Project.scaffold(args.name, args.platform)
    print(f"Created project workspace: {project.root}")

    if args.zip:
        zip_path = Path(args.zip).expanduser().resolve()
        if not zip_path.exists():
            print(f"Error: ZIP file not found: {zip_path}")
            raise SystemExit(1)
        if not zipfile.is_zipfile(zip_path):
            print(f"Error: not a valid ZIP file: {zip_path}")
            raise SystemExit(1)

        _extract_and_classify(project, zip_path, args)
    else:
        print("  No ZIP provided - empty workspace created")
        print(f"  Add ROM to: {project.root / 'rom/'}")
        print(f"  Add knowledge to: {project.root / 'knowledge/'}")


def _extract_and_classify(project: Project, zip_path: Path, args):
    """Extract ZIP and use Claude agent to classify files."""
    from rommer.preprocessor.claude import invoke

    print(f"  Extracting: {zip_path.name}")

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)

        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(tmp)

        # Collect all files (flatten nested dirs)
        all_files = [f for f in tmp.rglob("*") if f.is_file() and not f.name.startswith(".")]
        print(f"  Found {len(all_files)} files")

        # Build file listing with metadata for the agent
        file_listing = _build_file_listing(all_files, tmp)

        print(f"  Classifying files with Claude agent...")
        prompt = CLASSIFICATION_PROMPT.format(file_listing=file_listing)

        result = invoke(
            prompt=prompt,
            model="sonnet",
            timeout=120,
        )

        if isinstance(result, str):
            print(f"  WARNING: Agent returned text instead of JSON, falling back to basic classification")
            _fallback_classify(project, all_files, tmp)
            return

        classification = result.get("classification", [])
        if not classification:
            print(f"  WARNING: Empty classification, falling back to basic")
            _fallback_classify(project, all_files, tmp)
            return

        # Show the proposed classification
        print()
        print("  Proposed classification:")
        for entry in classification:
            src = entry.get("source", "")
            dest = entry.get("destination", "")
            reason = entry.get("reason", "")
            print(f"    {src}")
            print(f"      → {dest}")
            if reason:
                print(f"        ({reason})")

        if result.get("notes"):
            print()
            print(f"  Agent notes: {result['notes']}")

        print()

        # Apply classification — copy files to destinations
        _apply_classification(project, classification, all_files, tmp)

    # Validate ROM and extract header metadata
    _validate_rom(project)

    # Init DB
    from rommer.db.models import init_db
    conn = project.get_db()
    init_db(conn)
    meta = project.project_json
    game_title = meta.get("rom", {}).get("game_title", args.name)
    conn.execute(
        "INSERT OR IGNORE INTO project (game_id, game_title) VALUES (?, ?)",
        (args.name, game_title),
    )
    conn.commit()
    conn.close()
    print("  Database initialized")


def _build_file_listing(files: list[Path], base_dir: Path) -> str:
    """Build a descriptive file listing for the agent."""
    lines = []
    for f in sorted(files):
        rel = f.relative_to(base_dir)
        size = f.stat().st_size
        size_str = _human_size(size)

        # Peek at text files
        preview = ""
        if f.suffix.lower() in (".txt", ".md", ".csv", ".xml", ".json", ".cht"):
            try:
                text = f.read_text(errors="replace")[:200]
                preview = f' — preview: "{text.strip()[:100]}"'
            except Exception:
                pass

        lines.append(f"- {rel} ({size_str}){preview}")

    return "\n".join(lines)


def _human_size(size: int) -> str:
    """Format bytes as human-readable."""
    if size < 1024:
        return f"{size}B"
    elif size < 1024 * 1024:
        return f"{size / 1024:.1f}KB"
    else:
        return f"{size / (1024 * 1024):.1f}MB"


def _apply_classification(project: Project, classification: list[dict], all_files: list[Path], tmp: Path):
    """Copy files according to agent classification."""
    # Build a lookup from filename to source path
    file_map = {}
    for f in all_files:
        file_map[f.name] = f
        # Also index by relative path in case of nested dirs
        rel = str(f.relative_to(tmp))
        file_map[rel] = f

    copied = 0
    missed = 0

    for entry in classification:
        src_name = entry.get("source", "")
        dest_rel = entry.get("destination", "")

        if not src_name or not dest_rel:
            continue

        # Find the source file
        src_path = file_map.get(src_name)
        if not src_path:
            # Try matching just the filename part
            for key, path in file_map.items():
                if Path(key).name == src_name or key.endswith(src_name):
                    src_path = path
                    break

        if not src_path:
            print(f"    WARNING: source not found: {src_name}")
            missed += 1
            continue

        # Create destination
        dest_path = project.root / dest_rel
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_path, dest_path)
        copied += 1

    print(f"  Copied {copied} files ({missed} not found)")


def _fallback_classify(project: Project, files: list[Path], tmp: Path):
    """Basic extension-based classification when agent fails."""
    ext_map = {
        ".gba": "rom", ".gb": "rom", ".nes": "rom",
        ".sav": "save_states", ".xps": "save_states", ".ss0": "save_states",
        ".png": "knowledge/maps", ".gif": "knowledge/maps",
        ".txt": "knowledge/guides", ".md": "knowledge/guides", ".pdf": "knowledge/guides",
        ".xml": "knowledge/codes", ".cht": "knowledge/codes",
    }

    for f in files:
        ext = f.suffix.lower()
        dest_dir = ext_map.get(ext, "knowledge/misc")
        dest = project.root / dest_dir / f.name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, dest)

    print(f"  Fallback: copied {len(files)} files by extension")


def _validate_rom(project: Project):
    """Validate ROM file and store header metadata in project.json."""
    rom_path = project.rom_path
    if not rom_path.exists():
        print("  WARNING: No ROM file found in project")
        return

    platform = project.project_json.get("platform", "gba")

    if platform == "gba":
        from rommer.rom.gba_header import parse_gba_header
        header = parse_gba_header(rom_path)
        if header is None:
            print(f"  WARNING: {rom_path.name} does not appear to be a valid GBA ROM")
            return

        if not header["checksum_valid"]:
            print(f"  WARNING: ROM header checksum invalid")

        project.update_metadata(
            rom=header,
            game_title=header["game_title"],
        )
        print(f"  ROM validated: {header['game_title']} ({header['game_code']}) [{header['maker_name']}]")
        print(f"    Region: {header['region']} | Size: {header['rom_size_mb']} MB | Checksum: {'OK' if header['checksum_valid'] else 'INVALID'}")
    else:
        print(f"  ROM header parsing not yet supported for platform: {platform}")
