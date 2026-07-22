"""Define our routes for music based API endpoints."""

import asyncio
import logging

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from plexapi.exceptions import PlexApiException

from backend.services.plex import (
    fetch_accessible_plex_servers,
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
    search_music_on_server,
    stop_playback,
    skip_current_track,
)
from backend.services.redis import (
    add_to_queue_redis,
    clear_cache,
    clear_redis_queue,
    get_redis_queue,
    remove_from_redis_queue,
)
from backend.websockets import send_current_playing, send_queue

router = APIRouter(prefix="/api/music", tags=["Music"])
logger = logging.getLogger(__name__)


class QueueAddRequest(BaseModel):
    server_id: str | None = None
    server_name: str | None = None


@router.post("/queue/{item_id}")
async def add_to_queue(
    item_id: int,
    background_tasks: BackgroundTasks,
    payload: QueueAddRequest | None = None,
):
    """Add an item to the playback queue in Redis with optional server connection info.

    Returns:
        A message that says we added to the queue.
    """
    try:
        server_id = payload.server_id if payload else None
        server_name = payload.server_name if payload else None

        if server_id and not settings.testing:
            all_servers = fetch_accessible_plex_servers()
            target_res = next((s for s in all_servers if s["server_id"] == server_id), None)
            if target_res and target_res.get("server_url"):
                from plexapi.server import PlexServer
                t_token = target_res.get("access_token") or settings.plex_token
                t_plex = PlexServer(target_res["server_url"], t_token, timeout=5)
                song = t_plex.fetchItem(item_id)
                add_to_queue_redis(
                    song,
                    server_id=server_id,
                    server_name=server_name or target_res.get("name"),
                    server_token=t_token,
                    server_address=target_res.get("server_url"),
                )
            else:
                song = get_track(item_id)
                add_to_queue_redis(song, server_id=server_id, server_name=server_name)
        else:
            song = get_track(item_id)
            add_to_queue_redis(song, server_id=server_id, server_name=server_name)

        background_tasks.add_task(send_queue)

    except PlexApiException as e:
        raise HTTPException(status_code=500, detail=f"Plex error: {e}") from e
    except HTTPException:
        # Ensure 400 exceptions (like 'Song is already in the queue') are caught and returned correctly
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error adding item to queue: {e}"
        ) from e
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
        raise HTTPException(
            status_code=500, detail=f"Error removing item from queue: {e}"
        ) from e
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
        raise HTTPException(
            status_code=500, detail=f"Error fetching the queue: {e!s}"
        ) from e
    else:
        return [
            {
                "item_id": item["item_id"],
                "title": item["title"],
                "artist": item.get("artist", "Unknown Artist"),
                "duration": item.get("duration", "0:00"),
                "album_art": item.get("album_art", None),
                "server_id": item.get("server_id"),
                "server_name": item.get("server_name"),
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

        await send_queue()
        await send_current_playing()

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error clearing the queue: {e}"
        ) from e
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
    background_tasks.add_task(send_current_playing)
    return result


@router.post("/skip")
async def skip_track(background_tasks: BackgroundTasks):
    """Skip the currently playing track.
    
    Returns:
        A JSON message about skipping track.
    """
    result = skip_current_track()
    background_tasks.add_task(send_queue)
    background_tasks.add_task(send_current_playing)
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
        raise HTTPException(
            status_code=500, detail=f"Error fetching artists: {e}"
        ) from e


# Fetch albums for a specific artist
@router.get("/artists/{artist_id}/albums")
def get_albums_for_artist(artist_id: int, server_id: str | None = None):
    """Fetch albums for a specific artist by ID.

    Returns:
        All the albums for a given artist.
    """
    try:
        return fetch_albums_for_artist(artist_id, server_id=server_id)
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error fetching albums for artist {artist_id}: {e}"
        ) from e


# Fetch tracks for a specific album
@router.get("/albums/{album_id}/tracks")
def get_tracks_for_album(album_id: int, server_id: str | None = None):
    """Fetch tracks for a specific album by ID.

    Returns:
        Tracks for a given album.
    """
    try:
        return fetch_tracks_for_album(album_id, server_id=server_id)
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error fetching tracks for album {album_id}: {e}"
        ) from e


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
        raise HTTPException(
            status_code=500, detail=f"Error searching music library: {e}"
        ) from e


@router.get("/servers")
def get_accessible_servers():
    """Fetch all Plex Media Servers accessible to the user account."""
    try:
        return fetch_accessible_plex_servers()
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error fetching accessible servers: {e}"
        ) from e


@router.get("/unified-search")
async def unified_search_endpoint(query: str, server_ids: str | None = None):
    """Search for music across multiple selected Plex servers concurrently."""
    try:
        all_servers = fetch_accessible_plex_servers()
        if not all_servers:
            return search_music(query)

        target_servers = all_servers
        if server_ids:
            requested_ids = set(server_ids.split(","))
            target_servers = [s for s in all_servers if s["server_id"] in requested_ids]
            if not target_servers:
                target_servers = all_servers

        tasks = [asyncio.to_thread(search_music_on_server, s, query) for s in target_servers]
        results_nested = await asyncio.gather(*tasks, return_exceptions=True)

        combined_results = []
        for res in results_nested:
            if isinstance(res, list):
                combined_results.extend(res)

        return combined_results
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error executing unified search: {e}"
        ) from e


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
        raise HTTPException(
            status_code=500, detail=f"Error fetching players: {e}"
        ) from e
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
        raise HTTPException(
            status_code=500, detail=f"Error fetching active player: {e}"
        ) from e
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
        raise HTTPException(
            status_code=500, detail=f"Error fetching current track: {e!s}"
        ) from e
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
def get_artist_image(artist_id: int, request: Request):
    """Fetch and proxy the artist image from Plex.

    Returns:
        The artist image from Plex in streaming response format.
    """
    etag = f'"artist-{artist_id}"'
    headers = {
        "Cache-Control": "public, max-age=86400, stale-while-revalidate=604800",
        "ETag": etag,
    }
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=headers)

    try:
        response = fetch_art(artist_id, "artist")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error fetching artist image: {e}"
        ) from e
    else:
        return StreamingResponse(
            response.iter_content(chunk_size=1024), media_type="image/jpeg", headers=headers
        )


@router.get("/album-art/{album_id}")
def get_album_art(album_id: int, request: Request):
    """Fetch and proxy the album art from Plex.

    Returns:
        Album art from Plex in streaming response format.
    """
    etag = f'"album-{album_id}"'
    headers = {
        "Cache-Control": "public, max-age=86400, stale-while-revalidate=604800",
        "ETag": etag,
    }
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=headers)

    try:
        response = fetch_art(album_id, "album")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error fetching album art: {e}"
        ) from e
    else:
        return StreamingResponse(
            response.iter_content(chunk_size=1024), media_type="image/jpeg", headers=headers
        )


@router.get("/track-art/{track_id}")
def get_track_art(track_id: int, request: Request):
    """Fetch and proxy the track art from Plex.

    Returns:
        Track art from Plex in streaming response format.
    """
    etag = f'"track-{track_id}"'
    headers = {
        "Cache-Control": "public, max-age=86400, stale-while-revalidate=604800",
        "ETag": etag,
    }
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=headers)

    try:
        response = fetch_art(track_id, "track")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error fetching track art: {e}"
        ) from e
    else:
        return StreamingResponse(
            response.iter_content(chunk_size=1024), media_type="image/jpeg", headers=headers
        )
