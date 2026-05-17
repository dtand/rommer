"""Project workspace management and path resolution."""

import json
import os
import sqlite3
from pathlib import Path


def get_projects_root() -> Path:
    """Resolve ROMMER_PROJECTS_ROOT from env or default."""
    root = os.environ.get("ROMMER_PROJECTS_ROOT", "~/.rommer/projects")
    return Path(root).expanduser()


class Project:
    """Manages a project workspace with standardized directory structure."""

    def __init__(self, name: str):
        self.name = name
        self._root = get_projects_root() / name

    @classmethod
    def scaffold(cls, name: str, platform: str) -> "Project":
        """Create a new project workspace with full directory tree."""
        project = cls(name)
        root = project._root

        dirs = [
            root / "rom",
            root / "knowledge" / "maps",
            root / "knowledge" / "guides",
            root / "knowledge" / "codes",
            root / "knowledge" / "saves",
            root / "knowledge" / "misc",
            root / "graph" / "nodes",
            root / "graph" / "preprocessor_output",
            root / "db",
            root / "save_states",
            root / "src" / "functions",
            root / "src" / "include",
            root / "src" / "docs",
            root / "ghidra",
        ]

        for d in dirs:
            d.mkdir(parents=True, exist_ok=True)

        # Write project metadata
        metadata = {
            "name": name,
            "platform": platform,
            "created_at": None,  # Set by caller
        }
        (root / "project.json").write_text(json.dumps(metadata, indent=2))

        return project

    @classmethod
    def list_projects(cls) -> list[str]:
        """List all project names in the projects root."""
        root = get_projects_root()
        if not root.exists():
            return []
        return [
            d.name for d in root.iterdir()
            if d.is_dir() and (d / "project.json").exists()
        ]

    # --- Path properties ---

    @property
    def root(self) -> Path:
        return self._root

    @property
    def rom_path(self) -> Path:
        """Path to the ROM file (first file in rom/ dir)."""
        rom_dir = self._root / "rom"
        if rom_dir.exists():
            roms = list(rom_dir.iterdir())
            if roms:
                return roms[0]
        return rom_dir / "game.gba"

    @property
    def db_path(self) -> Path:
        return self._root / "db" / "rommer.db"

    @property
    def knowledge_dir(self) -> Path:
        return self._root / "knowledge"

    @property
    def graph_dir(self) -> Path:
        return self._root / "graph"

    @property
    def src_dir(self) -> Path:
        return self._root / "src"

    @property
    def ghidra_dir(self) -> Path:
        return self._root / "ghidra"

    @property
    def save_states_dir(self) -> Path:
        return self._root / "save_states"

    # --- Methods ---

    @property
    def project_json(self) -> dict:
        """Read project metadata."""
        path = self._root / "project.json"
        if path.exists():
            return json.loads(path.read_text())
        return {}

    def update_metadata(self, **kwargs) -> None:
        """Update project metadata fields."""
        meta = self.project_json
        meta.update(kwargs)
        (self._root / "project.json").write_text(json.dumps(meta, indent=2))

    def get_db(self):
        """Get a database connection — Postgres if configured, else SQLite."""
        from rommer.db.connection import is_postgres, PostgresConnectionWrapper, get_postgres_connection
        if is_postgres():
            return PostgresConnectionWrapper(get_postgres_connection())

        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def exists(self) -> bool:
        """Check if this project workspace exists."""
        return (self._root / "project.json").exists()
