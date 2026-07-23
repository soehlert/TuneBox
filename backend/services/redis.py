"""Handle interaction with redis queue and caching."""

import json
import logging

from fastapi import HTTPException, status

from backend.services.redis_client import get_redis_cache_client, get_redis_queue_client
from backend.utils import is_song_in_queue, is_track_object

logger = logging.getLogger(__name__)

CACHE_TTL = 21600


def add_to_queue_redis(song, server_id=None, server_name=None, server_token=None, server_address=None, is_fallback=False):
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

    moods = [m.tag if hasattr(m, "tag") else str(m) for m in getattr(song, "moods", [])] if hasattr(song, "moods") else []

    # Cascade to Album and Artist level for moods if track level is empty
    if not moods:
        try:
            if hasattr(song, "album"):
                album = song.album()
                if album and hasattr(album, "moods") and album.moods:
                    moods = [m.tag if hasattr(m, "tag") else str(m) for m in album.moods]
        except Exception:
            pass

    if not moods:
        try:
            if hasattr(song, "artist"):
                artist = song.artist()
                if artist and hasattr(artist, "moods") and artist.moods:
                    moods = [m.tag if hasattr(m, "tag") else str(m) for m in artist.moods]
        except Exception:
            pass

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
        "is_fallback": is_fallback,
        "moods": moods,
    }

    client = get_redis_queue_client()
    if is_fallback:
        # If it's fallback, just append it to the end of the queue
        client.rpush("playback_queue", json.dumps(song_data))
        logger.info("Added fallback track %s to Redis queue.", song.title)
    else:
        # If it's a guest song, check if fallback songs exist in the queue
        queue = client.lrange("playback_queue", 0, -1)
        fallback_indices = []
        for i, item_bytes in enumerate(queue):
            item = json.loads(item_bytes)
            if item.get("is_fallback"):
                fallback_indices.append(i)
        
        if fallback_indices:
            # Only allow leapfrogging fallback tracks that are not currently playing (index >= 1)
            candidate_indices = [idx for idx in fallback_indices if idx >= 1]
            if candidate_indices:
                first_fallback_idx = candidate_indices[0]
                first_fallback_data = queue[first_fallback_idx]
                client.linsert("playback_queue", "BEFORE", first_fallback_data, json.dumps(song_data))
                
                # Drop the last fallback track in the queue to maintain queue size
                last_fallback_idx = fallback_indices[-1]
                last_fallback_data = queue[last_fallback_idx]
                client.lrem("playback_queue", -1, last_fallback_data)
                logger.info("Inserted guest song %s before first non-playing fallback and dropped last fallback.", song.title)
            else:
                # If the only fallback track is at index 0 (currently playing), append to the end
                client.rpush("playback_queue", json.dumps(song_data))
                logger.info("Added guest song %s to end of Redis queue (playing track is fallback).", song.title)
        else:
            # If no fallback tracks exist, just append to the end as normal
            client.rpush("playback_queue", json.dumps(song_data))
            logger.info("Added guest song %s to Redis queue.", song.title)



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


def add_to_history(track_id: int):
    """Add a track ID to the playback history list in Redis (capped at 10 items)."""
    try:
        client = get_redis_queue_client()
        # Push to the left (newest first)
        client.lpush("playback_history", track_id)
        # Trim to keep only the 10 most recent entries
        client.ltrim("playback_history", 0, 9)
        logger.info("Added track %s to playback history.", track_id)
    except Exception as e:
        logger.warning("Failed to update playback history: %s", e)


def get_playback_history():
    """Retrieve the recent playback history track IDs from Redis."""
    try:
        client = get_redis_queue_client()
        history = client.lrange("playback_history", 0, -1)
        return [int(tid) for tid in history]
    except Exception as e:
        logger.warning("Failed to fetch playback history: %s", e)
        return []


def is_autoplay_enabled() -> bool:
    """Check if autoplay mode is enabled in Redis."""
    try:
        val = get_redis_queue_client().get("autoplay_enabled")
        return val in ("true", b"true")
    except Exception:
        return False


def set_autoplay_enabled(enabled: bool):
    """Set the autoplay mode state in Redis."""
    try:
        get_redis_queue_client().set("autoplay_enabled", "true" if enabled else "false")
    except Exception as e:
        logger.warning("Failed to set autoplay state: %s", e)


