"""Tests for queue playback history feature."""

import json
from fastapi.testclient import TestClient
from backend.config import settings
from backend.main import app
from backend.services.redis import add_to_history, get_playback_history

client = TestClient(app)


def test_add_to_history_caps_at_20_entries(mock_redis):
    """Verify add_to_history pushes track dict objects and caps history at 20 entries."""
    mock_queue_client, _ = mock_redis
    key_storage = {}

    def fake_lpush(key, value):
        if key not in key_storage:
            key_storage[key] = []
        key_storage[key].insert(0, value)

    def fake_ltrim(key, start, end):
        if key in key_storage:
            del key_storage[key][end + 1:]

    def fake_lrange(key, start, end):
        return key_storage.get(key, [])

    mock_queue_client.lpush.side_effect = fake_lpush
    mock_queue_client.ltrim.side_effect = fake_ltrim
    mock_queue_client.lrange.side_effect = fake_lrange

    orig_testing = settings.testing
    settings.testing = True
    try:
        # Push 25 tracks
        for i in range(25):
            track_data = {
                "item_id": 3000 + i,
                "title": f"Song {i}",
                "artist": "Test Artist",
                "album": "Test Album",
                "duration": 180,
            }
            add_to_history(track_data)

        history = get_playback_history()
        assert len(history) == 20
        assert history[0]["title"] == "Song 24"
        assert history[-1]["title"] == "Song 5"
    finally:
        settings.testing = orig_testing


def test_get_playback_history_endpoint(mock_redis):
    """Verify GET /api/music/queue/history returns list of historical track objects."""
    mock_queue_client, _ = mock_redis
    sample_data = json.dumps({
        "item_id": 9999,
        "title": "History Track",
        "artist": "History Artist",
        "album": "History Album",
        "duration": 210,
    })
    mock_queue_client.lrange.return_value = [sample_data]

    orig_testing = settings.testing
    settings.testing = True
    try:
        response = client.get("/api/music/queue/history")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["title"] == "History Track"
    finally:
        settings.testing = orig_testing
