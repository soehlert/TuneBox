from unittest.mock import MagicMock
from fastapi.testclient import TestClient
from backend.config import settings
from backend.main import app
from backend.services.plex import fetch_tracks_for_album

client = TestClient(app)


def test_fetch_tracks_for_album_includes_track_numbers(mocker):
    """Verify that fetch_tracks_for_album includes track_number for each track."""
    orig_testing = settings.testing
    settings.testing = True
    try:
        res = fetch_tracks_for_album(2001)
        assert "tracks" in res
        assert len(res["tracks"]) > 0
        for idx, track in enumerate(res["tracks"], start=1):
            assert "track_number" in track
            assert track["track_number"] == idx
    finally:
        settings.testing = orig_testing


def test_add_album_to_queue_endpoint(mocker, mock_redis):
    """Verify POST /api/music/albums/{album_id}/add-to-queue adds all album tracks to the queue."""
    orig_testing = settings.testing
    settings.testing = True
    try:
        mocker.patch("backend.routers.music.send_queue")
        mocker.patch("backend.routers.music.send_current_playing")
        mocker.patch("backend.services.stats.increment_adds")
        mock_add_to_queue = mocker.patch("backend.routers.music.add_to_queue_redis", return_value={"message": "Track added"})

        response = client.post(
            "/api/music/albums/2001/add-to-queue",
            headers={"x-client-id": "test_client_1"}
        )
        assert response.status_code == 200, response.json()
        data = response.json()
        assert data["message"] == "Album added to queue successfully."
        assert data["added_count"] > 0

        assert mock_add_to_queue.call_count == data["added_count"]
    finally:
        settings.testing = orig_testing
