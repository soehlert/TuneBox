import logging

from fastapi import APIRouter, HTTPException, BackgroundTasks
from backend.services.plex import (
    fetch_item_by_rating_key,
    add_to_local_queue,
    remove_from_local_queue,
    clear_local_queue,
    get_local_playback_queue,
    fetch_all_artists,
    fetch_albums_for_artist,
    fetch_tracks_for_album,
    get_all_players,
    get_current_playing_track,
    get_track,
    get_active_player,
    search_music
)

from backend.state import playback_queue
from backend.websockets import send_queue
from plexapi.exceptions import PlexApiException

router = APIRouter(
    prefix="/api/music",
    tags=["Music"]
)


# Helper function to check if the song is already in the queue
def is_song_in_queue(item):
    """Check if a song with the same ratingKey already exists in the queue."""
    # If the queue is empty, return False as it can't be in the queue
    if not playback_queue:
        return False
    return any(track.ratingKey == item.ratingKey for track in playback_queue)


@router.post("/queue/{item_id}")
async def add_to_queue(item_id: int, background_tasks: BackgroundTasks):
    """Add an item to the playback queue."""
    try:
        item = get_track(item_id)

        if is_song_in_queue(item):
            # Return a 400 error with an appropriate message if the song is already in the queue
            raise HTTPException(status_code=400, detail="Song is already in the queue.")

        add_to_local_queue(item)

        # Call the WebSocket function to notify clients of the updated queue
        background_tasks.add_task(send_queue)

        return {"message": f"Added {item.title} to the playback queue."}

    except PlexApiException as e:
        raise HTTPException(status_code=500, detail=f"Plex error: {e}")
    except HTTPException as e:
        # Ensure 400 exceptions (like 'Song is already in the queue') are caught and returned correctly
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error adding item to queue: {e}")


@router.get("/queue")
def get_playback_queue():
    """Get the current playback queue."""
    try:
        queue = get_local_playback_queue()
        logging.debug(f"Current queue: {queue}")
        return [
            {
                "item_id": item["item_id"],
                "title": item["title"],
                "artist": item.get("artist", "Unknown Artist"),
                "duration": item.get("duration", "0:00")
            }
            for item in queue
        ]
    except Exception as e:
        logging.error(f"Error fetching the queue: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error fetching the queue: {str(e)}")


@router.post("/clear-queue")
def clear_the_queue():
    """Clear the playback queue."""
    try:
        clear_local_queue()

        return {"message": "Queue has been cleared."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error clearing the queue: {e}")

# Fetch all artists
@router.get("/artists")
def get_all_artists():
    """Fetch a list of all artists."""
    try:
        return fetch_all_artists()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching artists: {e}")


# Fetch albums for a specific artist
@router.get("/artists/{artist_id}/albums")
def get_albums_for_artist(artist_id: int):
    """Fetch albums for a specific artist by ID."""
    try:
        return fetch_albums_for_artist(artist_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching albums for artist {artist_id}: {e}")

# Fetch tracks for a specific album
@router.get("/albums/{album_id}/tracks")
def get_tracks_for_album(album_id: int):
    """Fetch tracks for a specific album by ID."""
    try:
        return fetch_tracks_for_album(album_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching tracks for album {album_id}: {e}")

# Search for artists, albums, or tracks
@router.get("/search")
def search_music_endpoint(query: str):
    """Search for music in the Plex library."""
    try:
        return search_music(query)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error searching music library: {e}")

# Fetch the list of available playback devices (players)
@router.get("/players")
def get_players():
    """Get the list of available playback devices (players)."""
    try:
        players = get_all_players()
        return players
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching players: {e}")


@router.get("/now-playing")
def get_current_playing():
    """Get the currently playing track."""
    try:
        current_track = get_current_playing_track()
        logging.debug(f"Current playing track: {current_track}")
        if not current_track:
            logging.debug("No track is currently playing, raising 404.")
            raise HTTPException(status_code=404, detail="No track is currently playing")
        return {"current_track": current_track}
    except HTTPException as e:  # Catch HTTPException and let FastAPI handle it
        raise e  # Just re-raise it, so FastAPI can process it

    except Exception as e:
        logging.error(f"Error fetching current track: {e}")  # Log the error details
        raise HTTPException(status_code=500, detail=f"Error fetching current track: {str(e)}")