"""Database migrations for adding new tables/columns to existing DBs."""

import sqlite3

from rommer.config import Project


def migrate(project_name: str) -> None:
    """Run all pending migrations on a project's database."""
    project = Project(project_name)
    conn = project.get_db()
    migrate_db(conn)
    conn.close()


def migrate_db(conn: sqlite3.Connection) -> None:
    """Apply migrations to an open connection."""
    _add_knowledge_tables(conn)
    _add_discovery_source_column(conn)
    _add_discovery_metadata_column(conn)
    _add_discovery_tier_index(conn)
    _add_human_hints_column(conn)


def _add_knowledge_tables(conn: sqlite3.Connection) -> None:
    """Add knowledge_resource and node_knowledge tables if missing."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS knowledge_resource (
            id INTEGER PRIMARY KEY,
            project_id INTEGER REFERENCES project(id),
            type TEXT NOT NULL,
            filename TEXT NOT NULL,
            path TEXT NOT NULL,
            description TEXT,
            metadata TEXT
        );

        CREATE TABLE IF NOT EXISTS node_knowledge (
            id INTEGER PRIMARY KEY,
            node_id TEXT NOT NULL,
            resource_id INTEGER REFERENCES knowledge_resource(id),
            relevance TEXT,
            context_snippet TEXT
        );
    """)


def _add_discovery_source_column(conn: sqlite3.Connection) -> None:
    """Add source column to discovery table if missing."""
    try:
        conn.execute("SELECT source FROM discovery LIMIT 1")
    except sqlite3.OperationalError:
        conn.execute("ALTER TABLE discovery ADD COLUMN source TEXT DEFAULT 'dynamic'")
        conn.commit()


def _add_discovery_metadata_column(conn: sqlite3.Connection) -> None:
    """Add metadata JSON column to discovery table if missing."""
    try:
        conn.execute("SELECT metadata FROM discovery LIMIT 1")
    except sqlite3.OperationalError:
        conn.execute("ALTER TABLE discovery ADD COLUMN metadata TEXT")
        conn.commit()


def _add_discovery_tier_index(conn: sqlite3.Connection) -> None:
    """Add tier index if missing."""
    conn.execute("CREATE INDEX IF NOT EXISTS idx_discovery_tier ON discovery(tier)")
    conn.commit()


def _add_human_hints_column(conn: sqlite3.Connection) -> None:
    """Add human_hints column to graph_node if missing."""
    try:
        conn.execute("SELECT human_hints FROM graph_node LIMIT 1")
    except sqlite3.OperationalError:
        conn.execute("ALTER TABLE graph_node ADD COLUMN human_hints TEXT")
        conn.commit()
