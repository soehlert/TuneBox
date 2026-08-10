import pytest
from fastapi.testclient import TestClient
from backend.main import app
from backend.services.library import get_library_health_stats

client = TestClient(app)


def test_get_library_health_stats_service(tmp_path):
    db_path = str(tmp_path / "test_library.db")
    from backend.db.library_db import init_library_db, get_db_connection
    init_library_db(db_path)

    conn = get_db_connection(db_path)
    from backend.services.library import upsert_artist, upsert_album, upsert_track
    conn.execute("INSERT INTO servers (server_id, name, enabled, is_primary) VALUES ('s1', 'Server 1', 1, 1)")
    upsert_artist(name="Artist One", server_id="s1", server_artist_id="a101", thumb="/real/thumb.jpg", db_path=db_path, conn=conn)
    upsert_artist(name="Artist Two", server_id="s1", server_artist_id="a102", thumb="", db_path=db_path, conn=conn)
    upsert_album(artist_id=1, artist_name="Artist One", title="Album One", server_id="s1", server_album_id="al201", thumb="/real/album.jpg", db_path=db_path, conn=conn)
    upsert_album(artist_id=2, artist_name="Artist Two", title="Album Two", server_id="s1", server_album_id="al202", thumb="", db_path=db_path, conn=conn)
    upsert_track(album_id=1, server_id="s1", server_track_id="t301", artist_name="Artist One", album_title="Album One", title="Track One", duration=180, db_path=db_path, conn=conn)
    conn.commit()
    conn.close()

    res = get_library_health_stats(db_path=db_path)
    assert res["total_artists"] == 2
    assert res["total_albums"] == 2
    assert res["total_tracks"] == 1
    assert res["missing_artist_art"] == 1
    assert res["missing_album_art"] == 1
    assert len(res["servers"]) == 1
    assert res["servers"][0]["server_name"] == "Server 1"
    assert res["servers"][0]["artist_count"] == 2


def test_get_library_health_stats_endpoint():
    response = client.get("/api/stats/library")
    assert response.status_code == 200
    data = response.json()
    assert "total_artists" in data
    assert "total_albums" in data
    assert "total_tracks" in data
    assert "missing_artist_art" in data
    assert "missing_album_art" in data
    assert "servers" in data
