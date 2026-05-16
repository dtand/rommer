"""Project endpoints."""

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
    """Get project stats. Defaults to first available project."""
    if not name:
        names = Project.list_projects()
        if not names:
            return {"error": "No projects found"}
        name = names[0]

    project = Project(name)
    if not project.exists():
        return {"error": f"Project '{name}' not found"}

    conn = project.get_db()
    stats = {}
    try:
        stats["discoveries"] = conn.execute("SELECT COUNT(*) FROM discovery").fetchone()[0]
        stats["golden"] = conn.execute("SELECT COUNT(*) FROM discovery WHERE tier='golden'").fetchone()[0]
        stats["graph_nodes"] = conn.execute("SELECT COUNT(*) FROM graph_node").fetchone()[0]
        stats["graph_edges"] = conn.execute("SELECT COUNT(*) FROM graph_edge").fetchone()[0]
    except Exception:
        pass
    conn.close()

    return {
        "name": name,
        **project.project_json,
        "stats": stats,
    }
