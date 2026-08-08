"""Tests for autoplay generation and orchestrator error isolation."""

import json
from unittest.mock import MagicMock
from backend.config import settings
from backend.services.plex import generate_autoplay_tracks


def test_generate_autoplay_tracks_handles_history_dicts(mock_redis, mocker):
    """Verify generate_autoplay_tracks succeeds when get_playback_history returns dictionary objects."""
    mock_queue_client, _ = mock_redis

    # Return mock history containing dict objects
    history_dicts = [
        {"item_id": 1001, "title": "Track 1", "artist": "Artist 1"},
        {"item_id": 1002, "title": "Track 2", "artist": "Artist 2"},
    ]
    mock_queue_client.lrange.return_value = [json.dumps(d) for d in history_dicts]

    # Mock add_to_queue_redis to capture generated tracks
    mock_add = mocker.patch("backend.services.redis.add_to_queue_redis")

    orig_testing = settings.testing
    settings.testing = False
    try:
        # Must execute without raising TypeError: unhashable type: 'dict'
        generate_autoplay_tracks()
    finally:
        settings.testing = orig_testing


def test_get_playback_history_ids_returns_integers(mock_redis):
    """Verify get_playback_history_ids returns integer IDs from dict history."""
    mock_queue_client, _ = mock_redis
    history_dicts = [
        json.dumps({"item_id": 2001, "title": "Track 1"}),
        json.dumps({"item_id": 2002, "title": "Track 2"}),
    ]
    mock_queue_client.lrange.return_value = history_dicts

    from backend.services.redis import get_playback_history_ids
    ids = get_playback_history_ids()
    assert ids == [2001, 2002]
