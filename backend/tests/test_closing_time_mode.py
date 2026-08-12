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
