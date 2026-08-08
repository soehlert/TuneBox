"""Unit tests for library_db.py SQLite schema initialization and WAL mode."""

import os
import tempfile
import pytest
from backend.db.library_db import get_db_connection, init_library_db


@pytest.fixture
def temp_db():
    """Create a temporary SQLite database file for isolated testing."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    init_library_db(path)
    yield path
    if os.path.exists(path):
        os.remove(path)


def test_init_library_db_creates_tables_and_indexes(temp_db):
    """Verify library database initialization creates all expected tables and indexes."""
    conn = get_db_connection(temp_db)
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = {row["name"] for row in cursor.fetchall()}
        
        expected_tables = {"servers", "artists", "artist_sources", "albums", "album_sources", "tracks"}
        assert expected_tables.issubset(tables)

        cursor.execute("PRAGMA journal_mode;")
        mode = cursor.fetchone()[0]
        assert mode.lower() == "wal"
    finally:
        conn.close()


def test_servers_crud_operations(temp_db):
    """Verify inserting and querying servers in SQLite."""
    conn = get_db_connection(temp_db)
    try:
        conn.execute(
            "INSERT INTO servers (server_id, name, server_url, is_primary, enabled) VALUES (?, ?, ?, ?, ?)",
            ("srv-1", "Alpha Server", "http://alpha:32400", 1, 1),
        )
        conn.commit()

        cursor = conn.execute("SELECT * FROM servers WHERE server_id = ?", ("srv-1",))
        row = cursor.fetchone()
        assert row is not None
        assert row["name"] == "Alpha Server"
        assert row["enabled"] == 1
    finally:
        conn.close()


def test_clean_library_deduplication(temp_db):
    """Verify clean_library_deduplication consolidates stale space-containing norm keys into single artist/album rows."""
    from backend.services.library import clean_library_deduplication, upsert_server, get_indexed_artists
    conn = get_db_connection(temp_db)
    try:
        upsert_server("srv-1", "Alpha Server", enabled=True, db_path=temp_db)
        
        # Insert duplicate artists manually with old vs new norm_name
        conn.execute("INSERT INTO artists (norm_name, name, updated_at) VALUES ('aaron neville', 'Aaron Neville', 100)")
        id1 = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.execute("INSERT INTO artist_sources (artist_id, server_id, server_artist_id) VALUES (?, 'srv-1', '101')", (id1,))
        
        conn.execute("INSERT INTO artists (norm_name, name, updated_at) VALUES ('aaronneville', 'Aaron Neville', 200)")
        id2 = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.execute("INSERT INTO artist_sources (artist_id, server_id, server_artist_id) VALUES (?, 'srv-1', '102')", (id2,))
        conn.commit()

        # Run deduplication cleanup
        res = clean_library_deduplication(db_path=temp_db)
        assert res["removed_artists"] == 1

        artists = get_indexed_artists(db_path=temp_db)
        assert len(artists) == 1
        assert artists[0]["name"] == "Aaron Neville"
    finally:
        conn.close()
