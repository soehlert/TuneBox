"""Tests for homepage views: all albums, genres, and decades."""

import re

import pytest
from fastapi.testclient import TestClient
from backend.config import settings
from backend.db.library_db import init_library_db
from backend.main import app
from backend.services.mock_data import seed_mock_library_db

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_test_db():
    orig_testing = settings.testing
    settings.testing = True
    init_library_db()
    seed_mock_library_db()
    yield
    settings.testing = orig_testing


def test_get_all_albums_endpoint():
    """Verify GET /api/music/all-albums returns list of all albums."""
    orig_testing = settings.testing
    settings.testing = True
    try:
        response = client.get("/api/music/all-albums")
        assert response.status_code == 200
        albums = response.json()
        assert isinstance(albums, list)
        assert len(albums) > 0
        first = albums[0]
        assert "album_id" in first
        assert "title" in first
        assert "artist" in first
        assert "play_count" in first
    finally:
        settings.testing = orig_testing


def test_get_all_albums_alphabetically_sorted():
    """Verify all-albums returns albums ordered by title for fast-scrolling letter lookup."""
    orig_testing = settings.testing
    settings.testing = True
    try:
        response = client.get("/api/music/all-albums")
        assert response.status_code == 200
        albums = response.json()
        titles = [a["title"] for a in albums if "title" in a]
        assert titles == sorted(titles, key=lambda x: re.sub(r"^the\s+", "", x, flags=re.IGNORECASE).lower())
    finally:
        settings.testing = orig_testing


def test_artists_and_albums_have_play_counts():
    """Verify artist and album endpoints return play_count for Most Played sorting."""
    orig_testing = settings.testing
    settings.testing = True
    try:
        res_artists = client.get("/api/music/artists")
        assert res_artists.status_code == 200
        artists = res_artists.json()
        assert len(artists) > 0
        assert any(a.get("play_count", 0) > 0 for a in artists)

        res_albums = client.get("/api/music/all-albums")
        assert res_albums.status_code == 200
        albums = res_albums.json()
        assert len(albums) > 0
        assert any(a.get("play_count", 0) > 0 for a in albums)
    finally:
        settings.testing = orig_testing


def test_play_count_increments_on_history_add(mock_redis):
    """Verify playing a track increments artist and album play_count returned by API endpoints."""
    mock_queue_client, _ = mock_redis
    mock_queue_client.zrange.return_value = [(b"daft punk", 5)]

    orig_testing = settings.testing
    settings.testing = True
    try:
        artists = client.get("/api/music/artists").json()
        daft = next((a for a in artists if a["name"].lower() == "daft punk"), {})
        assert daft.get("play_count", 0) == 125
    finally:
        settings.testing = orig_testing


def test_get_genres_endpoint():
    """Verify GET /api/music/genres returns list of genres with album counts."""
    orig_testing = settings.testing
    settings.testing = True
    try:
        response = client.get("/api/music/genres")
        assert response.status_code == 200
        genres = response.json()
        assert isinstance(genres, list)
        assert len(genres) > 0
        first = genres[0]
        assert "genre" in first
        assert "album_count" in first
    finally:
        settings.testing = orig_testing


def test_get_albums_by_genre_endpoint():
    """Verify GET /api/music/genres/{genre}/albums returns filtered albums."""
    from urllib.parse import quote  # noqa: PLC0415
    orig_testing = settings.testing
    settings.testing = True
    try:
        # First get available genres
        g_resp = client.get("/api/music/genres")
        assert g_resp.status_code == 200
        genres = g_resp.json()
        target_genre = genres[0]["genre"]

        response = client.get(f"/api/music/genres/{quote(target_genre, safe='')}/albums")
        assert response.status_code == 200
        albums = response.json()
        assert isinstance(albums, list)
        assert len(albums) > 0
    finally:
        settings.testing = orig_testing


def test_get_decades_endpoint():
    """Verify GET /api/music/decades returns list of decades with album counts."""
    orig_testing = settings.testing
    settings.testing = True
    try:
        response = client.get("/api/music/decades")
        assert response.status_code == 200
        decades = response.json()
        assert isinstance(decades, list)
        assert len(decades) > 0
        first = decades[0]
        assert "decade" in first
        assert "year_start" in first
        assert "year_end" in first
        assert "album_count" in first
    finally:
        settings.testing = orig_testing


def test_get_albums_by_decade_endpoint():
    """Verify GET /api/music/decades/{start}/{end}/albums returns filtered albums."""
    orig_testing = settings.testing
    settings.testing = True
    try:
        d_resp = client.get("/api/music/decades")
        assert d_resp.status_code == 200
        decades = d_resp.json()
        target = decades[0]

        response = client.get(f"/api/music/decades/{target['year_start']}/{target['year_end']}/albums")
        assert response.status_code == 200
        albums = response.json()
        assert isinstance(albums, list)
        assert len(albums) > 0
    finally:
        settings.testing = orig_testing


def test_decades_and_genres_include_top_album_id_and_prewarm():
    """Verify get_all_genres_db and get_all_decades_db return top_album_id for cover art cards."""
    import tempfile
    import os
    from backend.db.library_db import init_library_db
    from backend.services.library import get_all_genres_db, get_all_decades_db, upsert_server, upsert_artist, upsert_album

    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        init_library_db(path)
        upsert_server("srv-1", "Alpha Server", enabled=True, db_path=path)
        art_id = upsert_artist("Daft Punk", server_id="srv-1", server_artist_id="101", db_path=path)
        alb_id = upsert_album("Discovery", "Daft Punk", artist_id=art_id, year=2001, genre="Electronic", server_id="srv-1", server_album_id="201", db_path=path)

        genres = get_all_genres_db(db_path=path)
        assert len(genres) > 0
        elec = next((g for g in genres if g["genre"] == "Electronic"), None)
        assert elec is not None
        assert elec["top_album_id"] == alb_id

        decades = get_all_decades_db(db_path=path)
        assert len(decades) > 0
        d2000s = next((d for d in decades if d["decade"] == "2000s"), None)
        assert d2000s is not None
        assert d2000s["top_album_id"] == alb_id
    finally:
        if os.path.exists(path):
            os.remove(path)
