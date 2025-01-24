"""Handle lazily creating redis clients in a central location."""

import redis

from backend.config import settings


def get_redis_queue_client():
    """Lazy initialization of the Redis queue client.

    Returns:
        A Redis queue client.
    """
    if not hasattr(get_redis_queue_client, "client"):
        get_redis_queue_client.client = redis.StrictRedis.from_url(settings.redis_url, db=0, decode_responses=True)
    return get_redis_queue_client.client


def get_redis_cache_client():
    """Lazy initialization of the Redis cache client.

    Returns:
        A Redis cache client.
    """
    if not hasattr(get_redis_cache_client, "client"):
        get_redis_cache_client.client = redis.StrictRedis.from_url(settings.redis_url, db=1, decode_responses=True)
    return get_redis_cache_client.client


def get_redis_settings_client():
    """Lazy initialization of the Redis settings client.

    Returns:
        A Redis settings client.
    """
    if not hasattr(get_redis_settings_client, "client"):
        get_redis_settings_client.client = redis.StrictRedis.from_url(settings.redis_url, db=2, decode_responses=True)
    return get_redis_settings_client.client