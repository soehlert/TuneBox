"""Tests for play_song now_playing Redis state recording and track validation."""

from unittest.mock import MagicMock, patch

import pytest

from backend.config import settings
from backend.db.library_db import init_library_db, get_db_connection
from backend.services.library import upsert_server, upsert_artist, upsert_album, upsert_track
from backend.services.plex import play_song


@pytest.fixture
def setup_now_playing_db(tmp_path):
    """Seed SQLite database with an album and track."""
    db_file = str(tmp_path / "test_now_playing.db")
    init_library_db(db_file)
    upsert_server("server-1", "Primary Server", "http://primary:32400", is_primary=True, enabled=True, db_path=db_file)
    artist_id = upsert_artist("Nirvana", server_id="server-1", server_artist_id="10", db_path=db_file)
    album_id = upsert_album("Nevermind", "Nirvana", artist_id=artist_id, server_id="server-1", server_album_id="20", db_path=db_file)
    track_id = upsert_track(album_id, "server-1", "300", "Nirvana", "Nevermind", "Smells Like Teen Spirit", 301, db_path=db_file)
    return db_file, album_id, track_id


@patch("backend.services.plex.cache_data")
@patch("backend.services.plex.get_plex_connection")
def test_play_song_stores_now_playing_with_verified_track_id(mock_get_conn, mock_cache_data, setup_now_playing_db):
    """play_song must verify sqlite_track_id in DB, resolve album_id, and store now_playing in Redis."""
    db_file, album_id, track_id = setup_now_playing_db

    mock_player = MagicMock()
    mock_player.title = "Living Room Speaker"

    mock_song = MagicMock()
    mock_song.title = "Smells Like Teen Spirit"
    mock_song.grandparentTitle = "Nirvana"
    mock_song.parentTitle = "Nevermind"
    mock_song.duration = 301000  # ms
    mock_song.sqlite_track_id = track_id
    mock_song.ratingKey = "300"
    mock_song.media = []

    mock_server = MagicMock()
    mock_get_conn.return_value = mock_server

    orig_testing = settings.testing
    settings.testing = False
    try:
        with patch("backend.services.plex.get_db_connection", side_effect=lambda db_path=None: get_db_connection(db_file)), \
             patch("backend.services.library.get_db_connection", side_effect=lambda db_path=None: get_db_connection(db_file)):
            play_song(mock_player, mock_song)

        mock_cache_data.assert_called_once()
        cache_key, song_data = mock_cache_data.call_args[0]

        assert cache_key == "now_playing"
        assert song_data["item_id"] == str(track_id)
        assert song_data["album_id"] == str(album_id)
        assert song_data["title"] == "Smells Like Teen Spirit"
        assert song_data["album_art"] == f"/api/music/track-art/{track_id}"
        assert song_data["track_state"] == "playing"
    finally:
        settings.testing = orig_testing


@patch("backend.services.plex.cache_data")
@patch("backend.services.plex.get_plex_connection")
def test_play_song_logs_warning_when_sqlite_track_id_unverified(mock_get_conn, mock_cache_data, setup_now_playing_db, caplog):
    """When song has an unindexed or invalid sqlite_track_id, play_song must log a warning."""
    db_file, _, _ = setup_now_playing_db

    mock_player = MagicMock()
    mock_player.title = "Living Room Speaker"

    mock_song = MagicMock()
    mock_song.title = "Unindexed Track"
    mock_song.grandparentTitle = "Unknown"
    mock_song.parentTitle = "Unknown"
    mock_song.duration = 180000
    mock_song.sqlite_track_id = 999999  # Not in SQLite
    mock_song.ratingKey = "777"
    mock_song.media = []

    mock_server = MagicMock()
    mock_get_conn.return_value = mock_server

    orig_testing = settings.testing
    settings.testing = False
    try:
        with patch("backend.services.plex.get_db_connection", side_effect=lambda db_path=None: get_db_connection(db_file)), \
             patch("backend.services.library.get_db_connection", side_effect=lambda db_path=None: get_db_connection(db_file)):
            play_song(mock_player, mock_song)

        assert "has no valid sqlite_track_id" in caplog.text
    finally:
        settings.testing = orig_testing
