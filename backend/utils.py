import time

class TrackTimeTracker:
    def __init__(self):
        self.start_time = None
        self.elapsed_time = 0
        self.is_playing = False
        self.track_name = None

    def start(self, track_name):
        """Start tracking a new track."""
        self.track_name = track_name
        self.start_time = time.time() - self.elapsed_time  # Adjust if resumed after pause
        self.is_playing = True

    def pause(self):
        """Pause the track and record elapsed time."""
        if self.is_playing:
            self.elapsed_time = time.time() - self.start_time
            self.is_playing = False

    def resume(self):
        """Resume the track from where it left off."""
        if not self.is_playing:
            self.start_time = time.time() - self.elapsed_time  # Adjust the start time
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
        return 0  # Return 0 if the track isn't being tracked

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