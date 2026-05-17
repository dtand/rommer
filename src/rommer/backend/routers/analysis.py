"""Analysis API endpoints — function analysis data for the UI."""

import json

from fastapi import APIRouter, Query

from rommer.config import Project

router = APIRouter()


@router.get("/analysis/stats")
def get_analysis_stats(project: str = Query(...)):
    """Get overall analysis statistics."""
    p = Project(project)
    if not p.exists():
        return {"error": f"Project '{project}' not found"}

    conn = p.get_db()
    ph = "%s" if hasattr(conn, '_conn') else "?"

    try:
        total = conn.execute("SELECT COUNT(*) as cnt FROM function_analysis").fetchone()["cnt"]
        by_system = conn.execute(
            "SELECT system, COUNT(*) as cnt, AVG(confidence) as avg_conf, AVG(completeness) as avg_comp "
            "FROM function_analysis WHERE system IS NOT NULL GROUP BY system ORDER BY cnt DESC"
        ).fetchall()
        by_level = conn.execute(
            "SELECT level, COUNT(*) as cnt FROM function_analysis GROUP BY level ORDER BY level"
        ).fetchall()
    except Exception:
        total = 0
        by_system = []
        by_level = []

    # Get total function count from call graph
    call_graph_path = p.src_dir / "call_graph.json"
    total_functions = 0
    if call_graph_path.exists():
        cg = json.loads(call_graph_path.read_text())
        total_functions = cg.get("total_functions", 0)

    conn.close()

    return {
        "total_functions": total_functions,
        "analyzed": total,
        "percent": round(total / max(total_functions, 1) * 100, 1),
        "by_system": [dict(r) for r in by_system],
        "by_level": [dict(r) for r in by_level],
    }


@router.get("/analysis/functions")
def get_analysis_functions(
    project: str = Query(...),
    level: int | None = Query(default=None),
    system: str | None = Query(default=None),
    status: str | None = Query(default=None),  # analyzed, unanalyzed
    search: str | None = Query(default=None),
    offset: int = Query(default=0),
    limit: int = Query(default=50),
):
    """Get analyzed functions with filters."""
    p = Project(project)
    if not p.exists():
        return {"error": f"Project '{project}' not found"}

    conn = p.get_db()
    ph = "%s" if hasattr(conn, '_conn') else "?"

    query = "SELECT * FROM function_analysis WHERE 1=1"
    params: list = []

    if level is not None:
        query += f" AND level = {ph}"
        params.append(level)
    if system:
        query += f" AND system = {ph}"
        params.append(system)
    if search:
        query += f" AND (name LIKE {ph} OR address LIKE {ph} OR description LIKE {ph})"
        params.extend([f"%{search}%", f"%{search}%", f"%{search}%"])

    # Count
    count_query = query.replace("SELECT *", "SELECT COUNT(*) as cnt")
    total = conn.execute(count_query, params).fetchone()["cnt"]

    # Fetch page
    query += f" ORDER BY level, address LIMIT {ph} OFFSET {ph}"
    params.extend([limit, offset])
    rows = conn.execute(query, params).fetchall()

    conn.close()

    return {
        "total": total,
        "functions": [dict(r) for r in rows],
    }


@router.get("/analysis/functions/{address}")
def get_function_detail(address: str, project: str = Query(...)):
    """Get detailed analysis for a specific function."""
    p = Project(project)
    if not p.exists():
        return {"error": f"Project '{project}' not found"}

    conn = p.get_db()
    ph = "%s" if hasattr(conn, '_conn') else "?"

    row = conn.execute(
        f"SELECT * FROM function_analysis WHERE address = {ph}", (address,)
    ).fetchone()
    conn.close()

    if not row:
        return {"error": f"Function {address} not found"}

    result = dict(row)

    # Load the .c file content
    funcs_dir = p.src_dir / "functions"
    addr_prefix = address.replace("0x", "").upper()
    for f in funcs_dir.glob(f"{addr_prefix}*.c"):
        result["code"] = f.read_text()
        result["filename"] = f.name
        break

    return result
