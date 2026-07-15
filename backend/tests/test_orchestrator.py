"""Tests for the playback orchestrator and Plexamp resync loops."""

import asyncio
import time
from unittest.mock import MagicMock

import pytest

from backend.services.plex import (
    check_plexamp_resync,
    playback_orchestrator,
    track_time_tracker,
)


@pytest.fixture(autouse=True)
def clean_state():
    """Ensure variables are in a clean state before and after each test."""
    import backend.services.plex  # noqa: PLC0415

    backend.services.plex.playback_active = False
    track_time_tracker.stop()
    yield
    backend.services.plex.playback_active = False
    track_time_tracker.stop()


@pytest.mark.asyncio
async def test_orchestrator_starts_song(mocker):
    """Verify that when playback is active and the tracker is idle, a track from the queue starts playing."""
    import backend.services.plex  # noqa: PLC0415

    backend.services.plex.playback_active = True

    mock_queue = [
        {
            "item_id": "123",
            "title": "Queue Song",
            "artist": "Queue Artist",
            "duration": 180,
        }
    ]
    mocker.patch("backend.services.plex.get_redis_queue", return_value=mock_queue)

    mock_player = MagicMock()
    mocker.patch("backend.services.plex.get_active_player", return_value=mock_player)

    mock_track = MagicMock()
    mock_track.ratingKey = "123"
    mock_track.title = "Queue Song"
    mock_track.grandparentTitle = "Queue Artist"
    mock_track.duration = 180000  # in ms
    mocker.patch("backend.services.plex.get_track", return_value=mock_track)

    mock_play_song = mocker.patch("backend.services.plex.play_song")
    mocker.patch("backend.websockets.send_queue")
    mocker.patch("backend.websockets.send_current_playing")

    # Run one tick of orchestrator by canceling it after a brief sleep
    task = asyncio.create_task(playback_orchestrator())
    await asyncio.sleep(0.1)
    task.cancel()

    mock_play_song.assert_called_once_with(mock_player, mock_track)


@pytest.mark.asyncio
async def test_resync_detects_drift(mocker):
    """Test that check_plexamp_resync detects drift and aligns the local tracker."""
    track_time_tracker.start("Sync Song")
    track_time_tracker.accumulated_elapsed = 5.0
    track_time_tracker.last_resume_time = time.time()  # Active state calculation

    # Mock Plex Session showing elapsed time as 10s (5s drift)
    mock_session = MagicMock()
    mock_session.title = "Sync Song"
    mock_session.duration = 180000
    mock_session.viewOffset = 10000  # 10s in ms
    mock_session.player.state = "playing"
    mock_session.player.machineIdentifier = "mock_machine"

    mock_player = MagicMock()
    mock_player.machineIdentifier = "mock_machine"

    mock_plex = MagicMock()
    mock_plex.sessions.return_value = [mock_session]

    mocker.patch("backend.services.plex.get_plex_connection", return_value=mock_plex)
    mocker.patch("backend.services.plex.get_active_player", return_value=mock_player)
    mocker.patch(
        "backend.services.plex.get_cached_data",
        return_value={"title": "Sync Song", "duration": 180},
    )
    mocker.patch("backend.services.plex.cache_data")
    mocker.patch("backend.websockets.send_current_playing")

    await check_plexamp_resync()

    expected_elapsed = 10.0
    # The accumulated elapsed time should be adjusted to 10s (Plex's offset)
    assert pytest.approx(track_time_tracker.accumulated_elapsed) == expected_elapsed
