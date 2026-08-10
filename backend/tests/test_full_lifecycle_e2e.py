"""Full Lifecycle End-to-End Simulation Tests for TuneBox.

Simulates complete track lifecycles:
- Wall-clock time stepping from 0s -> duration -> end
- Queue addition while stopped (no autoplay verification)
- Natural queue advancement across multiple tracks
- Single-track queue exhaustion to clean stopped state
"""

import asyncio, pytest
from unittest.mock import AsyncMock, MagicMock
from fastapi.testclient import TestClient

from backend.config import settings
from backend.main import app
from backend.services.plex import (
    get_current_playing_track,
    playback_orchestrator,
    track_time_tracker,
)

client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_lifecycle_state(mock_redis):
    """Ensure clean test environment before and after each lifecycle test."""
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


def test_e2e_queue_addition_no_autoplay_when_stopped(mock_redis, mocker):
    """Verify adding a track to the queue while stopped NEVER triggers autoplay."""
    mock_song = MagicMock()
    mock_song.ratingKey = "7970"
    mock_song.title = "Dial Up"
    mock_song.grandparentTitle = "Childish Gambino"
    mock_song.parentTitle = "Because the Internet"
    mock_song.duration = 44000
    mock_song.thumb = "/thumb.jpg"
    mock_song.media = []

    mocker.patch("backend.routers.music.get_track", return_value=mock_song)
    mocker.patch("backend.routers.music.get_target_plex_connection", return_value=MagicMock())
    mocker.patch("backend.routers.music.fetch_accessible_plex_servers", return_value=[])
    mock_add = mocker.patch("backend.routers.music.add_to_queue_redis")
    mocker.patch("backend.routers.music.send_queue")

    response = client.post(
        "/api/music/queue/7970",
        json={"server_id": "plex-so", "server_name": "plex-so", "username": "Admin"},
    )
    assert response.status_code == 200
    mock_add.assert_called_once()

    import backend.services.plex
    assert backend.services.plex.playback_active is False
    assert track_time_tracker.state == "stopped"


@pytest.mark.asyncio
async def test_e2e_single_song_completion_and_queue_exhaustion(mock_redis, mocker):
    """Simulate a single track playing to completion and verify clean queue exhaustion."""
    import backend.services.plex
    backend.services.plex.playback_active = True

    single_track = {
        "item_id": "7970",
        "title": "Dial Up",
        "artist": "Childish Gambino",
        "album": "Because the Internet",
        "duration": 44.0,
        "server_id": "plex-so",
    }

    # 1. Start track
    track_time_tracker.start("Dial Up", item_id="7970")
    mocker.patch("backend.services.plex.get_cached_data", return_value=single_track)

    # Verify track is active at start (elapsed ~0s)
    curr = get_current_playing_track()
    assert curr is not None
    assert curr["title"] == "Dial Up"
    assert curr["elapsed_time"] == pytest.approx(0.0, abs=0.1)
    assert curr["remaining_time"] == pytest.approx(44.0, abs=0.1)

    # 2. Advance time to mid-song (22s)
    track_time_tracker.accumulated_elapsed = 22.0
    track_time_tracker.last_resume_time = None
    curr_mid = get_current_playing_track()
    assert curr_mid["elapsed_time"] == pytest.approx(22.0, abs=0.1)
    assert curr_mid["remaining_time"] == pytest.approx(22.0, abs=0.1)

    # 3. Advance time to track completion (45s >= 44s)
    track_time_tracker.accumulated_elapsed = 45.0

    call_count = [0]
    def queue_side_effect():
        call_count[0] += 1
        if call_count[0] <= 1:
            return [single_track]
        return []

    mocker.patch("backend.services.plex.get_redis_queue", side_effect=queue_side_effect)
    mocker.patch("backend.services.plex.is_autoplay_enabled", return_value=False)
    mock_history = mocker.patch("backend.services.plex.add_to_history")
    mock_remove = mocker.patch("backend.services.plex.remove_from_redis_queue")
    mock_stop_player = mocker.patch("backend.services.plex.stop_playback")

    mocker.patch("backend.websockets.send_queue", new_callable=AsyncMock)
    mocker.patch("backend.websockets.send_current_playing", new_callable=AsyncMock)
    mocker.patch("backend.websockets.reset_skip_votes", new_callable=AsyncMock)
    mocker.patch("backend.services.plex.clear_cache")

    task = asyncio.create_task(playback_orchestrator())
    await asyncio.sleep(0.4)
    task.cancel()

    # Verify queue exhaustion outcome
    assert backend.services.plex.playback_active is False
    assert track_time_tracker.state == "stopped"
    mock_remove.assert_called_once_with("7970")
    mock_history.assert_called_once()
    mock_stop_player.assert_called_once()


@pytest.mark.asyncio
async def test_e2e_multi_song_natural_queue_advancement(mock_redis, mocker):
    """Simulate track A finishing and automatically advancing to track B."""
    import backend.services.plex
    backend.services.plex.playback_active = True

    track_a = {"item_id": "1001", "title": "Track A", "artist": "Artist 1", "duration": 30.0, "server_id": "plex-so"}
    track_b = {"item_id": "1002", "title": "Track B", "artist": "Artist 2", "duration": 45.0, "server_id": "plex-so"}

    track_time_tracker.start("Track A", item_id="1001")
    track_time_tracker.accumulated_elapsed = 31.0
    track_time_tracker.last_resume_time = None

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
    mock_track_b.ratingKey = "1002"
    mock_track_b.title = "Track B"
    mock_track_b.grandparentTitle = "Artist 2"
    mock_track_b.duration = 45000
    mocker.patch("backend.services.plex.get_track", return_value=mock_track_b)
    mock_play = mocker.patch("backend.services.plex.play_song")

    mocker.patch("backend.websockets.send_queue", new_callable=AsyncMock)
    mocker.patch("backend.websockets.send_current_playing", new_callable=AsyncMock)
    mocker.patch("backend.websockets.reset_skip_votes", new_callable=AsyncMock)
    mocker.patch("backend.services.plex.clear_cache")

    task = asyncio.create_task(playback_orchestrator())
    await asyncio.sleep(0.4)
    task.cancel()

    assert backend.services.plex.playback_active is True
    mock_remove.assert_called_once_with("1001")
    mock_history.assert_called_once()
    mock_play.assert_called_once_with(mock_player, mock_track_b)
