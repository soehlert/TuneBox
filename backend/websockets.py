from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import json
import logging
import asyncio
from backend.state import playback_queue
from backend.services.plex import get_current_playing_track

# Setup logging
logging.basicConfig(level=logging.DEBUG)

router = APIRouter()
active_connections = []

# Variables to store last sent data
last_sent_queue = None
last_sent_track = None

def track_to_dict(track):
    """Convert a Plex Track object to a dictionary."""
    return {
        "item_id": track.ratingKey,
        "title": track.title,
        "artist": getattr(track, "grandparentTitle", "Unknown Artist"),
        "duration": track.duration if hasattr(track, "duration") else None
    }

async def send_queue():
    """Send the current queue to all connected WebSocket clients, if it has changed."""
    global last_sent_queue

    play_queue = [track_to_dict(track) for track in playback_queue]
    logging.debug(f"Sending current queue: {play_queue}")

    # Only send if the queue has changed
    if play_queue != last_sent_queue:
        message = json.dumps({"message": "Queue update", "queue": play_queue})  # Create the message
        for connection in active_connections:
            try:
                logging.debug(f"Sending queue to connection {id(connection)}")
                await connection.send_text(message)
            except Exception as e:
                logging.error(f"Error sending message to client {id(connection)}: {e}")
                # If sending fails, remove the connection from active_connections
                active_connections.remove(connection)

        # Update the last sent queue
        last_sent_queue = play_queue

async def send_current_playing():
    """Send the current playing track to all connected WebSocket clients, if it has changed."""
    global last_sent_track

    try:
        current_track = get_current_playing_track()
        logging.debug(f"Send current playing track: {current_track}")
        if current_track:
            track_data = {
                "title": current_track["title"],
                "artist": current_track["artist"]
            }

            # Only send if the current track has changed
            if track_data != last_sent_track:
                message = json.dumps({
                    "message": "Current track update",
                    "current_track": track_data
                })
                logging.debug(f"Sending current playing track: {track_data}")

                for connection in active_connections:
                    try:
                        logging.debug(f"Sending current track to connection {id(connection)}")
                        await connection.send_text(message)
                    except Exception as e:
                        logging.error(f"Error sending current track to client {id(connection)}: {e}")
                        # If sending fails, remove the connection from active_connections
                        active_connections.remove(connection)

                # Update the last sent track
                last_sent_track = track_data
        else:
            logging.warning("No current track found.")
    except Exception as e:
        logging.error(f"Error fetching current track: {e}")

async def update_websocket_clients():
    """Periodically send updates to all connected WebSocket clients."""
    while True:
        if active_connections:
            logging.debug("Sending websocket updates")
            await send_queue()
            await send_current_playing()
        await asyncio.sleep(5)  # Sleep for 5 seconds before sending again

async def websocket_handler(websocket: WebSocket):
    """Handle incoming WebSocket connections."""
    await websocket.accept()
    active_connections.append(websocket)
    logging.info(f"New WebSocket connection established from {websocket.client} "
                 f"Active connections: {len(active_connections)}")

    try:
        while True:
            message = await websocket.receive_text()
            data = json.loads(message)
            logging.debug(f"Received message: {data}")

            if data.get("message") == "ping":
                logging.debug("Sending pong...");
                await websocket.send_text(json.dumps({"message": "pong"}))

            elif data.get("message") == "get_current_queue":
                await send_queue()

            elif data.get("message") == "get_current_track":
                await send_current_playing()

    except WebSocketDisconnect as e:
        active_connections.remove(websocket)
        logging.info(f"WebSocket connection from {websocket.client} closed. "
                     f"Active connections: {len(active_connections)}")
    except Exception as e:
        logging.error(f"Error handling WebSocket message: {e}")


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket_handler(websocket)
