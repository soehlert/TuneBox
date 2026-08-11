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

from backend.config import settings

client = TestClient(app)

@pytest.fixture
def setup_test_db(tmp_path):
    db_file = str(tmp_path / "test_rating.db")
    init_library_db(db_file)
    upsert_server("primary-server-1", "Primary Server", "http://primary-server:32400", is_primary=True, enabled=True, db_path=db_file)
    upsert_server("secondary-server-2", "Secondary Server", "http://secondary-server:32400", is_primary=False, enabled=True, db_path=db_file)

    artist_id = upsert_artist("Test Artist", server_id="primary-server-1", server_artist_id="101", db_path=db_file)
    album_id = upsert_album("Test Album", "Test Artist", artist_id=artist_id, server_id="primary-server-1", server_album_id="201", db_path=db_file)
    primary_track_id = upsert_track(album_id, "primary-server-1", "301", "Test Artist", "Test Album", "Primary Track", 200, db_path=db_file)

    sec_artist_id = upsert_artist("Sec Artist", server_id="secondary-server-2", server_artist_id="102", db_path=db_file)
    sec_album_id = upsert_album("Sec Album", "Sec Artist", artist_id=sec_artist_id, server_id="secondary-server-2", server_album_id="202", db_path=db_file)
    secondary_track_id = upsert_track(sec_album_id, "secondary-server-2", "302", "Sec Artist", "Sec Album", "Secondary Track", 200, db_path=db_file)

    return db_file, primary_track_id, secondary_track_id


def test_rate_track_db(setup_test_db):
    db_file, track_id, _ = setup_test_db

    # Rate 4.5 stars
    rate_track_db(track_id, 4.5, db_path=db_file)

    conn = get_db_connection(db_file)
    row = conn.execute("SELECT user_rating FROM tracks WHERE track_id = ?", (track_id,)).fetchone()
    conn.close()

    assert row is not None
    assert row["user_rating"] == 4.5


def test_rate_track_requires_admin_token(setup_test_db):
    _, primary_track_id, _ = setup_test_db
    settings.admin_token = "secret-admin-token-123"

    # Missing token -> 401
    response = client.post(f"/api/music/tracks/{primary_track_id}/rate", json={"rating": 3.5})
    assert response.status_code == 401

    # Invalid token -> 401
    response = client.post(
        f"/api/music/tracks/{primary_track_id}/rate",
        json={"rating": 3.5},
        headers={"x-admin-token": "wrong-token"},
    )
    assert response.status_code == 401


def test_rate_track_non_primary_server_forbidden(setup_test_db):
    _, _, secondary_track_id = setup_test_db
    settings.admin_token = "secret-admin-token-123"

    with patch("backend.services.library.is_track_on_primary_server") as mock_is_primary:
        mock_is_primary.return_value = False

        response = client.post(
            f"/api/music/tracks/{secondary_track_id}/rate",
            json={"rating": 3.5},
            headers={"x-admin-token": "secret-admin-token-123"},
        )
        assert response.status_code == 403
        assert "primary server" in response.json()["detail"].lower()


def test_rate_track_admin_and_primary_server_success(setup_test_db):
    _, primary_track_id, _ = setup_test_db
    settings.admin_token = "secret-admin-token-123"

    with patch("backend.services.library.is_track_on_primary_server") as mock_is_primary, \
         patch("backend.services.library.rate_track_db") as mock_rate_db, \
         patch("backend.services.plex.rate_track_in_plex") as mock_plex_rate:
        mock_is_primary.return_value = True
        mock_plex_rate.return_value = True

        response = client.post(
            f"/api/music/tracks/{primary_track_id}/rate",
            json={"rating": 4.5},
            headers={"x-admin-token": "secret-admin-token-123"},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "success"
        assert response.json()["user_rating"] == 4.5


def test_rate_track_in_plex_converts_half_stars_and_uses_rating_key(setup_test_db):
    db_file, primary_track_id, _ = setup_test_db
    mock_item = MagicMock()
    mock_plex = MagicMock()
    mock_plex.fetchItem.return_value = mock_item

    with patch("backend.services.plex.get_target_plex_connection", return_value=mock_plex), \
         patch("backend.services.library.get_art_source_info", return_value=(None, "primary-server-1", "301")):
        from backend.services.plex import rate_track_in_plex
        success = rate_track_in_plex(primary_track_id, 4.5)

        assert success is True
        mock_plex.fetchItem.assert_called_once_with(301)
        mock_item.rate.assert_called_once_with(9)


def test_upsert_track_updates_zero_user_rating(setup_test_db):
    db_file, primary_track_id, _ = setup_test_db
    conn = get_db_connection(db_file)
    try:
        # First set 4.0 stars
        upsert_track(1, "primary-server-1", "301", "Test Artist", "Test Album", "Primary Track", 200, user_rating=4.0, db_path=db_file, conn=conn)
        row = conn.execute("SELECT user_rating FROM tracks WHERE track_id = ?", (primary_track_id,)).fetchone()
        assert row["user_rating"] == 4.0

        # Now clear rating in Plex -> 0.0 stars
        upsert_track(1, "primary-server-1", "301", "Test Artist", "Test Album", "Primary Track", 200, user_rating=0.0, db_path=db_file, conn=conn)
        row = conn.execute("SELECT user_rating FROM tracks WHERE track_id = ?", (primary_track_id,)).fetchone()
        assert row["user_rating"] == 0.0
    finally:
        conn.close()
