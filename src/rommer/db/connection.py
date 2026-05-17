"""Database connection utilities.

Supports both SQLite (per-project, file-based) and Postgres (shared).
Set DATABASE_URL env var to use Postgres, otherwise falls back to SQLite.
"""

import os
import sqlite3

import psycopg2
import psycopg2.extras


def get_database_url() -> str | None:
    """Get Postgres connection URL from env."""
    return os.environ.get("DATABASE_URL")


def get_postgres_connection():
    """Get a Postgres connection with dict-like row access."""
    url = get_database_url()
    if not url:
        raise RuntimeError("DATABASE_URL not set")
    conn = psycopg2.connect(url)
    conn.autocommit = False
    return conn


def get_postgres_cursor(conn):
    """Get a cursor that returns dict-like rows."""
    return conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)


def is_postgres() -> bool:
    """Check if we're configured for Postgres."""
    return get_database_url() is not None


class HybridRow(dict):
    """Dict that also supports index-based access like sqlite3.Row."""

    def __init__(self, data: dict):
        super().__init__(data)
        self._keys = list(data.keys())

    def __getitem__(self, key):
        if isinstance(key, int):
            return super().__getitem__(self._keys[key])
        return super().__getitem__(key)


class PostgresConnectionWrapper:
    """Wraps psycopg2 connection to provide a sqlite3-like interface.

    Returns HybridRow objects that support both row["col"] and row[0] access.
    """

    def __init__(self, conn):
        self._conn = conn
        self._cursor = None

    def execute(self, sql: str, params=None):
        """Execute SQL and return self for chaining."""
        sql = sql.replace("?", "%s")
        sql = sql.replace("INSERT OR REPLACE", "INSERT")
        sql = sql.replace("INSERT OR IGNORE", "INSERT")
        # Handle last_insert_rowid() → lastval()
        sql = sql.replace("last_insert_rowid()", "lastval()")
        self._cursor = self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        try:
            self._cursor.execute(sql, params or ())
        except psycopg2.errors.UniqueViolation:
            self._conn.rollback()
            self._cursor = self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        return self

    def executescript(self, sql: str):
        """Execute multiple SQL statements."""
        cur = self._conn.cursor()
        cur.execute(sql)
        self._conn.commit()

    def fetchone(self):
        if self._cursor is None:
            return None
        row = self._cursor.fetchone()
        return HybridRow(row) if row else None

    def fetchall(self):
        if self._cursor is None:
            return []
        return [HybridRow(r) for r in self._cursor.fetchall()]

    def commit(self):
        self._conn.commit()

    def close(self):
        self._conn.close()

    @property
    def row_factory(self):
        return None

    @row_factory.setter
    def row_factory(self, value):
        pass  # Postgres wrapper always returns dicts


def get_connection_for_project(project_name: str):
    """Get a DB connection — Postgres if available, else SQLite."""
    if is_postgres():
        return PostgresConnectionWrapper(get_postgres_connection())

    from rommer.config import Project
    project = Project(project_name)
    return project.get_db()


def init_project_db_postgres(project_name: str):
    """Ensure project exists in Postgres."""
    if not is_postgres():
        return
    conn = get_postgres_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO project (game_id, game_title) VALUES (%s, %s) ON CONFLICT (game_id) DO NOTHING",
        (project_name, project_name),
    )
    conn.commit()
    conn.close()
