import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from backend.main import app
from backend.services.redis import set_closing_time_mode, get_closing_time_mode
from backend.services.library import find_closing_time_track_db

client = TestClient(app)


class MockRedisStore:
    def __init__(self):
        self.store = {}

    def get(self, key):
        return self.store.get(key)

    def set(self, key, value):
        self.store[key] = value

    def delete(self, key):
        self.store.pop(key, None)


@pytest.fixture(autouse=True)
def setup_mock_redis(mocker):
    fake = MockRedisStore()
    mocker.patch("backend.services.redis.get_redis_queue_client", return_value=fake)
    mocker.patch("backend.services.redis_client.get_redis_queue_client", return_value=fake)
    return fake


def test_closing_time_mode_redis_state():
    """Test getting and setting closing time mode in Redis cache."""
    set_closing_time_mode(True)
    assert get_closing_time_mode() is True

    set_closing_time_mode(False)
    assert get_closing_time_mode() is False


def test_find_closing_time_track_db(tmp_path):
    """Test searching SQLite library for a track matching 'Closing Time'."""
    db_file = str(tmp_path / "test_library.db")

    import sqlite3
    conn = sqlite3.connect(db_file)
    conn.execute("CREATE TABLE servers (server_id TEXT PRIMARY KEY, is_primary INTEGER);")
    conn.execute("INSERT INTO servers VALUES ('s1', 1);")
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
    conn.execute("INSERT INTO tracks VALUES (1, 100, 's1', 'st1', 'Semisonic', 'Feeling Strangely Fine', 'Closing Time', 230000, '/thumb.jpg');")
    conn.commit()
    conn.close()

    track = find_closing_time_track_db(db_path=db_file)
    assert track is not None
    assert track["title"] == "Closing Time"
    assert track["artist"] == "Semisonic"


def test_guest_queue_addition_blocked_during_closing_time():
    """Test that guests receive 403 when adding tracks during Closing Time mode."""
    set_closing_time_mode(True)

    try:
        response = client.post("/api/music/queue/123")
        assert response.status_code == 403
        data = response.json()
        assert "Last Call" in data["detail"] or "closing" in data["detail"].lower()
    finally:
        set_closing_time_mode(False)


def test_admin_trigger_closing_time_endpoint():
    """Test POST /api/music/closing-time endpoint as admin."""
    admin_headers = {"X-Admin-Token": "test-admin-secret"}

    with patch("backend.config.settings.admin_token", "test-admin-secret"), \
         patch("backend.routers.music.trigger_closing_time_mode") as mock_trigger:

        mock_trigger.return_value = {
            "success": True,
            "message": "🍸 Last Call activated! 'Closing Time' added to queue.",
            "closing_time": True,
        }

        response = client.post("/api/music/closing-time", headers=admin_headers)
        assert response.status_code == 200
        assert response.json()["closing_time"] is True
        mock_trigger.assert_called_once()


def test_admin_cancel_closing_time_endpoint():
    """Test DELETE /api/music/closing-time endpoint to cancel Last Call."""
    admin_headers = {"X-Admin-Token": "test-admin-secret"}

    with patch("backend.config.settings.admin_token", "test-admin-secret"), \
         patch("backend.routers.music.cancel_closing_time_mode") as mock_cancel:

        mock_cancel.return_value = {
            "success": True,
            "message": "🎉 Last Call cancelled! Party mode resumed.",
            "closing_time": False,
        }

        response = client.delete("/api/music/closing-time", headers=admin_headers)
        assert response.status_code == 200
        assert response.json()["closing_time"] is False
        mock_cancel.assert_called_once()


def test_purge_non_human_tracks_from_queue_redis(mocker):
    """Test purging autoplay/seeded tracks while retaining human-requested tracks."""
    import json
    from backend.services.redis import purge_non_human_tracks_from_queue_redis

    item_0 = json.dumps({"title": "Currently Playing", "added_by": "TuneBox Autoplay", "is_fallback": True})
    item_1 = json.dumps({"title": "Human Guest Song", "added_by": "Sam", "is_fallback": False})
    item_2 = json.dumps({"title": "Smart Seed Song", "added_by": "Vibe Seed", "is_fallback": True})
    item_3 = json.dumps({"title": "Human Admin Song", "added_by": "Admin", "is_fallback": False})

    class FakeListClient:
        def __init__(self):
            self.items = [item_0, item_1, item_2, item_3]

        def lrange(self, name, start, end):
            return self.items

        def delete(self, name):
            self.items = []

        def rpush(self, name, *values):
            self.items.extend(values)

    fake_client = FakeListClient()
    mocker.patch("backend.services.redis.get_redis_queue_client", return_value=fake_client)

    purge_non_human_tracks_from_queue_redis()

    remaining = [json.loads(i) for i in fake_client.items]
    assert len(remaining) == 3
    assert remaining[0]["title"] == "Currently Playing"
    assert remaining[1]["title"] == "Human Guest Song"
    assert remaining[2]["title"] == "Human Admin Song"


def test_trigger_closing_time_mode_adds_track(mocker):
    """Test that trigger_closing_time_mode purges non-human tracks and appends Closing Time finale song."""
    from backend.services.plex import trigger_closing_time_mode

    mock_closing_track = {
        "title": "Closing Time",
        "artist": "Semisonic",
        "album": "Feeling Strangely Fine",
        "duration": 230000,
        "ratingKey": "9999",
        "track_id": 9999,
        "album_id": 8888,
        "server_id": "s1",
        "thumb": "/thumb.jpg",
    }

    mock_add = mocker.patch("backend.services.plex.add_to_queue_redis")
    mocker.patch("backend.services.plex.find_closing_time_track_db", return_value=mock_closing_track)
    mocker.patch("backend.services.redis.purge_non_human_tracks_from_queue_redis")
    mocker.patch("backend.websockets.broadcast_queue_threadsafe")
    mocker.patch("backend.websockets.broadcast_json_threadsafe")

    res = trigger_closing_time_mode()
    assert res["success"] is True
    assert "Closing Time" in res["finale_track"]
    mock_add.assert_called_once()


def test_cancel_closing_time_mode_unqueues_track(mocker):
    """Test that cancelling Last Call mode unqueues the pending Closing Time track."""
    import json
    from backend.services.plex import cancel_closing_time_mode

    item_0 = json.dumps({"title": "Currently Playing", "added_by": "Sam", "is_fallback": False})
    item_1 = json.dumps({"title": "Closing Time", "added_by": "Admin (Last Call)", "is_closing_time": True})

    class FakeListClient:
        def __init__(self):
            self.items = [item_0, item_1]

        def lrange(self, name, start, end):
            return self.items

        def lrem(self, name, count, value):
            if value in self.items:
                self.items.remove(value)
                return 1
            return 0

    fake_client = FakeListClient()
    mocker.patch("backend.services.redis.get_redis_queue_client", return_value=fake_client)
    mocker.patch("backend.websockets.broadcast_queue_threadsafe")
    mocker.patch("backend.websockets.broadcast_json_threadsafe")

    res = cancel_closing_time_mode()
    assert res["success"] is True
    assert res["closing_time"] is False
    assert len(fake_client.items) == 1
    assert json.loads(fake_client.items[0])["title"] == "Currently Playing"
