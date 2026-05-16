"""FastAPI application - REST API for rommer."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from rommer.backend.routers import project, graph

app = FastAPI(title="Rommer API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(project.router, prefix="/api")
app.include_router(graph.router, prefix="/api")
