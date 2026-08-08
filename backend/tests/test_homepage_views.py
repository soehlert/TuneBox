"""Tests for homepage views: all albums, genres, and decades."""

from fastapi.testclient import TestClient
from backend.config import settings
from backend.main import app

client = TestClient(app)


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
        assert titles == sorted(titles, key=lambda x: x.lower())
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
    orig_testing = settings.testing
    settings.testing = True
    try:
        # First get available genres
        g_resp = client.get("/api/music/genres")
        assert g_resp.status_code == 200
        genres = g_resp.json()
        target_genre = genres[0]["genre"]

        response = client.get(f"/api/music/genres/{target_genre}/albums")
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
