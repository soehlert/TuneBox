"""Create some utility tools to help in other modules."""

import json
import time

from plexapi.audio import Track

from backend.services.redis_client import get_redis_queue_client


def is_track_object(item):
    """Check if the given item is a track object (not a video).

    Returns:
        Boolean if the given item is a track object.
    """
    return isinstance(item, Track)


def milliseconds_to_seconds(milliseconds):
    """Convert duration in milliseconds to total seconds.

    Returns:
        Time in seconds.
    """
    return milliseconds // 1000


def is_song_in_queue(item):
    """Check if a song with the same ratingKey already exists in the Redis queue.

    Returns:
        A track if it's in the queue.
    """
    redis_queue_client = get_redis_queue_client()
    queue = redis_queue_client.lrange("playback_queue", 0, -1)

    queue_items = [json.loads(item) for item in queue]

    return any(track["item_id"] == item.ratingKey for track in queue_items)


class TrackTimeTracker:
    """Keep track of what time a song is at even when paused/resumed or stopped."""

    def __init__(self):
        """Initialize a TrackTimeTracker object."""
        self.track_name = None
        self.state = "stopped"  # "playing", "paused", "stopped"
        self.accumulated_elapsed = 0.0
        self.last_resume_time = None
        self.current_track = None

    @property
    def last_update_time(self):
        """Deprecated: use last_resume_time instead. Kept for test compatibility."""
        return self.last_resume_time

    @last_update_time.setter
    def last_update_time(self, value):
        self.last_resume_time = value

    @property
    def is_playing(self):
        """Check if the tracker is currently playing."""
        return self.state == "playing"

    @property
    def elapsed_time(self):
        """The current elapsed time in seconds."""
        if self.track_name is None:
            return 0.0
        return self.get_elapsed_time(self.track_name)

    @property
    def start_time(self):
        """Estimate the starting wall-clock time of the track."""
        if self.state == "stopped":
            return None
        return time.time() - self.elapsed_time

    def start(self, track_name):
        """Start tracking a new track."""
        self.track_name = track_name
        self.state = "playing"
        self.accumulated_elapsed = 0.0
        self.last_resume_time = time.time()

    def pause(self):
        """Pause the track and record elapsed time."""
        if self.state == "playing" and self.last_resume_time is not None:
            self.accumulated_elapsed += time.time() - self.last_resume_time
            self.state = "paused"
            self.last_resume_time = None

    def resume(self):
        """Resume the track from where it left off."""
        if self.state == "paused":
            self.last_resume_time = time.time()
            self.state = "playing"

    def stop(self):
        """Stop tracking the track."""
        self.state = "stopped"
        self.track_name = None
        self.accumulated_elapsed = 0.0
        self.last_resume_time = None

    def reset(self):
        """Reset track time."""
        self.stop()
        self.current_track = None

    def get_elapsed_time(self, track_name):
        """Get the elapsed time for the currently playing track.

        Returns:
            Elapsed time in seconds.
        """
        if self.track_name != track_name:
            return 0.0

        if self.state == "playing" and self.last_resume_time is not None:
            return self.accumulated_elapsed + (time.time() - self.last_resume_time)

        return self.accumulated_elapsed

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
            if self.state == "paused":
                self.resume()

