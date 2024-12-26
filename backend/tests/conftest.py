"""Set up reusable components for pytest."""

import pytest

from unittest.mock import MagicMock, patch

from backend.config import Settings


@pytest.fixture(autouse=True)
def mock_settings():
    """Mock our settings required for tests to run."""
    with patch("backend.config.Settings") as mock_settings:
        mock_settings.return_value = Settings(
            plex_base_url="http://fake-plex:32400",
            plex_token="fake-token",
            client_name="test-client",
            redis_url="redis://fake-redis:6379",
            tunebox_url="http://fake-tunebox:8000",
        )
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
