"""Set up reusable components for pytest."""

from unittest.mock import MagicMock, patch

import pytest

from backend.config import Settings


@pytest.fixture(autouse=True)
def mock_settings():
    """Mock settings for all tests."""
    mock_settings = Settings(
        plex_base_url="http://fake-plex:32400",
        plex_token="fake-token",
        client_name="test-client",
        redis_url="redis://fake-redis:6379",
        tunebox_url="http://fake-tunebox:8000",
    )

    with patch("backend.config.settings", mock_settings):
        yield mock_settings


@pytest.fixture
def mock_redis(mocker):
    """Mock Redis clients to avoid actual Redis connection.

    Returns:
        tuple: (mock_redis_queue, mock_redis_cache) - Mocked Redis clients for queue and cache
    """
    mock_redis_queue = MagicMock()
    mock_redis_cache = MagicMock()

    mocker.patch("backend.services.redis.get_redis_queue_client", return_value=mock_redis_queue)
    mocker.patch("backend.services.redis.get_redis_cache_client", return_value=mock_redis_cache)

    return mock_redis_queue, mock_redis_cache
