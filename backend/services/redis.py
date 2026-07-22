"""Handle interaction with redis queue and caching."""

import json
import logging

from fastapi import HTTPException, status

from backend.services.redis_client import get_redis_cache_client, get_redis_queue_client
from backend.utils import is_song_in_queue, is_track_object

logger = logging.getLogger(__name__)

CACHE_TTL = 21600


def add_to_queue_redis(song, server_id=None, server_name=None, server_token=None, server_address=None):
    """Add a song to the Redis queue with optional multi-server connection metadata."""
    if not is_track_object(song):
        msg = "Only songs can be added to the queue."
        raise ValueError(msg)

    target_server_id = server_id or getattr(song, "server_id", None)
    if is_song_in_queue(song, server_id=target_server_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Song {song.title} is already in the queue.",
        )

    song_data = {
        "item_id": song.ratingKey,
        "title": song.title,
        "artist": getattr(song, "grandparentTitle", "Unknown Artist"),
        "duration": song.duration,
        "album_art": song.thumb if hasattr(song, "thumb") else None,
        "server_id": target_server_id,
        "server_name": server_name or getattr(song, "server_name", None),
        "server_token": server_token or getattr(song, "server_token", None),
        "server_address": server_address or getattr(song, "server_address", None),
    }

    # Store the song as a JSON object in Redis
    get_redis_queue_client().rpush("playback_queue", json.dumps(song_data))
    logger.info("Added %s (server: %s) to Redis playback queue.", song.title, song_data.get("server_name") or "primary")


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


def cache_data(key, data, ttl: int = CACHE_TTL):
    """Cache data in Redis with custom TTL."""
    try:
        get_redis_cache_client().setex(key, ttl, json.dumps(data))
        logger.info("Cached data under key: %s (TTL: %d)", key, ttl)
    except Exception as e:
        logger.warning("Redis cache write error for key %s: %s", key, e)


def get_cached_data(key):
    """Retrieve cached data from Redis.

    Returns:
        Cached data from Redis.
    """
    try:
        cached_data = get_redis_cache_client().get(key)
        if cached_data:
            try:
                return json.loads(cached_data)
            except json.JSONDecodeError:
                return None
    except Exception as e:
        logger.warning("Redis cache read error for key %s: %s", key, e)
    return None


def clear_cache(key: str):
    """Clear a specific cache key in Redis.

    Returns:
        A message about a cleared cache.
    """
    try:
        get_redis_cache_client().delete(key)
        logger.info("Cache cleared for key: %s", key)
    except Exception as e:
        logger.warning("Redis cache clear error for key %s: %s", key, e)
    return {"message": f"Cache cleared for key: {key}"}
