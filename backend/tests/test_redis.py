from unittest.mock import MagicMock

import pytest
from plexapi.audio import Track

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
def mock_redis(mocker):
    """Mock Redis clients to avoid actual Redis connection."""
    # Mock the Redis client used in add_to_queue_redis
    mock_redis_queue = MagicMock()
    mock_redis_cache = MagicMock()

    # Patch the lazy initialization functions to return the mock Redis clients
    mocker.patch("backend.services.redis.get_redis_queue_client", return_value=mock_redis_queue)
    mocker.patch("backend.services.redis.get_redis_cache_client", return_value=mock_redis_cache)

    return mock_redis_queue, mock_redis_cache


# Fixture to mock the Plex Track object
@pytest.fixture
def mock_plex_track():
    # Mocking the Plex Track object and its necessary attributes
    mock_track = MagicMock(spec=Track)
    mock_track.ratingKey = "12345"
    mock_track.title = "Test Song"
    mock_track.duration = 180
    mock_track.thumb = "http://example.com/album_art.jpg"
    mock_track.grandparentTitle = "Test Artist"
    return mock_track


# Test add_to_queue_redis
def test_add_to_queue_redis(mock_redis, mock_plex_track, mocker):
    # Mocking the is_track_object function to always return True for the test
    mocker.patch("backend.utils.is_track_object", return_value=True)

    mock_redis[0].rpush.return_value = None

    # Perform the actual test
    add_to_queue_redis(mock_plex_track)

    # Check that the rpush method was called with the correct arguments
    mock_redis[0].rpush.assert_called_once_with(
        "playback_queue",
        '{"item_id": "12345", "title": "Test Song", "artist": "Test Artist", "duration": 180, "album_art": "http://example.com/album_art.jpg"}',
    )


# Test remove_from_redis_queue
def test_remove_from_redis_queue(mock_redis, mock_plex_track):
    mock_redis[0].lrange.return_value = [
        '{"item_id": "12345", "title": "Test Song", "artist": "Test Artist", "duration": 180, "album_art": "http://example.com/album_art.jpg"}'
    ]
    mock_redis[0].lrem.return_value = None

    response = remove_from_redis_queue("12345")

    mock_redis[0].lrem.assert_called_once_with(
        "playback_queue",
        0,
        '{"item_id": "12345", "title": "Test Song", "artist": "Test Artist", "duration": 180, "album_art": "http://example.com/album_art.jpg"}',
    )
    assert response == {"message": "Removed Test Song from the queue."}


# Test get_redis_queue
def test_get_redis_queue(mock_redis):
    mock_redis[0].lrange.return_value = [
        '{"item_id": "12345", "title": "Test Song", "artist": "Test Artist", "duration": 180, "album_art": "http://example.com/album_art.jpg"}'
    ]

    queue = get_redis_queue()
    assert len(queue) == 1
    assert queue[0]["title"] == "Test Song"


# Test clear_redis_queue
def test_clear_redis_queue(mock_redis):
    mock_redis[0].delete.return_value = None

    response = clear_redis_queue()

    mock_redis[0].delete.assert_called_once_with("playback_queue")
    assert response == {"message": "The queue has been cleared."}


# Test cache_data
def test_cache_data(mock_redis):
    mock_redis[1].setex.return_value = None
    key = "test_key"
    data = {"some": "data"}

    cache_data(key, data)

    mock_redis[1].setex.assert_called_once_with(key, 21600, '{"some": "data"}')


# Test get_cached_data
def test_get_cached_data(mock_redis):
    mock_redis[1].get.return_value = '{"some": "data"}'

    data = get_cached_data("test_key")
    assert data == {"some": "data"}


# Test get_cached_data with no data found
def test_get_cached_data_not_found(mock_redis):
    mock_redis[1].get.return_value = None

    data = get_cached_data("test_key")
    assert data is None


# Test clear_cache
def test_clear_cache(mock_redis):
    mock_redis[1].delete.return_value = None

    response = clear_cache("test_key")

    mock_redis[1].delete.assert_called_once_with("test_key")
    assert response == {"message": "Cache cleared for key: test_key"}
