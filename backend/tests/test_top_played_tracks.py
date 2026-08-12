import sqlite3
import pytest
from fastapi.testclient import TestClient
from backend.main import app
from backend.services.library import get_top_played_tracks_db

client = TestClient(app)


def setup_test_db(db_path):
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE tracks (
            track_id INTEGER PRIMARY KEY,
            album_id INTEGER,
            server_id TEXT,
            server_track_id TEXT,
            artist_name TEXT,
            album_title TEXT,
            title TEXT,
            duration INTEGER,
            thumb TEXT
        );
        """
    )
    conn.execute(
        """
        CREATE TABLE playback_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            track_id INTEGER,
            artist_name TEXT,
            album_title TEXT,
            track_title TEXT,
            username TEXT,
            played_at INTEGER
        );
        """
    )

    conn.execute("INSERT INTO tracks VALUES (1, 10, 's1', 'st1', 'Artist A', 'Album A', 'Track 1', 200000, '/thumb1.jpg');")
    conn.execute("INSERT INTO tracks VALUES (2, 10, 's1', 'st2', 'Artist B', 'Album B', 'Track 2', 180000, '/thumb2.jpg');")

    # Track 1 played 3 times, Track 2 played 1 time
    conn.execute("INSERT INTO playback_history (track_id, artist_name, album_title, track_title, username, played_at) VALUES (1, 'Artist A', 'Album A', 'Track 1', 'user1', 1000);")
    conn.execute("INSERT INTO playback_history (track_id, artist_name, album_title, track_title, username, played_at) VALUES (1, 'Artist A', 'Album A', 'Track 1', 'user2', 2000);")
    conn.execute("INSERT INTO playback_history (track_id, artist_name, album_title, track_title, username, played_at) VALUES (1, 'Artist A', 'Album A', 'Track 1', 'user1', 3000);")
    conn.execute("INSERT INTO playback_history (track_id, artist_name, album_title, track_title, username, played_at) VALUES (2, 'Artist B', 'Album B', 'Track 2', 'user2', 4000);")

    conn.commit()
    conn.close()


def test_get_top_played_tracks_db(tmp_path):
    db_file = str(tmp_path / "test_library.db")
    setup_test_db(db_file)

    top_tracks = get_top_played_tracks_db(limit=10, db_path=db_file)
    assert len(top_tracks) == 2

    # Track 1 should be #1 with play_count = 3
    assert top_tracks[0]["track_id"] == 1
    assert top_tracks[0]["title"] == "Track 1"
    assert top_tracks[0]["play_count"] == 3

    # Track 2 should be #2 with play_count = 1
    assert top_tracks[1]["track_id"] == 2
    assert top_tracks[1]["title"] == "Track 2"
    assert top_tracks[1]["play_count"] == 1


def test_get_top_played_tracks_endpoint(mocker):
    mock_tracks = [
        {
            "track_id": 1,
            "title": "Track 1",
            "artist": "Artist A",
            "album": "Album A",
            "duration": 200000,
            "thumb": "/thumb1.jpg",
            "server_id": "s1",
            "play_count": 5,
        }
    ]
    mocker.patch("backend.routers.music.get_top_played_tracks_db", return_value=mock_tracks)

    response = client.get("/api/music/tracks/top-played")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["title"] == "Track 1"
    assert data[0]["play_count"] == 5
