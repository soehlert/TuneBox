from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import json
import logging
import asyncio

from requests import session

from backend.services.plex import get_current_playing_track, get_redis_queue

router = APIRouter()

last_sent_queue = None
last_sent_track = None

# Dictionary to store WebSocket connections categorized by type
active_connections = {
    "music_control": {},  # Store music control connections
    "queue-update": {},   # Store queue update connections
}


async def send_to_specific_client(session_id: str, message: dict):
    """Send a message to a specific WebSocket client based on session ID."""
    connection = active_connections.get(session_id)
    if connection:
        try:
            logging.debug(f"Sending message to connection {session_id}")
            await connection.send_text(json.dumps(message))
        except Exception as e:
            logging.error(f"Error sending message to client {session_id}: {e}")
            # If sending fails, remove the connection from active_connections
            active_connections.pop(session_id, None)
    else:
        logging.error(f"No connection found for session ID: {session_id}")


async def send_queue():
    """Send the current queue to all connected WebSocket clients of 'queue-update' message_type."""
    play_queue = get_redis_queue()

    message = json.dumps({"message": "Queue update", "queue": play_queue})
    logging.debug(f"Sending message: {message}")

    # Send the queue to all active connections of message_type 'queue-update'
    for session_id, connection in active_connections["queue-update"].items():
        try:
            logging.debug(f"Sending queue to connection {session_id}")
            await send_to_specific_client(session_id, message, "queue-update")
        except Exception as e:
            logging.error(f"Error sending message to client {session_id}: {e}")
            # If sending fails, remove the connection from active_connections
            active_connections["queue-update"].pop(session_id, None)

async def send_current_playing():
    """Send the current playing track to all connected WebSocket clients of 'music_control' message_type."""
    try:
        current_track = get_current_playing_track()
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

            message = json.dumps({
                "message": "Current track update",
                "current_track": track_data
            })
            logging.debug(f"Sending current playing track: {track_data}")

            # Loop through all active connections of message_type 'music_control' and send to each one
            for session_id, connection in active_connections["music_control"].items():
                try:
                    logging.debug(f"Sending current track to connection {session_id}")
                    await send_to_specific_client(session_id, message, "music_control")
                except Exception as e:
                    logging.error(f"Error sending message to client {session_id}: {e}")
                    # If sending fails, remove the connection from active_connections
                    active_connections["music_control"].pop(session_id, None)

        else:
            logging.warning("No current track found.")
    except Exception as e:
        logging.error(f"Error fetching current track: {e}")


async def update_websocket_clients():
    """Periodically send updates to all connected WebSocket clients."""
    while True:
        if active_connections:
            await send_queue()
            await send_current_playing()
        await asyncio.sleep(3)


async def websocket_handler(websocket: WebSocket):
    """Handle incoming WebSocket connections."""
    await websocket.accept()

    # Wait for the first message from the client to get the type
    message = await websocket.receive_text()
    data = json.loads(message)

    # Extract the 'type' field to determine how to store the WebSocket connection
    message_type = data.get("type")
    if not message_type:
        logging.error("Received message with no 'type'.")
        await websocket.close()
        return

    # Store the WebSocket connection under the correct type
    if message_type not in active_connections:
        active_connections[message_type] = {}

    session_id = str(id(websocket))  # Using id(websocket) as the unique identifier
    active_connections[message_type][session_id] = websocket

    logging.info(f"New WebSocket connection of type '{message_type}' from {websocket.client} "
                 f"Active connections: {len(active_connections)}")

    try:
        while True:
            message = await websocket.receive_text()
            data = json.loads(message)

            # Handle messages based on their type
            message_type = data.get("type")
            if not message_type:
                logging.error("Received message with no 'type'.")
                continue

            if message_type == "ping":
                await websocket.send_text(json.dumps({"message": "pong"}))

            elif message_type == "get_current_queue":
                await send_queue()

            elif message_type == "get_current_track":
                # Send the current track to the client that requested it
                await send_current_playing(session_id, message_type)

    except WebSocketDisconnect as e:
        # Remove the WebSocket connection from active_connections on disconnect
        for key in active_connections:
            if session_id in active_connections[key]:
                active_connections[key].pop(session_id, None)
        logging.info(f"WebSocket connection from {websocket.client} closed. "
                     f"Active connections: {len(active_connections)}")
    except Exception as e:
        logging.error(f"Error handling WebSocket message: {e}")


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket_handler(websocket)
