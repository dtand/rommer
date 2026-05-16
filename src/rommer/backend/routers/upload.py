"""Upload endpoint - handles ZIP file upload and project initialization.

Flow:
1. POST /api/init-project — classify files, validate ROM, return walkthroughs list
2. POST /api/project/{name}/start-pipeline — run passes 1-3, auto-kick background jobs
"""

import json
import tempfile
from pathlib import Path

from fastapi import APIRouter, File, Form, UploadFile
from pydantic import BaseModel

from rommer.config import Project

router = APIRouter()


@router.post("/init-project")
async def init_project(
    name: str = Form(...),
    platform: str = Form(default="gba"),
    file: UploadFile = File(...),
):
    """Upload a ZIP and create a new project with agent-driven classification.

    Returns the project info + list of detected walkthroughs.
    If only one walkthrough, frontend can auto-call start-pipeline.
    If multiple, frontend shows a picker.
    """
    if Project(name).exists():
        return {"error": f"Project '{name}' already exists"}

    with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        from rommer.cli.commands.init_project import _extract_and_classify

        project = Project.scaffold(name, platform)

        class Args:
            pass
        args = Args()
        args.name = name
        args.platform = platform

        _extract_and_classify(project, Path(tmp_path), args)

        # Detect walkthroughs
        walkthroughs = _detect_walkthroughs(project)

        return {
            "name": name,
            "walkthroughs": walkthroughs,
            "notes": "Project created. Select walkthrough to start pipeline.",
        }
    except Exception as e:
        return {"error": str(e)}
    finally:
        Path(tmp_path).unlink(missing_ok=True)


class StartPipelineRequest(BaseModel):
    walkthrough: str | None = None
    model: str = "opus"


@router.post("/project/{name}/start-pipeline")
def start_pipeline(name: str, req: StartPipelineRequest):
    """Run passes 1-3 (blocking), then auto-kick background jobs.

    This is called after init-project, once the user has confirmed
    the walkthrough (or it was auto-selected).
    """
    project = Project(name)
    if not project.exists():
        return {"error": f"Project '{name}' not found"}

    # Find walkthrough
    guides_dir = project.knowledge_dir / "guides"
    if req.walkthrough:
        wt_path = guides_dir / req.walkthrough
    else:
        wt_files = sorted(guides_dir.glob("walkthrough*")) if guides_dir.exists() else []
        if not wt_files:
            return {"error": "No walkthrough file found in knowledge/guides/"}
        wt_path = wt_files[0]

    if not wt_path.exists():
        return {"error": f"Walkthrough not found: {req.walkthrough}"}

    # Run passes 1-3 (blocking)
    from rommer.preprocessor.pass1_structure import detect_structure
    from rommer.preprocessor.pass2_systems import audit_systems
    from rommer.preprocessor.pass3_extraction import extract_data
    from rommer.db.models import init_db

    conn = project.get_db()
    init_db(conn)

    # Ensure project row exists
    row = conn.execute("SELECT id FROM project LIMIT 1").fetchone()
    if not row:
        conn.execute("INSERT INTO project (game_id, game_title) VALUES (?, ?)",
                     (name, project.project_json.get("game_title", name)))
        conn.commit()

    output_dir = project.graph_dir / "preprocessor_output"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Pass 1
    section_map = detect_structure(req.model, wt_path)
    (output_dir / "pass1_section_map.json").write_text(json.dumps(section_map, indent=2))

    # Pass 2
    systems = audit_systems(req.model, wt_path, section_map)
    (output_dir / "pass2_systems.json").write_text(json.dumps(systems, indent=2))

    # Pass 3
    data = extract_data(req.model, wt_path, section_map, systems)
    (output_dir / "pass3_data.json").write_text(json.dumps(data, indent=2))

    # Store results in DB
    _store_schema_results(conn, section_map, systems, data)
    conn.close()

    # Auto-kick background jobs
    from rommer.jobs.manager import JobManager
    mgr = JobManager(project)

    jobs_started = []

    # Graph generation
    job_id = mgr.create_job("graph_gen", {"model": req.model, "walkthrough": wt_path.name})
    mgr.start_job(job_id)
    jobs_started.append({"id": job_id, "type": "graph_gen"})

    # Knowledge analysis
    job_id = mgr.create_job("knowledge_analysis", {"model": "sonnet"})
    mgr.start_job(job_id)
    jobs_started.append({"id": job_id, "type": "knowledge_analysis"})

    # Ghidra decompile (if ROM exists)
    if project.rom_path.exists():
        job_id = mgr.create_job("ghidra_decompile", {})
        mgr.start_job(job_id)
        jobs_started.append({"id": job_id, "type": "ghidra_decompile"})

    return {
        "ok": True,
        "sections": len(section_map.get("sections", [])),
        "systems": len(systems.get("game_systems", [])),
        "data_rows": sum(len(v) for v in data.get("tables", {}).values()),
        "jobs": jobs_started,
    }


def _detect_walkthroughs(project: Project) -> list[dict]:
    """Find walkthrough files in the project."""
    guides_dir = project.knowledge_dir / "guides"
    if not guides_dir.exists():
        return []

    walkthroughs = []
    for f in sorted(guides_dir.iterdir()):
        if f.is_file() and "walkthrough" in f.name.lower():
            walkthroughs.append({
                "filename": f.name,
                "size": f.stat().st_size,
            })
    return walkthroughs


def _store_schema_results(conn, section_map: dict, systems: dict, data: dict):
    """Store passes 1-3 results in DB."""
    import json

    project_id = conn.execute("SELECT id FROM project LIMIT 1").fetchone()[0]

    # Sections
    for section in section_map.get("sections", []):
        conn.execute(
            """INSERT OR REPLACE INTO section
               (project_id, section_id, title, type, line_start, line_end, description)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (project_id, section.get("section_id"), section.get("title"),
             section.get("type"), section.get("line_start"), section.get("line_end"),
             section.get("description")),
        )

    # Game systems
    for system in systems.get("game_systems", []):
        conn.execute(
            """INSERT OR REPLACE INTO game_system (project_id, name, description, table_names)
               VALUES (?, ?, ?, ?)""",
            (project_id, system.get("name"), system.get("description"),
             json.dumps(system.get("table_names", []))),
        )

    # Control mappings
    for ctrl in systems.get("control_mappings", []):
        conn.execute(
            "INSERT INTO control_mapping (project_id, context, button, action) VALUES (?, ?, ?, ?)",
            (project_id, ctrl.get("context"), ctrl.get("button"), ctrl.get("action")),
        )

    # Schema SQL
    if systems.get("schema_sql"):
        conn.execute("INSERT INTO schema_sql (project_id, sql_text) VALUES (?, ?)",
                     (project_id, systems["schema_sql"]))

    # Data tables
    for table_name, rows in data.get("tables", {}).items():
        if not rows:
            continue
        columns = list(rows[0].keys()) if isinstance(rows[0], dict) else []
        conn.execute(
            "INSERT INTO game_data_table (project_id, table_name, column_names) VALUES (?, ?, ?)",
            (project_id, table_name, json.dumps(columns)),
        )
        table_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        for i, row in enumerate(rows):
            conn.execute(
                "INSERT INTO game_data_row (table_id, row_index, row_data) VALUES (?, ?, ?)",
                (table_id, i, json.dumps(row)),
            )

    conn.commit()
