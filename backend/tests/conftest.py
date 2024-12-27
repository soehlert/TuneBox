"""Set up reusable components for pytest."""

from unittest.mock import MagicMock, patch

import pytest
from plexapi.audio import Track

mock_env = {
    "PLEX_BASE_URL": "http://fake-plex:32400",
    "PLEX_TOKEN": "fake-token",
    "CLIENT_NAME": "test-client",
    "REDIS_URL": "redis://fake-redis:6379",
    "TUNEBOX_URL": "http://fake-tunebox:8000",
}

with patch.dict("os.environ", mock_env):
    from backend.config import settings


@pytest.fixture(autouse=True)
def mock_settings():
    """Mock settings for all tests."""
    with patch("backend.config.settings", settings):
        yield settings


@pytest.fixture
def mock_plex_track():
    """Create a mock Plex Track object with test attributes.

    Returns:
        MagicMock: Simulated Plex Track object
    """
    mock_track = MagicMock(spec=Track)
    mock_track.ratingKey = "12345"
    mock_track.title = "Test Song"
    mock_track.duration = 180
    mock_track.thumb = "http://example.com/album_art.jpg"
    mock_track.grandparentTitle = "Test Artist"
    return mock_track


@pytest.fixture
def mock_redis(mocker, mock_settings):
    """Mock Redis clients to avoid actual Redis connection.

    Returns:
        tuple: (mock_redis_queue, mock_redis_cache) - Mocked Redis clients for queue and cache
    """
    mock_redis_queue = MagicMock()
    mock_redis_cache = MagicMock()

    mocker.patch("backend.services.redis_client.get_redis_queue_client", return_value=mock_redis_queue)
    mocker.patch("backend.services.redis_client.get_redis_cache_client", return_value=mock_redis_cache)

    return mock_redis_queue, mock_redis_cache
