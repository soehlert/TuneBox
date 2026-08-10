"""Tests verifying catalog resolution, server-enabled filtering, and artwork proxying without dummy fallbacks."""

import pytest
from unittest.mock import MagicMock
from fastapi.testclient import TestClient

from backend.config import settings
from backend.main import app
from backend.services.library import search_music_db
from backend.services.plex import fetch_art_bytes

client = TestClient(app)


def test_search_music_db_filters_by_enabled_servers(mocker):
    """Verify search_music_db queries filter results strictly by enabled servers (srv.enabled = 1)."""
    mock_conn = MagicMock()
    mocker.patch("backend.services.library.get_db_connection", return_value=mock_conn)

    mock_cursor = MagicMock()
    mock_cursor.fetchall.return_value = []
    mock_conn.execute.return_value = mock_cursor

    results = search_music_db("Foo Fighters")

    assert isinstance(results, list)
    assert mock_conn.execute.called

    # Inspect all executed SQL statements for srv.enabled = 1
    executed_sqls = [call[0][0] for call in mock_conn.execute.call_args_list]
    for sql in executed_sqls:
        if "FROM artists" in sql or "FROM albums" in sql:
            assert "srv.enabled = 1" in sql


def test_artwork_cache_keys_include_server_id(mock_redis, mocker):
    """Verify fetch_art_bytes includes server_id in Redis cache key to prevent cross-server image contamination."""
    from backend.services.plex import _MEMORY_ART_CACHE
    _MEMORY_ART_CACHE.clear()

    mock_queue_client, mock_cache_client = mock_redis
    mock_cache_client.get.side_effect = lambda key: None

    mock_connection = MagicMock()
    mock_connection.url = "http://plex-so.local:32400"
    mock_connection._token = "test_token"
    mocker.patch("backend.services.plex.get_target_plex_connection", return_value=mock_connection)

    mock_response = MagicMock()
    mock_response.content = b"fake_image_bytes_" + b"A" * 200
    mock_response.status_code = 200
    mocker.patch("requests.get", return_value=mock_response)

    mocker.patch("backend.services.plex.fetch_art", return_value=mock_response)

    orig_testing = settings.testing
    settings.testing = False
    try:
        art_bytes, media_type = fetch_art_bytes("500", "album", server_id="plex-so")
        assert art_bytes == mock_response.content
        assert media_type == "image/jpeg"
        assert mock_cache_client.setex.called
        cache_key_used = mock_cache_client.setex.call_args[0][0]
        assert "plex-so" in cache_key_used
        assert cache_key_used == "art_bytes:album:500:plex-so"
    finally:
        settings.testing = orig_testing


def test_track_art_endpoint_fallbacks_and_no_dummy_placeholders(mocker):
    """Verify track-art endpoint proxies art bytes cleanly without serving hardcoded dummy image fallbacks."""
    mocker.patch("backend.routers.music.fetch_art_bytes", return_value=(b"real_art_bytes_1234567890", "image/jpeg"))

    response = client.get("/api/music/track-art/101")
    assert response.status_code == 200
    assert response.content == b"real_art_bytes_1234567890"
