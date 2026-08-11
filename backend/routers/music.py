"""Define our routes for music based API endpoints."""

import asyncio
import logging
import threading

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request, Response, Header
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from plexapi.exceptions import PlexApiException

from backend.config import settings
from backend.services import library, plex, redis, stats
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
    track_time_tracker,
    rate_track_in_plex,
    _failed_connection_cache,
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
    get_redis_cache_client,
)
from backend.services.library import (
    get_art_source_info,
    get_indexed_artists,
    get_albums_for_artist_db,
    get_indexed_albums,
    get_recently_added_albums,
    get_all_genres_db,
    get_albums_by_genre_db,
    get_all_decades_db,
    get_albums_by_decade_db,
    get_tracks_for_album_db,
    search_music_db,
    _ART_SOURCE_MEM_CACHE,
    get_all_art_sources,
    is_track_on_primary_server,
    rate_track_db,
)
from backend.services.stats import increment_adds
from backend.services.indexer import index_server, sync_all_servers
from backend.websockets import send_current_playing, send_queue, reset_skip_votes, current_indexing_status
import backend.websockets as ws

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

        if not server_id and not settings.testing:
            try:
                _, res_sid, _ = get_art_source_info(item_id, "track")
                if res_sid:
                    server_id = res_sid
            except Exception as res_ex:
                logger.debug("Could not resolve server_id for queue item %s: %s", item_id, res_ex)

        song = get_track(item_id, server_id=server_id)
        if not getattr(song, "server_id", None) and server_id:
            setattr(song, "server_id", server_id)

        t_plex = get_target_plex_connection(server_id)

        all_servers = fetch_accessible_plex_servers() if (server_id and not settings.testing) else []
        target_res = next((s for s in all_servers if s.get("server_id") == server_id or str(s.get("name")).lower() == str(server_id).lower()), None)

        s_name = server_name or (target_res.get("name") if target_res else getattr(song, "server_name", None) or settings.plex_server_name or "plex-so")
        
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
    item_id: int | str,
    background_tasks: BackgroundTasks,
    x_admin_token: str | None = Header(None),
):
    """Remove an item from the Redis playback queue.

    Returns:
        Removal of track.
    """
    if settings.admin_token and x_admin_token != settings.admin_token:
        raise HTTPException(status_code=401, detail="Unauthorized: Invalid admin token")
    try:
        # Check if the song being removed is the currently playing track (index 0)
        queue_before = get_redis_queue()
        is_active = len(queue_before) > 0 and str(queue_before[0].get("item_id")) == str(item_id)
        
        result = remove_from_redis_queue(item_id)

        if is_active:
            await reset_skip_votes()

        background_tasks.add_task(send_queue)
        return result

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error removing item from queue: {e}"
        ) from e


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
    """Clear the entire Redis playback queue and stop active playback.

    Returns:
        The clearing of the queue.
    """
    try:
        try:
            stop_playback()
        except Exception as stop_ex:
            logger.debug("Error stopping playback during clear_the_queue: %s", stop_ex)

        track_time_tracker.stop()
        result = clear_redis_queue(force_all=True)
        clear_cache("now_playing")

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

    await reset_skip_votes()

    result = skip_current_track()
    background_tasks.add_task(send_queue)
    background_tasks.add_task(send_current_playing)
    return result


# Fetch all artists
@router.get("/artists")
def get_all_artists():
    """Fetch a list of all artists from enabled servers in SQLite."""
    try:
        if settings.testing:
            return fetch_all_artists()
        return get_indexed_artists()
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error fetching artists: {e}"
        ) from e


# Fetch albums for a specific artist
@router.get("/artists/{artist_id}/albums")
def get_albums_for_artist(artist_id: int, server_id: str | None = None):
    """Fetch albums for a specific artist by ID from enabled servers in SQLite."""
    try:
        if settings.testing:
            return fetch_albums_for_artist(artist_id, server_id=server_id)
        return get_albums_for_artist_db(artist_id)
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error fetching albums for artist {artist_id}: {e}"
        ) from e


# Fetch all unique albums across music library
@router.get("/all-albums")
def get_all_albums_endpoint():
    """Fetch all unique albums from local SQLite index."""
    try:
        return get_indexed_albums()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching all albums: {e}") from e


@router.get("/albums/recently-added")
def get_recently_added_endpoint(limit: int = 50):
    """Fetch recently added albums across all currently enabled servers."""
    try:
        return get_recently_added_albums(limit=limit)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching recently added albums: {e}") from e


# Fetch music genres with album counts
@router.get("/genres")
def get_genres_endpoint():
    """Fetch all music genres with album counts from SQLite."""
    try:
        return get_all_genres_db()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching genres: {e}") from e


# Fetch albums by genre
@router.get("/genres/{genre_name:path}/albums")
def get_albums_by_genre_endpoint(genre_name: str):
    """Fetch all albums matching a specific genre."""
    try:
        return get_albums_by_genre_db(genre_name)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching albums for genre {genre_name}: {e}") from e


# Fetch decade breakdown with album counts
@router.get("/decades")
def get_decades_endpoint():
    """Fetch decade breakdown with album counts from enabled servers in SQLite."""
    try:
        if settings.testing:
            return fetch_all_decades()
        return get_all_decades_db()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching decades: {e}") from e


# Fetch albums by decade range
@router.get("/decades/{year_start}/{year_end}/albums")
def get_albums_by_decade_endpoint(year_start: int, year_end: int):
    """Fetch all albums released within a specific decade year range from enabled servers in SQLite."""
    try:
        if settings.testing:
            return fetch_albums_by_decade(year_start, year_end)
        return get_albums_by_decade_db(year_start, year_end)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching albums for decade {year_start}-{year_end}: {e}") from e


# Fetch tracks for a specific album
@router.get("/albums/{album_id}/tracks")
def get_tracks_for_album(album_id: int, server_id: str | None = None):
    """Fetch tracks for a specific album by ID from enabled servers in SQLite."""
    try:
        if settings.testing:
            return fetch_tracks_for_album(album_id, server_id=server_id)
        try:
            plex.sync_album_ratings_from_plex(album_id)
        except Exception:
            pass
        res = get_tracks_for_album_db(album_id)
        if res is None:
            raise HTTPException(status_code=404, detail="Album tracks not found")
        return res
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching tracks for album {album_id}: {e}") from e


# Add entire album to queue
@router.post("/albums/{album_id}/add-to-queue")
async def add_album_to_queue_endpoint(
    album_id: int,
    background_tasks: BackgroundTasks,
    server_id: str | None = None,
    username: str | None = None,
):
    """Fetch tracks for album from SQLite index and add to playback queue."""
    try:
        if settings.testing:
            album_data = fetch_tracks_for_album(album_id, server_id=server_id)
        else:
            album_data = get_tracks_for_album_db(album_id) or fetch_tracks_for_album(album_id, server_id=server_id)
        tracks = album_data.get("tracks", [])
        if not tracks:
            raise HTTPException(status_code=404, detail="No tracks found for album.")

        added_count = 0
        added_by = username or "Guest"

        for t in tracks:
            item_id = t.get("server_track_id") or t.get("rating_key") or t.get("item_id") or t.get("track_id")
            t_server_id = t.get("server_id") or server_id
            song = get_track(item_id, server_id=t_server_id)
            try:
                add_to_queue_redis(song, server_id=t_server_id, added_by=added_by)
                added_count += 1
                if added_by and added_by != "Guest":
                    increment_adds(added_by)
            except HTTPException as hex_err:
                if hex_err.status_code == 400 and "already in the queue" in str(hex_err.detail).lower():
                    continue
                raise

        await ws.send_queue()
        await ws.send_current_playing()

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
        if settings.testing:
            return search_music(query)
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


@router.get("/indexing-status")
def get_indexing_status():
    """Fetch live library indexing status."""
    try:
        return current_indexing_status
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error fetching indexing status: {e}"
        ) from e


@router.post("/reindex")
def trigger_reindex(server_id: str | None = Query(None)):
    """Clear negative connection caches and trigger re-indexing for a specific server or all enabled servers."""
    try:
        _failed_connection_cache.clear()
    except Exception:
        pass

    try:
        _ART_SOURCE_MEM_CACHE.clear()
    except Exception:
        pass

    def _bg_reindex():
        try:
            if server_id:
                servers = fetch_accessible_plex_servers()
                srv = next((s for s in servers if s.get("server_id") == server_id or str(s.get("name")).lower() == str(server_id).lower()), None)
                if srv:
                    index_server(srv, force_full=True)
                else:
                    sync_all_servers(force_full=True)
            else:
                sync_all_servers(force_full=True)
        except Exception as ex:
            logger.exception("Error in background reindex task: %s", ex)

    threading.Thread(target=_bg_reindex, daemon=True).start()
    return {"status": "ok", "message": "Re-indexing started in background."}


@router.get("/unified-search")
async def unified_search_endpoint(query: str, server_ids: str | None = None):
    """Search for music instantly in local SQLite library database."""
    try:
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
    """Fetch and proxy the artist image from Plex."""
    content_bytes, media_type = fetch_art_bytes(artist_id, "artist", server_id=server_id)
    is_fallback = not content_bytes or len(content_bytes) < 100 or content_bytes.startswith(b"\x89PNG")
    if is_fallback:
        return Response(
            content=content_bytes,
            media_type=media_type,
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate, max-age=0",
                "Pragma": "no-cache",
                "Expires": "0",
            },
        )

    etag = f'"artist-{artist_id}-{len(content_bytes)}-{server_id or "primary"}"'
    headers = {
        "Cache-Control": "public, max-age=3600, must-revalidate",
        "ETag": etag,
    }
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=headers)

    return Response(content=content_bytes, media_type=media_type, headers=headers)


@router.get("/album-art/{album_id}")
def get_album_art(album_id: int | str, request: Request, server_id: str | None = None):
    """Fetch and proxy the album art from Plex."""
    content_bytes, media_type = fetch_art_bytes(album_id, "album", server_id=server_id)
    is_fallback = not content_bytes or len(content_bytes) < 100 or content_bytes.startswith(b"\x89PNG")
    if is_fallback:
        return Response(
            content=content_bytes,
            media_type=media_type,
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate, max-age=0",
                "Pragma": "no-cache",
                "Expires": "0",
            },
        )

    etag = f'"album-{album_id}-{len(content_bytes)}-{server_id or "primary"}"'
    headers = {
        "Cache-Control": "public, max-age=86400, must-revalidate",
        "ETag": etag,
    }
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=headers)

    return Response(content=content_bytes, media_type=media_type, headers=headers)


@router.get("/track-art/{track_id}")
def get_track_art(track_id: int | str, request: Request, server_id: str | None = None):
    """Fetch and proxy the track art from Plex."""
    if not server_id and not settings.testing:
        try:
            _, res_sid, _ = get_art_source_info(track_id, "track")
            if res_sid:
                server_id = res_sid
        except Exception:
            pass

    content_bytes, media_type = fetch_art_bytes(track_id, "track", server_id=server_id)
    is_fallback = not content_bytes or len(content_bytes) < 100 or content_bytes.startswith(b"\x89PNG")

    if is_fallback and not settings.testing:
        try:
            alb_sources = get_all_art_sources(track_id, "album")
            if alb_sources and alb_sources[0][0]:
                alb_bytes, alb_mime = fetch_art_bytes(track_id, "album", server_id=server_id)
                if alb_bytes and len(alb_bytes) > 100 and not alb_bytes.startswith(b"\x89PNG"):
                    content_bytes, media_type = alb_bytes, alb_mime
                    is_fallback = False
        except Exception as alb_art_ex:
            logger.debug("Album art fallback for track %s failed: %s", track_id, alb_art_ex)

    if is_fallback:
        return Response(
            content=content_bytes,
            media_type=media_type,
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate, max-age=0",
                "Pragma": "no-cache",
                "Expires": "0",
            },
        )

    etag = f'"track-{track_id}-{len(content_bytes)}-{server_id or "primary"}"'
    headers = {
        "Cache-Control": "public, max-age=86400, must-revalidate",
        "ETag": etag,
    }
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=headers)

    return Response(content=content_bytes, media_type=media_type, headers=headers)


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


class RateTrackRequest(BaseModel):
    rating: float


@router.post("/tracks/{track_id}/rate")
def rate_track_endpoint(
    track_id: int,
    payload: RateTrackRequest,
    x_admin_token: str | None = Header(None),
):
    """Rate a track (0.0 to 5.0 stars) in both SQLite database and Plex (restricted to admin and primary server)."""
    if not settings.admin_token or x_admin_token != settings.admin_token:
        raise HTTPException(status_code=401, detail="Unauthorized: Invalid admin token")

    if not library.is_track_on_primary_server(track_id):
        raise HTTPException(
            status_code=403,
            detail="Forbidden: Star rating is only supported for tracks on your primary server",
        )

    rating = max(0.0, min(5.0, float(payload.rating)))
    library.rate_track_db(track_id, rating)
    plex.rate_track_in_plex(track_id, rating)
    return {"status": "success", "track_id": track_id, "user_rating": rating}


