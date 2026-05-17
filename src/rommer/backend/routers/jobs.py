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
    parallel: int = 1
    merge_strategy: str = "union"  # union, consensus, hybrid


def _start_job_or_parallel(mgr: JobManager, job_type: str, config: dict, req: JobRequest) -> dict:
    """Start a single job or parallel group."""
    if req.parallel > 1:
        job_ids = mgr.create_parallel_jobs(
            job_type, config, req.parallel, req.merge_strategy
        )
        return {"job_ids": job_ids, "parallel": req.parallel, "merge_strategy": req.merge_strategy, "status": "running"}
    else:
        job_id = mgr.create_job(job_type, config)
        mgr.start_job(job_id)
        return {"job_id": job_id, "status": "running"}


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
    """Start graph generation job(s)."""
    p = Project(req.project)
    if not p.exists():
        return {"error": f"Project '{req.project}' not found"}
    mgr = JobManager(p)
    return _start_job_or_parallel(mgr, "graph_gen", {"model": req.model, "walkthrough": req.walkthrough}, req)


@router.post("/jobs/knowledge-analysis")
def start_knowledge_analysis(req: JobRequest):
    """Start knowledge analysis job(s)."""
    p = Project(req.project)
    if not p.exists():
        return {"error": f"Project '{req.project}' not found"}
    mgr = JobManager(p)
    return _start_job_or_parallel(mgr, "knowledge_analysis", {"model": req.model}, req)


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


class AgentJobRequest(BaseModel):
    project: str
    model: str = "opus"
    focus: str | None = None
    parallel: int = 1
    merge_strategy: str = "union"


@router.post("/jobs/static-analysis")
def start_static_analysis(req: AgentJobRequest):
    """Start static analysis agent."""
    p = Project(req.project)
    if not p.exists():
        return {"error": f"Project '{req.project}' not found"}
    mgr = JobManager(p)
    config = {"model": req.model, "focus": req.focus}
    job_id = mgr.create_job("static_analysis", config)
    mgr.start_job(job_id)
    return {"job_id": job_id, "status": "running"}


@router.post("/jobs/refactor/{stage}")
def start_refactor_stage(stage: str, req: AgentJobRequest):
    """Start a refactor pipeline stage.

    Stages: type_resolver, literal_pool, forward_decl, struct_annotator, system_tracer
    """
    valid_stages = ["type_resolver", "literal_pool", "forward_decl", "struct_annotator", "system_tracer"]
    if stage not in valid_stages:
        return {"error": f"Unknown stage '{stage}'. Valid: {valid_stages}"}

    p = Project(req.project)
    if not p.exists():
        return {"error": f"Project '{req.project}' not found"}
    mgr = JobManager(p)
    config = {"model": req.model, "focus": req.focus}
    job_id = mgr.create_job(stage, config)
    mgr.start_job(job_id)
    return {"job_id": job_id, "status": "running"}
