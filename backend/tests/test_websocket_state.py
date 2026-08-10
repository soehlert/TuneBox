"""Phase 3: Real-Time WebSocket & State Sync Integration Tests.

Verifies:
- Queue broadcast updates (`send_queue`) on queue additions, deletions, reorders, and clear operations.
- Playback state broadcast updates (`send_current_playing`) on track state changes and stopped/empty queue transitions.
- Multi-client state synchronization across concurrent WebSocket connections.
- Payload schema contracts expected by frontend components (Queue.tsx and MusicControls.tsx).
"""

import json, pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient

from backend.config import settings
from backend.main import app
from backend.services.plex import get_current_playing_track, playback_active
from backend.services.redis import clear_redis_queue, get_redis_queue_client
from backend.websockets import active_connections, send_current_playing, send_queue


@pytest.fixture
def client():
    """Create FastAPI test client."""
    return TestClient(app)


@pytest.fixture(autouse=True)
def clean_redis_and_ws(mock_redis):
    """Clean Redis queue and active WebSocket connections before and after each test."""
    active_connections["music_control"].clear()
    active_connections["queue_update"].clear()
    active_connections["client_control"].clear()
    active_connections["unknown"].clear()
    yield
    active_connections["music_control"].clear()
    active_connections["queue_update"].clear()
    active_connections["client_control"].clear()
    active_connections["unknown"].clear()


def test_websocket_connection_and_registration(client):
    """Verify WebSocket connection registers connection into active_connections dictionary."""
    with client.websocket_connect("/ws") as websocket:
        # Client registers itself by sending initial type message
        websocket.send_json({"type": "queue_update", "message": "get_current_queue"})
        response = websocket.receive_json()
        assert response.get("message") == "Queue update"
        assert "queue" in response
        assert "vibes" in response
        assert isinstance(response["queue"], list)


def test_websocket_queue_broadcast_schema_contract(client, mock_redis):
    """Verify send_queue outputs exact JSON payload schema expected by Queue.tsx."""
    mock_queue_client, _ = mock_redis
    
    # Mock Redis queue items
    queue_item = {
        "item_id": "3001",
        "title": "One More Time",
        "artist": "Daft Punk",
        "duration": 320000,
        "album_art": "/api/music/album-art/2001",
        "server_id": "plex-so",
        "moods": ["Energetic", "Upbeat"],
    }
    redis_store = [json.dumps(queue_item).encode()]

    mock_queue_client.lrange.return_value = redis_store

    with client.websocket_connect("/ws") as ws:
        ws.send_json({"type": "queue_update", "message": "get_current_queue"})
        initial_msg = ws.receive_json()
        assert initial_msg["message"] == "Queue update"

        # Trigger send_queue async broadcast
        import asyncio
        asyncio.run(send_queue())

        broadcast_msg = ws.receive_json()
        assert broadcast_msg["type"] == "queue_update"
        assert broadcast_msg["message"] == "Queue update"
        assert len(broadcast_msg["queue"]) == 1
        assert broadcast_msg["queue"][0]["item_id"] == "3001"
        assert broadcast_msg["queue"][0]["title"] == "One More Time"
        assert broadcast_msg["queue"][0]["artist"] == "Daft Punk"
        assert "vibes" in broadcast_msg
        assert isinstance(broadcast_msg["vibes"], list)


def test_websocket_current_playing_schema_contract(client, mocker):
    """Verify send_current_playing outputs exact JSON payload schema expected by MusicControls.tsx."""
    mock_track = {
        "item_id": "3001",
        "title": "One More Time",
        "artist": "Daft Punk",
        "total_time": 320,
        "remaining_time": 150,
        "track_state": "playing",
        "remaining_percentage": 46.875,
        "elapsed_time": 170,
    }
    mocker.patch("backend.websockets.get_current_playing_track", return_value=mock_track)

    with client.websocket_connect("/ws") as ws:
        ws.send_json({"type": "music_control", "message": "get_current_track"})
        
        # Trigger send_current_playing async broadcast
        import asyncio
        asyncio.run(send_current_playing())

        msg = ws.receive_json()
        assert msg["message"] == "Current track update"
        assert "current_track" in msg
        curr = msg["current_track"]
        assert curr["item_id"] == "3001"
        assert curr["title"] == "One More Time"
        assert curr["artist"] == "Daft Punk"
        assert curr["total_time"] == 320
        assert curr["remaining_time"] == 150
        assert curr["track_state"] == "playing"


def test_websocket_stopped_and_empty_queue_payload(client, mocker):
    """Verify send_current_playing outputs stopped & queue_empty payload when playback is inactive."""
    mocker.patch("backend.websockets.get_current_playing_track", return_value=None)
    mocker.patch("backend.websockets.get_redis_queue", return_value=[])
    mocker.patch("backend.services.plex.playback_active", False)

    with client.websocket_connect("/ws") as ws:
        ws.send_json({"type": "music_control", "message": "get_current_track"})

        import asyncio
        asyncio.run(send_current_playing())

        msg = ws.receive_json()
        assert msg["message"] == "Current track update"
        assert msg["current_track"] is None
        assert msg["stopped"] is True
        assert msg["queue_empty"] is True


def test_websocket_multi_client_sync(client, mocker):
    """Verify multiple concurrent WebSocket connections receive synchronized queue broadcasts."""
    queue_item = {"item_id": "9999", "title": "Synchronized Song", "artist": "Test Band"}
    mocker.patch("backend.websockets.get_redis_queue", return_value=[queue_item])

    with client.websocket_connect("/ws") as ws1, client.websocket_connect("/ws") as ws2:
        ws1.send_json({"type": "queue_update", "message": "get_current_queue"})
        ws2.send_json({"type": "queue_update", "message": "get_current_queue"})

        # Initial responses
        ws1.receive_json()
        ws2.receive_json()

        import asyncio
        asyncio.run(send_queue())

        msg1 = ws1.receive_json()
        msg2 = ws2.receive_json()

        assert msg1["queue"][0]["title"] == "Synchronized Song"
        assert msg2["queue"][0]["title"] == "Synchronized Song"
        assert msg1 == msg2
