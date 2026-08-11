"""Regression tests for multi-server track resolution and search server_id metadata."""

import sqlite3
import pytest
from backend.db.library_db import init_library_db
from backend.services.library import (
    get_all_art_sources,
    get_art_source_info,
    search_music_db,
    upsert_album,
    upsert_artist,
    upsert_server,
    upsert_track,
)


@pytest.fixture
def temp_library_db(tmp_path):
    """Set up a temporary library database with disabled primary server and enabled secondary server."""
    db_file = str(tmp_path / "test_resolution.db")
    init_library_db(db_path=db_file)

    # Disabled primary server
    upsert_server(
        server_id="b209587d2371fba252ef0321e96bf68f9b4ba3bc",
        name="plex-so",
        server_url="http://plex-so:32400",
        is_primary=True,
        enabled=False,
        db_path=db_file,
    )

    # Enabled secondary server
    enabled_sid = "3da9127d0f6a973bb6c58b2cd1e60cfae642339e"
    upsert_server(
        server_id=enabled_sid,
        name="cc-ls-plex01",
        server_url="http://cc-ls-plex01:32400",
        is_primary=False,
        enabled=True,
        db_path=db_file,
    )

    # Upsert artist, album, track for enabled server
    a_id = upsert_artist(name="David Bowie", server_id=enabled_sid, server_artist_id="500", db_path=db_file)
    alb_id = upsert_album(
        title="Let's Dance",
        artist_name="David Bowie",
        artist_id=a_id,
        server_id=enabled_sid,
        server_album_id="9206",
        db_path=db_file,
    )
    t_id = upsert_track(
        album_id=alb_id,
        server_id=enabled_sid,
        server_track_id="9210",
        artist_name="David Bowie",
        album_title="Let's Dance",
        title="Without You",
        duration=189,
        db_path=db_file,
    )

    return db_file, enabled_sid, t_id, "9210"


def test_get_art_source_info_resolves_server_track_id(temp_library_db):
    """Verify get_art_source_info resolves source info when passed internal track_id."""
    db_file, enabled_sid, sqlite_tid, server_tid = temp_library_db

    # Test resolving by internal track_id
    _, res_sid_str, res_key_str = get_art_source_info(sqlite_tid, "track", db_path=db_file)
    assert res_sid_str == enabled_sid
    assert res_key_str == server_tid


def test_search_music_db_includes_server_id_and_server_name(temp_library_db):
    """Verify search_music_db includes server_id and server_name in track results."""
    db_file, enabled_sid, _, _ = temp_library_db

    results = search_music_db("Without You", db_path=db_file)
    tracks = [r for r in results if r.get("type") == "track"]

    assert len(tracks) > 0
    first_track = tracks[0]
    assert first_track.get("server_id") == enabled_sid
    assert first_track.get("server_name") == "cc-ls-plex01"


def test_disabled_server_filters_exclusive_catalog_items(temp_library_db):
    """Verify setting servers.enabled = 0 excludes items exclusive to that server."""
    from backend.services.library import get_indexed_artists
    db_file, enabled_sid, _, _ = temp_library_db

    # Add a disabled server with exclusive artist
    disabled_sid = "srv-disabled-999"
    upsert_server(disabled_sid, "Disabled Server", enabled=False, db_path=db_file)
    upsert_artist("Exclusive Disabled Artist", server_id=disabled_sid, server_artist_id="99901", db_path=db_file)

    artists = get_indexed_artists(db_path=db_file)
    artist_names = [a["name"] for a in artists]

    assert "David Bowie" in artist_names
    assert "Exclusive Disabled Artist" not in artist_names
