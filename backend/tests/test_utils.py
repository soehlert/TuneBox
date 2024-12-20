"""Test utils functions"""
import time
from unittest.mock import MagicMock, patch

import pytest
from plexapi.audio import Track

from backend.services.redis import get_redis_queue_client
from backend.utils import (
    TrackTimeTracker,
    is_song_in_queue,
    is_track_object,
)

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def mock_redis(mocker):
    """Mock Redis client to avoid actual Redis connection.

    Returns a MagicMock object that simulates Redis client behavior.
    """
    mock_redis_queue = MagicMock()
    mocker.patch("backend.utils.get_redis_queue_client", return_value=mock_redis_queue)
    return mock_redis_queue


@pytest.fixture
def mock_plex_track():
    """Create a mock Plex Track object with standard test attributes.
    Returns a MagicMock object simulating a Plex Track.
    """
    track = MagicMock()
    track.ratingKey = "12345"
    track.title = "Mock Song"
    track.artist = "Mock Artist"
    track.duration = 180
    return track


@pytest.fixture
def tracker():
    """Create a fresh TrackTimeTracker instance for testing.
    Returns a new TrackTimeTracker object.
    """
    return TrackTimeTracker()

# ============================================================================
# Redis Client Tests
# ============================================================================


@patch("backend.services.redis.redis.StrictRedis.from_url")
def test_get_redis_queue_client(mock_redis):
    """Test the lazy initialization of Redis client."""
    mock_redis_queue = MagicMock()
    mock_redis.return_value = mock_redis_queue

    with patch("backend.config.settings.redis_url", "redis://redis:6379"):
        client = get_redis_queue_client()
        assert client is mock_redis_queue
        mock_redis.assert_called_once_with("redis://redis:6379", db=0, decode_responses=True)

# ============================================================================
# Track Object Tests
# ============================================================================


def test_is_track_object():
    """Test identification of valid Plex Track objects."""
    track = MagicMock(spec=Track)
    not_a_track = object()

    assert is_track_object(track) is True
    assert is_track_object(not_a_track) is False

# ============================================================================
# Queue Tests
# ============================================================================


def test_song_found_in_queue(mock_redis, mock_plex_track):
    """Test when a song exists in the queue."""
    mock_redis.lrange.return_value = [
        '{"item_id": "12345", "title": "Mock Song", "artist": "Mock Artist"}'
    ]
    assert is_song_in_queue(mock_plex_track) is True
    mock_redis.lrange.assert_called_once_with("playback_queue", 0, -1)


def test_song_not_in_queue(mock_redis, mock_plex_track):
    """Test when a song is not in the queue."""
    mock_redis.lrange.return_value = [
        '{"item_id": "67890", "title": "Different Song", "artist": "Different Artist"}'
    ]
    assert is_song_in_queue(mock_plex_track) is False


def test_empty_queue(mock_redis, mock_plex_track):
    """Test behavior with an empty queue."""
    mock_redis.lrange.return_value = []
    assert is_song_in_queue(mock_plex_track) is False


def test_redis_exception_handling(mock_redis, mock_plex_track):
    """Test exception handling for Redis failures."""
    mock_redis.lrange.side_effect = Exception("Redis connection failed")
    assert is_song_in_queue(mock_plex_track) is False


def test_invalid_json_in_queue(mock_redis, mock_plex_track):
    """Test handling of invalid JSON in the queue."""
    mock_redis.lrange.return_value = ["{invalid json}"]
    assert is_song_in_queue(mock_plex_track) is False


def test_multiple_items_in_queue(mock_redis, mock_plex_track):
    """Test with multiple items in the queue."""
    mock_redis.lrange.return_value = [
        '{"item_id": "11111", "title": "Song 1"}',
        '{"item_id": "12345", "title": "Mock Song"}',
        '{"item_id": "22222", "title": "Song 2"}'
    ]
    assert is_song_in_queue(mock_plex_track) is True

# ============================================================================
# TrackTimeTracker Tests
# ============================================================================


def test_tracker_start(tracker):
    """Test starting track playback."""
    tracker.start("Test Track")
    assert tracker.track_name == "Test Track"
    assert tracker.is_playing is True
    assert tracker.start_time is not None
    assert tracker.last_update_time is not None


def test_tracker_pause(tracker):
    """Test pausing track playback."""
    tracker.start("Test Track")
    time.sleep(1)
    tracker.pause()
    assert tracker.is_playing is False
    assert tracker.elapsed_time > 0


def test_tracker_resume(tracker):
    """Test resuming track playback."""
    tracker.start("Test Track")
    time.sleep(1)
    tracker.pause()
    time.sleep(1)
    tracker.resume()
    assert tracker.is_playing is True
    assert tracker.start_time is not None
    assert tracker.elapsed_time > 0


def test_tracker_stop(tracker):
    """Test stopping track playback."""
    tracker.start("Test Track")
    time.sleep(1)
    tracker.stop()
    assert tracker.is_playing is False
    assert tracker.elapsed_time == 0
    assert tracker.track_name is None
    assert tracker.last_update_time is None


def test_tracker_reset(tracker):
    """Test resetting the tracker state."""
    tracker.start("Test Track")
    time.sleep(1)
    tracker.reset()
    assert tracker.is_playing is False
    assert tracker.track_name is None
    assert tracker.elapsed_time == 0


def test_tracker_get_elapsed_time(tracker):
    """Test elapsed time calculation."""
    tracker.start("Test Track")
    time.sleep(1)
    elapsed_time = tracker.get_elapsed_time("Test Track")
    assert elapsed_time > 0
    tracker.stop()
    assert tracker.get_elapsed_time("Test Track") == 0


def test_tracker_update(tracker):
    """Test updating tracker with new track information."""
    tracker.start("Test Track")
    time.sleep(1)
    current_track = {"title": "New Track", "track_state": "playing"}
    tracker.update(current_track)
    assert tracker.track_name == "New Track"
    assert tracker.is_playing is True
    assert tracker.start_time is not None