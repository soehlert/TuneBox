import time
import json
import logging
import redis
from backend.config import settings
from plexapi.audio import Track


def get_redis_queue_client():
    """Lazy initialization of the Redis queue client."""
    if not hasattr(get_redis_queue_client, "client"):
        try:
            get_redis_queue_client.client = redis.StrictRedis.from_url(settings.redis_url, db=0, decode_responses=True)
        except Exception as e:
            logging.error(f"Redis queue client connection error: {e}")
            raise
    return get_redis_queue_client.client


def is_track_object(item):
    """Check if the given item is a track object (not a video)."""
    return isinstance(item, Track)


def milliseconds_to_seconds(milliseconds):
    """Convert duration in milliseconds to total seconds."""
    seconds = milliseconds // 1000
    return seconds


def is_song_in_queue(item):
    """Check if a song with the same ratingKey already exists in the Redis queue."""
    try:
        redis_queue_client = get_redis_queue_client()
        queue = redis_queue_client.lrange("playback_queue", 0, -1)

        queue_items = [json.loads(item) for item in queue]

        return any(track["item_id"] == item.ratingKey for track in queue_items)

    except Exception as e:
        logging.error(f"Error checking if song is in queue: {e}")
        return False


class TrackTimeTracker:
    def __init__(self):
        self.current_track = None
        self.start_time = None
        self.elapsed_time = 0
        self.is_playing = False
        self.track_name = None
        self.last_update_time = None  # Last time the track progress was updated

    def start(self, track_name):
        """Start tracking a new track."""
        self.track_name = track_name
        # Adjust if resumed after pause
        self.start_time = time.time() - self.elapsed_time
        self.last_update_time = time.time()  # Start tracking time
        self.is_playing = True

    def pause(self):
        """Pause the track and record elapsed time."""
        if self.is_playing:
            self.elapsed_time = time.time() - self.start_time
            self.is_playing = False
            self.last_update_time = None  # Stop tracking time

    def resume(self):
        """Resume the track from where it left off."""
        if not self.is_playing:
            # Adjust the start time
            self.start_time = time.time() - self.elapsed_time
            self.last_update_time = time.time()  # Resume tracking time
            self.is_playing = True

    def stop(self):
        """Stop tracking the track."""
        self.elapsed_time = 0
        self.is_playing = False
        self.track_name = None
        self.last_update_time = None

    def reset(self):
        self.stop()
        self.current_track = None
        self.elapsed_time = 0
        self.last_update_time = None

    def get_elapsed_time(self, track_name):
        """Get the elapsed time for the currently playing track."""
        if self.track_name == track_name:
            if self.is_playing:
                # Update elapsed time based on the last update time
                time_diff = time.time() - self.last_update_time
                self.elapsed_time += time_diff
                self.last_update_time = time.time()
            return self.elapsed_time
        return 0

    def update(self, current_track):
        """Update the tracker based on the current track information."""
        if self.track_name != current_track["title"]:
            # If the track has changed, start tracking the new track
            self.stop()
            self.start(current_track["title"])

        # If the track is paused, pause the tracker
        if current_track["track_state"] == "paused":
            self.pause()
        elif current_track["track_state"] == "playing":
            if not self.is_playing:
                self.resume()
