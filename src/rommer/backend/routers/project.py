"""Project endpoints."""

import json
from pathlib import Path

from fastapi import APIRouter, Query

from rommer.config import Project

router = APIRouter()


@router.get("/projects")
def list_projects():
    """List all available projects."""
    names = Project.list_projects()
    projects = []
    for name in names:
        p = Project(name)
        meta = p.project_json
        projects.append({
            "name": name,
            "platform": meta.get("platform"),
            "game_title": meta.get("game_title"),
        })
    return {"projects": projects}


@router.get("/project")
def get_project(name: str = Query(default=None)):
    """Get full project info including ROM metadata and knowledge files."""
    if not name:
        names = Project.list_projects()
        if not names:
            return {"error": "No projects found"}
        name = names[0]

    project = Project(name)
    if not project.exists():
        return {"error": f"Project '{name}' not found"}

    meta = project.project_json

    # DB stats
    conn = project.get_db()
    stats = {}
    try:
        stats["discoveries"] = conn.execute("SELECT COUNT(*) FROM discovery").fetchone()[0]
        stats["golden"] = conn.execute("SELECT COUNT(*) FROM discovery WHERE tier='golden'").fetchone()[0]
        stats["graph_nodes"] = conn.execute("SELECT COUNT(*) FROM graph_node").fetchone()[0]
        stats["graph_edges"] = conn.execute("SELECT COUNT(*) FROM graph_edge").fetchone()[0]
    except Exception:
        stats = {"discoveries": 0, "golden": 0, "graph_nodes": 0, "graph_edges": 0}
    conn.close()

    # Knowledge files
    knowledge = _scan_knowledge(project)

    return {
        "name": name,
        "platform": meta.get("platform"),
        "game_title": meta.get("game_title"),
        "created_at": meta.get("created_at"),
        "rom": meta.get("rom"),
        "stats": stats,
        "knowledge": knowledge,
    }


@router.get("/project/{name}/knowledge")
def get_knowledge_files(name: str):
    """List knowledge files for a project."""
    project = Project(name)
    if not project.exists():
        return {"error": f"Project '{name}' not found"}
    return {"files": _scan_knowledge(project)}


def _scan_knowledge(project: Project) -> list[dict]:
    """Scan the project workspace for knowledge files."""
    files = []
    knowledge_dir = project.knowledge_dir

    if not knowledge_dir.exists():
        return files

    for f in sorted(knowledge_dir.rglob("*")):
        if f.is_file() and not f.name.startswith("."):
            rel = str(f.relative_to(project.root))
            category = f.parent.name if f.parent != knowledge_dir else "misc"
            files.append({
                "path": rel,
                "name": f.name,
                "category": category,
                "size": f.stat().st_size,
            })

    # Also include save states
    saves_dir = project.save_states_dir
    if saves_dir.exists():
        for f in sorted(saves_dir.iterdir()):
            if f.is_file():
                files.append({
                    "path": str(f.relative_to(project.root)),
                    "name": f.name,
                    "category": "save_states",
                    "size": f.stat().st_size,
                })

    return files
