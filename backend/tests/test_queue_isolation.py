"""Tests verifying strict queue isolation and complete queue clearing without unexpected track seeding."""

import pytest
from fastapi.testclient import TestClient

from backend.config import settings
from backend.main import app
from backend.services.redis import (
    add_to_queue_redis,
    clear_redis_queue,
    get_redis_queue,
)
from backend.services.plex import generate_autoplay_tracks

client = TestClient(app)


def test_clear_queue_endpoint_clears_upcoming_and_preserves_active(mocker):
    """Verify POST /api/music/clear-queue clears upcoming tracks while preserving active index 0 without stopping playback."""
    mocker.patch("backend.services.redis.get_redis_queue_client")
    mock_stop = mocker.patch("backend.routers.music.stop_playback")
    mock_clear = mocker.patch("backend.routers.music.clear_redis_queue", return_value={"message": "The queue has been cleared."})
    mocker.patch("backend.websockets.reset_skip_votes")
    mocker.patch("backend.routers.music.send_queue")
    mocker.patch("backend.routers.music.send_current_playing")

    response = client.post("/api/music/clear-queue")
    assert response.status_code == 200
    assert response.json() == {"message": "The queue has been cleared."}

    mock_stop.assert_not_called()
    mock_clear.assert_called_once_with(force_all=False)


def test_stop_queue_endpoint_stops_playback_and_clears_full_queue(mocker):
    """Verify POST /api/music/stop-queue stops playback and completely empties the entire queue."""
    mocker.patch("backend.services.redis.get_redis_queue_client")
    mock_stop = mocker.patch("backend.routers.music.stop_playback")
    mock_clear = mocker.patch("backend.routers.music.clear_redis_queue", return_value={"message": "The queue has been cleared."})
    mock_clear_cache = mocker.patch("backend.routers.music.clear_cache")
    mocker.patch("backend.websockets.reset_skip_votes")
    mocker.patch("backend.routers.music.send_queue")
    mocker.patch("backend.routers.music.send_current_playing")

    response = client.post("/api/music/stop-queue", headers={"x-admin-token": settings.admin_token})
    assert response.status_code == 200

    mock_stop.assert_called_once()
    mock_clear.assert_called_once_with(force_all=True)
    mock_clear_cache.assert_called_once_with("now_playing")


def test_only_user_added_songs_exist_in_queue(mock_redis, mock_plex_track):
    """Verify that ONLY explicitly added songs exist in the queue and no unrequested fallback tracks appear."""
    mock_queue_client, _ = mock_redis
    stored_queue = []

    def rpush_side_effect(key, value):
        stored_queue.append(value)

    def lrange_side_effect(key, start, end):
        return stored_queue[start : end + 1 if end != -1 else None]

    def delete_side_effect(key):
        stored_queue.clear()

    mock_queue_client.rpush.side_effect = rpush_side_effect
    mock_queue_client.lrange.side_effect = lrange_side_effect
    mock_queue_client.delete.side_effect = delete_side_effect

    # Initial state: queue is completely empty
    clear_redis_queue(force_all=True)
    assert get_redis_queue() == []

    mock_plex_track.ratingKey = "9210"
    mock_plex_track.title = "Without You"
    mock_plex_track.grandparentTitle = "David Bowie"

    add_to_queue_redis(mock_plex_track, server_id="3da9127d0f6a973bb6c58b2cd1e60cfae642339e", server_name="cc-ls-plex01")

    # Queue must contain EXACTLY the 1 track added by the user
    current_queue = get_redis_queue()
    assert len(current_queue) == 1
    assert current_queue[0]["title"] == "Without You"
    assert current_queue[0]["artist"] == "David Bowie"
    assert current_queue[0]["server_id"] == "3da9127d0f6a973bb6c58b2cd1e60cfae642339e"
    assert current_queue[0]["server_name"] == "cc-ls-plex01"

    # Clearing queue with force_all=True empties the queue completely to 0 tracks
    clear_redis_queue(force_all=True)
    assert get_redis_queue() == []


def test_autoplay_does_not_seed_when_disabled(mocker):
    """Verify generate_autoplay_tracks exits immediately when autoplay is disabled in settings."""
    mocker.patch("backend.services.plex.is_autoplay_enabled", return_value=False)
    mock_add = mocker.patch("backend.services.redis.add_to_queue_redis")

    orig_testing = settings.testing
    settings.testing = False
    try:
        generate_autoplay_tracks()
        mock_add.assert_not_called()
    finally:
        settings.testing = orig_testing
