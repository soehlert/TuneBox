"""Unit tests for background indexer and diff sync."""

import os
import tempfile
import pytest
from backend.config import settings
from backend.db.library_db import init_library_db, get_db_connection
from backend.services.indexer import (
    sync_all_servers,
    resolve_album_genre_from_tracks,
)
from backend.services.library import set_server_enabled_status, get_indexed_artists


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


def test_resolve_album_genre_from_tracks():
    """Verify track genres roll up to albums preferring subgenres over primary genres."""
    # Prefers consensus subgenre (Indie Rock) even when primary genre (Rock) appears on all tracks
    assert (
        resolve_album_genre_from_tracks(
            "Uncategorized",
            ["Rock", "Indie Rock", "Rock", "Indie Rock", "Rock", "Dream Pop"],
            tagged_track_count=3,
        )
        == "Indie Rock"
    )
    # Upgrades existing broad album genre (Rock or Pop/Rock) to consensus subgenre
    assert (
        resolve_album_genre_from_tracks(
            "Rock",
            ["Rock", "Indie Rock", "Rock", "Indie Rock"],
            tagged_track_count=2,
        )
        == "Indie Rock"
    )
    assert (
        resolve_album_genre_from_tracks(
            "Pop/Rock",
            ["Punk", "Skate Punk", "Punk", "Skate Punk"],
            tagged_track_count=2,
        )
        == "Skate Punk"
    )
    # Falls back to consensus primary genre (Rock) when subgenres are split (< 50% each)
    assert (
        resolve_album_genre_from_tracks(
            "Uncategorized",
            ["Rock", "Indie Rock", "Rock", "Garage Rock", "Rock", "Post-Punk"],
            tagged_track_count=3,
        )
        == "Rock"
    )
    # Falls back to Pop/Rock when no track genre reaches 50% of tagged tracks
    assert (
        resolve_album_genre_from_tracks(
            "Uncategorized",
            ["Electronic", "Hip-Hop", "Pop", "Jazz"],
            tagged_track_count=4,
        )
        == "Pop/Rock"
    )
    # Never downgrades an existing specific genre to Pop/Rock and skips no-op updates
    assert (
        resolve_album_genre_from_tracks(
            "Jazz",
            ["Electronic", "Hip-Hop", "Pop", "Jazz"],
            tagged_track_count=4,
        )
        is None
    )
    assert (
        resolve_album_genre_from_tracks(
            "Indie Rock",
            ["Rock", "Indie Rock", "Rock", "Indie Rock"],
            tagged_track_count=2,
        )
        is None
    )
    # Returns None when tracks have no usable genres
    assert resolve_album_genre_from_tracks("Uncategorized", ["Uncategorized", ""], tagged_track_count=0) is None
