"""Graph endpoints."""

import json

from fastapi import APIRouter, Query

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
    query = "SELECT label, address, data_type, tier, confidence, discovered_by_node FROM discovery"
    params = []
    if tier:
        query += " WHERE tier = ?"
        params.append(tier)
    query += " ORDER BY address"

    rows = conn.execute(query, params).fetchall()
    conn.close()

    return {"discoveries": [dict(r) for r in rows]}
