import logging

from fastapi import APIRouter, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse
from backend.services.plex import (
    fetch_all_artists,
    fetch_albums_for_artist,
    fetch_tracks_for_album,
    play_queue_on_device,
    get_all_players,
    get_current_playing_track,
    get_track,
    get_active_player,
    search_music,
    fetch_art,
)
from backend.services.redis import (
    clear_redis_queue,
    add_to_queue_redis,
    remove_from_redis_queue,
    get_redis_queue,
    clear_cache,
)
from backend.websockets import send_queue
from plexapi.exceptions import PlexApiException


router = APIRouter(
    prefix="/api/music",
    tags=["Music"]
)


@router.post("/queue/{item_id}")
async def add_to_queue(item_id: int, background_tasks: BackgroundTasks):
    """Add an item to the playback queue in Redis."""
    try:
        song = get_track(item_id)

        # Add the song to the Redis queue
        add_to_queue_redis(song)

        # Call the WebSocket function to notify clients of the updated queue
        background_tasks.add_task(send_queue)

        return {"message": f"Added {song.title} to the playback queue."}

    except PlexApiException as e:
        raise HTTPException(status_code=500, detail=f"Plex error: {e}")
    except HTTPException as e:
        # Ensure 400 exceptions (like 'Song is already in the queue') are caught and returned correctly
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error adding item to queue: {e}")


@router.delete("/queue/{item_id}")
async def remove_from_queue(item_id: int, background_tasks: BackgroundTasks):
    """Remove an item from the Redis playback queue."""
    try:
        song = get_track(item_id)
        logging.debug(f"Removing song: {song.title}")
        result = remove_from_redis_queue(item_id)

        # Notify clients via WebSocket that the queue has been updated
        background_tasks.add_task(send_queue)

        return result

    except PlexApiException as e:
        raise HTTPException(status_code=500, detail=f"Plex error: {e}")
    except HTTPException as e:
        # Ensure 404 exceptions (like 'Song not found in the queue') are caught and returned correctly
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error removing item from queue: {e}")


@router.get("/queue")
def get_playback_queue():
    """Get the current playback queue from Redis."""
    try:
        queue = get_redis_queue()
        logging.debug(f"Current queue: {queue}")

        return [
            {
                "item_id": item["item_id"],
                "title": item["title"],
                "artist": item.get("artist", "Unknown Artist"),
                "duration": item.get("duration", "0:00"),
                "album_art": item.get("album_art", None)
            }
            for item in queue
        ]
    except Exception as e:
        logging.error(f"Error fetching the queue: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error fetching the queue: {str(e)}")


@router.post("/clear-queue")
async def clear_the_queue(background_tasks: BackgroundTasks):
    """Clear the Redis playback queue."""
    try:
        result = clear_redis_queue()

        # Notify clients via WebSocket that the queue has been cleared
        background_tasks.add_task(send_queue)

        return result

    except Exception as e:
        logging.error(f"Error clearing the queue: {e}")
        raise HTTPException(status_code=500, detail=f"Error clearing the queue: {e}")


@router.post("/play-queue")
async def play_queue(background_tasks: BackgroundTasks):
    """Start playing the entire queue on the active player."""
    background_tasks.add_task(play_queue_on_device)
    return {"message": "Playback started in the background."}


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


@router.get("/active-player")
def get_active_player_endpoint():
    """Get the active player details."""
    try:
        active_player = get_active_player()
        return {
            "player_id": active_player.machineIdentifier,
            "name": active_player.title,
            "device": active_player.device
        }
    except Exception as e:
        logging.error(f"Error fetching active player: {e}")
        raise HTTPException(status_code=500, detail=f"Error fetching active player: {e}")


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

    except HTTPException as e:
        # Catch HTTPException and let FastAPI handle it
        raise e

    except Exception as e:
        # Log unexpected errors and raise a 500 error
        logging.error(f"Error fetching current track: {e}")
        raise HTTPException(status_code=500, detail=f"Error fetching current track: {str(e)}")


@router.post("/clear-cache/{key}")
async def clear_redis_cache(key: str):
    """Clear a specific cache key in Redis."""
    try:
        result = clear_cache(key)
        return result
    except Exception as e:
        logging.error(f"Error clearing cache for key {key}: {e}")
        raise HTTPException(status_code=500, detail=f"Error clearing cache: {e}")


@router.get("/artist-image/{artist_id}")
def get_artist_image(artist_id: int):
    """Fetch and proxy the artist image from Plex."""
    try:
        # Call the combined function to get the artist image
        response = fetch_art(artist_id, "artist")

        # Return the image as a streaming response
        return StreamingResponse(response.iter_content(chunk_size=1024), media_type="image/jpeg")

    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching artist image: {e}")


@router.get("/album-art/{album_id}")
def get_album_art(album_id: int):
    """Fetch and proxy the album art from Plex."""
    try:
        # Call the combined function to get the album art
        response = fetch_art(album_id, "album")

        # Return the image as a streaming response
        return StreamingResponse(response.iter_content(chunk_size=1024), media_type="image/jpeg")

    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching album art: {e}")
