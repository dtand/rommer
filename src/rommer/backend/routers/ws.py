"""WebSocket endpoint for real-time job updates."""

import asyncio
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter()


class ConnectionManager:
    """Manages WebSocket connections and broadcasts events."""

    def __init__(self):
        self.connections: list[tuple[WebSocket, str | None]] = []  # (ws, project_filter)
        self._loop: asyncio.AbstractEventLoop | None = None

    async def connect(self, websocket: WebSocket, project: str | None = None):
        await websocket.accept()
        self.connections.append((websocket, project))

    def disconnect(self, websocket: WebSocket):
        self.connections = [(ws, p) for ws, p in self.connections if ws != websocket]

    async def broadcast(self, event: dict):
        """Send event to all connected clients (filtered by project if set)."""
        event_project = event.get("project")
        dead = []
        for ws, project_filter in self.connections:
            if project_filter and event_project and project_filter != event_project:
                continue
            try:
                await ws.send_json(event)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)

    def broadcast_sync(self, event: dict):
        """Broadcast from a sync context (called by job workers in threads)."""
        if self._loop and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(self.broadcast(event), self._loop)

    def set_loop(self, loop: asyncio.AbstractEventLoop):
        self._loop = loop


# Global connection manager instance
manager = ConnectionManager()


def get_broadcast_fn():
    """Return a sync-callable broadcast function for the job manager."""
    return manager.broadcast_sync


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, project: str | None = None):
    """WebSocket for real-time job/agent updates.

    Connect with optional ?project=name to filter events.
    """
    # Store the event loop for sync broadcasting
    manager.set_loop(asyncio.get_event_loop())

    await manager.connect(websocket, project)
    try:
        # Keep connection alive, handle client messages (ping/pong)
        while True:
            data = await websocket.receive_text()
            # Client can send ping or subscribe messages
            if data == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        manager.disconnect(websocket)
