"""Test redis functionality."""

import json

import pytest

from unittest.mock import patch

from backend.services.redis import (
    add_to_queue_redis,
    cache_data,
    clear_cache,
    clear_redis_queue,
    get_cached_data,
    get_redis_queue,
    remove_from_redis_queue,
)


@pytest.fixture
def sample_track_json():
    """Provide a sample track JSON string for testing.

    Returns:
        str: JSON string representing a track
    """
    return json.dumps({
        "item_id": "12345",
        "title": "Test Song",
        "artist": "Test Artist",
        "duration": 180,
        "album_art": "http://example.com/album_art.jpg",
    })


def test_add_to_queue_redis(mock_redis, mock_plex_track, mocker):
    """Test adding a track to the Redis queue."""
    mocker.patch("backend.utils.is_track_object", return_value=True)
    mock_redis_queue, _ = mock_redis

    with patch("backend.utils.get_redis_queue_client", return_value=mock_redis_queue):
        add_to_queue_redis(mock_plex_track)

    mock_redis_queue.rpush.assert_called_once()
    called_args = mock_redis_queue.rpush.call_args[0]
    assert called_args[0] == "playback_queue"
    track_data = json.loads(called_args[1])
    assert track_data["item_id"] == "12345"
    assert track_data["title"] == "Test Song"


def test_add_to_queue_redis_invalid_track(mock_redis, mocker):
    """Test adding an invalid track to the Redis queue."""
    mock_redis_queue, _ = mock_redis

    # Create an invalid track object (just a plain dict instead of a Track)
    invalid_track = {"title": "Test Song"}

    with pytest.raises(ValueError, match=r"Only songs can be added to the queue."):
        add_to_queue_redis(invalid_track)

    mock_redis_queue.rpush.assert_not_called()


def test_remove_from_redis_queue(mock_redis, sample_track_json):
    """Test removing a track from the Redis queue."""
    mock_redis_queue, _ = mock_redis
    mock_redis_queue.lrange.return_value = [sample_track_json]

    response = remove_from_redis_queue("12345")

    mock_redis_queue.lrem.assert_called_once_with("playback_queue", 0, sample_track_json)
    assert response == {"message": "Removed Test Song from the queue."}


def test_remove_from_redis_queue_not_found(mock_redis):
    """Test removing a non-existent track from the Redis queue."""
    mock_redis_queue, _ = mock_redis
    mock_redis_queue.lrange.return_value = []

    response = remove_from_redis_queue("99999")

    mock_redis_queue.lrem.assert_not_called()
    assert response == {"message": "Song not found in the queue."}


def test_get_redis_queue_with_items(mock_redis, sample_track_json):
    """Test retrieving items from the Redis queue."""
    mock_redis_queue, _ = mock_redis
    mock_redis_queue.lrange.return_value = [sample_track_json]

    queue = get_redis_queue()

    assert len(queue) == 1
    assert queue[0]["title"] == "Test Song"
    mock_redis_queue.lrange.assert_called_once_with("playback_queue", 0, -1)


def test_get_redis_queue_empty(mock_redis):
    """Test retrieving an empty Redis queue."""
    mock_redis_queue, _ = mock_redis
    mock_redis_queue.lrange.return_value = []

    queue = get_redis_queue()

    assert len(queue) == 0
    mock_redis_queue.lrange.assert_called_once_with("playback_queue", 0, -1)


def test_clear_redis_queue(mock_redis):
    """Test clearing the entire Redis queue."""
    mock_redis_queue, _ = mock_redis

    response = clear_redis_queue()

    mock_redis_queue.delete.assert_called_once_with("playback_queue")
    assert response == {"message": "The queue has been cleared."}


def test_cache_data_success(mock_redis):
    """Test successfully caching data."""
    _, mock_redis_cache = mock_redis
    key = "test_key"
    data = {"some": "data"}

    cache_data(key, data)

    mock_redis_cache.setex.assert_called_once_with(key, 21600, json.dumps(data))


def test_get_cached_data_exists(mock_redis):
    """Test retrieving existing cached data."""
    _, mock_redis_cache = mock_redis
    mock_redis_cache.get.return_value = '{"some": "data"}'

    data = get_cached_data("test_key")

    assert data == {"some": "data"}
    mock_redis_cache.get.assert_called_once_with("test_key")


def test_get_cached_data_not_found(mock_redis):
    """Test retrieving non-existent cached data."""
    _, mock_redis_cache = mock_redis
    mock_redis_cache.get.return_value = None

    data = get_cached_data("test_key")

    assert data is None
    mock_redis_cache.get.assert_called_once_with("test_key")


def test_clear_cache_success(mock_redis):
    """Test successfully clearing cached data."""
    _, mock_redis_cache = mock_redis
    key = "test_key"

    response = clear_cache(key)

    mock_redis_cache.delete.assert_called_once_with(key)
    assert response == {"message": f"Cache cleared for key: {key}"}
