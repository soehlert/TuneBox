from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import json
import logging
import asyncio

from backend.services.plex import get_current_playing_track, get_redis_queue

router = APIRouter()

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
        logging.error(f"Session ID {session_id} not found in {message_type}")
    except Exception as e:
        logging.error(f"Error sending message to client {session_id}: {e}")


async def send_queue():
    """Send the current queue to all connected WebSocket clients of 'queue_update' message_type."""
    play_queue = get_redis_queue()
    message = {
        "type": "queue_update",
        "message": "Queue update",
        "queue": play_queue,  # No need for json.dumps here
    }
    logging.debug(f"Sending play queue: {play_queue}")

    # Send the queue to all active connections of message_type 'queue_update'
    for session_id, connection in active_connections["queue_update"].items():
        try:
            logging.debug(f"Sending queue to connection {session_id}")
            await send_to_specific_client(session_id, message, "queue_update")
        except Exception as e:
            logging.error(f"Error sending message to client {session_id}: {e}")
            # If sending fails, remove the connection from active_connections
            active_connections["queue_update"].pop(session_id, None)


async def send_current_playing():
    """Send the current playing track to all connected WebSocket clients of 'music_control' message_type."""
    try:
        current_track = get_current_playing_track()
        logging.debug(f"Sending current playing track: {current_track}")

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

            # Prepare the message
            message = {"message": "Current track update", "current_track": track_data}

            logging.debug(f"Sending current playing track: {track_data}")

            # Send the message to all active connections of message_type 'music_control'
            for session_id, connection in active_connections["music_control"].items():
                try:
                    logging.debug(f"Sending current track to connection {session_id}")
                    await send_to_specific_client(session_id, message, "music_control")
                except Exception as e:
                    logging.error(f"Error sending message to client {session_id}: {e}")
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

    # Ensure the correct category exists in active_connections
    if message_type not in active_connections:
        active_connections[message_type] = {}

    session_id = str(id(websocket))  # Using id(websocket) as the unique identifier

    # Store the WebSocket connection under the correct type
    active_connections[message_type][session_id] = websocket
    logging.debug(f"Current active connections for '{message_type}': {active_connections[message_type]}")
    logging.debug(f"Stored WebSocket connection {session_id} under {message_type}")

    logging.info(
        f"New WebSocket connection of type '{message_type}' from {websocket.client} "
        f"Active connections: {len(active_connections)}"
    )

    try:
        while True:
            message = await websocket.receive_text()
            data = json.loads(message)
            logging.debug(f"Received message from client {message}")

            # Handle messages based on their type
            message_type = data.get("type")
            if not message_type:
                logging.error("Received message with no 'type'.")
                continue

            if message_type == "heartbeat":
                logging.debug("sending heartbeat")
                await websocket.send_text(json.dumps({"message": "pong"}))

            elif message_type == "queue_update":
                logging.debug("sending queue_update")
                await send_queue()

            elif message_type == "music_control":
                logging.debug("sending current_playing")
                await send_current_playing()

    except WebSocketDisconnect:
        # Remove the WebSocket connection from active_connections on disconnect
        for key in active_connections:
            if session_id in active_connections[key]:
                active_connections[key].pop(session_id, None)
        logging.info(
            f"WebSocket connection from {websocket.client} closed. Active connections: {len(active_connections)}"
        )
    except Exception as e:
        logging.error(f"Error handling WebSocket message: {e}")


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket_handler(websocket)
