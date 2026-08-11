import time
import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.db.library_db import get_db_connection, init_library_db
from backend.services.library import (
    upsert_artist,
    upsert_album,
    get_recently_added_albums,
)

client = TestClient(app)


@pytest.fixture
def temp_db(tmp_path):
    db_file = str(tmp_path / "test_library.db")
    init_library_db(db_file)
    conn = get_db_connection(db_file)
    conn.execute(
        "INSERT INTO servers (server_id, name, is_primary, enabled) VALUES ('srv1', 'Server One', 1, 1)"
    )
    conn.execute(
        "INSERT INTO servers (server_id, name, is_primary, enabled) VALUES ('srv2', 'Server Two', 0, 0)"
    )
    conn.commit()
    conn.close()
    return db_file


def test_get_recently_added_albums_ordering_and_filtering(temp_db):
    artist_id = upsert_artist("Spoon", db_path=temp_db)

    # Insert older album on enabled server
    alb1_id = upsert_album(
        title="Ga Ga Ga Ga Ga",
        artist_name="Spoon",
        artist_id=artist_id,
        year=2007,
        genre="Indie",
        server_id="srv1",
        server_album_id="101",
        db_path=temp_db,
    )

    # Artificially set updated_at timestamps
    conn = get_db_connection(temp_db)
    conn.execute("UPDATE albums SET updated_at = ? WHERE album_id = ?", (1000, alb1_id))
    conn.commit()
    conn.close()

    # Insert newer album on enabled server
    alb2_id = upsert_album(
        title="Lucifer on the Sofa",
        artist_name="Spoon",
        artist_id=artist_id,
        year=2022,
        genre="Indie",
        server_id="srv1",
        server_album_id="102",
        db_path=temp_db,
    )
    conn = get_db_connection(temp_db)
    conn.execute("UPDATE albums SET updated_at = ? WHERE album_id = ?", (2000, alb2_id))
    conn.commit()
    conn.close()

    # Insert album on DISABLED server (srv2)
    alb3_id = upsert_album(
        title="Disabled Server Album",
        artist_name="Spoon",
        artist_id=artist_id,
        year=2020,
        genre="Indie",
        server_id="srv2",
        server_album_id="103",
        db_path=temp_db,
    )
    conn = get_db_connection(temp_db)
    conn.execute("UPDATE albums SET updated_at = ? WHERE album_id = ?", (3000, alb3_id))
    conn.commit()
    conn.close()

    recent = get_recently_added_albums(limit=10, db_path=temp_db)

    # Should only return albums from enabled servers (srv1), ordered by updated_at DESC
    assert len(recent) == 2
    assert recent[0]["album_id"] == alb2_id
    assert recent[0]["title"] == "Lucifer on the Sofa"
    assert recent[1]["album_id"] == alb1_id
    assert recent[1]["title"] == "Ga Ga Ga Ga Ga"


def test_recently_added_api_endpoint(monkeypatch, temp_db):
    monkeypatch.setattr("backend.db.library_db.DB_PATH", temp_db)
    monkeypatch.setattr("backend.routers.music.get_recently_added_albums", lambda limit=50, db_path=None: [
        {
            "album_id": 1,
            "artist_id": 10,
            "artist": "Spoon",
            "title": "Kill the Moonlight",
            "year": 2002,
            "genre": "Indie",
            "thumb": "/thumb.jpg",
            "play_count": 5,
            "updated_at": 1700000000,
            "server_names": "Server One",
            "server_count": 1,
        }
    ])

    response = client.get("/api/music/albums/recently-added")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["title"] == "Kill the Moonlight"
    assert data[0]["artist"] == "Spoon"
