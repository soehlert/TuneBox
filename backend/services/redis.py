import logging
import redis
import json

from backend.config import settings
from backend.utils import is_song_in_queue, is_track_object

redis_client = redis.StrictRedis.from_url(settings.redis_url, decode_responses=True)

def add_to_queue_redis(song):
    """Add a song to the Redis queue, including album art."""
    try:
        if not is_track_object(song):
            logging.error(f"The object being added is not a song: {song}")
            raise ValueError("Only songs can be added to the queue.")

        if is_song_in_queue(song):
            logging.info(f"Song {song.title} is already in the Redis queue.")
            return {"message": f"Song {song.title} is already in the queue."}

        song_data = {
            "item_id": song.ratingKey,
            "title": song.title,
            "artist": getattr(song, "grandparentTitle", "Unknown Artist"),
            "duration": song.duration,
            "album_art": song.thumb if hasattr(song, "thumb") else None  # Grab the album art URL if available
        }

        # Store the song as a JSON object in Redis
        redis_client.rpush("playback_queue", json.dumps(song_data))  # Use json.dumps to convert the dict to a JSON string
        logging.info(f"Added {song.title} to the Redis playback queue.")
    except Exception as e:
        logging.error(f"Error adding song to Redis queue: {e}")
        raise


def remove_from_redis_queue(item_id):
    """Remove a song from the Redis playback queue by its item_id."""
    try:
        # Fetch all items from the queue
        queue = redis_client.lrange("playback_queue", 0, -1)

        # Loop through the queue to find the song with the given item_id
        for song_data in queue:
            song = json.loads(song_data)
            if song["item_id"] == item_id:
                # Remove the song from the queue
                redis_client.lrem("playback_queue", 0, song_data)
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
        queue = redis_client.lrange("playback_queue", 0, -1)

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
        redis_client.delete("playback_queue")
        logging.info("The Redis playback queue has been cleared.")
        return {"message": "The queue has been cleared."}
    except Exception as e:
        logging.error(f"Error clearing Redis queue: {e}")
        raise