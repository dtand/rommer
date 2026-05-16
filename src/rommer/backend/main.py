"""FastAPI application - REST API for rommer."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from rommer.backend.routers import project, graph, upload, jobs, ws
from rommer.jobs.manager import set_broadcast


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Set up broadcast function on startup."""
    set_broadcast(ws.get_broadcast_fn())
    yield


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
