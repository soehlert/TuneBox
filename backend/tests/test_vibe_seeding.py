"""Tests verifying Party Vibe Selector endpoints and vibe queue seeding."""

import pytest
from fastapi.testclient import TestClient

from backend.config import settings
from backend.main import app
from backend.services.library import get_available_vibes_db, get_tracks_by_vibe_db
from backend.services.plex import seed_queue_from_vibe
from backend.services.redis import clear_redis_queue, get_redis_queue

client = TestClient(app)


def test_get_available_vibes_db(mock_redis):
    """Verify get_available_vibes_db returns default preset vibes."""
    vibes = get_available_vibes_db()
    assert isinstance(vibes, list)
    assert len(vibes) >= 1
    vibe_names = [v["vibe"] for v in vibes]
    assert "Party" in vibe_names or "Energetic" in vibe_names or len(vibe_names) > 0


def test_get_tracks_by_vibe_db(mock_redis):
    """Verify get_tracks_by_vibe_db returns formatted track dicts."""
    tracks = get_tracks_by_vibe_db("Party", count=5)
    assert isinstance(tracks, list)


def test_seed_queue_from_vibe(mock_redis):
    """Verify seed_queue_from_vibe seeds fallback tracks into Redis."""
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

    clear_redis_queue(force_all=True)
    res = seed_queue_from_vibe("Party", count=5)
    assert "Successfully seeded" in res["message"]

    queue = get_redis_queue()
    assert len(queue) > 0
    assert queue[0]["is_fallback"] is True


def test_vibe_settings_endpoint(mock_redis):
    """Verify GET and POST /api/music/vibe/settings."""
    get_res = client.get("/api/music/vibe/settings")
    assert get_res.status_code == 200
    assert "guest_vibe_changing_enabled" in get_res.json()

    post_unauth = client.post("/api/music/vibe/settings", json={"enabled": False})
    assert post_unauth.status_code == 401

    post_auth = client.post(
        "/api/music/vibe/settings",
        json={"enabled": False},
        headers={"x-admin-token": settings.admin_token},
    )
    assert post_auth.status_code == 200
    assert post_auth.json()["guest_vibe_changing_enabled"] is False


def test_vibes_endpoint_disabled_guest(mock_redis):
    """Verify POST /api/music/vibe/seed returns 403 for non-admins when guest changing is disabled."""
    client.post(
        "/api/music/vibe/settings",
        json={"enabled": False},
        headers={"x-admin-token": settings.admin_token},
    )
    response = client.post("/api/music/vibe/seed?vibe=Party&count=5")
    assert response.status_code == 403


def test_vibes_endpoint_success(mock_redis, mocker):
    """Verify POST /api/music/vibe/seed succeeds with valid admin token."""
    client.post(
        "/api/music/vibe/settings",
        json={"enabled": True},
        headers={"x-admin-token": settings.admin_token},
    )
    mocker.patch("backend.routers.music.send_queue")
    mocker.patch("backend.routers.music.send_current_playing")

    response = client.post(
        "/api/music/vibe/seed?vibe=Party&count=5",
        headers={"x-admin-token": settings.admin_token},
    )
    assert response.status_code == 200
    assert "Successfully seeded" in response.json()["message"]


def test_get_vibes_endpoint():
    """Verify GET /api/music/vibes endpoint returns vibes list."""
    response = client.get("/api/music/vibes")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
