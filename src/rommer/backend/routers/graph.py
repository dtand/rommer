"""Graph endpoints."""

import json

from fastapi import APIRouter, Query
from pydantic import BaseModel

from rommer.config import Project

router = APIRouter()


@router.get("/graph/nodes")
def get_nodes(project: str = Query(...)):
    """Get all graph nodes for a project."""
    p = Project(project)
    if not p.exists():
        return {"error": f"Project '{project}' not found"}

    conn = p.get_db()
    rows = conn.execute(
        "SELECT node_id, name, title, description, section_ref, status, tags, order_index "
        "FROM graph_node ORDER BY order_index"
    ).fetchall()
    conn.close()

    return {
        "nodes": [
            {
                "node_id": r["node_id"],
                "name": r["name"],
                "title": r["title"],
                "description": r["description"],
                "section_ref": r["section_ref"],
                "status": r["status"],
                "tags": json.loads(r["tags"]) if r["tags"] else [],
                "order_index": r["order_index"],
            }
            for r in rows
        ]
    }


@router.get("/graph/edges")
def get_edges(project: str = Query(...)):
    """Get all graph edges for a project."""
    p = Project(project)
    if not p.exists():
        return {"error": f"Project '{project}' not found"}

    conn = p.get_db()
    rows = conn.execute(
        "SELECT from_node, to_node, edge_type FROM graph_edge"
    ).fetchall()
    conn.close()

    return {"edges": [dict(r) for r in rows]}


@router.get("/graph/discoveries")
def get_discoveries(project: str = Query(...), tier: str = Query(default=None)):
    """Get discoveries, optionally filtered by tier."""
    p = Project(project)
    if not p.exists():
        return {"error": f"Project '{project}' not found"}

    conn = p.get_db()
    try:
        query = "SELECT id, label, address, data_type, tier, confidence, discovered_by_node, source, notes FROM discovery"
        params: list[str] = []
        if tier:
            query += " WHERE tier = ?"
            params.append(tier)
        query += " ORDER BY address"
        rows = conn.execute(query, params).fetchall()
    except Exception:
        rows = []
    conn.close()

    return {"discoveries": [dict(r) for r in rows]}


class TierUpdate(BaseModel):
    tier: str  # 'golden' or 'scratch'


@router.patch("/graph/discoveries/{discovery_id}/tier")
def update_discovery_tier(discovery_id: int, body: TierUpdate, project: str = Query(...)):
    """Promote or demote a discovery's tier."""
    if body.tier not in ("golden", "scratch"):
        return {"error": "tier must be 'golden' or 'scratch'"}

    p = Project(project)
    if not p.exists():
        return {"error": f"Project '{project}' not found"}

    conn = p.get_db()
    conn.execute(
        "UPDATE discovery SET tier = ? WHERE id = ?",
        (body.tier, discovery_id),
    )
    conn.commit()
    conn.close()
    return {"ok": True, "id": discovery_id, "tier": body.tier}


@router.get("/graph/sections")
def get_sections(project: str = Query(...)):
    """Get walkthrough sections for a project."""
    p = Project(project)
    if not p.exists():
        return {"error": f"Project '{project}' not found"}

    conn = p.get_db()
    try:
        rows = conn.execute(
            "SELECT section_id, title, type, line_start, line_end, description "
            "FROM section ORDER BY line_start"
        ).fetchall()
    except Exception:
        rows = []
    conn.close()

    return {"sections": [dict(r) for r in rows]}
