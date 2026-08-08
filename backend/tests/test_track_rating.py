import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch

from backend.main import app
from backend.db.library_db import init_library_db, get_db_connection
from backend.services.library import (
    upsert_server,
    upsert_artist,
    upsert_album,
    upsert_track,
    rate_track_db,
)

client = TestClient(app)

@pytest.fixture
def setup_test_db(tmp_path):
    db_file = str(tmp_path / "test_rating.db")
    init_library_db(db_file)
    upsert_server("test-server-1", "Test Server", "http://test-server:32400", is_primary=True, enabled=True, db_path=db_file)
    artist_id = upsert_artist("Test Artist", server_id="test-server-1", server_artist_id="101", db_path=db_file)
    album_id = upsert_album("Test Album", "Test Artist", artist_id=artist_id, server_id="test-server-1", server_album_id="201", db_path=db_file)
    track_id = upsert_track(album_id, "test-server-1", "301", "Test Artist", "Test Album", "Test Track", 200, db_path=db_file)
    return db_file, track_id


def test_rate_track_db(setup_test_db):
    db_file, track_id = setup_test_db

    # Rate 4.5 stars
    rate_track_db(track_id, 4.5, db_path=db_file)

    conn = get_db_connection(db_file)
    row = conn.execute("SELECT user_rating FROM tracks WHERE track_id = ?", (track_id,)).fetchone()
    conn.close()

    assert row is not None
    assert row["user_rating"] == 4.5


def test_rate_track_api_endpoint(setup_test_db):
    db_file, track_id = setup_test_db, setup_test_db[1]

    with patch("backend.services.plex.rate_track_in_plex") as mock_plex_rate:
        mock_plex_rate.return_value = True

        response = client.post(f"/api/music/tracks/{track_id}/rate", json={"rating": 3.5})
        assert response.status_code == 200
        assert response.json()["status"] == "success"
        assert response.json()["user_rating"] == 3.5
