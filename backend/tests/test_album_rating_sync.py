"""Tests for sync_album_ratings_from_plex rating sync logic."""

from unittest.mock import MagicMock, patch

import pytest

from backend.config import settings
from backend.db.library_db import init_library_db, get_db_connection
from backend.services.library import upsert_server, upsert_artist, upsert_album, upsert_track
from backend.services.plex import sync_album_ratings_from_plex


@pytest.fixture
def setup_rating_db(tmp_path):
    """Seed SQLite database with an album and two tracks."""
    db_file = str(tmp_path / "test_rating_sync.db")
    init_library_db(db_file)
    upsert_server("server-1", "Primary Server", "http://primary:32400", is_primary=True, enabled=True, db_path=db_file)
    artist_id = upsert_artist("Daft Punk", server_id="server-1", server_artist_id="100", db_path=db_file)
    album_id = upsert_album("Discovery", "Daft Punk", artist_id=artist_id, server_id="server-1", server_album_id="200", db_path=db_file)

    # Track 1: server_track_id = "301"
    t1_id = upsert_track(album_id, "server-1", "301", "Daft Punk", "Discovery", "One More Time", 320, user_rating=0.0, db_path=db_file)
    # Track 2: server_track_id = "302"
    t2_id = upsert_track(album_id, "server-1", "302", "Daft Punk", "Discovery", "Aerodynamic", 210, user_rating=0.0, db_path=db_file)

    return db_file, album_id, t1_id, t2_id


@patch("backend.services.plex.get_target_plex_connection")
def test_sync_album_ratings_updates_sqlite_ratings(mock_conn, setup_rating_db):
    """sync_album_ratings_from_plex fetches album tracks from Plex and updates user_rating in SQLite.

    Plex uses 0-10 rating scale; TuneBox converts to 0-5 star scale (userRating / 2.0).
    """
    db_file, album_id, t1_id, t2_id = setup_rating_db

    # Mock Plex Track 1: ratingKey "301", userRating 8.0 -> 4.0 stars
    trk1 = MagicMock()
    trk1.ratingKey = "301"
    trk1.userRating = 8.0

    # Mock Plex Track 2: ratingKey "302", userRating 10.0 -> 5.0 stars
    trk2 = MagicMock()
    trk2.ratingKey = "302"
    trk2.userRating = 10.0

    mock_album = MagicMock()
    mock_album.tracks.return_value = [trk1, trk2]

    mock_plex = MagicMock()
    mock_plex.fetchItem.return_value = mock_album
    mock_conn.return_value = mock_plex

    orig_testing = settings.testing
    settings.testing = False
    try:
        with patch("backend.services.plex.get_db_connection", side_effect=lambda db_path=None: get_db_connection(db_file)), \
             patch("backend.services.library.get_db_connection", side_effect=lambda db_path=None: get_db_connection(db_file)):
            result = sync_album_ratings_from_plex(album_id)

        assert result is True

        conn = get_db_connection(db_file)
        r1 = conn.execute("SELECT user_rating FROM tracks WHERE track_id = ?", (t1_id,)).fetchone()
        r2 = conn.execute("SELECT user_rating FROM tracks WHERE track_id = ?", (t2_id,)).fetchone()
        conn.close()

        assert r1["user_rating"] == 4.0
        assert r2["user_rating"] == 5.0
    finally:
        settings.testing = orig_testing


@patch("backend.services.plex.get_target_plex_connection")
def test_sync_album_ratings_skips_unindexed_tracks_safely(mock_conn, setup_rating_db):
    """Tracks returned from Plex that are not indexed in SQLite should be skipped without failing."""
    db_file, album_id, t1_id, _ = setup_rating_db

    # Track 1 is indexed ("301")
    trk1 = MagicMock()
    trk1.ratingKey = "301"
    trk1.userRating = 6.0  # 3.0 stars

    # Track 999 is NOT in SQLite database
    trk_unindexed = MagicMock()
    trk_unindexed.ratingKey = "999999"
    trk_unindexed.userRating = 10.0

    mock_album = MagicMock()
    mock_album.tracks.return_value = [trk1, trk_unindexed]

    mock_plex = MagicMock()
    mock_plex.fetchItem.return_value = mock_album
    mock_conn.return_value = mock_plex

    orig_testing = settings.testing
    settings.testing = False
    try:
        with patch("backend.services.plex.get_db_connection", side_effect=lambda db_path=None: get_db_connection(db_file)), \
             patch("backend.services.library.get_db_connection", side_effect=lambda db_path=None: get_db_connection(db_file)):
            result = sync_album_ratings_from_plex(album_id)

        assert result is True

        conn = get_db_connection(db_file)
        r1 = conn.execute("SELECT user_rating FROM tracks WHERE track_id = ?", (t1_id,)).fetchone()
        conn.close()

        assert r1["user_rating"] == 3.0
    finally:
        settings.testing = orig_testing
