"""Tests for get_track strict ID resolution behavior."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from backend.config import settings
from backend.db.library_db import init_library_db, get_db_connection
from backend.services.library import upsert_server, upsert_artist, upsert_album, upsert_track
from backend.services.plex import get_track


@pytest.fixture(autouse=True)
def non_testing_mode():
    """Run get_track tests with settings.testing=False to exercise the real resolution path."""
    original = settings.testing
    settings.testing = False
    yield
    settings.testing = original


@pytest.fixture
def setup_test_db(tmp_path):
    """Seed a real isolated SQLite database with a known track and server mapping."""
    db_file = str(tmp_path / "test_get_track.db")
    init_library_db(db_file)
    upsert_server("server-abc", "Primary Server", "http://primary:32400", is_primary=True, enabled=True, db_path=db_file)
    artist_id = upsert_artist("Green Day", server_id="server-abc", server_artist_id="100", db_path=db_file)
    album_id = upsert_album("Dookie", "Green Day", artist_id=artist_id, server_id="server-abc", server_album_id="200", db_path=db_file)
    # Track in SQLite: SQLite track_id = 42 (or auto-assigned), Plex server_track_id ratingKey = "87654"
    track_id = upsert_track(album_id, "server-abc", "87654", "Green Day", "Dookie", "Basket Case", 180, db_path=db_file)
    return db_file, track_id, "87654"


@patch("backend.services.plex.get_target_plex_connection")
def test_get_track_resolves_via_rating_key_and_calls_fetch_item(mock_conn, setup_test_db):
    """Valid internal track_id in SQLite must resolve to its Plex ratingKey and call fetchItem with that int.

    Uses a real SQLite database so the full query pipeline is executed.
    """
    db_file, track_id, expected_rating_key = setup_test_db

    mock_track = MagicMock()
    mock_track.title = "Basket Case"
    mock_plex = MagicMock()
    mock_plex.fetchItem.return_value = mock_track
    mock_conn.return_value = mock_plex

    # Route SQLite connections in library service to our test database
    with patch("backend.services.library.get_db_connection", side_effect=lambda db_path=None: get_db_connection(db_file)):
        result = get_track(track_id)

    # Must call fetchItem with integer Plex ratingKey (87654), NOT the internal track_id
    mock_plex.fetchItem.assert_called_once_with(int(expected_rating_key))
    # sqlite_track_id must be stamped onto the returned track object for queue/frontend
    assert getattr(result, "sqlite_track_id", None) == track_id


@patch("backend.services.plex.get_target_plex_connection")
def test_get_track_raises_404_when_track_not_in_library(mock_conn, setup_test_db):
    """track_id not in SQLite database must raise HTTP 404 without making any Plex calls."""
    db_file, _, _ = setup_test_db

    mock_plex = MagicMock()
    mock_conn.return_value = mock_plex

    with patch("backend.services.library.get_db_connection", side_effect=lambda db_path=None: get_db_connection(db_file)):
        with pytest.raises(HTTPException) as exc_info:
            get_track(99999)  # 99999 does not exist in SQLite DB

    assert exc_info.value.status_code == 404
    # Plex must NEVER be contacted when the track is not indexed in SQLite
    mock_plex.fetchItem.assert_not_called()
