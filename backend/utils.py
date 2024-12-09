import time
import json
import logging
import redis

from plexapi.audio import Track

redis_client = redis.StrictRedis(host='localhost', port=6379, db=0, decode_responses=True)


def is_track_object(item):
    """Check if the given item is a track object (not a video)."""
    return isinstance(item, Track)

def milliseconds_to_seconds(milliseconds):
    """Convert duration in milliseconds to total seconds."""
    seconds = milliseconds // 1000
    return seconds


def track_to_dict(track):
    """Convert a Plex Track object to a dictionary."""
    return {
        "item_id": track.ratingKey,
        "title": track.title,
        "artist": getattr(track, "grandparentTitle", "Unknown Artist"),
        "duration": track.duration if hasattr(track, "duration") else None
    }


def is_song_in_queue(item):
    """Check if a song with the same ratingKey already exists in the Redis queue."""
    try:
        queue = redis_client.lrange("playback_queue", 0, -1)

        queue_items = [json.loads(item) for item in queue]

        return any(track['item_id'] == item.ratingKey for track in queue_items)

    except Exception as e:
        logging.error(f"Error checking if song is in queue: {e}")
        return False


class TrackTimeTracker:
    def __init__(self):
        self.start_time = None
        self.elapsed_time = 0
        self.is_playing = False
        self.track_name = None

    def start(self, track_name):
        """Start tracking a new track."""
        self.track_name = track_name
        # Adjust if resumed after pause
        self.start_time = time.time() - self.elapsed_time
        self.is_playing = True

    def pause(self):
        """Pause the track and record elapsed time."""
        if self.is_playing:
            self.elapsed_time = time.time() - self.start_time
            self.is_playing = False

    def resume(self):
        """Resume the track from where it left off."""
        if not self.is_playing:
            # Adjust the start time
            self.start_time = time.time() - self.elapsed_time
            self.is_playing = True

    def stop(self):
        """Stop tracking the track."""
        self.elapsed_time = 0
        self.is_playing = False
        self.track_name = None

    def get_elapsed_time(self, track_name):
        """Get the elapsed time for the currently playing track."""
        if self.track_name == track_name:
            if self.is_playing:
                return time.time() - self.start_time
            return self.elapsed_time
        # We are not tracking this song
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
            # If the track is playing, resume or continue tracking
            if not self.is_playing:
                self.resume()