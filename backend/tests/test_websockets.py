"""Test WebSocket functionality in the application."""

import asyncio
import json
import logging
from unittest.mock import patch

import pytest
from fastapi import FastAPI, WebSocket
from fastapi.testclient import TestClient
from fastapi.websockets import WebSocketDisconnect
from starlette.websockets import WebSocketState

from backend.routers.music import router

from backend.websockets import active_connections, send_current_playing, send_queue, websocket_handler

app = FastAPI()
app.include_router(router)


@pytest.fixture
def test_client():
    """Provide a test client for the application."""
    return TestClient(app)


@pytest.fixture
def mock_current_track():
    """Provide a mock current track for testing."""
    return {
        "title": "Test Song",
        "artist": "Test Artist",
        "total_time": 180000,
        "remaining_time": 120000,
        "track_state": "playing",
        "remaining_percentage": 66.67,
        "elapsed_time": 60000,
    }


@pytest.fixture
def mock_queue():
    """Provide a mock playback queue for testing."""
    return [{"id": 1, "title": "Song 1", "artist": "Artist 1"}, {"id": 2, "title": "Song 2", "artist": "Artist 2"}]


class MockWebSocket(WebSocket):
    """Simulate WebSocket interactions for testing."""

    def __init__(self):
        """Initialize a mock WebSocket instance."""

        scope = {
            "type": "websocket",
            "path": "/ws",
            "headers": [],
            "client": ("127.0.0.1", 50000),
            "server": ("127.0.0.1", 8000),
        }
        self._receive_queue = asyncio.Queue()
        self._send_queue = asyncio.Queue()
        super().__init__(scope, self._receive_queue.get, self._send_queue.put)

        self.sent_messages = []
        self.closed = False
        self._receive_count = 0
        self.client_state = WebSocketState.CONNECTED

    async def accept(self):
        """Simulate accepting a WebSocket connection."""

        self.client_state = WebSocketState.CONNECTED
        logging.debug("MockWebSocket: Connection accepted.")
        return await super().accept()

    async def send_text(self, message: str):
        """Simulate sending a message."""

        self.sent_messages.append(message)
        return await super().send_text(message)

    async def receive_text(self):
        """Simulate receiving a message."""

        self._receive_count += 1
        try:
            message = await self._receive_queue.get()
            if message == "__DISCONNECT__":
                logging.debug("MockWebSocket: Simulating disconnect")
                raise WebSocketDisconnect()
            logging.debug(f"MockWebSocket: Returning message: {message}")
            return message
        except asyncio.QueueEmpty:
            logging.debug("MockWebSocket: Queue is empty, raising WebSocketDisconnect")
            raise WebSocketDisconnect()

    async def close(self):
        """Simulate closing the WebSocket connection."""

        self.closed = True
        self.client_state = WebSocketState.DISCONNECTED
        return await super().close()


@pytest.mark.asyncio
async def test_websocket_handler_connection():
    """Test that websocket connections are properly established and stored."""
    mock_ws = MockWebSocket()

    with (
        patch("backend.services.plex.get_current_playing_track") as mock_get_track,
        patch("backend.services.plex.get_redis_queue") as mock_get_queue,
    ):
        mock_get_track.return_value = None
        mock_get_queue.return_value = []

        handler_task = asyncio.create_task(websocket_handler(mock_ws))

        await asyncio.sleep(0.1)

        await mock_ws._receive_queue.put(json.dumps({"type": "music_control"}))
        await asyncio.sleep(0.1)

        print(f"Active connections after sending message: {active_connections}")
        assert len(active_connections["music_control"]) > 0

        handler_task.cancel()
        try:
            await handler_task
        except asyncio.CancelledError:
            pass


from unittest.mock import MagicMock


@pytest.mark.asyncio
async def test_send_current_playing(mock_current_track):
    """Test sending current playing track information."""
    mock_ws = MockWebSocket()
    session_id = str(id(mock_ws))
    active_connections["music_control"][session_id] = mock_ws

    mock_player = MagicMock()
    mock_player.machineIdentifier = "mock_player_id"

    mock_session = MagicMock()
    mock_session.player.machineIdentifier = "mock_player_id"
    mock_session.title = mock_current_track["title"]
    mock_session.grandparentTitle = mock_current_track["artist"]
    mock_session.parentTitle = mock_current_track.get("album", "Test Album")
    mock_session.player.state = mock_current_track["track_state"]

    mock_plex = MagicMock()
    mock_plex.sessions.return_value = [mock_session]

    with (
        patch("backend.services.plex.get_active_player", return_value=mock_player),
        patch("backend.services.plex.get_plex_connection", return_value=mock_plex),
        patch(
            "backend.services.plex.calculate_playback_state",
            return_value={
                "total_time": mock_current_track["total_time"],
                "elapsed_time": mock_current_track["elapsed_time"],
                "remaining_time": mock_current_track["remaining_time"],
                "remaining_percentage": mock_current_track["remaining_percentage"],
            },
        ),
    ):
        await send_current_playing()

        assert len(mock_ws.sent_messages) == 1, f"Expected 1 message, found {len(mock_ws.sent_messages)}"
        sent_data = json.loads(mock_ws.sent_messages[0])

        assert sent_data["current_track"]["title"] == mock_current_track["title"]
        assert sent_data["current_track"]["artist"] == mock_current_track["artist"]


@pytest.mark.asyncio
async def test_send_queue(mock_queue, mock_redis):
    """Test sending queue updates."""
    mock_ws = MockWebSocket()
    session_id = str(id(mock_ws))
    active_connections["queue_update"][session_id] = mock_ws

    mock_redis_queue, _ = mock_redis
    mock_redis_queue.lrange.return_value = [json.dumps(item) for item in mock_queue]

    await send_queue()

    assert len(mock_ws.sent_messages) == 1
    sent_data = json.loads(mock_ws.sent_messages[0])
    assert sent_data["type"] == "queue_update"
    assert sent_data["queue"] == mock_queue


@pytest.mark.asyncio
async def test_websocket_heartbeat(caplog):
    """Test the heartbeat functionality."""
    caplog.set_level(logging.DEBUG)

    mock_ws = MockWebSocket()

    with (
        patch("backend.services.plex.get_current_playing_track") as mock_get_track,
        patch("backend.services.plex.get_redis_queue") as mock_get_queue,
    ):
        mock_get_track.return_value = None
        mock_get_queue.return_value = []

        handler_task = asyncio.create_task(websocket_handler(mock_ws))

        await mock_ws._receive_queue.put(json.dumps({"type": "music_control"}))
        await asyncio.sleep(0.1)

        await mock_ws._receive_queue.put(json.dumps({"type": "heartbeat"}))
        await asyncio.sleep(0.1)

        assert any('"message": "pong"' in message for message in mock_ws.sent_messages), (
            f"Expected 'pong' in sent messages, found: {mock_ws.sent_messages}"
        )

        handler_task.cancel()
        try:
            await handler_task
        except asyncio.CancelledError:
            pass


@pytest.mark.asyncio
async def test_websocket_disconnect(caplog):
    """Test proper cleanup on WebSocket disconnect."""
    caplog.set_level(logging.DEBUG)

    mock_ws = MockWebSocket()
    session_id = str(id(mock_ws))

    active_connections["music_control"][session_id] = mock_ws
    active_connections["queue_update"][session_id] = mock_ws

    async def simulate_disconnect():
        try:
            await websocket_handler(mock_ws)
        except WebSocketDisconnect:
            pass  # Expected disconnect

    handler_task = asyncio.create_task(simulate_disconnect())

    await mock_ws._receive_queue.put(json.dumps({"type": "music_control"}))
    await asyncio.sleep(0.1)
    await mock_ws._receive_queue.put("__DISCONNECT__")
    await asyncio.sleep(0.1)

    for connection_type in active_connections:
        assert session_id not in active_connections[connection_type], (
            f"Connection {session_id} was not removed from {connection_type}"
        )

    handler_task.cancel()
    try:
        await handler_task
    except asyncio.CancelledError:
        pass


@pytest.fixture(autouse=True)
def cleanup():
    """Clean up mock websocket connections."""
    yield
    for connection_type in active_connections:
        active_connections[connection_type].clear()
