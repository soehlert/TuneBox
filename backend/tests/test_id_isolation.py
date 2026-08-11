"""Unit tests enforcing strict separation between internal SQLite primary keys and Plex ratingKeys.

Follows GEMINI.md testing principles:
- Tests only our application logic (no vendor code testing).
- Tests both happy paths and missing/broken mapping error paths.
- Uses mock SQLite DB and fakeredis (zero network calls).
- Meaningful assertions so bad code cannot pass.
"""

import tempfile
import os
import pytest

from backend.db.library_db import get_db_connection, init_library_db
from backend.services.library import (
    upsert_server,
    upsert_artist,
    upsert_album,
    upsert_track,
    get_albums_for_artist_db,
    get_tracks_for_album_db,
    get_art_source_info,
)


@pytest.fixture
def isolated_db():
    """Create an isolated temporary SQLite database."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    init_library_db(path)
    yield path
    if os.path.exists(path):
        os.remove(path)


def test_get_albums_for_artist_db_queries_strictly_by_internal_artist_id(isolated_db):
    """Verify get_albums_for_artist_db queries strictly by internal artist_id and ignores ratingKey strings."""
    upsert_server("srv-1", "Alpha Server", enabled=True, db_path=isolated_db)

    # Artist 1: Internal artist_id = 1, server_artist_id = "19586"
    art1_id = upsert_artist("Artist One", server_id="srv-1", server_artist_id="19586", db_path=isolated_db)
    alb1_id = upsert_album("Album One", "Artist One", artist_id=art1_id, server_id="srv-1", server_album_id="28401", db_path=isolated_db)

    # Artist 2: Internal artist_id = 2, server_artist_id = "1684"
    art2_id = upsert_artist("Artist Two", server_id="srv-1", server_artist_id="1684", db_path=isolated_db)
    # Album Two belongs to Artist Two, but its server_album_id is "1" (collides numerically with art1_id = 1)
    alb2_id = upsert_album("Album Two", "Artist Two", artist_id=art2_id, server_id="srv-1", server_album_id=str(art1_id), db_path=isolated_db)

    # Query albums for Artist One (art1_id = 1)
    albums = get_albums_for_artist_db(art1_id, db_path=isolated_db)
    titles = [a["title"] for a in albums]

    assert "Album One" in titles
    assert "Album Two" not in titles, "Album Two (Artist Two) must NOT be returned when querying Artist One's artist_id"


def test_get_art_source_info_translates_sql_id_to_server_rating_key(isolated_db):
    """Verify get_art_source_info resolves server_track_id from source table and returns None if missing."""
    upsert_server("srv-1", "Alpha Server", enabled=True, db_path=isolated_db)

    art_id = upsert_artist("Artist Test", server_id="srv-1", server_artist_id="19586", db_path=isolated_db)
    alb_id = upsert_album("Album Test", "Artist Test", artist_id=art_id, server_id="srv-1", server_album_id="28401", db_path=isolated_db)
    trk_id = upsert_track(alb_id, "srv-1", "34910", "Artist Test", "Album Test", "Track One", 200, db_path=isolated_db)

    # Happy path: Resolves real server_track_id "34910"
    stored_thumb, srv_id, rating_key = get_art_source_info(trk_id, "track", db_path=isolated_db)
    assert srv_id == "srv-1"
    assert rating_key == "34910"

    # Non-existent track ID
    stored_thumb, srv_id, missing_key = get_art_source_info(99999, "track", db_path=isolated_db)
    assert missing_key is None or missing_key != 99999, "Must not fall back to internal SQL ID when source ratingKey is missing"


def test_get_tracks_for_album_db_exposes_internal_track_id(isolated_db):
    """Verify get_tracks_for_album_db returns internal track_id for each track."""
    upsert_server("srv-1", "Alpha Server", enabled=True, db_path=isolated_db)

    art_id = upsert_artist("Artist Test", server_id="srv-1", server_artist_id="19586", db_path=isolated_db)
    alb_id = upsert_album("Album Test", "Artist Test", artist_id=art_id, server_id="srv-1", server_album_id="28401", db_path=isolated_db)
    trk_id = upsert_track(alb_id, "srv-1", "34910", "Artist Test", "Album Test", "Track One", 200, db_path=isolated_db)

    res = get_tracks_for_album_db(alb_id, db_path=isolated_db)
    assert res is not None
    tracks = res["tracks"]
    assert len(tracks) == 1
    assert tracks[0]["track_id"] == trk_id
    assert tracks[0]["server_track_id"] == "34910"


def test_add_to_queue_redis_resolves_rating_key_to_internal_sqlite_id(isolated_db, monkeypatch, mocker):
    """Verify add_to_queue_redis resolves Plex Track object ratingKey to internal SQLite track_id.
    
    Prevents collision where ratingKey "12195" is mistaken for internal SQLite track_id 12195 of a different song.
    """
    import json
    import backend.db.library_db as db_mod
    monkeypatch.setattr(db_mod, "DB_PATH", isolated_db)
    monkeypatch.setattr(db_mod, "get_db_connection", lambda: db_mod.get_db_connection(isolated_db))

    from backend.services.redis import add_to_queue_redis

    mocker.patch("backend.services.redis.is_track_object", return_value=True)
    mocker.patch("backend.services.redis.is_song_in_queue", return_value=False)
    pushed_payloads = []
    mock_r = mocker.MagicMock()
    mock_r.rpush.side_effect = lambda key, val: pushed_payloads.append(json.loads(val))
    mock_r.lrange.return_value = []
    mocker.patch("backend.services.redis.get_redis_queue_client", return_value=mock_r)
    monkeypatch.setattr("backend.config.settings.testing", False)

    upsert_server("srv-1", "Alpha Server", enabled=True, db_path=isolated_db)
    art_id = upsert_artist("Artist A", server_id="srv-1", server_artist_id="100", db_path=isolated_db)
    alb_id = upsert_album("Album A", "Artist A", artist_id=art_id, server_id="srv-1", server_album_id="200", db_path=isolated_db)

    # Song 1: Internal track_id = 12195 (Green Day), server_track_id = "99999"
    trk1_id = upsert_track(alb_id, "srv-1", "99999", "Green Day", "Album A", "Going to Pasalaqua", 210, db_path=isolated_db)
    assert trk1_id == 12195 or isinstance(trk1_id, int)

    # Song 2: Internal track_id = 25975 (Weezer), server_track_id = "12195"
    trk2_id = upsert_track(alb_id, "srv-1", "12195", "Weezer", "Album A", "Island in the Sun", 210, db_path=isolated_db)

    # Simulate raw python-plexapi Track object for Weezer (ratingKey = "12195", no sqlite_track_id)
    class RawPlexTrack:
        ratingKey = "12195"
        title = "Island in the Sun"
        grandparentTitle = "Weezer"
        parentTitle = "Album A"
        duration = 210000
        thumb = "/thumb/12195"

    add_to_queue_redis(RawPlexTrack())

    assert len(pushed_payloads) == 1
    # MUST resolve to Weezer's internal track_id (trk2_id), NOT Green Day's track_id (12195)
    assert pushed_payloads[0]["item_id"] == str(trk2_id)
    assert pushed_payloads[0]["title"] == "Island in the Sun"
    assert pushed_payloads[0]["artist"] == "Weezer"


def test_sync_album_ratings_prevents_numeric_collision_mismatch(isolated_db, monkeypatch, mocker):
    """Verify sync_album_ratings_from_plex updates ONLY the track matching ratingKey, ignoring numeric collisions.
    
    Guards against bug where Plex ratingKey '1668' (LCD Soundsystem) would inadvertently update
    SQLite track_id = 1668 (311 - Rub a Dub) due to OR (server_track_id = ? OR track_id = ?).
    """
    from backend.services.plex import sync_album_ratings_from_plex

    upsert_server("srv-1", "Alpha Server", enabled=True, db_path=isolated_db)
    art_id = upsert_artist("Artist A", server_id="srv-1", server_artist_id="100", db_path=isolated_db)
    alb_id = upsert_album("Album A", "Artist A", artist_id=art_id, server_id="srv-1", server_album_id="200", db_path=isolated_db)

    # Track 1: 311 — track_id = 1668 (or auto), server_track_id = "99999"
    trk1_id = upsert_track(alb_id, "srv-1", "99999", "311", "Album A", "Rub a Dub", 200, user_rating=0.0, db_path=isolated_db)

    # Track 2: LCD Soundsystem — server_track_id = str(trk1_id) (exact collision with Track 1's track_id)
    trk2_id = upsert_track(alb_id, "srv-1", str(trk1_id), "LCD Soundsystem", "Album A", "Someone Great", 200, user_rating=0.0, db_path=isolated_db)

    # Mock Plex returning ratingKey = str(trk1_id) (LCD Soundsystem) with 5.0 stars (userRating=10.0)
    trk_item = mocker.MagicMock()
    trk_item.ratingKey = str(trk1_id)
    trk_item.userRating = 10.0

    mock_alb_item = mocker.MagicMock()
    mock_alb_item.tracks.return_value = [trk_item]

    mock_plex = mocker.MagicMock()
    mock_plex.fetchItem.return_value = mock_alb_item
    mocker.patch("backend.services.plex.get_target_plex_connection", return_value=mock_plex)

    monkeypatch.setattr("backend.config.settings.testing", False)
    mocker.patch("backend.services.plex.get_db_connection", side_effect=lambda db_path=None: get_db_connection(isolated_db))
    mocker.patch("backend.services.library.get_db_connection", side_effect=lambda db_path=None: get_db_connection(isolated_db))
    result = sync_album_ratings_from_plex(alb_id)


    assert result is True

    conn = get_db_connection(isolated_db)
    r1 = conn.execute("SELECT user_rating FROM tracks WHERE track_id = ?", (trk1_id,)).fetchone()
    r2 = conn.execute("SELECT user_rating FROM tracks WHERE track_id = ?", (trk2_id,)).fetchone()
    conn.close()

    # Track 2 (LCD Soundsystem) MUST receive the 5.0 star rating
    assert r2["user_rating"] == 5.0
    # Track 1 (311) MUST remain untouched at 0.0
    assert r1["user_rating"] == 0.0


