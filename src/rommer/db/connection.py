"""Database connection utilities."""

import sqlite3
from pathlib import Path

from rommer.config import Project


def get_connection(project_name: str) -> sqlite3.Connection:
    """Get a database connection for a project by name."""
    project = Project(project_name)
    return project.get_db()


def init_project_db(project: Project) -> sqlite3.Connection:
    """Initialize a project's database with the full schema."""
    from rommer.db.models import init_db
    conn = project.get_db()
    init_db(conn)
    return conn
