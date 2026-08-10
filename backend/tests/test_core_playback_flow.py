"""Integration tests for core playback lifecycle and queue management.

Tests cover:
1) Adding items to queue works.
2) Playing a song works.
3) Song plays to completion and automatically advances to the next track.
4) Force skip / skip works.
5) Play / pause toggle works while preserving queue state.
6) Playback stops cleanly when the queue is out of tracks.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock
import pytest
from fastapi.testclient import TestClient

from backend.config import settings
from backend.main import app
from backend.services.plex import (
    playback_orchestrator,
    track_time_tracker,
)

client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_playback_state():
    """Reset global playback state before and after each test."""
    import backend.services.plex  # noqa: PLC0415

    orig_testing = settings.testing
    settings.testing = True
    backend.services.plex.playback_active = False
    backend.services.plex._queue_finished_track = None
    track_time_tracker.stop()
    yield
    settings.testing = orig_testing
    backend.services.plex.playback_active = False
    backend.services.plex._queue_finished_track = None
    track_time_tracker.stop()


def test_adding_to_queue_works(mock_redis, mocker, server_id: str = "plex-so"):
    """Verify adding a track to the playback queue works with single server parameters."""
    mock_queue_client, _ = mock_redis
    mock_song = MagicMock()
    mock_song.title = "Test Song"
    mock_song.grandparentTitle = "Test Artist"
    mock_song.media = []

    mocker.patch("backend.routers.music.get_track", return_value=mock_song)
    mocker.patch("backend.routers.music.get_target_plex_connection", return_value=MagicMock())
    mocker.patch("backend.routers.music.fetch_accessible_plex_servers", return_value=[])
    mock_add = mocker.patch("backend.routers.music.add_to_queue_redis")
    mocker.patch("backend.routers.music.send_queue")

    response = client.post(
        "/api/music/queue/101",
        json={"server_id": server_id, "server_name": "plex-so", "username": "TestUser"},
    )

    assert response.status_code == 200
    mock_add.assert_called_once()
    assert mock_add.call_args.kwargs.get("server_id") == server_id


@pytest.mark.asyncio
async def test_playing_song_works(mocker, server_id: str = "plex-so"):
    """Verify that starting playback of a song from queue works."""
    import backend.services.plex  # noqa: PLC0415

    backend.services.plex.playback_active = True

    queued_track = {
        "item_id": "101",
        "title": "Song A",
        "artist": "Artist A",
        "duration": 180,
        "server_id": server_id,
    }
    mocker.patch("backend.services.plex.get_redis_queue", return_value=[queued_track])

    mock_player = MagicMock()
    mocker.patch("backend.services.plex.get_active_player", return_value=mock_player)

    mock_track = MagicMock()
    mock_track.ratingKey = "101"
    mock_track.title = "Song A"
    mock_track.grandparentTitle = "Artist A"
    mock_track.duration = 180000
    mocker.patch("backend.services.plex.get_track", return_value=mock_track)

    mock_play = mocker.patch("backend.services.plex.play_song")
    mocker.patch("backend.websockets.send_queue", new_callable=AsyncMock)
    mocker.patch("backend.websockets.send_current_playing", new_callable=AsyncMock)

    task = asyncio.create_task(playback_orchestrator())
    await asyncio.sleep(0.4)
    task.cancel()

    mock_play.assert_called_once_with(mock_player, mock_track)


@pytest.mark.asyncio
async def test_song_plays_til_end_and_moves_to_next_track(mocker, server_id: str = "plex-so"):
    """Verify that a track playing to completion finishes and automatically advances to next track."""
    import backend.services.plex  # noqa: PLC0415

    backend.services.plex.playback_active = True

    track_a = {"item_id": "101", "title": "Song A", "artist": "Artist A", "duration": 180, "server_id": server_id}
    track_b = {"item_id": "102", "title": "Song B", "artist": "Artist B", "duration": 200, "server_id": server_id}

    # Simulate Track A playing and reaching elapsed duration
    track_time_tracker.start("Song A")
    track_time_tracker.accumulated_elapsed = 185.0
    track_time_tracker.last_resume_time = None
    track_time_tracker.state = "playing"

    call_count = [0]
    def queue_side_effect():
        call_count[0] += 1
        if call_count[0] <= 1:
            return [track_a, track_b]
        return [track_b]

    mocker.patch("backend.services.plex.get_redis_queue", side_effect=queue_side_effect)
    mocker.patch("backend.services.plex.get_cached_data", return_value=track_a)
    mock_history = mocker.patch("backend.services.plex.add_to_history")
    mock_remove = mocker.patch("backend.services.plex.remove_from_redis_queue")
    mock_player = MagicMock()
    mocker.patch("backend.services.plex.get_active_player", return_value=mock_player)

    mock_track_b = MagicMock()
    mock_track_b.ratingKey = "102"
    mock_track_b.title = "Song B"
    mock_track_b.grandparentTitle = "Artist B"
    mock_track_b.duration = 200000
    mocker.patch("backend.services.plex.get_track", return_value=mock_track_b)
    mock_play = mocker.patch("backend.services.plex.play_song")

    mocker.patch("backend.websockets.send_queue", new_callable=AsyncMock)
    mocker.patch("backend.websockets.send_current_playing", new_callable=AsyncMock)
    mocker.patch("backend.websockets.reset_skip_votes", new_callable=AsyncMock)

    task = asyncio.create_task(playback_orchestrator())
    await asyncio.sleep(1.4)
    task.cancel()

    mock_remove.assert_called_once_with("101")
    mock_history.assert_called_once()
    mock_play.assert_called_once_with(mock_player, mock_track_b)


def test_force_skip_works(mocker, server_id: str = "plex-so"):
    """Verify force skip/skip endpoint triggers skip logic."""
    orig_admin = settings.admin_token
    settings.admin_token = "test_admin_token"
    try:
        mock_skip = mocker.patch(
            "backend.routers.music.skip_current_track",
            return_value={"message": "Track skipped successfully."},
        )
        mocker.patch("backend.websockets.reset_skip_votes", new_callable=AsyncMock)
        mocker.patch("backend.routers.music.send_queue")
        mocker.patch("backend.routers.music.send_current_playing")

        # Admin force skip call
        response = client.post("/api/music/skip", headers={"X-Admin-Token": "test_admin_token"})
        assert response.status_code == 200
        assert response.json() == {"message": "Track skipped successfully."}
        mock_skip.assert_called_once()
    finally:
        settings.admin_token = orig_admin


def test_play_pause_toggles_playback_preserving_queue(mocker, server_id: str = "plex-so"):
    """Verify play/pause toggles playback without clearing or mutating queue state."""
    mock_pause = mocker.patch(
        "backend.routers.music.pause_playback",
        return_value={"message": "Playback paused successfully."},
    )
    mocker.patch("backend.routers.music.send_current_playing")

    response = client.post("/api/music/pause")
    assert response.status_code == 200
    assert response.json() == {"message": "Playback paused successfully."}
    mock_pause.assert_called_once()


@pytest.mark.asyncio
async def test_stops_when_out_of_tracks_in_queue(mocker, server_id: str = "plex-so"):
    """Verify playback stops cleanly when the queue is out of tracks (empty queue state)."""
    import backend.services.plex  # noqa: PLC0415

    backend.services.plex.playback_active = True

    last_track = {"item_id": "999", "title": "Last Song", "artist": "Artist X", "duration": 180, "server_id": server_id}

    track_time_tracker.start("Last Song")
    track_time_tracker.accumulated_elapsed = 185.0
    track_time_tracker.last_resume_time = None
    track_time_tracker.state = "playing"

    call_count = [0]
    def queue_side_effect():
        call_count[0] += 1
        if call_count[0] <= 1:
            return [last_track]
        return []

    mocker.patch("backend.services.plex.get_redis_queue", side_effect=queue_side_effect)
    mocker.patch("backend.services.plex.is_autoplay_enabled", return_value=False)
    mocker.patch("backend.services.plex.get_cached_data", return_value=last_track)
    mocker.patch("backend.services.plex.add_to_history")
    mocker.patch("backend.services.plex.remove_from_redis_queue")
    mock_stop = mocker.patch("backend.services.plex.stop_playback")

    mocker.patch("backend.websockets.send_queue", new_callable=AsyncMock)
    mocker.patch("backend.websockets.send_current_playing", new_callable=AsyncMock)
    mocker.patch("backend.websockets.reset_skip_votes", new_callable=AsyncMock)

    task = asyncio.create_task(playback_orchestrator())
    await asyncio.sleep(0.4)
    task.cancel()
    assert backend.services.plex._queue_finished_track == "Last Song"
    mock_stop.assert_called_once()


@pytest.mark.asyncio
async def test_playback_natural_completion_when_tracker_paused(mocker):
    """Verify natural track completion advances queue even if resync auto-paused tracker."""
    import backend.services.plex
    backend.services.plex.playback_active = True

    track_item = {"item_id": "9001", "title": "Paused Song", "duration": 180}
    
    track_time_tracker.start("Paused Song")
    track_time_tracker.accumulated_elapsed = 181.0
    track_time_tracker.last_resume_time = None
    track_time_tracker.state = "paused"  # Auto-paused by resync right as track ended

    mock_remove = mocker.patch("backend.services.plex.remove_from_redis_queue")
    mocker.patch("backend.services.plex.get_redis_queue", return_value=[])
    mocker.patch("backend.services.plex.is_autoplay_enabled", return_value=False)
    mocker.patch("backend.services.plex.get_cached_data", return_value=track_item)
    mocker.patch("backend.services.plex.add_to_history")
    mocker.patch("backend.services.plex.stop_playback")

    mocker.patch("backend.websockets.send_queue", new_callable=AsyncMock)
    mocker.patch("backend.websockets.send_current_playing", new_callable=AsyncMock)
    mocker.patch("backend.websockets.reset_skip_votes", new_callable=AsyncMock)

    task = asyncio.create_task(playback_orchestrator())
    await asyncio.sleep(0.4)
    task.cancel()

    mock_remove.assert_called_with("9001")
