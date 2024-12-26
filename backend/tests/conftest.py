import pytest
from unittest.mock import MagicMock

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
