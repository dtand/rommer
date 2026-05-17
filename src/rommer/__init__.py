"""Rommer - AI-driven reverse engineering platform for GBA ROMs."""

import os
from pathlib import Path


def _load_env():
    """Load .env file from project root if it exists."""
    env_path = Path(__file__).parent.parent.parent / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip()
            # Expand ~ in paths
            if value.startswith("~"):
                value = os.path.expanduser(value)
            # Don't override existing env vars
            if key not in os.environ:
                os.environ[key] = value


_load_env()
