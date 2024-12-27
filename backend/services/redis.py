"""Handle interaction with redis queue and caching."""

import json
import logging

import redis
from fastapi import HTTPException, status

from backend.config import settings
from backend.utils import is_song_in_queue, is_track_object

logger = logging.getLogger(__name__)

CACHE_TTL = 21600


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
        A redis cache client.
    """
    if not hasattr(get_redis_cache_client, "client"):
        get_redis_cache_client.client = redis.StrictRedis.from_url(settings.redis_url, db=1, decode_responses=True)

    return get_redis_cache_client.client


def add_to_queue_redis(song):
    """Add a song to the Redis queue."""
    if not is_track_object(song):
        msg = "Only songs can be added to the queue."
        raise ValueError(msg)

    if is_song_in_queue(song):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"Song {song.title} is already in the queue."
        )

    song_data = {
        "item_id": song.ratingKey,
        "title": song.title,
        "artist": getattr(song, "grandparentTitle", "Unknown Artist"),
        "duration": song.duration,
        "album_art": song.thumb if hasattr(song, "thumb") else None,
    }

    # Store the song as a JSON object in Redis
    get_redis_queue_client().rpush("playback_queue", json.dumps(song_data))
    logger.info("Added %s to the Redis playback queue.", song.title)


def remove_from_redis_queue(item_id):
    """Remove a song from the Redis playback queue by its item_id.

    Returns:
        A message about the song in the queue.
    """
    queue = get_redis_queue_client().lrange("playback_queue", 0, -1)

    for song_data in queue:
        song = json.loads(song_data)
        if song["item_id"] == item_id:
            # Remove the song from the queue
            get_redis_queue_client().lrem("playback_queue", 0, song_data)
            logger.info("Removed %s from the Redis playback queue.", song["title"])
            return {"message": f"Removed {song['title']} from the queue."}

    # If the song wasn't found in the queue
    logger.warning("Song with item_id %s not found in the Redis queue.", item_id)

    return {"message": "Song not found in the queue."}


def get_redis_queue():
    """Get all songs in the Redis playback queue (metadata only).

    Returns:
        The redis queue as a list.
    """
    queue = get_redis_queue_client().lrange("playback_queue", 0, -1)

    queue_items = []
    for item_data in queue:
        song_metadata = json.loads(item_data)
        queue_items.append(song_metadata)
    return queue_items


def clear_redis_queue():
    """Clear the entire Redis playback queue.

    Returns:
        A cleared redis queue.
    """
    get_redis_queue_client().delete("playback_queue")
    logger.info("The Redis playback queue has been cleared.")

    return {"message": "The queue has been cleared."}


def cache_data(key, data):
    """Cache data in Redis."""
    get_redis_cache_client().setex(key, CACHE_TTL, json.dumps(data))
    logger.info("Cached data under key: %s", key)


def get_cached_data(key):
    """Retrieve cached data from Redis.

    Returns:
        Cached data from Redis.
    """
    cached_data = get_redis_cache_client().get(key)
    if cached_data:
        try:
            return json.loads(cached_data)
        except json.JSONDecodeError:
            return None
    logger.info("No cached data found for key: %s", key)

    return None


def clear_cache(key: str):
    """Clear a specific cache key in Redis.

    Returns:
        A message about a cleared cache.
    """
    get_redis_cache_client().delete(key)
    logger.info("Cache cleared for key: %s", key)
    return {"message": f"Cache cleared for key: {key}"}
