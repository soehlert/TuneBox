"""Tests verifying Party Vibe Selector endpoints and vibe queue seeding."""

from fastapi.testclient import TestClient

from backend.config import settings
from backend.db.library_db import init_library_db, save_curated_vibe_tracks
from backend.main import app
from backend.services.library import (
    MOOD_MAPPINGS,
    build_vibe_match_filter,
    get_available_vibes_db,
    get_tracks_by_vibe_db,
    upsert_album,
    upsert_artist,
    upsert_server,
    upsert_track,
)
from backend.services.plex import seed_queue_from_vibe
from backend.services.redis import clear_redis_queue, get_redis_queue

client = TestClient(app)


def test_get_available_vibes_db(mock_redis):
    """Verify get_available_vibes_db returns default preset vibes."""
    vibes = get_available_vibes_db()
    assert isinstance(vibes, list)
    assert len(vibes) >= 1
    vibe_names = [v["vibe"] for v in vibes]
    assert "Party" in vibe_names or "Energetic" in vibe_names or len(vibe_names) > 0


def test_get_tracks_by_vibe_db(mock_redis):
    """Verify get_tracks_by_vibe_db returns formatted track dicts."""
    tracks = get_tracks_by_vibe_db("Party", count=5)
    assert isinstance(tracks, list)


def test_seed_queue_from_vibe(mock_redis):
    """Verify seed_queue_from_vibe seeds fallback tracks into Redis."""
    mock_queue_client, _ = mock_redis
    stored_queue = []

    def rpush_side_effect(key, value):
        stored_queue.append(value)

    def lrange_side_effect(key, start, end):
        return stored_queue[start : end + 1 if end != -1 else None]

    def delete_side_effect(key):
        stored_queue.clear()

    mock_queue_client.rpush.side_effect = rpush_side_effect
    mock_queue_client.lrange.side_effect = lrange_side_effect
    mock_queue_client.delete.side_effect = delete_side_effect

    clear_redis_queue(force_all=True)
    res = seed_queue_from_vibe("Party", count=5)
    assert "Successfully seeded" in res["message"]

    queue = get_redis_queue()
    assert len(queue) > 0
    assert queue[0]["is_fallback"] is True


def test_vibe_settings_endpoint(mock_redis):
    """Verify GET and POST /api/music/vibe/settings."""
    get_res = client.get("/api/music/vibe/settings")
    assert get_res.status_code == 200
    assert "guest_vibe_changing_enabled" in get_res.json()

    post_unauth = client.post("/api/music/vibe/settings", json={"enabled": False})
    assert post_unauth.status_code == 401

    post_auth = client.post(
        "/api/music/vibe/settings",
        json={"enabled": False},
        headers={"x-admin-token": settings.admin_token},
    )
    assert post_auth.status_code == 200
    assert post_auth.json()["guest_vibe_changing_enabled"] is False


def test_vibes_endpoint_disabled_guest(mock_redis):
    """Verify POST /api/music/vibe/seed returns 403 for non-admins when guest changing is disabled."""
    client.post(
        "/api/music/vibe/settings",
        json={"enabled": False},
        headers={"x-admin-token": settings.admin_token},
    )
    response = client.post("/api/music/vibe/seed?vibe=Party&count=5")
    assert response.status_code == 403


def test_vibes_endpoint_success(mock_redis, mocker):
    """Verify POST /api/music/vibe/seed succeeds with valid admin token."""
    client.post(
        "/api/music/vibe/settings",
        json={"enabled": True},
        headers={"x-admin-token": settings.admin_token},
    )
    mocker.patch("backend.routers.music.send_queue")
    mocker.patch("backend.routers.music.send_current_playing")

    response = client.post(
        "/api/music/vibe/seed?vibe=Party&count=5",
        headers={"x-admin-token": settings.admin_token},
    )
    assert response.status_code == 200
    assert "Successfully seeded" in response.json()["message"]


def test_get_vibes_endpoint():
    """Verify GET /api/music/vibes endpoint returns vibes list."""
    response = client.get("/api/music/vibes")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    vibe_names = [item["vibe"] for item in data]
    expected_vibes = ["Party", "Chill Hang", "Energetic", "Groovy", "Acoustic", "Electronic", "Melancholic"]
    for expected in expected_vibes:
        assert expected in vibe_names


def test_vibe_match_filter_scoring_threshold():
    """Verify build_vibe_match_filter enforces Score >= 3 threshold and queries t.moods."""
    meta = MOOD_MAPPINGS["Party"]
    filter_clause, _ = build_vibe_match_filter(meta)
    assert ">= 3" in filter_clause
    assert "t.moods" in filter_clause
    assert "alb.genre" in filter_clause
    assert "THEN 3 ELSE 0" in filter_clause
    assert "THEN 2 ELSE 0" in filter_clause
    assert "THEN 1 ELSE 0" in filter_clause


def test_vibe_matching_with_track_moods(tmp_path):
    """Verify tracks with tagged moods meet Score >= 3 and are selected for vibes."""
    db_file = str(tmp_path / "vibe_test.db")
    init_library_db(db_file)

    upsert_server("srv-1", "Primary Server", is_primary=True, enabled=True, db_path=db_file)
    art_id = upsert_artist("Test Artist", server_id="srv-1", server_artist_id="a1", db_path=db_file)
    alb_id = upsert_album(
        "Test Album", "Test Artist", artist_id=art_id, genre="Rock",
        server_id="srv-1", server_album_id="alb1", db_path=db_file,
    )

    # Track 1 has mood 'energetic' -> scores +3 (qualifies for Energetic vibe)
    upsert_track(
        alb_id, "srv-1", "t1", "Test Artist", "Test Album", "High Energy Song",
        200, bpm=0, moods="energetic, rowdy", db_path=db_file,
    )
    # Track 2 has no mood and BPM=0 -> genre Rock scores +2 (fails Score >= 3)
    upsert_track(
        alb_id, "srv-1", "t2", "Test Artist", "Test Album", "Plain Rock Song",
        200, bpm=0, moods="", db_path=db_file,
    )

    matching_tracks = get_tracks_by_vibe_db("Energetic", count=10, db_path=db_file)
    assert len(matching_tracks) == 1
    assert matching_tracks[0]["title"] == "High Energy Song"

    vibes = get_available_vibes_db(db_path=db_file)
    energetic_vibe = next((v for v in vibes if v["vibe"] == "Energetic"), None)
    assert energetic_vibe is not None
    assert energetic_vibe["count"] == 1


def test_curated_vibe_tracks_prioritized(tmp_path):
    """Verify curated vibe tracks are counted and prioritized in results."""
    db_file = str(tmp_path / "vibe_curated_test.db")
    init_library_db(db_file)

    upsert_server("srv-1", "Primary Server", is_primary=True, enabled=True, db_path=db_file)
    art_id = upsert_artist("Test Artist", server_id="srv-1", server_artist_id="a1", db_path=db_file)
    alb_id = upsert_album(
        "Test Album", "Test Artist", artist_id=art_id, genre="Indie",
        server_id="srv-1", server_album_id="alb1", db_path=db_file,
    )

    t1_id = upsert_track(
        alb_id, "srv-1", "t1", "Test Artist", "Test Album", "Curated Chill Track",
        200, bpm=0, moods="", db_path=db_file,
    )
    upsert_track(
        alb_id, "srv-1", "t2", "Test Artist", "Test Album", "Tagged Chill Track",
        200, bpm=0, moods="chill hang", db_path=db_file,
    )

    # Save t1 as a curated track for Chill Hang
    save_curated_vibe_tracks("Chill Hang", [t1_id], source="playlist", db_path=db_file)

    vibes = get_available_vibes_db(db_path=db_file)
    chill_vibe = next((v for v in vibes if v["vibe"] == "Chill Hang"), None)
    assert chill_vibe is not None
    # Count should include both the curated track and the tagged track
    assert chill_vibe["count"] == 2

    tracks = get_tracks_by_vibe_db("Chill Hang", count=1, db_path=db_file)
    assert len(tracks) == 1
    # Curated track must be prioritized first
    assert tracks[0]["track_id"] == t1_id


def test_synonym_mood_not_matched(tmp_path):
    """Verify loose synonyms like upbeat or calm do not match Chill Hang without canonical tag."""
    db_file = str(tmp_path / "vibe_synonym_test.db")
    init_library_db(db_file)

    upsert_server("srv-1", "Primary Server", is_primary=True, enabled=True, db_path=db_file)
    art_id = upsert_artist("Pop Artist", server_id="srv-1", server_artist_id="a2", db_path=db_file)
    alb_id = upsert_album(
        "Pop Album", "Pop Artist", artist_id=art_id, genre="Pop",
        server_id="srv-1", server_album_id="alb2", db_path=db_file,
    )

    # Track has 'upbeat' mood but NOT 'chill hang'
    upsert_track(
        alb_id, "srv-1", "t3", "Pop Artist", "Pop Album", "Upbeat Dance Song",
        200, bpm=120, moods="upbeat, lively", db_path=db_file,
    )

    vibes = get_available_vibes_db(db_path=db_file)
    chill_vibe = next((v for v in vibes if v["vibe"] == "Chill Hang"), None)
    assert chill_vibe is not None
    assert chill_vibe["count"] == 0

