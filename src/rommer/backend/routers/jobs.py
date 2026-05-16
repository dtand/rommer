"""Jobs API endpoints."""

from fastapi import APIRouter, Query
from pydantic import BaseModel

from rommer.config import Project
from rommer.jobs.manager import JobManager

router = APIRouter()


class JobRequest(BaseModel):
    project: str
    model: str = "opus"
    walkthrough: str | None = None


@router.get("/jobs")
def list_jobs(project: str = Query(...)):
    """List all jobs for a project."""
    p = Project(project)
    if not p.exists():
        return {"error": f"Project '{project}' not found"}
    mgr = JobManager(p)
    return {"jobs": mgr.list_jobs()}


@router.get("/jobs/{job_id}")
def get_job(job_id: str):
    """Get job details."""
    # Search across all projects for the job
    for name in Project.list_projects():
        p = Project(name)
        mgr = JobManager(p)
        status = mgr.get_status(job_id)
        if status:
            return status
    return {"error": "Job not found"}


@router.get("/jobs/{job_id}/events")
def get_job_events(job_id: str):
    """Get job event log."""
    import json
    for name in Project.list_projects():
        p = Project(name)
        conn = p.get_db()
        rows = conn.execute(
            "SELECT * FROM job_event WHERE job_id = ? ORDER BY timestamp", (job_id,)
        ).fetchall()
        conn.close()
        if rows:
            return {"events": [
                {"id": r["id"], "type": r["type"], "timestamp": r["timestamp"],
                 "data": json.loads(r["data"]) if r["data"] else None}
                for r in rows
            ]}
    return {"events": []}


@router.post("/jobs/{job_id}/cancel")
def cancel_job(job_id: str):
    """Cancel a running job."""
    for name in Project.list_projects():
        p = Project(name)
        mgr = JobManager(p)
        status = mgr.get_status(job_id)
        if status:
            mgr.cancel_job(job_id)
            return {"ok": True}
    return {"error": "Job not found"}


@router.post("/jobs/graph-gen")
def start_graph_gen(req: JobRequest):
    """Start graph generation job."""
    p = Project(req.project)
    if not p.exists():
        return {"error": f"Project '{req.project}' not found"}
    mgr = JobManager(p)
    job_id = mgr.create_job("graph_gen", {"model": req.model, "walkthrough": req.walkthrough})
    mgr.start_job(job_id)
    return {"job_id": job_id, "status": "running"}


@router.post("/jobs/knowledge-analysis")
def start_knowledge_analysis(req: JobRequest):
    """Start knowledge analysis job."""
    p = Project(req.project)
    if not p.exists():
        return {"error": f"Project '{req.project}' not found"}
    mgr = JobManager(p)
    job_id = mgr.create_job("knowledge_analysis", {"model": req.model})
    mgr.start_job(job_id)
    return {"job_id": job_id, "status": "running"}


@router.post("/jobs/ghidra-decompile")
def start_ghidra_decompile(req: JobRequest):
    """Start Ghidra decompile job."""
    p = Project(req.project)
    if not p.exists():
        return {"error": f"Project '{req.project}' not found"}
    mgr = JobManager(p)
    job_id = mgr.create_job("ghidra_decompile", {"model": req.model})
    mgr.start_job(job_id)
    return {"job_id": job_id, "status": "running"}
