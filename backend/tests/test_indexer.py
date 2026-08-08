"""Unit tests for background indexer and diff sync."""

import os
import tempfile
import pytest
from unittest.mock import MagicMock
from backend.db.library_db import init_library_db, get_db_connection
from backend.services.indexer import sync_all_servers, index_server


@pytest.fixture
def temp_db():
    """Create temporary SQLite database for indexer testing."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    init_library_db(path)
    yield path
    if os.path.exists(path):
        os.remove(path)


def test_sync_all_servers_seeds_db_in_mock_mode(temp_db, monkeypatch):
    """Verify sync_all_servers seeds SQLite database in test/mock mode."""
    from backend.config import settings
    monkeypatch.setattr(settings, "testing", True)

    sync_all_servers(db_path=temp_db)

    conn = get_db_connection(temp_db)
    try:
        cursor = conn.execute("SELECT COUNT(*) as count FROM artists")
        artist_count = cursor.fetchone()["count"]
        assert artist_count > 0

        cursor = conn.execute("SELECT COUNT(*) as count FROM albums")
        album_count = cursor.fetchone()["count"]
        assert album_count > 0
    finally:
        conn.close()


def test_disabled_server_filtering(temp_db, monkeypatch):
    """Verify disabling a server keeps data in SQLite but hides it from queries."""
    from backend.config import settings
    from backend.services.library import set_server_enabled_status, get_indexed_artists
    monkeypatch.setattr(settings, "testing", True)

    # Seed data
    sync_all_servers(db_path=temp_db)

    # Initial check: artists returned
    artists_before = get_indexed_artists(db_path=temp_db)
    assert len(artists_before) > 0

    # Disable mock server
    set_server_enabled_status("mock-server-001", enabled=False, db_path=temp_db)

    # Verify query returns empty list while data stays stored in SQLite
    artists_disabled = get_indexed_artists(db_path=temp_db)
    assert len(artists_disabled) == 0

    # Verify raw rows remain in SQLite table
    conn = get_db_connection(temp_db)
    try:
        raw_rows = conn.execute("SELECT COUNT(*) as count FROM artists").fetchone()["count"]
        assert raw_rows > 0
    finally:
        conn.close()
