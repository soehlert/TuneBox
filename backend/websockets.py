"""Set up our websockets and handle messaging."""

import asyncio
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend.services.plex import get_current_playing_track, get_redis_queue

router = APIRouter()

logger = logging.getLogger(__name__)


# Dictionary to store WebSocket connections categorized by type
active_connections = {
    "music_control": {},  # Store music control connections
    "queue_update": {},  # Store queue update connections
    "unknown": {},
}


async def send_to_specific_client(session_id: str, message: dict, message_type: str):
    """Send a message to a specific WebSocket client based on session ID."""
    try:
        connection = active_connections[message_type][session_id]
        await connection.send_text(json.dumps(message))
    except KeyError:
        logger.exception("Session ID %s not found in %s", session_id, active_connections)


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
    for session_id in active_connections["queue_update"]:
        try:
            logger.debug("Sending queue to connection %s", session_id)
            await send_to_specific_client(session_id, message, "queue_update")
        # ruff: noqa: BLE001
        except Exception:
            active_connections["queue_update"].pop(session_id, None)


async def send_current_playing():
    """Send the current playing track to all connected WebSocket clients of 'music_control' message_type."""
    current_track = get_current_playing_track()
    logger.debug("Sending current playing track: %s", current_track)

    if current_track:
        track_data = {
            "title": current_track["title"],
            "artist": current_track["artist"],
            "total_time": current_track["total_time"],
            "remaining_time": current_track["remaining_time"],
            "track_state": current_track["track_state"],
            "remaining_percentage": current_track["remaining_percentage"],
            "elapsed_time": current_track["elapsed_time"],
        }

        message = {"message": "Current track update", "current_track": track_data}

        logger.debug("Sending current playing track: %s", track_data)

        # Send the message to all active connections of message_type 'music_control'
        for session_id in active_connections["music_control"]:
            try:
                logger.debug("Sending current track to connection %s", session_id)
                await send_to_specific_client(session_id, message, "music_control")
            except Exception:
                active_connections["music_control"].pop(session_id, None)
    else:
        logger.warning("No current track found.")


async def update_websocket_clients():
    """Periodically send updates to all connected WebSocket clients."""
    while True:
        if active_connections:
            await send_queue()
            await send_current_playing()
        await asyncio.sleep(3)


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

    session_id = str(id(websocket))  # Using id(websocket) as the unique identifier

    # Store the WebSocket connection under the correct type
    active_connections[message_type][session_id] = websocket
    logger.debug("Current active connections for '%s': %s", message_type, active_connections[message_type])
    logger.debug("Stored WebSocket connection %s under %s", session_id, message_type)

    logger.info("New WebSocket connection of type %s from %s", message_type, active_connections[message_type])
    logger.info("Active connections: %d", len(active_connections))

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

    except WebSocketDisconnect:
        # Remove the WebSocket connection from active_connections on disconnect
        for key in active_connections.items():
            if session_id in active_connections[key]:
                active_connections[key].pop(session_id, None)
        logger.info(
            "WebSocket connection from %s closed. Active connections: %d", websocket.client, len(active_connections)
        )


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """Create our websocket endpoint."""
    await websocket_handler(websocket)
