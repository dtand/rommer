"""rommer init-project - scaffold a new project workspace from a ZIP."""

import shutil
import tempfile
import zipfile
from pathlib import Path

from rommer.config import Project


# File classification by extension
EXTENSION_MAP = {
    # ROMs
    ".gba": "rom",
    ".gb": "rom",
    ".gbc": "rom",
    ".nes": "rom",
    ".sfc": "rom",
    ".smc": "rom",
    # Save states
    ".sav": "save_states",
    ".xps": "save_states",
    ".ss0": "save_states",
    ".ss1": "save_states",
    ".ss2": "save_states",
    ".state": "save_states",
    # Maps/images
    ".png": "knowledge/maps",
    ".gif": "knowledge/maps",
    ".jpg": "knowledge/maps",
    ".jpeg": "knowledge/maps",
    ".bmp": "knowledge/maps",
    # Guides/docs
    ".txt": "knowledge/guides",
    ".md": "knowledge/guides",
    ".pdf": "knowledge/guides",
    ".rtf": "knowledge/guides",
    ".doc": "knowledge/guides",
    ".docx": "knowledge/guides",
    # Codes
    ".xml": "knowledge/codes",
    ".cht": "knowledge/codes",
    # Generic
    ".json": "knowledge/misc",
    ".csv": "knowledge/misc",
}

# Filename patterns that override extension-based classification
FILENAME_PATTERNS = {
    "walkthrough": "knowledge/guides",
    "manual": "knowledge/guides",
    "guide": "knowledge/guides",
    "map": "knowledge/maps",
    "layout": "knowledge/maps",
    "code": "knowledge/codes",
    "cheat": "knowledge/codes",
    "codebreaker": "knowledge/codes",
    "gameshark": "knowledge/codes",
    "action_replay": "knowledge/codes",
}


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

        _extract_and_classify(project, zip_path)
    else:
        print("  No ZIP provided - empty workspace created")
        print(f"  Add ROM to: {project.root / 'rom/'}")
        print(f"  Add knowledge to: {project.root / 'knowledge/'}")


def _extract_and_classify(project: Project, zip_path: Path):
    """Extract ZIP contents and classify files into project structure."""
    print(f"  Extracting: {zip_path.name}")

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)

        # Extract ZIP
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(tmp)

        # Collect all files (flatten nested dirs)
        all_files = [f for f in tmp.rglob("*") if f.is_file() and not f.name.startswith(".")]

        print(f"  Found {len(all_files)} files")
        print()

        classified = {}
        for file_path in sorted(all_files):
            dest = _classify_file(file_path)
            classified.setdefault(dest, []).append(file_path)

        # Copy files to destinations
        for dest, files in sorted(classified.items()):
            dest_dir = project.root / dest
            dest_dir.mkdir(parents=True, exist_ok=True)
            print(f"  {dest}/ ({len(files)} files)")
            for f in files:
                target = dest_dir / f.name
                # Handle duplicates
                if target.exists():
                    stem = f.stem
                    suffix = f.suffix
                    i = 1
                    while target.exists():
                        target = dest_dir / f"{stem}_{i}{suffix}"
                        i += 1
                shutil.copy2(f, target)
                print(f"    {f.name}")

    # Summary
    print()
    print("  Classification complete. Review the workspace:")
    print(f"    {project.root}")
    print()

    # Check for ROM
    rom_dir = project.root / "rom"
    roms = list(rom_dir.iterdir()) if rom_dir.exists() else []
    if roms:
        print(f"  ROM found: {roms[0].name}")
    else:
        print("  WARNING: No ROM file detected in ZIP")

    # Check for walkthrough
    guides_dir = project.root / "knowledge" / "guides"
    guides = list(guides_dir.iterdir()) if guides_dir.exists() else []
    walkthroughs = [g for g in guides if "walkthrough" in g.name.lower()]
    if walkthroughs:
        print(f"  Walkthrough found: {walkthroughs[0].name}")
    elif guides:
        print(f"  Guides found: {len(guides)} files (no file named 'walkthrough')")
    else:
        print("  WARNING: No walkthrough/guide files found")

    # Init DB with schema
    from rommer.db.models import init_db
    conn = project.get_db()
    init_db(conn)
    conn.execute(
        "INSERT OR IGNORE INTO project (game_id, game_title) VALUES (?, ?)",
        (args.name, args.name),
    )
    conn.commit()
    conn.close()
    print("  Database initialized")


def _classify_file(file_path: Path) -> str:
    """Classify a file into a destination directory."""
    name_lower = file_path.name.lower()
    ext = file_path.suffix.lower()

    # Check filename patterns first (more specific)
    for pattern, dest in FILENAME_PATTERNS.items():
        if pattern in name_lower:
            return dest

    # Fall back to extension
    if ext in EXTENSION_MAP:
        return EXTENSION_MAP[ext]

    # Unknown — put in misc
    return "knowledge/misc"
