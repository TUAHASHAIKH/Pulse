"""
Pulse Orchestrator — Socket.io Server

Handles real-time communication between the orchestrator and the
Next.js dashboard. The dashboard connects via Socket.io and receives
live events as agents work.

Architecture:
  - The Socket.io server is mounted as an ASGI app alongside FastAPI
  - Both share the same process and port (no extra server to run)
  - Any module can call emit_event() to push data to all connected clients

Events emitted:
  - "webhook_received"  → a GitHub webhook was received and validated
  - "agent_started"     → an agent began processing (Phase 2+)
  - "agent_completed"   → an agent finished with findings (Phase 2+)
  - "repair_attempt"    → Repair Agent is trying a fix (Phase 4+)
  - "incident_detected" → Sentinel detected an issue (Phase 7+)
"""

import socketio
from app.config import settings
from app.utils.logger import setup_logger

logger = setup_logger("pulse.socket")

# Create the Socket.io async server
# cors_allowed_origins controls which frontends can connect
sio = socketio.AsyncServer(
    async_mode="asgi",
    cors_allowed_origins=[
        settings.dashboard_origin,
        "http://localhost:3000",
        "http://localhost:4000",
    ],
    logger=False,       # Socket.io's own logging is noisy; we use ours
    engineio_logger=False,
)

# Wrap as an ASGI app — this gets mounted in main.py
socket_app = socketio.ASGIApp(sio)


# ─── Connection Handlers ───

@sio.event
async def connect(sid, environ):
    """Called when a dashboard client connects."""
    logger.info(f"🔌 Dashboard client connected: {sid}")
    # Send a welcome event so the client knows it's connected
    await sio.emit("connected", {"message": "Connected to Pulse orchestrator"}, room=sid)


@sio.event
async def disconnect(sid):
    """Called when a dashboard client disconnects."""
    logger.info(f"🔌 Dashboard client disconnected: {sid}")


# ─── Event Emitter (used by other modules) ───

async def emit_event(event_name: str, data: dict):
    """
    Broadcast an event to ALL connected dashboard clients.

    This is the main function other modules use to push real-time
    updates to the dashboard.

    Args:
        event_name: The Socket.io event name (e.g. "webhook_received")
        data: The event payload as a dict
    """
    await sio.emit(event_name, data)
    logger.debug(f"📡 Emitted '{event_name}' to {len(sio.manager.rooms.get('/', {}))} client(s)")
