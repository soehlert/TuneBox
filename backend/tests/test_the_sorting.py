"""Unit tests verifying that artist and album sorting ignores leading 'The '."""

import tempfile
import os
import pytest
from backend.db.library_db import get_db_connection, init_library_db
from backend.services.library import (
    upsert_server,
    upsert_artist,
    upsert_album,
    get_indexed_artists,
    get_indexed_albums,
)


@pytest.fixture
def test_db():
    """Create a temporary SQLite database for isolated test execution."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    init_library_db(path)
    upsert_server("srv-1", "Main Server", enabled=True, db_path=path)
    yield path
    if os.path.exists(path):
        os.remove(path)


def test_get_indexed_artists_ignores_the_prefix(test_db):
    """Verify 'The Beatles' sorts under 'B' between 'Beach Boys' and 'Blink-182'."""
    upsert_artist("The Beatles", server_id="srv-1", server_artist_id="1", db_path=test_db)
    upsert_artist("Aerosmith", server_id="srv-1", server_artist_id="2", db_path=test_db)
    upsert_artist("Blink-182", server_id="srv-1", server_artist_id="3", db_path=test_db)
    upsert_artist("Beach Boys", server_id="srv-1", server_artist_id="4", db_path=test_db)

    artists = get_indexed_artists(sort_mode="name_asc", db_path=test_db)
    names = [a["name"] for a in artists]

    assert names == ["Aerosmith", "Beach Boys", "The Beatles", "Blink-182"]


def test_get_indexed_albums_ignores_the_prefix(test_db):
    """Verify 'The Dark Side of the Moon' sorts under 'D' between 'Abbey Road' and 'Eldorado'."""
    art_id = upsert_artist("Pink Floyd", server_id="srv-1", server_artist_id="10", db_path=test_db)
    upsert_album("The Dark Side of the Moon", "Pink Floyd", artist_id=art_id, server_id="srv-1", server_album_id="101", db_path=test_db)
    upsert_album("Abbey Road", "The Beatles", artist_id=art_id, server_id="srv-1", server_album_id="102", db_path=test_db)
    upsert_album("Eldorado", "Electric Light Orchestra", artist_id=art_id, server_id="srv-1", server_album_id="103", db_path=test_db)

    albums = get_indexed_albums(sort_mode="name_asc", db_path=test_db)
    titles = [a["title"] for a in albums]

    assert titles == ["Abbey Road", "The Dark Side of the Moon", "Eldorado"]


def test_get_indexed_artists_and_albums_plays_sorting(test_db):
    """Verify get_indexed_artists and get_indexed_albums respect plays_desc (Most Played) vs plays_asc (Least Played)."""
    art1_id = upsert_artist("Artist High Plays", play_count=100, server_id="srv-1", server_artist_id="101", db_path=test_db)
    art2_id = upsert_artist("Artist Low Plays", play_count=5, server_id="srv-1", server_artist_id="102", db_path=test_db)

    upsert_album("Album High Plays", "Artist High Plays", artist_id=art1_id, play_count=100, server_id="srv-1", server_album_id="201", db_path=test_db)
    upsert_album("Album Low Plays", "Artist Low Plays", artist_id=art2_id, play_count=5, server_id="srv-1", server_album_id="202", db_path=test_db)

    # Most Played (desc)
    artists_desc = get_indexed_artists(sort_mode="plays_desc", db_path=test_db)
    assert artists_desc[0]["name"] == "Artist High Plays"
    assert artists_desc[1]["name"] == "Artist Low Plays"

    albums_desc = get_indexed_albums(sort_mode="plays_desc", db_path=test_db)
    assert albums_desc[0]["title"] == "Album High Plays"
    assert albums_desc[1]["title"] == "Album Low Plays"

    # Least Played (asc)
    artists_asc = get_indexed_artists(sort_mode="plays_asc", db_path=test_db)
    assert artists_asc[0]["name"] == "Artist Low Plays"
    assert artists_asc[1]["name"] == "Artist High Plays"

    albums_asc = get_indexed_albums(sort_mode="plays_asc", db_path=test_db)
    assert albums_asc[0]["title"] == "Album Low Plays"
    assert albums_asc[1]["title"] == "Album High Plays"
