"""FastAPI application - REST API for rommer."""

import asyncio
import json
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from rommer.backend.routers import project, graph, upload, jobs, ws
from rommer.db.connection import is_postgres


async def _listen_postgres(ws_manager):
    """Listen for Postgres NOTIFY events and push to WebSocket channels."""
    import asyncpg

    url = os.environ.get("DATABASE_URL")
    if not url:
        return

    conn = await asyncpg.connect(url)

    async def handle_job_event(conn, pid, channel, payload):
        try:
            data = json.loads(payload)
            job_id = data.get("job_id")
            if job_id:
                await ws_manager.send_to_channel(f"job:{job_id}", {
                    "type": "job_log",
                    "job_id": job_id,
                    "data": json.loads(data.get("data", "{}")) if data.get("data") else {},
                })
        except Exception:
            pass

    async def handle_job_status(conn, pid, channel, payload):
        try:
            data = json.loads(payload)
            job_id = data.get("job_id")
            status = data.get("status")
            if job_id:
                event = {
                    "type": f"job_{status}" if status in ("completed", "failed") else "job_progress",
                    "job_id": job_id,
                    "data": {"status": status},
                }
                if status == "failed":
                    event["error"] = data.get("error")
                # Send to both job and project channels
                await ws_manager.send_to_channel(f"job:{job_id}", event)
                # Find project for this job (query DB)
                # For now broadcast to all project channels
                for channel_name in list(ws_manager.channels.keys()):
                    if channel_name.startswith("project:"):
                        await ws_manager.send_to_channel(channel_name, event)
        except Exception:
            pass

    await conn.add_listener("job_events", handle_job_event)
    await conn.add_listener("job_status", handle_job_status)

    # Keep alive
    try:
        while True:
            await asyncio.sleep(3600)
    finally:
        await conn.close()


async def _recover_zombie_jobs():
    """Mark any running jobs with dead PIDs as failed."""
    if not is_postgres():
        return
    import psycopg2
    url = os.environ.get("DATABASE_URL")
    conn = psycopg2.connect(url)
    cur = conn.cursor()
    cur.execute("SELECT id, pid FROM job WHERE status = 'running' AND pid IS NOT NULL")
    for row in cur.fetchall():
        job_id, pid = row
        try:
            os.kill(pid, 0)  # Check if alive
        except (ProcessLookupError, PermissionError):
            cur.execute(
                "UPDATE job SET status = 'failed', error = 'Worker died (startup recovery)' WHERE id = %s",
                (job_id,),
            )
    conn.commit()
    conn.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start Postgres LISTEN and recover zombie jobs."""
    await _recover_zombie_jobs()

    listen_task = None
    if is_postgres():
        listen_task = asyncio.create_task(_listen_postgres(ws.manager))

    yield

    if listen_task:
        listen_task.cancel()


app = FastAPI(title="Rommer API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000", "http://localhost:5174"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(project.router, prefix="/api")
app.include_router(graph.router, prefix="/api")
app.include_router(upload.router, prefix="/api")
app.include_router(jobs.router, prefix="/api")
app.include_router(ws.router, prefix="/api")
