"""Set up our websockets and handle messaging."""

import asyncio
import json
import logging
from datetime import UTC, datetime

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend.services.plex import get_current_playing_track, get_redis_queue

router = APIRouter()

logger = logging.getLogger(__name__)


# Dictionary to store WebSocket connections categorized by type
active_connections = {
    "music_control": {},  # Store music control connections
    "queue_update": {},  # Store queue update connections
    "client_control": {},  # Store per-browser control connections
    "unknown": {},
}

# Registry of named browser sessions keyed by client_id (browser-generated UUID)
client_registry: dict[str, dict] = {}


async def send_to_specific_client(session_id: str, message: dict, message_type: str):
    """Send a message to a specific WebSocket client based on session ID."""
    try:
        connection = active_connections[message_type][session_id]
        await connection.send_text(json.dumps(message))
    except KeyError:
        logger.exception(
            "Session ID %s not found in %s", session_id, active_connections
        )


async def send_to_client_id(client_id: str, message: dict):
    """Send a message to all WS connections belonging to a browser client_id."""
    ws = active_connections["client_control"].get(client_id)
    if ws:
        try:
            await ws.send_text(json.dumps(message))
        except Exception:
            logger.exception("Failed to send to client_id %s", client_id)
            active_connections["client_control"].pop(client_id, None)
            client_registry.pop(client_id, None)


async def send_queue():
    """Send the current queue to all connected WebSocket clients of 'queue_update' message_type."""
    play_queue = get_redis_queue()
    message = {
        "type": "queue_update",
        "message": "Queue update",
        "queue": play_queue,  # No need for json.dumps here
    }
    logger.debug("Sending play queue: %s", play_queue)

    # Send the queue to all active connections of message_type 'queue_update'
    for session_id in list(active_connections["queue_update"].keys()):
        try:
            logger.debug("Sending queue to connection %s", session_id)
            await send_to_specific_client(session_id, message, "queue_update")
        except Exception as e:
            # ruff: noqa: TRY401
            logger.exception("Failed to send to session %s: %s", session_id, e)
            active_connections["queue_update"].pop(session_id, None)


async def send_current_playing():
    """Send the current playing track to all connected WebSocket clients of 'music_control' message_type."""
    current_track = get_current_playing_track()
    logger.debug("Sending current playing track: %s", current_track)

    if current_track:
        track_data = {
            "item_id": current_track.get("item_id"),
            "title": current_track["title"],
            "artist": current_track["artist"],
            "total_time": current_track["total_time"],
            "remaining_time": current_track["remaining_time"],
            "track_state": current_track["track_state"],
            "remaining_percentage": current_track["remaining_percentage"],
            "elapsed_time": current_track["elapsed_time"],
        }
    else:
        track_data = None

    message = {"message": "Current track update", "current_track": track_data}

    # Send the message to all active connections of message_type 'music_control'
    for session_id in list(active_connections["music_control"].keys()):
        try:
            logger.debug("Sending current track to connection %s", session_id)
            await send_to_specific_client(session_id, message, "music_control")
        except Exception as e:
            logger.exception("Failed to send to session %s: %s", session_id, e)
            active_connections["music_control"].pop(session_id, None)


async def update_websocket_clients():
    """Periodically send updates to all connected WebSocket clients."""
    while True:
        try:
            # Lazy import to avoid circular dependencies
            from backend.services.plex import track_time_tracker  # noqa: PLC0415

            if active_connections:
                if track_time_tracker.is_playing:
                    await send_current_playing()
        except Exception as e:
            logger.exception("Error in update_websocket_clients loop: %s", e)
        await asyncio.sleep(1)


def _register_client(client_id: str, name: str, role: str, is_display: bool = False):
    """Upsert a client entry in the registry."""
    existing = client_registry.get(client_id, {})
    client_registry[client_id] = {
        "name": name,
        "role": role,
        "is_display": is_display or existing.get("is_display", False),
        "connected_at": existing.get("connected_at", datetime.now(UTC).isoformat()),
    }


# ruff: noqa: C901
async def websocket_handler(websocket: WebSocket):
    """Handle incoming WebSocket connections."""
    logger.debug("websocket_handler: Starting handler")
    await websocket.accept()
    logger.debug("websocket_handler: Connection accepted")

    # Wait for the first message from the client to get the type
    message = await websocket.receive_text()
    logger.debug("websocket_handler: Received message: %s", message)
    data = json.loads(message)

    # Extract the 'type' field to determine how to store the WebSocket connection
    message_type = data.get("type")
    logger.debug("websocket_handler: Extracted message type: %s", message_type)

    if not message_type:
        logger.error("Received message with no 'type'.")
        await websocket.close()
        return

    # Ensure the correct category exists in active_connections
    if message_type not in active_connections:
        active_connections[message_type] = {}

    # client_control connections are keyed by client_id (browser-generated UUID)
    if message_type == "client_control":
        client_id = data.get("client_id", str(id(websocket)))
        name = data.get("name", "Unknown")
        role = data.get("role", "guest")
        is_display = data.get("is_display", False)
        _register_client(client_id, name, role, is_display)
        active_connections["client_control"][client_id] = websocket
        session_id = client_id
    else:
        session_id = str(id(websocket))
        active_connections[message_type][session_id] = websocket

    logger.debug(
        "Current active connections for '%s': %s",
        message_type,
        active_connections[message_type],
    )
    logger.info(
        "New WebSocket connection of type %s, session %s", message_type, session_id
    )

    # Send initial state update immediately to the new client
    try:
        if message_type == "music_control":
            from backend.services.plex import check_plexamp_resync  # noqa: PLC0415
            await check_plexamp_resync(force_align=True)
            await send_current_playing()
        elif message_type == "queue_update":
            await send_queue()
    except Exception as e:
        logger.exception("Failed to send initial state to %s: %s", session_id, e)

    try:
        while True:
            message = await websocket.receive_text()
            data = json.loads(message)
            logger.debug("Received message from client %s", message)

            # Handle messages based on their type
            message_type = data.get("type")
            if not message_type:
                logger.error("Received message with no 'type'.")
                continue

            if message_type == "heartbeat":
                logger.debug("sending heartbeat")
                await websocket.send_text(json.dumps({"message": "pong"}))

            elif message_type == "queue_update":
                logger.debug("sending queue_update")
                await send_queue()

            elif message_type == "music_control":
                logger.debug("sending current_playing")
                await send_current_playing()

            elif message_type == "client_control":
                # Re-registration message (e.g. after page refresh)
                client_id = data.get("client_id", session_id)
                name = data.get("name", "Unknown")
                role = data.get("role", "guest")
                is_display = data.get("is_display", False)
                _register_client(client_id, name, role, is_display)
                active_connections["client_control"][client_id] = websocket

    except WebSocketDisconnect:
        for key in list(active_connections.keys()):
            if session_id in active_connections[key]:
                active_connections[key].pop(session_id, None)
        # Remove from client_registry only for client_control (keyed by client_id)
        if message_type == "client_control":
            client_registry.pop(session_id, None)
        logger.info(
            "WebSocket connection from %s closed. Active connections: %d",
            websocket.client,
            len(active_connections),
        )


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """Create our websocket endpoint."""
    await websocket_handler(websocket)
