"""Tests for GET /api/music/track-art/{track_id} endpoint and album art fallback handling."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from backend.config import settings
from backend.db.library_db import init_library_db, get_db_connection
from backend.main import app
from backend.services.library import upsert_server, upsert_artist, upsert_album, upsert_track

client = TestClient(app)


@pytest.fixture
def setup_art_db(tmp_path):
    """Seed a test database with an indexed track."""
    db_file = str(tmp_path / "test_art.db")
    init_library_db(db_file)
    upsert_server("server-1", "Primary Server", "http://primary:32400", is_primary=True, enabled=True, db_path=db_file)
    artist_id = upsert_artist("Artist A", server_id="server-1", server_artist_id="10", db_path=db_file)
    album_id = upsert_album("Album A", "Artist A", artist_id=artist_id, server_id="server-1", server_album_id="20", db_path=db_file)

    # Track 1: Has valid album_id
    t1_id = upsert_track(album_id, "server-1", "100", "Artist A", "Album A", "Track With Album", 200, db_path=db_file)

    # Track 2: Unindexed track_id not in SQLite DB (so t_row is None -> real_album_id is None)
    t2_id = 999999

    return db_file, t1_id, t2_id, album_id


def test_get_track_art_success(setup_art_db):
    """When track art is available, return track art bytes with HTTP 200."""
    db_file, t1_id, _, _ = setup_art_db

    fake_jpeg = b"\xff\xd8\xff\xe0" + b"X" * 200  # Valid JPEG header simulation (> 100 bytes)

    orig_testing = settings.testing
    settings.testing = False
    try:
        with patch("backend.routers.music.fetch_art_bytes", return_value=(fake_jpeg, "image/jpeg")):
            response = client.get(f"/api/music/track-art/{t1_id}")
            assert response.status_code == 200
            assert response.content == fake_jpeg
            assert response.headers["content-type"] == "image/jpeg"
    finally:
        settings.testing = orig_testing


def test_get_track_art_falls_back_to_album_art_when_track_art_missing(setup_art_db):
    """When track art is missing/fallback, fetch_art_bytes should be called for the track's album_id."""
    db_file, t1_id, _, album_id = setup_art_db

    transparent_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 50  # Fallback PNG (< 100 bytes / PNG header)
    album_jpeg = b"\xff\xd8\xff\xe0" + b"AlbumArt" * 30

    def mock_fetch_art(item_id, item_type, server_id=None):
        if item_type == "track":
            return transparent_png, "image/png"
        elif item_type == "album" and item_id == album_id:
            return album_jpeg, "image/jpeg"
        return transparent_png, "image/png"

    orig_testing = settings.testing
    settings.testing = False
    try:
        with patch("backend.routers.music.get_db_connection", side_effect=lambda db_path=None: get_db_connection(db_file)), \
             patch("backend.routers.music.fetch_art_bytes", side_effect=mock_fetch_art):
            response = client.get(f"/api/music/track-art/{t1_id}")
            assert response.status_code == 200
            assert response.content == album_jpeg
    finally:
        settings.testing = orig_testing


def test_get_track_art_handles_none_album_id_without_extra_calls(setup_art_db):
    """When track is unindexed (real_album_id is None), album art fallback is skipped without calling fetch_art_bytes for album."""
    db_file, _, t2_id, _ = setup_art_db

    transparent_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 50

    fetch_calls = []

    def mock_fetch_art(item_id, item_type, server_id=None):
        fetch_calls.append((item_id, item_type))
        return transparent_png, "image/png"

    orig_testing = settings.testing
    settings.testing = False
    try:
        with patch("backend.routers.music.get_db_connection", side_effect=lambda db_path=None: get_db_connection(db_file)), \
             patch("backend.routers.music.fetch_art_bytes", side_effect=mock_fetch_art):
            response = client.get(f"/api/music/track-art/{t2_id}")

            assert response.status_code == 200
            # fetch_art_bytes should ONLY be called for the track, NEVER with item_id=None for album
            assert len(fetch_calls) == 1
            assert fetch_calls[0] == (t2_id, "track")
    finally:
        settings.testing = orig_testing
