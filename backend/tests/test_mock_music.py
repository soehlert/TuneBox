"""Integration tests for TuneBox mock music library simulation."""

import pytest
from fastapi.testclient import TestClient

from backend.config import settings
from backend.main import app


@pytest.fixture
def client():
    """Create a test client for the FastAPI app."""
    return TestClient(app)


@pytest.fixture(autouse=True)
def enable_testing_mode():
    """Automatically enable settings.testing for mock music tests."""
    prev_testing = settings.testing
    settings.testing = True
    yield
    settings.testing = prev_testing


def test_get_mock_artists(client):
    """Test retrieving mock artists list in test mode."""
    response = client.get("/api/music/artists")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 10
    assert data[0]["name"] == "Daft Punk"
    assert data[9]["name"] == "David Bowie"


def test_get_mock_albums_for_artist(client):
    """Test retrieving mock albums list for a specific artist in test mode."""
    response = client.get("/api/music/artists/1001/albums")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 6
    assert data[0]["title"] == "Homework"
    assert data[1]["title"] == "Discovery"


def test_get_mock_tracks_for_album(client):
    """Test retrieving mock tracks list for a specific album in test mode."""
    response = client.get("/api/music/albums/2002/tracks")
    assert response.status_code == 200
    data = response.json()
    assert data["album_title"] == "Discovery"
    assert len(data["tracks"]) == 15
    assert data["tracks"][0]["title"] == "Discovery - Track 1"
    assert data["tracks"][0]["duration"] == 180


def test_search_mock_music(client):
    """Test searching mock artists/albums/tracks in test mode."""
    response = client.get("/api/music/search?query=Discover")
    assert response.status_code == 200
    data = response.json()
    assert len(data) > 0
    # Should include Discovery album and Discovery tracks
    album_matches = [item for item in data if item["type"] == "album"]
    track_matches = [item for item in data if item["type"] == "track"]
    assert len(album_matches) == 1
    assert album_matches[0]["title"] == "Discovery"
    assert len(track_matches) == 15


def test_get_mock_album_art(client):
    """Test retrieving mock album art PNG stream in test mode."""
    response = client.get("/api/music/album-art/123")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/jpeg"
    # Check PNG signature in body
    assert response.content.startswith(b"\x89PNG")


def test_get_accessible_servers(client):
    """Test retrieving accessible Plex servers in test mode."""
    response = client.get("/api/music/servers")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    assert "server_id" in data[0]
    assert "name" in data[0]


def test_delete_queue_item_auth(client, mock_redis):
    """Test that deleting a queue item requires valid admin authentication."""
    # Attempt deleting without token header -> 401
    res_no_token = client.delete("/api/music/queue/3001")
    assert res_no_token.status_code == 401
    assert "Unauthorized" in res_no_token.json()["detail"]

    # Attempt deleting with invalid token header -> 401
    res_bad_token = client.delete(
        "/api/music/queue/3001", headers={"X-Admin-Token": "wrong-token"}
    )
    assert res_bad_token.status_code == 401

    # Attempt deleting with valid token header
    orig_token = settings.admin_token
    settings.admin_token = "valid_test_token"
    try:
        res_good_token = client.delete(
            "/api/music/queue/3001", headers={"X-Admin-Token": "valid_test_token"}
        )
        assert res_good_token.status_code == 200
        assert res_good_token.json() == {"message": "Song not found in the queue."}
    finally:
        settings.admin_token = orig_token


