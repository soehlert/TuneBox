import logging
import redis
import json

from fastapi import HTTPException, status
from backend.utils import is_song_in_queue, is_track_object
from backend.config import settings


def get_redis_queue_client():
    """Lazy initialization of the Redis queue client."""
    if not hasattr(get_redis_queue_client, "client"):
        try:
            get_redis_queue_client.client = redis.StrictRedis.from_url(settings.redis_url, db=0, decode_responses=True)
        except Exception as e:
            logging.error(f"Redis queue client connection error: {e}")
            raise
    return get_redis_queue_client.client

def get_redis_cache_client():
    """Lazy initialization of the Redis cache client."""
    if not hasattr(get_redis_cache_client, "client"):
        try:
            get_redis_cache_client.client = redis.StrictRedis.from_url(settings.redis_url, db=1, decode_responses=True)
        except Exception as e:
            logging.error(f"Redis cache client connection error: {e}")
            raise
    return get_redis_cache_client.client


CACHE_TTL = 21600


def add_to_queue_redis(song):
    """Add a song to the Redis queue, including album art."""
    try:
        if not is_track_object(song):
            logging.error(f"The object being added is not a song: {song}")
            raise ValueError("Only songs can be added to the queue.")

        if is_song_in_queue(song):
            logging.info(f"Song {song.title} is already in the Redis queue.")
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
        get_redis_queue_client().rpush(
            "playback_queue", json.dumps(song_data)
        )
        logging.info(f"Added {song.title} to the Redis playback queue.")
    except Exception as e:
        logging.error(f"Error adding song to Redis queue: {e}")
        raise


def remove_from_redis_queue(item_id):
    """Remove a song from the Redis playback queue by its item_id."""
    try:
        queue = get_redis_queue_client().lrange("playback_queue", 0, -1)

        for song_data in queue:
            song = json.loads(song_data)
            if song["item_id"] == item_id:
                # Remove the song from the queue
                get_redis_queue_client().lrem("playback_queue", 0, song_data)
                logging.info(f"Removed {song['title']} from the Redis playback queue.")
                return {"message": f"Removed {song['title']} from the queue."}

        # If the song wasn't found in the queue
        logging.warning(f"Song with item_id {item_id} not found in the Redis queue.")
        return {"message": "Song not found in the queue."}

    except Exception as e:
        logging.error(f"Error removing song from Redis queue: {e}")
        raise


def get_redis_queue():
    """Get all songs in the Redis playback queue (metadata only)."""
    try:
        queue = get_redis_queue_client().lrange("playback_queue", 0, -1)

        queue_items = []
        for item_data in queue:
            song_metadata = json.loads(item_data)
            queue_items.append(song_metadata)

        return queue_items
    except Exception as e:
        logging.error(f"Error fetching the Redis playback queue: {e}")
        raise


def clear_redis_queue():
    """Clear the entire Redis playback queue."""
    try:
        get_redis_queue_client().delete("playback_queue")
        logging.info("The Redis playback queue has been cleared.")
        return {"message": "The queue has been cleared."}
    except Exception as e:
        logging.error(f"Error clearing Redis queue: {e}")
        raise


def cache_data(key, data):
    """Cache data in Redis."""
    try:
        get_redis_cache_client().setex(key, CACHE_TTL, json.dumps(data))
        logging.info(f"Cached data under key: {key}")
    except Exception as e:
        logging.error(f"Error caching data under key {key}: {e}")
        raise


def get_cached_data(key):
    """Retrieve cached data from Redis."""
    try:
        cached_data = get_redis_cache_client().get(key)
        if cached_data:
            return json.loads(cached_data)
        else:
            logging.info(f"No cached data found for key: {key}")
            return None
    except Exception as e:
        logging.error(f"Error retrieving cached data for key {key}: {e}")
        raise


def clear_cache(key: str):
    """Clear a specific cache key in Redis."""
    try:
        get_redis_cache_client().delete(key)
        logging.info(f"Cache cleared for key: {key}")
        return {"message": f"Cache cleared for key: {key}"}
    except Exception as e:
        logging.error(f"Error clearing cache for key {key}: {e}")
        raise
