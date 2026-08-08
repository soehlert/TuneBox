"""Define our routes for music based API endpoints."""

import asyncio
import logging

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, Response, Header
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from plexapi.exceptions import PlexApiException

from backend.config import settings
from backend.services.plex import (
    fetch_accessible_plex_servers,
    fetch_albums_for_artist,
    fetch_all_artists,
    fetch_all_albums,
    fetch_all_genres,
    fetch_albums_by_genre,
    fetch_all_decades,
    fetch_albums_by_decade,
    fetch_art,
    fetch_art_bytes,
    fetch_tracks_for_album,
    get_active_player,
    get_all_players,
    get_current_playing_track,
    get_target_plex_connection,
    get_track,
    play_queue_on_device,
    search_music,
    search_music_on_server,
    stop_playback,
    pause_playback,
    skip_current_track,
    fetch_playlists,
    seed_queue_from_playlist,
)
from backend.services.redis import (
    add_to_queue_redis,
    clear_cache,
    clear_redis_queue,
    get_redis_queue,
    get_playback_history,
    move_to_top_redis_queue,
    remove_from_redis_queue,
    reorder_redis_queue,
    is_autoplay_enabled,
    set_autoplay_enabled,
)
from backend.websockets import send_current_playing, send_queue

router = APIRouter(prefix="/api/music", tags=["Music"])
logger = logging.getLogger(__name__)


class QueueReorderRequest(BaseModel):
    from_index: int
    to_index: int


class QueueMoveTopRequest(BaseModel):
    from_index: int


class QueueAddRequest(BaseModel):
    server_id: str | None = None
    server_name: str | None = None
    username: str | None = None


class AutoplayToggleRequest(BaseModel):
    enabled: bool


@router.post("/queue/reorder")
async def reorder_queue(
    payload: QueueReorderRequest,
    background_tasks: BackgroundTasks,
    x_admin_token: str | None = Header(None),
):
    """Reorder an item in the Redis playback queue (restricted to admin)."""
    if not settings.admin_token or x_admin_token != settings.admin_token:
        raise HTTPException(status_code=401, detail="Unauthorized host operation.")

    try:
        result = reorder_redis_queue(payload.from_index, payload.to_index)
        background_tasks.add_task(send_queue)
        return result
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve)) from ve
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reordering queue: {e}") from e


@router.post("/queue/move-top")
async def move_queue_top(
    payload: QueueMoveTopRequest,
    background_tasks: BackgroundTasks,
    x_admin_token: str | None = Header(None),
):
    """Move an item to index 1 (next track up) in the playback queue (restricted to admin)."""
    if not settings.admin_token or x_admin_token != settings.admin_token:
        raise HTTPException(status_code=401, detail="Unauthorized host operation.")

    try:
        result = move_to_top_redis_queue(payload.from_index)
        background_tasks.add_task(send_queue)
        return result
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve)) from ve
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error moving track to top of queue: {e}") from e


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
        username = payload.username if payload else None

        t_plex = get_target_plex_connection(server_id)
        song = t_plex.fetchItem(item_id)

        all_servers = fetch_accessible_plex_servers() if (server_id and not settings.testing) else []
        target_res = next((s for s in all_servers if s["server_id"] == server_id), None)

        s_name = server_name or (target_res.get("name") if target_res else settings.plex_server_name or "plex-so")
        
        codec = ""
        bitrate = 0
        if getattr(song, "media", None) and len(song.media) > 0:
            m = song.media[0]
            codec = (getattr(m, "audioCodec", "") or getattr(m, "container", "") or "").upper()
            bitrate = getattr(m, "bitrate", 0) or 0

        is_lossless = bool(codec and ("FLAC" in codec or "ALAC" in codec or "WAV" in codec))
        quality_score = 1000000 if is_lossless else (bitrate or 256)
        quality_str = f"{codec} {bitrate}kbps (Lossless)" if is_lossless else f"{codec or 'MP3'} {bitrate or 320}kbps"

        logger.info(
            "[Quality Selector] Queued track '%s' by '%s' from library '%s' | Audio Quality: %s (Quality Score: %d)",
            song.title,
            getattr(song, "grandparentTitle", getattr(song, "artist", "Unknown Artist")),
            s_name,
            quality_str,
            quality_score
        )

        add_to_queue_redis(
            song,
            server_id=server_id,
            server_name=s_name,
            server_token=target_res.get("access_token") if target_res else None,
            server_address=getattr(t_plex, "_baseurl", target_res.get("server_url") if target_res else None),
            added_by=username,
        )

        if username:
            from backend.services.stats import increment_adds
            increment_adds(username)

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
async def remove_from_queue(
    item_id: int,
    background_tasks: BackgroundTasks,
    x_admin_token: str | None = Header(None),
):
    """Remove an item from the Redis playback queue.

    Returns:
        Removal of track.
    """
    if not settings.admin_token or x_admin_token != settings.admin_token:
        raise HTTPException(status_code=401, detail="Unauthorized: Invalid admin token")
    try:
        song = get_track(item_id)
        logger.debug("Removing song: %s", song.title)
        
        # Check if the song being removed is the currently playing track (index 0)
        queue_before = get_redis_queue()
        is_active = len(queue_before) > 0 and queue_before[0]["item_id"] == item_id
        
        result = remove_from_redis_queue(item_id)

        if is_active:
            from backend.websockets import reset_skip_votes
            await reset_skip_votes()

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


@router.get("/queue/history")
def get_queue_history():
    """Get recent playback history from Redis (up to 20 tracks)."""
    try:
        return get_playback_history()
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error fetching playback history: {e!s}"
        ) from e


@router.post("/clear-queue")
async def clear_the_queue(background_tasks: BackgroundTasks):
    """Clear the Redis playback queue.

    Returns:
        The clearing of the queue.
    """
    try:
        result = clear_redis_queue()

        from backend.websockets import reset_skip_votes
        await reset_skip_votes()
        await send_queue()
        await send_current_playing()

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error clearing the queue: {e}"
        ) from e
    else:
        return result


@router.post("/stop-queue")
async def stop_the_queue(background_tasks: BackgroundTasks, x_admin_token: str | None = Header(None)):
    """Stop active playback, clear now playing, and drain the entire playback queue including the active track."""
    if not settings.admin_token or x_admin_token != settings.admin_token:
        raise HTTPException(status_code=401, detail="Unauthorized: Invalid admin token")
    try:
        from backend.services.plex import stop_playback, track_time_tracker
        from backend.services.redis import clear_cache, get_redis_cache_client

        try:
            stop_playback()
        except Exception as p_ex:
            logger.debug("Failed to issue player stop: %s", p_ex)

        track_time_tracker.stop()

        clear_cache("now_playing")
        try:
            get_redis_cache_client().delete("now_playing")
        except Exception:
            pass

        result = clear_redis_queue(force_all=True)

        from backend.websockets import reset_skip_votes
        await reset_skip_votes()
        await send_queue()
        await send_current_playing()
        return {"message": "Playback stopped and entire queue cleared successfully."}

    except Exception as e:
        logger.warning("Error stopping queue: %s", e)
        raise HTTPException(
            status_code=500, detail=f"Error stopping queue: {e}"
        ) from e


@router.post("/play-queue")
async def play_queue(background_tasks: BackgroundTasks):
    """Start playing the entire queue on the active player."""
    try:
        player = get_active_player()
        if not player:
            raise HTTPException(
                status_code=400,
                detail="No Plex playback player selected. Please select an active player in Settings.",
            )
    except PlexApiException as pae:
        raise HTTPException(
            status_code=400,
            detail="No Plex playback player selected or reachable. Please select an active player in Settings.",
        ) from pae
    except HTTPException:
        raise
    except Exception as e:
        if "Playback control is disabled" in str(e):
            raise HTTPException(
                status_code=400,
                detail="No Plex playback player selected. Please select an active player in Settings.",
            ) from e
        raise HTTPException(
            status_code=500, detail=f"Error checking active player: {e}"
        ) from e

    background_tasks.add_task(play_queue_on_device)
    return {"message": "Playback started in the background."}


@router.post("/pause")
async def pause_queue(background_tasks: BackgroundTasks):
    """Pause or resume playback on active player without clearing queue or now_playing track."""
    result = pause_playback()
    background_tasks.add_task(send_current_playing)
    return result





@router.post("/skip")
async def skip_track(
    background_tasks: BackgroundTasks,
    x_admin_token: str | None = Header(None),
):
    """Skip the currently playing track. If x_admin_token is supplied, forces an immediate skip."""
    if x_admin_token and x_admin_token != settings.admin_token:
        raise HTTPException(status_code=401, detail="Unauthorized host operation.")

    from backend.websockets import reset_skip_votes  # noqa: PLC0415
    await reset_skip_votes()

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


# Fetch all unique albums across music library
@router.get("/all-albums")
def get_all_albums_endpoint():
    """Fetch all unique albums from local SQLite index."""
    try:
        from backend.services.library import get_indexed_albums
        return get_indexed_albums()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching all albums: {e}") from e


# Fetch music genres with album counts
@router.get("/genres")
def get_genres_endpoint():
    """Fetch all music genres with album counts from SQLite."""
    try:
        from backend.services.library import get_all_genres_db
        return get_all_genres_db()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching genres: {e}") from e


# Fetch albums by genre
@router.get("/genres/{genre_name:path}/albums")
def get_albums_by_genre_endpoint(genre_name: str):
    """Fetch all albums matching a specific genre."""
    try:
        from backend.services.library import get_albums_by_genre_db
        return get_albums_by_genre_db(genre_name)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching albums for genre {genre_name}: {e}") from e


# Fetch decade breakdown with album counts
@router.get("/decades")
def get_decades_endpoint():
    """Fetch decade breakdown with album counts."""
    try:
        return fetch_all_decades()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching decades: {e}") from e


# Fetch albums by decade range
@router.get("/decades/{year_start}/{year_end}/albums")
def get_albums_by_decade_endpoint(year_start: int, year_end: int):
    """Fetch all albums released within a specific decade year range."""
    try:
        return fetch_albums_by_decade(year_start, year_end)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching albums for decade {year_start}-{year_end}: {e}") from e


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


# Add entire album to queue
@router.post("/albums/{album_id}/add-to-queue")
async def add_album_to_queue_endpoint(
    album_id: int,
    background_tasks: BackgroundTasks,
    server_id: str | None = None,
    username: str | None = None,
    x_client_id: str | None = Header(None),
):
    """Add all tracks of an album to the Redis queue in order."""
    try:
        album_data = fetch_tracks_for_album(album_id, server_id=server_id)
        tracks = album_data.get("tracks", [])
        if not tracks:
            raise HTTPException(status_code=404, detail="No tracks found for album.")

        added_count = 0
        added_by = username or "Guest"

        for t in tracks:
            item_id = t.get("track_id")
            song = get_track(item_id, server_id=server_id)
            add_to_queue_redis(song, server_id=server_id, added_by=added_by)
            added_count += 1
            if added_by and added_by != "Guest":
                from backend.services.stats import increment_adds
                increment_adds(added_by)

        from backend.websockets import send_current_playing, send_queue
        await send_queue()
        await send_current_playing()

        return {
            "message": "Album added to queue successfully.",
            "added_count": added_count,
            "album_title": album_data.get("album_title"),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error adding album {album_id} to queue: {e}"
        ) from e


# Search for artists, albums, or tracks
@router.get("/search")
def search_music_endpoint(query: str):
    """Search for music instantly in SQLite library database."""
    try:
        from backend.services.library import search_music_db
        return search_music_db(query)
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
    """Search for music instantly in local SQLite library database."""
    try:
        from backend.services.library import search_music_db
        return search_music_db(query)
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error searching music library: {e}"
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
def get_artist_image(artist_id: int | str, request: Request, server_id: str | None = None):
    """Fetch and proxy the artist photo from Plex."""
    try:
        from backend.services.library import get_art_source_info
        _, _, rating_key = get_art_source_info(artist_id, "artist")
    except Exception:
        rating_key = None

    etag = f'"artist-{artist_id}-{rating_key or "default"}-{server_id or "primary"}"'
    headers = {
        "Cache-Control": "public, max-age=31536000, immutable",
        "ETag": etag,
    }
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=headers)

    content_bytes, media_type = fetch_art_bytes(artist_id, "artist", server_id=server_id)
    return Response(content=content_bytes, media_type=media_type, headers=headers)


@router.get("/album-art/{album_id}")
def get_album_art(album_id: int | str, request: Request, server_id: str | None = None):
    """Fetch and proxy the album art from Plex."""
    try:
        from backend.services.library import get_art_source_info
        _, _, rating_key = get_art_source_info(album_id, "album")
    except Exception:
        rating_key = None

    etag = f'"album-{album_id}-{rating_key or "default"}-{server_id or "primary"}-v4"'
    headers = {
        "Cache-Control": "public, max-age=31536000, immutable",
        "ETag": etag,
    }
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=headers)

    content_bytes, media_type = fetch_art_bytes(album_id, "album", server_id=server_id)
    return Response(content=content_bytes, media_type=media_type, headers=headers)


@router.get("/track-art/{track_id}")
def get_track_art(track_id: int | str, request: Request, server_id: str | None = None):
    """Fetch and proxy the track art from Plex."""
    try:
        from backend.services.library import get_art_source_info
        _, _, rating_key = get_art_source_info(track_id, "track")
    except Exception:
        rating_key = None

    etag = f'"track-{track_id}-{rating_key or "default"}-{server_id or "primary"}"'
    headers = {
        "Cache-Control": "public, max-age=31536000, immutable",
        "ETag": etag,
    }
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=headers)

    content_bytes, media_type = fetch_art_bytes(track_id, "track", server_id=server_id)
    return Response(content=content_bytes, media_type=media_type, headers=headers)

    try:
        response = fetch_art(track_id, "track", server_id=server_id)
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


@router.get("/playlists")
def get_playlists(x_admin_token: str | None = Header(None)):
    """Fetch user playlists from Plex (restricted to admin)."""
    if not settings.admin_token or x_admin_token != settings.admin_token:
        raise HTTPException(status_code=401, detail="Unauthorized: Invalid admin token")
    try:
        return fetch_playlists()
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error fetching playlists: {e}"
        ) from e


@router.post("/playlists/{playlist_id}/seed")
async def seed_playlist(
    playlist_id: int,
    background_tasks: BackgroundTasks,
    count: int = 10,
    x_admin_token: str | None = Header(None),
):
    """Import, shuffle, and add tracks from a Plex playlist to the queue (restricted to admin)."""
    if not settings.admin_token or x_admin_token != settings.admin_token:
        raise HTTPException(status_code=401, detail="Unauthorized: Invalid admin token")
    try:
        result = seed_queue_from_playlist(playlist_id, count=count)
        # Notify WebSocket clients of queue change
        background_tasks.add_task(send_queue)
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error seeding playlist: {e}"
        ) from e


@router.get("/autoplay")
def get_autoplay_state():
    """Get the current autoplay enabled status."""
    return {"autoplay_enabled": is_autoplay_enabled()}


@router.post("/autoplay")
def set_autoplay_state(req: AutoplayToggleRequest, x_admin_token: str | None = Header(None)):
    """Set the autoplay enabled status (restricted to admin)."""
    if not settings.admin_token or x_admin_token != settings.admin_token:
        raise HTTPException(status_code=401, detail="Unauthorized: Invalid admin token")
    set_autoplay_enabled(req.enabled)
    return {"autoplay_enabled": is_autoplay_enabled()}


