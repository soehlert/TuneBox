"""Define our routes for music based API endpoints."""

import logging

from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import StreamingResponse
from plexapi.exceptions import PlexApiException

from backend.services.plex import (
    fetch_albums_for_artist,
    fetch_all_artists,
    fetch_art,
    fetch_tracks_for_album,
    get_active_player,
    get_all_players,
    get_current_playing_track,
    get_track,
    play_queue_on_device,
    search_music,
    stop_playback,
)
from backend.services.redis import (
    add_to_queue_redis,
    clear_cache,
    clear_redis_queue,
    get_redis_queue,
    remove_from_redis_queue,
)
from backend.websockets import send_queue

router = APIRouter(prefix="/api/music", tags=["Music"])
logger = logging.getLogger(__name__)


@router.post("/queue/{item_id}")
async def add_to_queue(item_id: int, background_tasks: BackgroundTasks):
    """Add an item to the playback queue in Redis.

    Returns:
        A message that says we added to the queue.
    """
    try:
        song = get_track(item_id)

        add_to_queue_redis(song)

        background_tasks.add_task(send_queue)

    except PlexApiException as e:
        raise HTTPException(status_code=500, detail=f"Plex error: {e}") from e
    except HTTPException:
        # Ensure 400 exceptions (like 'Song is already in the queue') are caught and returned correctly
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error adding item to queue: {e}") from e
    else:
        return {"message": f"Added {song.title} to the playback queue."}


@router.delete("/queue/{item_id}")
async def remove_from_queue(item_id: int, background_tasks: BackgroundTasks):
    """Remove an item from the Redis playback queue.

    Returns:
        Removal of track.
    """
    try:
        song = get_track(item_id)
        logger.debug("Removing song: %s", song.title)
        result = remove_from_redis_queue(item_id)

        background_tasks.add_task(send_queue)

    except PlexApiException as e:
        raise HTTPException(status_code=500, detail=f"Plex error: {e}") from e
    except HTTPException:
        # Ensure 404 exceptions (like 'Song not found in the queue') are caught and returned correctly
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error removing item from queue: {e}") from e
    else:
        return result


@router.get("/queue")
def get_playback_queue():
    """Get the current playback queue from Redis.

    Returns:
        A list of dicts of track objects.
    """
    try:
        queue = get_redis_queue()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching the queue: {e!s}") from e
    else:
        return [
            {
                "item_id": item["item_id"],
                "title": item["title"],
                "artist": item.get("artist", "Unknown Artist"),
                "duration": item.get("duration", "0:00"),
                "album_art": item.get("album_art", None),
            }
            for item in queue
        ]


@router.post("/clear-queue")
async def clear_the_queue(background_tasks: BackgroundTasks):
    """Clear the Redis playback queue.

    Returns:
        The clearing of the queue.
    """
    try:
        result = clear_redis_queue()

        background_tasks.add_task(send_queue)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error clearing the queue: {e}") from e
    else:
        return result


@router.post("/play-queue")
async def play_queue(background_tasks: BackgroundTasks):
    """Start playing the entire queue on the active player.

    Returns:
        A message where we have started the queue.
    """
    background_tasks.add_task(play_queue_on_device)
    return {"message": "Playback started in the background."}


@router.post("/stop-queue")
async def stop_queue(background_tasks: BackgroundTasks):
    """Stop playback on the active player.

    Returns:
        The stopping of the playback.
    """
    result = stop_playback()
    background_tasks.add_task(send_queue)
    return result


# Fetch all artists
@router.get("/artists")
def get_all_artists():
    """Fetch a list of all artists.

    Returns:
        All artists.
    """
    try:
        return fetch_all_artists()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching artists: {e}") from e


# Fetch albums for a specific artist
@router.get("/artists/{artist_id}/albums")
def get_albums_for_artist(artist_id: int):
    """Fetch albums for a specific artist by ID.

    Returns:
        All the albums for a given artist.
    """
    try:
        return fetch_albums_for_artist(artist_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching albums for artist {artist_id}: {e}") from e


# Fetch tracks for a specific album
@router.get("/albums/{album_id}/tracks")
def get_tracks_for_album(album_id: int):
    """Fetch tracks for a specific album by ID.

    Returns:
        Tracks for a given album.
    """
    try:
        return fetch_tracks_for_album(album_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching tracks for album {album_id}: {e}") from e


# Search for artists, albums, or tracks
@router.get("/search")
def search_music_endpoint(query: str):
    """Search for music in the Plex library.

    Returns:
        Search results.
    """
    try:
        return search_music(query)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error searching music library: {e}") from e


# Fetch the list of available playback devices (players)
@router.get("/players")
def get_players():
    """Get the list of available playback devices (players).

    Returns:
        A list of all available playback devices.
    """
    try:
        players = get_all_players()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching players: {e}") from e
    else:
        return players


@router.get("/active-player")
def get_active_player_endpoint():
    """Get the active player details.

    Returns:
        The active player details.
    """
    try:
        active_player = get_active_player()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching active player: {e}") from e
    else:
        return {
            "player_id": active_player.machineIdentifier,
            "name": active_player.title,
            "device": active_player.device,
        }


@router.get("/now-playing")
def get_current_playing():
    """Get the currently playing track.

    Returns:
        The currently playing track.
    """
    try:
        current_track = get_current_playing_track()
        logger.debug("Current playing track: %s", current_track)
        if not current_track:
            raise HTTPException(status_code=404, detail="No track is currently playing")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching current track: {e!s}") from e
    else:
        return {"current_track": current_track}


@router.post("/clear-cache/{key}")
async def clear_redis_cache(key: str):
    """Clear a specific cache key in Redis.

    Returns:
        A clear redis cache.
    """
    try:
        result = clear_cache(key)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error clearing cache: {e}") from e
    else:
        return result


@router.get("/artist-image/{artist_id}")
def get_artist_image(artist_id: int):
    """Fetch and proxy the artist image from Plex.

    Returns:
        The artist image from Plex in streaming response format.
    """
    try:
        response = fetch_art(artist_id, "artist")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching artist image: {e}") from e
    else:
        return StreamingResponse(response.iter_content(chunk_size=1024), media_type="image/jpeg")


@router.get("/album-art/{album_id}")
def get_album_art(album_id: int):
    """Fetch and proxy the album art from Plex.

    Returns:
        Album art from Plex in streaming response format.
    """
    try:
        response = fetch_art(album_id, "album")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching album art: {e}") from e
    else:
        return StreamingResponse(response.iter_content(chunk_size=1024), media_type="image/jpeg")
