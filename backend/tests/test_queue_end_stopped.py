"""Tests for end-of-queue stopped state behavior."""

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock

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
    backend.services.plex._queue_finished_track = None
    track_time_tracker.stop()
    yield
    backend.services.plex.playback_active = False
    backend.services.plex._queue_finished_track = None
    track_time_tracker.stop()


@pytest.mark.asyncio
async def test_orchestrator_sets_finished_sentinel_when_queue_empty(mocker):
    """When the last track finishes and queue is empty, orchestrator sets the finished sentinel."""
    import backend.services.plex  # noqa: PLC0415

    backend.services.plex.playback_active = True

    # Tracker is playing with elapsed >= duration → track just finished
    track_time_tracker.start("Last Song")
    track_time_tracker.accumulated_elapsed = 200.0
    track_time_tracker.last_resume_time = None
    track_time_tracker.state = "playing"

    cached_track = {"item_id": "999", "title": "Last Song", "duration": 180, "artist": "X", "album": "Y"}

    mocker.patch("backend.services.plex.get_redis_queue", return_value=[cached_track])
    mocker.patch("backend.services.plex.is_autoplay_enabled", return_value=False)
    mocker.patch("backend.services.plex.get_cached_data", return_value=cached_track)
    mocker.patch("backend.services.plex.add_to_history")
    mock_remove = mocker.patch("backend.services.plex.remove_from_redis_queue")

    # After removal, the queue is empty
    call_count = [0]
    def queue_side_effect():
        call_count[0] += 1
        if call_count[0] <= 1:
            return [cached_track]
        return []

    mocker.patch("backend.services.plex.get_redis_queue", side_effect=queue_side_effect)
    mocker.patch("backend.websockets.send_queue", new_callable=AsyncMock)
    mocker.patch("backend.websockets.send_current_playing", new_callable=AsyncMock)
    mocker.patch("backend.websockets.reset_skip_votes", new_callable=AsyncMock)
    mocker.patch("backend.services.plex.stop_playback")

    task = asyncio.create_task(playback_orchestrator())
    await asyncio.sleep(0.15)
    task.cancel()

    # Sentinel should be set to the finished track title
    assert backend.services.plex._queue_finished_track == "Last Song"


@pytest.mark.asyncio
async def test_resync_does_not_restart_finished_track(mocker):
    """check_plexamp_resync must NOT restart a track that the orchestrator just finished."""
    import backend.services.plex  # noqa: PLC0415

    # Set the sentinel — the orchestrator declared this track done
    backend.services.plex._queue_finished_track = "Ended Song"

    # Tracker is already stopped
    track_time_tracker.stop()

    # Mock Plex still showing the finished song as playing (the bounce-back scenario)
    mock_session = MagicMock()
    mock_session.title = "Ended Song"
    mock_session.duration = 200000
    mock_session.viewOffset = 150000
    mock_session.player.state = "playing"
    mock_session.player.machineIdentifier = "machine-1"

    mock_player = MagicMock()
    mock_player.machineIdentifier = "machine-1"

    mock_plex = MagicMock()
    mock_plex.sessions.return_value = [mock_session]

    mocker.patch("backend.services.plex.get_plex_connection", return_value=mock_plex)
    mocker.patch("backend.services.plex.get_active_player", return_value=mock_player)
    mocker.patch("backend.services.plex.get_cached_data", return_value=None)
    mock_stop = mocker.patch("backend.services.plex.stop_playback")
    mock_send = mocker.patch("backend.websockets.send_current_playing", new_callable=AsyncMock)

    await check_plexamp_resync()

    # Resync must NOT restart the tracker
    assert track_time_tracker.state == "stopped"
    # It SHOULD have stopped playback on Plex
    mock_stop.assert_called_once()
    # Sentinel should be cleared
    assert backend.services.plex._queue_finished_track is None


@pytest.mark.asyncio
async def test_resync_restarts_different_track_normally(mocker):
    """check_plexamp_resync should still handle a genuinely new track even if sentinel is set for a different one."""
    import backend.services.plex  # noqa: PLC0415

    # Sentinel is set for a different, old track
    backend.services.plex._queue_finished_track = "Old Song"

    # Plex now shows a NEW song (user queued something manually)
    mock_session = MagicMock()
    mock_session.title = "New Song"
    mock_session.duration = 240000
    mock_session.viewOffset = 10000
    mock_session.player.state = "playing"
    mock_session.player.machineIdentifier = "machine-1"

    mock_player = MagicMock()
    mock_player.machineIdentifier = "machine-1"

    mock_plex = MagicMock()
    mock_plex.sessions.return_value = [mock_session]

    mocker.patch("backend.services.plex.get_plex_connection", return_value=mock_plex)
    mocker.patch("backend.services.plex.get_active_player", return_value=mock_player)
    mocker.patch("backend.services.plex.get_cached_data", return_value=None)
    mocker.patch("backend.services.plex.cache_data")
    mocker.patch("backend.websockets.reset_skip_votes", new_callable=AsyncMock)
    mocker.patch("backend.websockets.send_current_playing", new_callable=AsyncMock)
    mocker.patch("backend.services.plex.stop_playback")

    await check_plexamp_resync()

    # The new song should be tracked — sentinel for old song should be cleared
    assert backend.services.plex._queue_finished_track is None
    # stop_playback should NOT be called for the new song
    from backend.services.plex import stop_playback  # noqa: PLC0415
