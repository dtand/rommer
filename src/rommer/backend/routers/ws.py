"""WebSocket endpoints for real-time job updates.

Two channels:
- /api/ws/jobs/{job_id} — live logs + progress for a specific job
- /api/ws/project/{project} — job status changes + toasts for a project
"""

import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter()


class ConnectionManager:
    """Manages WebSocket connections per channel."""

    def __init__(self):
        self.channels: dict[str, list[WebSocket]] = {}
        self._loop: asyncio.AbstractEventLoop | None = None

    async def connect(self, websocket: WebSocket, channel: str):
        await websocket.accept()
        self.channels.setdefault(channel, []).append(websocket)

    def disconnect(self, websocket: WebSocket, channel: str):
        if channel in self.channels:
            self.channels[channel] = [ws for ws in self.channels[channel] if ws != websocket]
            if not self.channels[channel]:
                del self.channels[channel]

    async def send_to_channel(self, channel: str, event: dict):
        if channel not in self.channels:
            return
        dead = []
        for ws in self.channels[channel]:
            try:
                await ws.send_json(event)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws, channel)

    def emit_sync(self, event: dict):
        """Emit from sync context (job workers in threads).
        Routes to job channel + project channel for status changes."""
        if not self._loop or not self._loop.is_running():
            return

        job_id = event.get("job_id")
        project = event.get("project")

        if job_id:
            asyncio.run_coroutine_threadsafe(
                self.send_to_channel(f"job:{job_id}", event), self._loop
            )

        if project and event.get("type") in (
            "job_started", "job_complete", "job_failed",
            "job_cancelled", "job_progress",
        ):
            asyncio.run_coroutine_threadsafe(
                self.send_to_channel(f"project:{project}", event), self._loop
            )

    def set_loop(self, loop: asyncio.AbstractEventLoop):
        self._loop = loop


manager = ConnectionManager()


def get_broadcast_fn():
    return manager.emit_sync


@router.websocket("/ws/jobs/{job_id}")
async def job_websocket(websocket: WebSocket, job_id: str):
    """Live logs + progress for a specific job."""
    manager.set_loop(asyncio.get_event_loop())
    channel = f"job:{job_id}"
    await manager.connect(websocket, channel)
    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        manager.disconnect(websocket, channel)


@router.websocket("/ws/project/{project}")
async def project_websocket(websocket: WebSocket, project: str):
    """Job status changes + toasts for a project."""
    manager.set_loop(asyncio.get_event_loop())
    channel = f"project:{project}"
    await manager.connect(websocket, channel)
    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        manager.disconnect(websocket, channel)
