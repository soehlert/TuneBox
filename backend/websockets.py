from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import json
import logging
import asyncio
from backend.services.plex import get_current_playing_track, get_redis_queue

router = APIRouter()
active_connections = []

last_sent_queue = None
last_sent_track = None


async def send_queue():
    """Send the current queue to all connected WebSocket clients, if it has changed."""
    global last_sent_queue
    play_queue =  get_redis_queue()
    logging.debug(f"Sending current queue: {play_queue}")

    # Only send if the queue has changed
    if play_queue != last_sent_queue:
        message = json.dumps({"message": "Queue update", "queue": play_queue})
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
        if current_track:
            track_data = {
                "title": current_track["title"],
                "artist": current_track["artist"],
                "total_time": current_track["total_time"],
                "remaining_time": current_track["remaining_time"],
                "track_state": current_track["track_state"],
                "remaining_percentage": current_track["remaining_percentage"],
            }

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
            await send_queue()
            await send_current_playing()
        await asyncio.sleep(5)

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

            if data.get("message") == "ping":
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
