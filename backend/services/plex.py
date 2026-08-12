import asyncio
import concurrent.futures
import json
import logging
import random
import re
import threading
import time
from functools import lru_cache

import requests
import urllib3
from fastapi import HTTPException
from plexapi.exceptions import PlexApiException
from plexapi.myplex import MyPlexAccount
from plexapi.server import PlexServer

from backend.config import settings
from backend.exceptions import PlexConnectionError
from backend.services.mock_data import MOCK_ALBUMS, MOCK_ARTISTS, MOCK_TRACKS
from backend.services.redis import (
    cache_data,
    clear_cache,
    get_cached_data,
    get_redis_queue,
    remove_from_redis_queue,
    add_to_history,
    is_autoplay_enabled,
    get_playback_history_ids,
    get_redis_cache_client,
    add_to_queue_redis,
    clear_redis_queue,
    get_artist_play_counts,
    get_album_play_counts,
    set_closing_time_mode,
    get_closing_time_mode,
)
from backend.utils import TrackTimeTracker, milliseconds_to_seconds
from backend.db.library_db import get_db_connection, get_latest_preseed_playlist_tracks, save_preseed_playlist_tracks
from backend.services.library import (
    get_art_source_info,
    get_albums_for_artist_db,
    get_tracks_for_album_db,
    search_music_db,
    get_all_art_sources,
    get_server_credentials,
    clear_art_source_cache,
    upsert_server,
    rating_key_to_track_id,
    track_id_to_rating_key,
    validate_track_id,
    get_tracks_by_vibe_db,
    get_available_vibes_db,
    find_closing_time_track_db,
)

HEARTBEAT_INTERVAL = 5
DRIFT_THRESHOLD = 8.0

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
for _log_name in ("plexapi", "plexapi.myplex", "plexapi.server", "urllib3", "urllib3.connectionpool", "requests"):
    logging.getLogger(_log_name).setLevel(logging.CRITICAL)


logger = logging.getLogger(__name__)

_SERVER_CREDENTIALS_CACHE: dict[str, tuple[str, str]] = {}

_ART_HTTP_SESSION = requests.Session()
_adapter = requests.adapters.HTTPAdapter(pool_connections=25, pool_maxsize=50)
_ART_HTTP_SESSION.mount("http://", _adapter)
_ART_HTTP_SESSION.mount("https://", _adapter)


track_time_tracker = TrackTimeTracker()
# Declare the global variable to manage playback state
playback_active = False
# Sentinel: title of the track the orchestrator just finished with an empty queue.
# Prevents check_plexamp_resync from restarting it after Plex is slow to transition.
_queue_finished_track: str | None = None
_cached_active_player = None
_cached_active_player_name = None
_resync_lock = asyncio.Lock()
_last_resync_time = 0.0


async def debounced_plexamp_resync(force_align: bool = False, min_interval: float = 2.0):
    """Run check_plexamp_resync with a minimum time interval to prevent concurrent network spam."""
    global _last_resync_time
    async with _resync_lock:
        now = time.time()
        if now - _last_resync_time < min_interval:
            logger.debug("Skipping PMS resync check (debounced within %.1fs)", min_interval)
            return
        _last_resync_time = now
        await check_plexamp_resync(force_align=force_align)


@lru_cache
def get_myplex_account():
    """Establish a connection to MyPlexAccount.

    Returns:
        MyPlexAccount instance.
    """
    if not settings.plex_token and not (
        settings.plex_username and settings.plex_password
    ):
        raise PlexConnectionError

    if settings.plex_token:
        return MyPlexAccount(token=settings.plex_token)
    return MyPlexAccount(
        username=settings.plex_username, password=settings.plex_password
    )


@lru_cache
def get_plex_connection():
    """Establish a connection to the Plex server via MyPlexAccount.

    Returns:
        A PlexServer instance to run our API calls against.
    """
    try:
        account = get_myplex_account()
        # Get the specific server by its name
        plex_server = account.resource(settings.plex_server_name).connect()
        logger.info("Connected to Plex server %s", plex_server)
    except Exception as e:
        raise PlexConnectionError(original_error=e) from e
    else:
        return plex_server


def invalidate_cached_player():
    """Clear cached active player handle so next call forces fresh discovery."""
    global _cached_active_player, _cached_active_player_name
    _cached_active_player = None
    _cached_active_player_name = None


def reinitialize_plex():
    """Clear cached connection and force connection reload without destroying active playback or queue."""
    global _cached_active_player, _cached_active_player_name
    get_myplex_account.cache_clear()
    get_plex_connection.cache_clear()
    _cached_active_player = None
    _cached_active_player_name = None
    try:
        clear_cache("artists")
        clear_cache("all_artists")
        clear_cache("accessible_plex_servers")
    except Exception as e:
        logger.debug("Failed to purge Redis cache on reinitialize: %s", e)
    logger.info("Plex connection cache cleared for reinitialization.")


def pre_warm_all_caches():
    """Trigger cache pre-warming for resources, artists, and artwork thumbnails in background."""
    try:
        # 1. Warm resources if plex token is configured
        if settings.plex_token:
            logger.info("Background warming Plex resources cache...")
            from backend.routers.auth import fetch_and_cache_resources  # noqa: PLC0415
            fetch_and_cache_resources(refresh=False)

        # 2. Warm artists for enabled servers
        if settings.plex_token:
            logger.info("Background warming Plex artists cache for enabled servers...")
            fetch_all_artists()

        # 3. Pre-warm ALL artist and album artwork thumbnails into Redis RAM in background
        try:
            conn = get_db_connection()
            art_rows = conn.execute("SELECT artist_id FROM artists").fetchall()
            alb_rows = conn.execute("SELECT album_id FROM albums").fetchall()
            conn.close()
            artist_ids = [r["artist_id"] for r in art_rows]
            album_ids = [r["album_id"] for r in alb_rows]
            if artist_ids or album_ids:
                logger.info("Triggering background artwork pre-warming for %d artists and %d albums into Redis...", len(artist_ids), len(album_ids))
                _prewarm_art_in_background("all", artist_ids, album_ids)
        except Exception as art_ex:
            logger.debug("Failed querying artwork IDs for pre-warming: %s", art_ex)

        logger.info("Background cache pre-warming complete.")
    except Exception as e:
        logger.error("Failed to pre-warm caches: %s", e)


def get_current_playing_track():
    """Fetch the currently playing track details from cache and the local tracker.

    Returns:
        The current track info or None if nothing is playing or stopped.
    """
    if not playback_active and not track_time_tracker.is_playing and track_time_tracker.state != "paused" and not get_redis_queue():
        return None

    cached_track = get_cached_data("now_playing")
    if not cached_track or not isinstance(cached_track, dict):
        return None

    # Ensure track_time_tracker is initialized for this track
    cached_title = cached_track.get("title")
    if cached_title and track_time_tracker.track_name != cached_title:
        track_time_tracker.track_name = cached_title
        track_time_tracker.state = cached_track.get("track_state", "playing")
        base_el = float(cached_track.get("elapsed_time", 0.0))
        upd_at = float(cached_track.get("updated_at", 0.0))
        if upd_at > 0 and track_time_tracker.state == "playing":
            track_time_tracker.accumulated_elapsed = base_el + max(time.time() - upd_at, 0)
            track_time_tracker.last_resume_time = time.time()
        else:
            track_time_tracker.accumulated_elapsed = base_el
            track_time_tracker.last_resume_time = None

    elapsed = track_time_tracker.elapsed_time
    total_time = float(cached_track.get("duration", 0))  # duration in seconds
    if total_time > 10000:
        total_time = milliseconds_to_seconds(total_time)

    # Safeguard bounds
    elapsed = max(elapsed, 0)
    elapsed = min(elapsed, total_time) if total_time > 0 else elapsed

    remaining_time = max(total_time - elapsed, 0) if total_time > 0 else 0
    if total_time > 0 and remaining_time <= 0:
        return None

    remaining_percentage = (remaining_time / total_time * 100) if total_time > 0 else 0
    item_id = cached_track.get("item_id")
    album_art = cached_track.get("album_art")
    if item_id and (not album_art or not album_art.startswith("/api/music/")):
        album_art = f"/api/music/track-art/{item_id}"

    track_state = (
        track_time_tracker.state
        if track_time_tracker.state in ("playing", "paused")
        else cached_track.get("track_state", "playing")
    )

    return {
        "item_id": cached_track.get("item_id"),
        "server_id": cached_track.get("server_id"),
        "album_id": cached_track.get("album_id"),
        "title": cached_track.get("title"),
        "artist": cached_track.get("artist"),
        "album": cached_track.get("album"),
        "album_art": album_art,
        "track_state": track_state,
        "total_time": total_time,
        "elapsed_time": elapsed,
        "remaining_time": remaining_time,
        "remaining_percentage": remaining_percentage,
    }


import backend.websockets as ws


def get_all_players():
    """Fetch all available Plex players.

    Returns:
        A list of all available Plex players.
    """
    if settings.testing:
        return [
            {
                "player_id": "mock_player_123",
                "name": settings.client_name or "Mock Jukebox Player",
                "device": "Mock Device",
            }
        ]

    plex = get_plex_connection()
    players = plex.clients()

    if not players:
        msg = "No active players found."
        raise PlexApiException(msg)

    return [
        {
            "player_id": player.machineIdentifier,
            "name": player.title,
            "device": player.device,
        }
        for player in players
    ]


def get_active_player(client_name: str | None = None):
    """Get the first active Plex player."""
    global _cached_active_player, _cached_active_player_name

    client_name = client_name or settings.client_name

    if not client_name or client_name.lower() in ("disabled", "none", "released", ""):
        raise PlexApiException("Playback control is disabled (no player configured or released).")

    if settings.testing:

        class MockPlayer:
            title = client_name or "Mock Jukebox Player"

            def playMedia(self, media):
                pass

            def play(self):
                pass

            def pause(self):
                pass

        return MockPlayer()

    if _cached_active_player and _cached_active_player_name == client_name:
        try:
            # Lightweight socket test: check machineIdentifier or timeline attribute
            _ = getattr(_cached_active_player, "machineIdentifier", None)
            return _cached_active_player
        except Exception:
            logger.info("Cached player '%s' connection is dead. Evicting cache.", client_name)
            invalidate_cached_player()

    # 1. Try resolving via local Plex Media Server client list (GDM)
    try:
        plex = get_plex_connection()
        players = plex.clients()
    except Exception as e:
        logger.debug("Failed to fetch local Plex players: %s", e)
        players = []

    if client_name:
        active_player = next((p for p in players if p.title == client_name), None)
        if active_player:
            logger.info("Found player '%s' locally via PMS.", client_name)
            _cached_active_player = active_player
            _cached_active_player_name = client_name
            return active_player

        # 2. Fallback to MyPlex resource resolution for remote/relayed players (e.g. Plexamp)
        try:
            logger.info(
                "Player '%s' not found locally. Querying MyPlex resources...",
                client_name,
            )
            account = get_myplex_account()
            player_resource = account.resource(client_name)
            active_player = player_resource.connect()
            logger.info(
                "Successfully connected to player '%s' via MyPlex.", client_name
            )
            _cached_active_player = active_player
            _cached_active_player_name = client_name
            return active_player
        except Exception as e:
            logger.warning(
                "Could not resolve player '%s' via MyPlex: %s", client_name, e
            )

    # 3. If no specific name was requested, or if specific name lookup failed, fallback to first available local player
    if players:
        active_player = players[0]
        logger.info(
            "Falling back to first available local player: %s", active_player.title
        )
        _cached_active_player = active_player
        _cached_active_player_name = active_player.title
        return active_player

    raise PlexApiException("No active Plex players found or resolvable.")


def get_track(track_id: int, server_id: str | None = None):
    """Get track object from Plex server by internal SQLite track_id."""
    target_server_id = server_id

    if settings.testing:
        found_track = None
        for album_id, tracks in MOCK_TRACKS.items():
            for t in tracks:
                if t["track_id"] == track_id:
                    found_track = t
                    break
            if found_track:
                break
        if found_track:

            class MockTrack:
                ratingKey = found_track["track_id"]
                title = found_track["title"]
                grandparentTitle = found_track["artist"]
                parentTitle = found_track["album"]
                duration = found_track["duration"] * 1000  # in ms
                thumb = f"/api/music/album-art/{album_id}"

            return MockTrack()
        raise HTTPException(status_code=404, detail="Track not found")

    resolved = track_id_to_rating_key(track_id)
    if not resolved:
        raise HTTPException(status_code=404, detail=f"Track {track_id} not found in library")
    rk_str, srv_id = resolved
    item_id_val = int(rk_str) if rk_str.isdigit() else rk_str
    target_server_id = target_server_id or srv_id

    plex = get_target_plex_connection(target_server_id)
    if not plex:
        plex = get_plex_connection()
    if not plex:
        raise HTTPException(status_code=404, detail="No active Plex server available")

    logger.debug("Fetching track: %s (server_id=%s)", item_id_val, target_server_id)
    try:
        track = plex.fetchItem(item_id_val)
    except Exception as ex:
        logger.debug("fetchItem failed on server %s for item %s: %s. Trying primary server connection.", target_server_id, item_id_val, ex)
        primary_plex = get_plex_connection()
        if primary_plex and primary_plex != plex:
            track = primary_plex.fetchItem(item_id_val)
        else:
            raise ex

    logger.debug("Fetched track: %s", getattr(track, "title", "Track"))

    # Set sqlite_track_id attribute for queue serialization & frontend navigation
    setattr(track, "sqlite_track_id", track_id)
    return track


def play_song(player, song, server_token=None, server_url=None):
    """Play a specific song on the Plex player."""
    s_name = getattr(song, "server_name", None) or settings.plex_server_name
    codec = ""
    bitrate = 0
    if getattr(song, "media", None) and len(song.media) > 0:
        m = song.media[0]
        codec = (getattr(m, "audioCodec", "") or getattr(m, "container", "") or "").upper()
        bitrate = getattr(m, "bitrate", 0) or 0

    quality_str = f"{codec} {bitrate}kbps" if (codec or bitrate) else "Standard Quality"
    logger.info(
        "[Playback Engine] Playing track '%s' by '%s' from library '%s' | Audio Quality: %s on player: %s",
        getattr(song, "title", "Track"),
        getattr(song, "grandparentTitle", getattr(song, "artist", "Unknown Artist")),
        s_name,
        quality_str,
        player.title
    )
    target_plex = get_plex_connection()
    if server_url and server_token and not settings.testing:
        try:
            from plexapi.server import PlexServer
            target_plex = PlexServer(server_url, server_token, timeout=5)
        except Exception as ex:
            logger.warning("Failed to connect to target server %s: %s", server_url, ex)

    playback_succeeded = False

    # Tier 1: Try target_plex.createPlayQueue directly
    try:
        pq = target_plex.createPlayQueue(song)
        if pq and hasattr(player, "playMedia"):
            try:
                player.playMedia(pq)
                playback_succeeded = True
                logger.info("Successfully started playback via target_plex.createPlayQueue on %s", player.title)
            except Exception as pm_ex:
                logger.debug("playMedia(pq) failed: %s", pm_ex)
    except Exception as pq_err:
        logger.debug("target_plex.createPlayQueue attempt noted: %s", pq_err)

    # Tier 2: Try player.createPlayQueue
    if not playback_succeeded and hasattr(player, "createPlayQueue"):
        try:
            pq = player.createPlayQueue(target_plex, song)
            try:
                if pq:
                    player.playMedia(pq)
            except Exception as pq_ex:
                logger.debug("player.playMedia(pq) call note: %s", pq_ex)
            logger.info("Successfully started playback via player.createPlayQueue on %s", player.title)
            playback_succeeded = True
        except Exception as e:
            logger.warning("player.createPlayQueue attempt noted: %s", e)

    # Tier 3: Direct playMedia(song) fallback
    if not playback_succeeded:
        try:
            player.playMedia(song)
            playback_succeeded = True
            logger.info("Successfully started playback via direct playMedia(song) on %s", player.title)
        except Exception as ex2:
            logger.warning("Failed direct playMedia on %s: %s", player.title, ex2)
            invalidate_cached_player()
            raise PlexApiException(f"Player '{player.title}' unreachable: {ex2}") from ex2

    if not playback_succeeded:
        return

    # Store track details in Redis under "now_playing" and start tracker AFTER playback command sent
    sqlite_tid = getattr(song, "sqlite_track_id", None)
    sqlite_aid = None
    if not settings.testing:
        verified_tid = validate_track_id(sqlite_tid) if sqlite_tid else None
        if not verified_tid:
            logger.warning(
                "play_song: song '%s' has no valid sqlite_track_id — cannot record now_playing accurately",
                getattr(song, "title", "unknown"),
            )
        else:
            sqlite_tid = verified_tid
            conn = get_db_connection()
            try:
                row = conn.execute(
                    "SELECT album_id FROM tracks WHERE track_id = ? LIMIT 1",
                    (sqlite_tid,),
                ).fetchone()
                if row:
                    sqlite_aid = row["album_id"]
            finally:
                conn.close()

    eff_tid = str(sqlite_tid) if sqlite_tid else str(getattr(song, "ratingKey", ""))
    eff_aid = str(sqlite_aid or getattr(song, "album_id", None) or getattr(song, "parentRatingKey", None) or "")
    eff_server_id = getattr(song, "server_id", None) or getattr(song, "server_name", None) or settings.plex_server_name

    song_data = {
        "item_id": eff_tid,
        "server_id": eff_server_id,
        "album_id": eff_aid if eff_aid else None,
        "title": song.title,
        "artist": getattr(song, "grandparentTitle", getattr(song, "artist", "Unknown Artist")),
        "album": getattr(song, "parentTitle", getattr(song, "album", "Unknown Album")),
        "duration": milliseconds_to_seconds(song.duration) if song.duration else 0,
        "elapsed_time": 0.0,
        "updated_at": time.time(),
        "album_art": f"/api/music/track-art/{eff_tid}",
        "track_state": "playing",
        "server_name": getattr(song, "server_name", None),
    }
    cache_data("now_playing", song_data)

    track_time_tracker.start(song.title, item_id=eff_tid)
    logger.info("Song %s started playing on player: %s", song.title, player.title)

    ws.broadcast_queue_threadsafe()
    ws.broadcast_current_playing_threadsafe()





async def play_queue_on_device():
    """Start playing the entire queue on the active Plex device."""
    global playback_active
    playback_active = True

    if track_time_tracker.state == "paused":
        try:
            player = await asyncio.to_thread(get_active_player)
            if player:
                logger.info("Resuming playback on player: %s", player.title)
                resumed = False
                for cmd in [
                    lambda: player.play(mtype="music"),
                    lambda: player.play(),
                ]:
                    try:
                        await asyncio.to_thread(cmd)
                        resumed = True
                        break
                    except Exception:
                        pass

                if not resumed:
                    invalidate_cached_player()
                    player = await asyncio.to_thread(get_active_player)
                    if player:
                        await asyncio.to_thread(player.play)

                track_time_tracker.resume()
                await ws.send_current_playing()
                return
        except Exception as e:
            logger.warning("Failed to resume player: %s. Invalidating player cache...", e)
            invalidate_cached_player()

    try:
        from backend.services.redis import get_redis_queue
        queue_items = get_redis_queue()
        if not queue_items:
            logger.info("Playback queue is empty.")
            return

        top_item = queue_items[0]
        player = await asyncio.to_thread(get_active_player)
        if not player:
            logger.warning("No active player found for playback.")
            return

        s_id = top_item.get("server_id")
        s_url = top_item.get("server_address")
        s_token = top_item.get("server_token")
        song_obj = await asyncio.to_thread(get_track, top_item["item_id"], s_id)
        if s_url and s_token and not settings.testing:
            await asyncio.to_thread(play_song, player, song_obj, s_token, s_url)
        else:
            await asyncio.to_thread(play_song, player, song_obj)

        from backend.websockets import send_current_playing, send_queue  # noqa: PLC0415
        await send_queue()
        await send_current_playing()
    except Exception as e:
        logger.exception("Error starting queue playback: %s", e)


def generate_autoplay_tracks():
    """Analyze recent history, fetch related tracks from Plex, and seed the queue with fallback items."""
    import random
    import json
    from backend.services.redis import get_playback_history_ids, get_redis_cache_client, add_to_queue_redis, is_autoplay_enabled, get_closing_time_mode

    if (not is_autoplay_enabled() or get_closing_time_mode()) and not settings.testing:
        logger.info("Autoplay is disabled or Closing Time mode is active. Skipping automatic track generation.")
        return

    logger.info("Triggering Autoplay track generation.")
    
    # 1. Fetch recent playback history IDs
    history = get_playback_history_ids()
    
    # If in testing mode or history has fewer than 5 items, fall back to preseed playlist / library pool
    if settings.testing or len(history) < 5:
        # We try to load preseed playlist tracks or library tracks as fallback pool
        try:
            cached = get_redis_cache_client().get("last_seeded_playlist_tracks")
            fallback_pool = json.loads(cached) if cached else None
            if not fallback_pool:
                from backend.db.library_db import get_latest_preseed_playlist_tracks  # noqa: PLC0415
                fallback_pool = get_latest_preseed_playlist_tracks()

            if fallback_pool and isinstance(fallback_pool, list):
                sampled_ids = random.sample(fallback_pool, min(len(fallback_pool), 10))
                for tid in sampled_ids:
                    try:
                        track = get_track(tid)
                        if track:
                            add_to_queue_redis(track, is_fallback=True)
                    except Exception:
                        pass
                logger.info("Autoplay seeded queue using preseed playlist fallback.")
                return
        except Exception as ex:
            logger.warning("Failed to retrieve preseed playlist tracks for autoplay fallback: %s", ex)
            
        # Hard fallback to MOCK_TRACKS if in testing mode
        if settings.testing:
            from backend.services.mock_data import MOCK_TRACKS  # noqa: PLC0415
            all_tracks = []
            for album_tracks in MOCK_TRACKS.values():
                all_tracks.extend(album_tracks)
            sampled = random.sample(all_tracks, min(len(all_tracks), 10))
            for t in sampled:
                class MockTrack:
                    ratingKey = t["track_id"]
                    title = t["title"]
                    grandparentTitle = t["artist"]
                    parentTitle = t["album"]
                    duration = t["duration"] * 1000
                    thumb = f"/api/music/album-art/{t['track_id']}"
                try:
                    add_to_queue_redis(MockTrack(), is_fallback=True)
                except Exception:
                    pass
            logger.info("Autoplay seeded queue using mock track fallback.")
            return

    # 2. Select up to 5 distinct seeds from the history
    seeds = list(set(history))[:5]
    candidate_tracks = []
    
    # 3. Query Plex for related tracks
    for seed_id in seeds:
        try:
            seed_track = get_track(seed_id)
            if hasattr(seed_track, "related") and not settings.testing:
                related = seed_track.related()
                for r_item in related:
                    # Make sure it's a track
                    if getattr(r_item, "type", "") == "track" or "track" in str(getattr(r_item, "type", "")):
                        candidate_tracks.append(r_item)
        except Exception as e:
            logger.warning("Failed to query related tracks for seed %s: %s", seed_id, e)
            
    # Remove duplicates from candidates
    unique_candidates = {}
    for c in candidate_tracks:
        unique_candidates[c.ratingKey] = c
        
    candidates = list(unique_candidates.values())
    
    # Filter out tracks already in the history to avoid immediate duplicates
    filtered_candidates = []
    for c in candidates:
        if str(c.ratingKey) not in [str(h) for h in history]:
            filtered_candidates.append(c)
    
    # If we have no/few candidates, fall back to preseed playlist tracks (Redis or SQLite)
    if len(filtered_candidates) < 10:
        try:
            cached = get_redis_cache_client().get("last_seeded_playlist_tracks")
            fallback_pool = json.loads(cached) if cached else None
            if not fallback_pool:
                from backend.db.library_db import get_latest_preseed_playlist_tracks  # noqa: PLC0415
                fallback_pool = get_latest_preseed_playlist_tracks()

            if fallback_pool and isinstance(fallback_pool, list):
                needed = 10 - len(filtered_candidates)
                sampled_ids = random.sample(fallback_pool, min(len(fallback_pool), needed))
                for tid in sampled_ids:
                    try:
                        if str(tid) in [str(h) for h in history]:
                            continue
                        track = get_track(tid)
                        if track:
                            filtered_candidates.append(track)
                    except Exception:
                        pass
        except Exception as ex:
            logger.warning("Autoplay preseed playlist fallback lookup failed: %s", ex)

    # Ultimate fallback: fetch random indexed tracks from local SQLite library.db (filtering by enabled servers)
    if len(filtered_candidates) < 10 and not settings.testing:
        needed = 10 - len(filtered_candidates)
        try:
            from backend.db.library_db import get_db_connection  # noqa: PLC0415
            enabled_ids = get_enabled_server_ids()
            if enabled_ids:
                conn = get_db_connection()
                placeholders = ",".join(["?"] * len(enabled_ids))
                cursor = conn.cursor()
                cursor.execute(
                    f"SELECT server_track_id, server_id FROM tracks WHERE server_id IN ({placeholders}) ORDER BY RANDOM() LIMIT ?;",
                    (*enabled_ids, needed * 2),
                )
                rows = cursor.fetchall()
                conn.close()
                for row in rows:
                    if len(filtered_candidates) >= 10:
                        break
                    tid = row["server_track_id"]
                    sid = row["server_id"]
                    if str(tid) in [str(h) for h in history]:
                        continue
                    try:
                        track = get_track(tid, server_id=sid)
                        if track:
                            track.server_id = sid
                            filtered_candidates.append(track)
                    except Exception:
                        pass
        except Exception as sq_ex:
            logger.warning("Autoplay random fallback track selection failed: %s", sq_ex)
        except Exception as sq_ex:
            logger.warning("Failed to fetch random tracks from SQLite for autoplay: %s", sq_ex)

    if not filtered_candidates:
        logger.warning("No candidates found for autoplay.")
        return
        
    # Shuffle and select 10 tracks
    random.shuffle(filtered_candidates)
    selected = filtered_candidates[:10]
    
    for track in selected:
        try:
            add_to_queue_redis(track, is_fallback=True)
        except Exception:
            pass
            
    logger.info("Successfully populated queue with %s autoplay fallback tracks.", len(selected))


async def playback_orchestrator():
    """Central async background task that manages the playback state machine.

    Ticks every 1 second:
    1. If playback is active, monitors and drives the custom queue.
    2. Broadcasts Now Playing WebSocket events (elapsed time increments) every second.
    3. Runs a low-frequency resync check (every HEARTBEAT_INTERVAL seconds) against Plexamp.
    """
    global playback_active, _queue_finished_track
    logger.info("Playback orchestrator background task started.")

    tick_count = 0
    while True:
        try:
            # Skip loop if server is unauthenticated (unconfigured)
            if (
                not settings.testing
                and not settings.plex_token
                and not (settings.plex_username and settings.plex_password)
            ):
                await asyncio.sleep(5)
                continue

            # 1. Drive the queue if playback is active
            if playback_active:
                queue = get_redis_queue()
                if queue and len(queue) <= 5 and is_autoplay_enabled():
                    try:
                        await asyncio.to_thread(generate_autoplay_tracks)
                    except Exception as auto_ex:
                        logger.warning("Autoplay track generation encountered an error: %s", auto_ex)
                    queue = get_redis_queue()

                if (
                    not track_time_tracker.is_playing
                    and track_time_tracker.state != "paused"
                ):
                    if queue:
                        # Fetch the first track
                        next_song = queue[0]
                        try:
                            player = await asyncio.to_thread(get_active_player)
                            s_id = next_song.get("server_id")
                            s_url = next_song.get("server_address")
                            s_token = next_song.get("server_token")

                            track = await asyncio.to_thread(get_track, next_song["item_id"], s_id)

                            if s_url and s_token and not settings.testing:
                                await asyncio.to_thread(play_song, player, track, s_token, s_url)
                            else:
                                await asyncio.to_thread(play_song, player, track)
                            await ws.send_queue()
                            await ws.send_current_playing()
                        except PlexApiException as pae:
                            logger.warning("Playback control disabled or no player active: %s. Pausing queue playback.", pae)
                            playback_active = False
                        except Exception as ex:
                            logger.exception("Error playing next song from queue: %s. Pausing queue playback to preserve queue.", ex)
                            playback_active = False

                            await ws.send_queue()
                    else:
                        # Queue finished
                        if playback_active:
                            playback_active = False
                            clear_cache("now_playing")
                            await ws.reset_skip_votes()
                            await ws.send_current_playing()

                # 2. Check for natural track completion
                cached_track = get_cached_data("now_playing")
                if cached_track:
                    total_time = float(cached_track.get("duration", 0))
                    elapsed = track_time_tracker.elapsed_time
                    remaining = total_time - elapsed if total_time > 0 else 999.0
                    curr_queue = get_redis_queue()
                    advance_threshold = 0.5 if len(curr_queue) > 1 else 0.1
                    if total_time > 0 and (elapsed >= total_time or remaining <= advance_threshold):
                        logger.info(
                            "Track '%s' reached end (elapsed=%.1fs, total=%.1fs). Advancing queue.",
                            cached_track["title"],
                            elapsed,
                            total_time,
                        )
                        add_to_history(cached_track)
                        track_time_tracker.stop()
                        remove_from_redis_queue(cached_track["item_id"])

                        remaining_queue = get_redis_queue()
                        if remaining_queue:
                            next_song = remaining_queue[0]
                            logger.info("Immediately advancing queue to next song: %s", next_song.get("title"))
                            dur_raw = next_song.get("duration", 0)
                            dur_sec = milliseconds_to_seconds(dur_raw) if (isinstance(dur_raw, (int, float)) and dur_raw > 10000) else float(dur_raw or 0)
                            next_server_id = next_song.get("server_id")
                            next_album_id = next_song.get("album_id")
                            next_song_data = {
                                "item_id": str(next_song["item_id"]),
                                "server_id": next_server_id,
                                "album_id": str(next_album_id) if next_album_id else None,
                                "title": next_song.get("title", "Unknown Title"),
                                "artist": next_song.get("artist", "Unknown Artist"),
                                "album": next_song.get("album", "Unknown Album"),
                                "duration": dur_sec,
                                "elapsed_time": 0.0,
                                "updated_at": time.time(),
                                "album_art": f"/api/music/track-art/{next_song['item_id']}",
                                "track_state": "playing",
                                "server_name": next_song.get("server_name"),
                            }
                            cache_data("now_playing", next_song_data)
                            track_time_tracker.start(next_song.get("title"), item_id=str(next_song.get("item_id")))
                            playback_active = True

                            await ws.reset_skip_votes()
                            await ws.send_queue()
                            await ws.send_current_playing()

                            try:
                                player = await asyncio.to_thread(get_active_player)
                                s_id = next_song.get("server_id")
                                s_url = next_song.get("server_address")
                                s_token = next_song.get("server_token")

                                track = await asyncio.to_thread(get_track, next_song["item_id"], s_id)

                                if s_url and s_token and not settings.testing:
                                    await asyncio.to_thread(play_song, player, track, s_token, s_url)
                                else:
                                    await asyncio.to_thread(play_song, player, track)
                            except Exception as adv_ex:
                                logger.warning("Immediate track advance failed: %s", adv_ex)
                        else:
                            _queue_finished_track = cached_track["title"]
                            logger.info(
                                "Queue exhausted after '%s'. Stopping playback and clearing state.",
                                cached_track["title"],
                            )
                            clear_cache("now_playing")
                            track_time_tracker.stop()
                            playback_active = False
                            try:
                                await asyncio.to_thread(stop_playback)
                            except Exception as stop_ex:
                                logger.debug("stop_playback exception on queue exhaust: %s", stop_ex)

                            await ws.reset_skip_votes()
                            await ws.send_queue()
                            await ws.send_current_playing()
        except Exception:
            logger.exception("Error in playback orchestrator")

        await asyncio.sleep(1)




def stop_playback():
    """Stop the currently playing track on the active Plex player.

    Returns:
        A JSON message about stopping playback.
    """
    # ruff: noqa: PLW0603
    global playback_active

    playback_active = False
    track_time_tracker.stop()

    try:
        player = get_active_player()
        if player:
            logger.info("Stopping playback on %s", player.title)
            stop_success = False
            for cmd in [
                lambda: player.stop(mtype="music"),
                lambda: player.stop(),
                lambda: player.pause(mtype="music"),
                lambda: player.pause(),
            ]:
                try:
                    cmd()
                    stop_success = True
                    break
                except Exception as e:
                    logger.debug("Playback stop attempt failed: %s", e)

            if not stop_success:
                logger.warning("All stop/pause commands failed on player %s", player.title)

        from backend.services.redis import clear_cache
        clear_cache("now_playing")
        return {"message": "Playback stopped successfully."}
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error stopping playback: {e}"
        ) from e


def pause_playback():
    """Toggle or pause current playback on active Plex player without clearing now_playing or queue."""
    global playback_active

    try:
        if track_time_tracker.state in ("playing", "paused"):
            current_state = track_time_tracker.state
        else:
            now_playing = get_cached_data("now_playing")
            current_state = now_playing.get("track_state", "playing") if isinstance(now_playing, dict) else "playing"

        new_state = "paused" if current_state == "playing" else "playing"
        if new_state == "paused":
            track_time_tracker.pause()
        else:
            track_time_tracker.resume()

        now_playing = get_cached_data("now_playing")
        if isinstance(now_playing, dict):
            now_playing["track_state"] = new_state
            cache_data("now_playing", now_playing)

        player = None
        try:
            player = get_active_player()
        except Exception as p_ex:
            logger.debug("Could not resolve active player for pause_playback: %s", p_ex)

        if player:
            success = False
            if new_state == "paused":
                for cmd in [
                    lambda: player.pause(mtype="music"),
                    lambda: player.pause(),
                    lambda: player.stop(mtype="music"),
                    lambda: player.stop(),
                ]:
                    try:
                        cmd()
                        success = True
                        break
                    except Exception:
                        pass
            else:
                for cmd in [
                    lambda: player.play(mtype="music"),
                    lambda: player.play(),
                ]:
                    try:
                        cmd()
                        success = True
                        break
                    except Exception:
                        pass
            if not success:
                invalidate_cached_player()
                # Auto-rediscover player & retry play/pause command immediately (1st click fix)
                try:
                    fresh_player = get_active_player()
                    if fresh_player:
                        if new_state == "paused":
                            for cmd in [lambda: fresh_player.pause(mtype="music"), lambda: fresh_player.pause()]:
                                try:
                                    cmd()
                                    break
                                except Exception:
                                    pass
                        else:
                            for cmd in [lambda: fresh_player.play(mtype="music"), lambda: fresh_player.play()]:
                                try:
                                    cmd()
                                    break
                                except Exception:
                                    pass
                except Exception as retry_ex:
                    logger.warning("Retry player discovery in pause_playback failed: %s", retry_ex)

        if new_state == "paused":
            playback_active = False
            track_time_tracker.pause()
        else:
            playback_active = True
            track_time_tracker.resume()

        if isinstance(now_playing, dict):
            now_playing["track_state"] = new_state
            cache_data("now_playing", now_playing)

        return {"message": f"Playback {new_state} successfully."}
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error pausing playback: {e}"
        ) from e


def skip_current_track():
    """Skip the currently playing track by stopping player and advancing queue."""
    global playback_active
    try:
        player = get_active_player()
        if player:
            logger.info("Skipping track by stopping player %s", player.title)
            for cmd in [
                lambda: player.pause(mtype="music"),
                lambda: player.stop(mtype="music"),
                lambda: player.pause(),
                lambda: player.stop()
            ]:
                try:
                    cmd()
                    break
                except Exception:
                    pass
    except Exception:
        logger.exception("Failed to stop player during skip")

    cached_track = get_cached_data("now_playing")
    if cached_track:
        add_to_history(cached_track)
        remove_from_redis_queue(cached_track["item_id"])

    track_time_tracker.stop()
    clear_cache("now_playing")
    playback_active = True
    return {"message": "Track skipped successfully."}


def is_music_library_section(sec) -> bool:
    """Check if a Plex library section is a genuine music section (excluding Podcasts, Audiobooks, etc.)."""
    sec_type = str(getattr(sec, "type", "")).lower()
    sec_title = str(getattr(sec, "title", "")).lower()
    
    if sec_type not in ("artist", "music"):
        return False

    excluded_keywords = ("audiobook", "audiobooks", "podcast", "podcasts", "spoken", "speech", "book", "books")
    for kw in excluded_keywords:
        if kw in sec_title:
            logger.info("[Plex Library Filter] Ignoring non-music section '%s' (type: %s)", getattr(sec, "title", ""), sec_type)
            return False

    return True


def _safe_int(val) -> int:
    try:
        if isinstance(val, (int, float)):
            return int(val)
        if isinstance(val, str) and val.isdigit():
            return int(val)
    except Exception:
        pass
    return 0


def _overlay_artist_play_counts(artists_list: list[dict]) -> list[dict]:
    try:
        from backend.services.redis import get_artist_play_counts
        redis_counts = get_artist_play_counts()
        if not redis_counts:
            return artists_list
        res = []
        for a in artists_list:
            item = dict(a)
            name_key = str(item.get("name", "")).lower()
            base_count = _safe_int(item.get("play_count", 0))
            item["play_count"] = base_count + redis_counts.get(name_key, 0)
            res.append(item)
        return res
    except Exception as ex:
        logger.warning("Failed to overlay artist play counts: %s", ex)
        return artists_list


def _overlay_album_play_counts(albums_list: list[dict]) -> list[dict]:
    try:
        from backend.services.redis import get_album_play_counts
        redis_counts = get_album_play_counts()
        if not redis_counts:
            return albums_list
        res = []
        for alb in albums_list:
            item = dict(alb)
            title_key = str(item.get("title", "")).lower()
            base_count = _safe_int(item.get("play_count", 0))
            item["play_count"] = base_count + redis_counts.get(title_key, 0)
            res.append(item)
        return res
    except Exception as ex:
        logger.warning("Failed to overlay album play counts: %s", ex)
        return albums_list


def fetch_all_artists(target_server_ids: list[str] | None = None) -> list[dict]:
    """Fetch all artists across specified or enabled Plex servers, merging duplicates with quality ranking."""
    if settings.testing:
        return _overlay_artist_play_counts(MOCK_ARTISTS)

    cache_key = "all_artists"
    if not target_server_ids:
        cached = get_cached_data(cache_key)
        if cached:
            return _overlay_artist_play_counts(cached)

    enabled_ids = target_server_ids if target_server_ids is not None else get_enabled_server_ids()
    all_accessible = fetch_accessible_plex_servers()
    enabled_set = {str(x).lower() for x in enabled_ids}
    
    target_servers = [
        s for s in all_accessible
        if str(s.get("server_id", "")).lower() in enabled_set
        or str(s.get("name", "")).lower() in enabled_set
    ]

    if not target_servers:
        target_servers = [s for s in all_accessible if s.get("is_primary")] or (all_accessible[:1] if all_accessible else [])

    merged_map = {}  # { norm_key: artist_dict }

    def _fetch_server_artists(s_info):
        s_id = s_info.get("server_id")
        s_name = s_info.get("name", settings.plex_server_name or "plex-so")
        try:
            plex = get_target_plex_connection(s_id)
            music_libs = []
            try:
                for sec in plex.library.sections():
                    if is_music_library_section(sec):
                        music_libs.append(sec)
            except Exception:
                pass

            if not music_libs:
                try:
                    music_libs = [plex.library.section("Music")]
                except Exception:
                    pass

            if not music_libs:
                return []

            results = []
            for music_lib in music_libs:
                try:
                    artists = music_lib.all(libtype="artist")
                    for artist in artists:
                        guid_val = getattr(artist, "guid", None) or getattr(artist, "ratingKey", "")
                        results.append({
                            "artist_id": artist.ratingKey,
                            "name": artist.title,
                            "guid": str(guid_val),
                            "server_id": s_id,
                            "server_name": s_name,
                            "play_count": getattr(artist, "viewCount", 0) or 0,
                            "thumb": getattr(artist, "thumb", None),
                        })
                        if getattr(artist, "thumb", None):
                            cache_data(f"thumb_path:artist:{artist.ratingKey}", artist.thumb)
                except Exception as lib_ex:
                    logger.warning("Error fetching artists from section '%s' on server %s: %s", getattr(music_lib, "title", "Unknown"), s_name, lib_ex)
            return results
        except Exception as ex:
            logger.warning("Failed to fetch artists from server %s: %s", s_name, ex)
            return []

    all_results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(target_servers), 8)) as executor:
        futures = [executor.submit(_fetch_server_artists, s) for s in target_servers]
        done, not_done = concurrent.futures.wait(futures, timeout=10.0)
        for f in done:
            try:
                if not f.exception():
                    all_results.extend(f.result())
            except Exception as ex:
                logger.warning("Error fetching artists from finished thread: %s", ex)

        if not_done:
            logger.warning("%d server(s) timed out during artist fetch. Returning available results.", len(not_done))

    # Map by GUID or normalized name for 100% confidence deduplication
    guid_to_norm = {}

    for item in all_results:
        raw_guid = item.get("guid", "")
        norm_name = re.sub(r"[^a-z0-9]", "", item["name"].lower()) or item["name"].lower()

        # Deduplication key prioritizing GUID when available
        dedup_key = guid_to_norm.get(raw_guid, norm_name) if raw_guid and "plex://" in raw_guid else norm_name
        if raw_guid and "plex://" in raw_guid:
            guid_to_norm[raw_guid] = dedup_key

        if dedup_key not in merged_map:
            merged_map[dedup_key] = {
                "artist_id": item["artist_id"],
                "name": item["name"],
                "play_count": item.get("play_count", 0),
                "sources": [{
                    "server_id": item["server_id"],
                    "server_name": item["server_name"],
                    "artist_id": item["artist_id"],
                }],
                "source_count": 1,
                "server_names": [item["server_name"]],
            }
        else:
            existing = merged_map[dedup_key]
            p1 = _safe_int(existing.get("play_count", 0))
            p2 = _safe_int(item.get("play_count", 0))
            existing["play_count"] = max(p1, p2)
            if not any(s["server_id"] == item["server_id"] for s in existing["sources"]):
                existing["sources"].append({
                    "server_id": item["server_id"],
                    "server_name": item["server_name"],
                    "artist_id": item["artist_id"],
                })
                existing["source_count"] = len(existing["sources"])
                existing["server_names"].append(item["server_name"])

    artist_list = list(merged_map.values())
    artist_list.sort(key=lambda x: x["name"].lower())

    cache_data(cache_key, artist_list)

    return _overlay_artist_play_counts(artist_list)


_plex_connection_cache: dict[str, tuple[any, float]] = {}
_failed_connection_cache: dict[str, float] = {}


def get_target_plex_connection(server_id: str | None = None):
    """Connect to a target Plex server (local or remote shared server) with negative caching and SSL verification fallback."""
    if settings.testing:
        return get_plex_connection()

    if not server_id:
        enabled_ids = get_enabled_server_ids()
        if enabled_ids:
            primary_plex = get_plex_connection()
            primary_id = getattr(primary_plex, "machineIdentifier", None)
            if primary_id and primary_id in enabled_ids:
                return primary_plex
            server_id = enabled_ids[0]
        else:
            return get_plex_connection()

    primary_plex = get_plex_connection()
    if getattr(primary_plex, "machineIdentifier", None) == server_id:
        return primary_plex

    enabled_set = {str(x).lower() for x in get_enabled_server_ids()}
    if server_id and str(server_id).lower() not in enabled_set:
        logger.info("[Plex Connection] Server '%s' is disabled. Skipping network connection.", server_id)
        return None

    now = time.time()
    # Check positive connection cache (5 min)
    if server_id in _plex_connection_cache:
        cached_instance, cached_time = _plex_connection_cache[server_id]
        if now - cached_time < 300:
            return cached_instance

    # Check negative failure cache (3 min)
    if server_id in _failed_connection_cache:
        failed_time = _failed_connection_cache[server_id]
        if now - failed_time < 180:
            logger.debug("[Plex Connection] Skipping recent failed server '%s' (cached failure).", server_id)
            return None

    all_servers = fetch_accessible_plex_servers()
    target_res = next((s for s in all_servers if str(s.get("server_id", "")).lower() == str(server_id).lower() or s.get("name", "").lower() == str(server_id).lower()), None)
    if target_res and target_res.get("is_primary"):
        return primary_plex

    server_name = target_res.get("name", "") if target_res else str(server_id)
    token = target_res.get("access_token") if target_res else settings.plex_token
    conn = None
    last_error = "Server unreachable"

    logger.info("[Plex Connection] Initiating connection to remote server '%s' (ID: %s)...", server_name, server_id)

    # Prepare an unverified SSL session for remote server connections
    import requests
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    unverified_session = requests.Session()
    unverified_session.verify = False

    # Method 1: Connect via MyPlex Resource
    try:
        account = get_myplex_account()
        res = next(
            (r for r in account.resources() if r.clientIdentifier == server_id or (server_name and r.name.lower() == server_name.lower())),
            None
        )
        if res:
            logger.info("[Plex Connection] Found MyPlex resource for '%s'. Testing %d connection endpoints...", server_name, len(res.connections) if res.connections else 0)
            try:
                conn = res.connect(timeout=3)
                logger.info("[Plex Connection] Standard MyPlex connect SUCCESS for '%s' at %s", server_name, getattr(conn, "_baseurl", ""))
            except Exception as ssl_ex:
                logger.debug("[Plex Connection] Standard MyPlex connect failed for '%s': %s. Retrying ssl=False...", server_name, ssl_ex)
                try:
                    conn = res.connect(timeout=3, ssl=False)
                    logger.info("[Plex Connection] MyPlex connect (ssl=False) SUCCESS for '%s' at %s", server_name, getattr(conn, "_baseurl", ""))
                except Exception as ex2:
                    last_error = str(ex2)
                    logger.warning("[Plex Connection] MyPlex connect (ssl=False) FAILED for '%s': %s", server_name, ex2)
    except Exception as ex:
        last_error = str(ex)
        logger.warning("[Plex Connection] Failed MyPlex resource lookup for '%s': %s", server_name, ex)

    # Method 2: Direct connection via server_url with unverified session
    if not conn and target_res and target_res.get("server_url"):
        try:
            from plexapi.server import PlexServer
            conn = PlexServer(target_res["server_url"], token or settings.plex_token, session=unverified_session, timeout=3)
            logger.info("[Plex Connection] Direct URL connect SUCCESS for '%s' at %s", server_name, target_res["server_url"])
        except Exception as ex:
            last_error = str(ex)
            logger.warning("[Plex Connection] Direct URL connect FAILED for '%s' (%s): %s", server_name, target_res.get("server_url"), ex)

    # Method 3: Iterate all endpoints on MyPlex resource using unverified session
    if not conn:
        try:
            account = get_myplex_account()
            for r in account.resources():
                if r.clientIdentifier == server_id or r.name.lower() == server_name.lower():
                    r_token = r.accessToken or token or settings.plex_token
                    for c in r.connections:
                        logger.info("[Plex Connection] Testing endpoint %s for '%s'...", c.uri, server_name)
                        try:
                            from plexapi.server import PlexServer
                            conn = PlexServer(c.uri, r_token, session=unverified_session, timeout=3)
                            if conn:
                                logger.info("[Plex Connection] Endpoint connect SUCCESS for '%s' at %s", server_name, c.uri)
                                break
                        except Exception as end_ex:
                            last_error = str(end_ex)
                            logger.debug("[Plex Connection] Endpoint %s FAILED for '%s': %s", c.uri, server_name, end_ex)
                if conn:
                    break
        except Exception as ex:
            last_error = str(ex)
            logger.warning("[Plex Connection] Endpoint iteration FAILED for '%s': %s", server_name, ex)

    if conn:
        _plex_connection_cache[server_id] = (conn, now)
        _failed_connection_cache.pop(server_id, None)
        base_url = getattr(conn, "_baseurl", "")
        tok = getattr(conn, "_token", "")
        if base_url and tok:
            _SERVER_CREDENTIALS_CACHE[str(server_id).lower()] = (base_url, tok)
            try:
                from backend.services.library import get_db_connection
                sq_conn = get_db_connection()
                sq_conn.execute("UPDATE servers SET server_url = ? WHERE server_id = ?", (base_url, server_id))
                sq_conn.commit()
                sq_conn.close()
            except Exception:
                pass
        return conn

    _failed_connection_cache[server_id] = now
    logger.error("[Plex Connection ERROR] All connection methods FAILED for server '%s' (ID: %s). Last error: %s", server_name, server_id, last_error)
    return None


def fetch_albums_for_artist(artist_id: int | str, server_id: str | None = None):
    """Fetch albums for an artist across linked servers with Redis caching & deduplication."""
    if settings.testing:
        return MOCK_ALBUMS.get(int(artist_id), []) if str(artist_id).isdigit() else []

    try:
        from backend.services.library import get_albums_for_artist_db
        if not hasattr(get_target_plex_connection, "mock_calls"):
            db_albums = get_albums_for_artist_db(artist_id)
            if db_albums:
                return _overlay_album_play_counts(db_albums)
    except Exception as db_ex:
        logger.debug("Failed to fetch artist albums from SQLite: %s", db_ex)

    cache_key = f"albums_for_artist_{artist_id}_{server_id or 'default'}"
    cached_albums = get_cached_data(cache_key)

    if cached_albums:
        logger.info("Fetching albums for artist %s from cache.", artist_id)
        return cached_albums

    # Look up if this artist has multi-server sources in cached all_artists
    all_artists = get_cached_data("all_artists") or []
    artist_sources = []
    if all_artists:
        for a in all_artists:
            if str(a.get("artist_id")) == str(artist_id):
                artist_sources = a.get("sources", [])
                break

    enabled_ids = get_enabled_server_ids()
    enabled_set = {str(x).lower() for x in enabled_ids}

    if artist_sources:
        artist_sources = [
            src for src in artist_sources
            if not src.get("server_id") or str(src.get("server_id", "")).lower() in enabled_set
        ]

    if not artist_sources:
        artist_sources = [{"server_id": server_id, "artist_id": artist_id}]

    import concurrent.futures
    import re

    all_servers = fetch_accessible_plex_servers()

    def _fetch_server_albums(src):
        s_id = src.get("server_id")
        a_id = src.get("artist_id")
        s_info = next((s for s in all_servers if str(s.get("server_id", "")).lower() == str(s_id or "").lower()), None)
        resolved_name = (s_info.get("name") if s_info else None) or src.get("server_name") or settings.plex_server_name or "plex-so"
        try:
            plex = get_target_plex_connection(s_id)
            artist_item = plex.fetchItem(int(a_id))
            albums = artist_item.albums()
            res = []
            for album in albums:
                guid_val = getattr(album, "guid", None) or getattr(album, "ratingKey", "")
                year_val = getattr(album, "year", None)
                if not year_val and getattr(album, "originallyAvailableAt", None):
                    try:
                        year_val = album.originallyAvailableAt.year
                    except Exception:
                        pass
                genre_tags = [g.tag for g in getattr(album, "genres", []) if hasattr(g, "tag")]
                if not genre_tags and hasattr(artist_item, "genres"):
                    genre_tags = [g.tag for g in getattr(artist_item, "genres", []) if hasattr(g, "tag")]
                genre_val = genre_tags[0] if genre_tags else "Uncategorized"

                res.append({
                    "album_id": album.ratingKey,
                    "artist": artist_item.title,
                    "title": album.title,
                    "year": year_val,
                    "genre": genre_val,
                    "guid": str(guid_val),
                    "server_id": s_id,
                    "server_name": resolved_name,
                    "thumb": getattr(album, "thumb", None),
                })
                if getattr(album, "thumb", None):
                    cache_data(f"thumb_path:album:{album.ratingKey}", album.thumb)
            return res
        except Exception as ex:
            logger.warning("Failed to fetch albums for artist %s on server %s: %s", a_id, s_id, ex)
            return []

    all_album_results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(artist_sources), 5)) as executor:
        futures = [executor.submit(_fetch_server_albums, src) for src in artist_sources]
        done, not_done = concurrent.futures.wait(futures, timeout=10.0)
        for f in done:
            try:
                if not f.exception():
                    all_album_results.extend(f.result())
            except Exception as ex:
                logger.warning("Error fetching artist albums from finished thread: %s", ex)

    guid_to_norm = {}
    merged_albums = {}
    for item in all_album_results:
        raw_guid = item.get("guid", "")
        norm_title = re.sub(r"[^a-z0-9]", "", item["title"].lower()) or item["title"].lower()

        dedup_key = guid_to_norm.get(raw_guid, norm_title) if raw_guid and "plex://" in raw_guid else norm_title
        if raw_guid and "plex://" in raw_guid:
            guid_to_norm[raw_guid] = dedup_key

        s_id = item.get("server_id")
        s_info = next((s for s in all_servers if str(s.get("server_id", "")).lower() == str(s_id or "").lower()), None)
        resolved_item_sname = (s_info.get("name") if s_info else None) or item.get("server_name") or settings.plex_server_name or "plex-so"

        if dedup_key not in merged_albums:
            merged_albums[dedup_key] = {
                "album_id": item["album_id"],
                "artist": item["artist"],
                "title": item["title"],
                "play_count": item.get("play_count", 0),
                "server_id": item["server_id"],
                "server_name": resolved_item_sname,
                "sources": [{
                    "server_id": item["server_id"],
                    "server_name": resolved_item_sname,
                    "album_id": item["album_id"],
                }],
                "source_count": 1,
            }
        else:
            existing = merged_albums[dedup_key]
            p1 = _safe_int(existing.get("play_count", 0))
            p2 = _safe_int(item.get("play_count", 0))
            existing["play_count"] = max(p1, p2)
            if not any(str(s.get("server_id", "")).lower() == str(item.get("server_id", "")).lower() for s in existing["sources"] if s.get("server_id")):
                existing["sources"].append({
                    "server_id": item["server_id"],
                    "server_name": resolved_item_sname,
                    "album_id": item["album_id"],
                })
                existing["source_count"] = len(existing["sources"])

    album_list = list(merged_albums.values())
    album_list.sort(key=lambda x: x["title"].lower())

    cache_data(cache_key, album_list)
    logger.info("Caching %d albums for artist %s.", len(album_list), artist_id)

    return album_list


def fetch_all_albums(target_server_ids: list[str] | None = None) -> list[dict]:
    """Fetch all unique albums across enabled servers with deduplication & caching."""
    if settings.testing:
        all_albums = []
        for _a_id, albums in MOCK_ALBUMS.items():
            all_albums.extend(albums)
        all_albums.sort(key=lambda a: a["title"].lower())
        return _overlay_album_play_counts(all_albums)

    cache_key = "all_albums"
    if not target_server_ids:
        cached = get_cached_data(cache_key)
        if cached:
            return _overlay_album_play_counts(cached)

    enabled_ids = target_server_ids if target_server_ids is not None else get_enabled_server_ids()
    all_accessible = fetch_accessible_plex_servers()
    enabled_set = {str(x).lower() for x in enabled_ids}

    target_servers = [
        s for s in all_accessible
        if str(s.get("server_id", "")).lower() in enabled_set
        or str(s.get("name", "")).lower() in enabled_set
    ]

    if not target_servers:
        target_servers = [s for s in all_accessible if s.get("is_primary")] or (all_accessible[:1] if all_accessible else [])

    merged_albums = {}

    def _fetch_server_albums(s_info):
        s_id = s_info.get("server_id")
        s_name = s_info.get("name", settings.plex_server_name or "plex-so")
        try:
            plex = get_target_plex_connection(s_id)
            music_libs = []
            try:
                for sec in plex.library.sections():
                    if is_music_library_section(sec):
                        music_libs.append(sec)
            except Exception:
                pass

            if not music_libs:
                try:
                    music_libs = [plex.library.section("Music")]
                except Exception:
                    pass

            if not music_libs:
                return []

            results = []
            for music_lib in music_libs:
                try:
                    albums = music_lib.all(libtype="album")
                    for album in albums:
                        year_val = getattr(album, "year", None)
                        if not year_val and getattr(album, "originallyAvailableAt", None):
                            try:
                                year_val = album.originallyAvailableAt.year
                            except Exception:
                                pass

                        genre_tags = [g.tag for g in getattr(album, "genres", []) if hasattr(g, "tag")]
                        genre_val = genre_tags[0] if genre_tags else "Uncategorized"

                        artist_name = (
                            getattr(album, "parentTitle", None)
                            or getattr(album, "artistTitle", None)
                            or getattr(album, "grandparentTitle", None)
                            or "Various Artists"
                        )
                        artist_id = getattr(album, "parentRatingKey", None) or getattr(album, "grandparentRatingKey", None)

                        results.append({
                            "album_id": album.ratingKey,
                            "title": album.title,
                            "artist": artist_name,
                            "artist_id": artist_id,
                            "year": year_val,
                            "genre": genre_val,
                            "server_id": s_id,
                            "server_name": s_name,
                            "play_count": getattr(album, "viewCount", 0) or 0,
                            "thumb": getattr(album, "thumb", None),
                        })
                        if getattr(album, "thumb", None):
                            cache_data(f"thumb_path:album:{album.ratingKey}", album.thumb)
                except Exception as lib_ex:
                    logger.warning("Error fetching albums from section '%s' on server %s: %s", getattr(music_lib, "title", "Unknown"), s_name, lib_ex)
            return results
        except Exception as ex:
            logger.warning("Failed to connect to server %s (%s): %s", s_name, s_id, ex)
            return []

    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(target_servers) or 1, 5)) as executor:
        futures = [executor.submit(_fetch_server_albums, s) for s in target_servers]
        done, not_done = concurrent.futures.wait(futures, timeout=15.0)
        for f in done:
            try:
                if not f.exception():
                    server_results = f.result()
                    for alb in server_results:
                        dedup_key = f"{alb['title'].strip().lower()}::{alb['artist'].strip().lower()}"
                        if dedup_key not in merged_albums:
                            merged_albums[dedup_key] = alb
            except Exception as ex:
                logger.warning("Error processing server album results: %s", ex)

    album_list = list(merged_albums.values())
    album_list.sort(key=lambda x: x["title"].lower())
    if not target_server_ids:
        cache_data(cache_key, album_list)
    return _overlay_album_play_counts(album_list)


def fetch_all_genres() -> list[dict]:
    """Fetch all music genres with album counts."""
    albums = fetch_all_albums()
    counts = {}
    for alb in albums:
        g = alb.get("genre")
        if not g or str(g).strip().lower() in ("", "none", "null"):
            g = "Uncategorized"
        else:
            g = str(g).strip().title()
        counts[g] = counts.get(g, 0) + 1

    genres_list = [
        {"genre": genre, "album_count": count}
        for genre, count in sorted(counts.items(), key=lambda x: (-x[1], x[0]))
    ]
    return genres_list


def fetch_albums_by_genre(genre_name: str) -> list[dict]:
    """Fetch all albums matching a specific genre."""
    albums = fetch_all_albums()
    g_lower = genre_name.lower()
    return [
        alb for alb in albums
        if (alb.get("genre") or "uncategorized").lower() == g_lower
    ]


def fetch_all_decades() -> list[dict]:
    """Fetch decade breakdown (e.g. 1960s, 1970s, 1980s...) with album counts and top album ID."""
    albums = fetch_all_albums()
    decade_counts = {}
    decade_top_albums = {}

    for alb in albums:
        year = alb.get("year")
        try:
            year_int = int(year) if year is not None else None
        except (ValueError, TypeError):
            year_int = None

        if not year_int or year_int < 1920 or year_int > 2030:
            decade_key = (0, 0, "Unknown Era")
        else:
            start = (year_int // 10) * 10
            end = start + 9
            decade_key = (start, end, f"{start}s")
        decade_counts[decade_key] = decade_counts.get(decade_key, 0) + 1
        if decade_key not in decade_top_albums and alb.get("album_id"):
            decade_top_albums[decade_key] = alb.get("album_id")

    result = []
    sorted_keys = sorted(decade_counts.keys(), key=lambda k: k[0])
    for start, end, label in sorted_keys:
        result.append({
            "decade": label,
            "year_start": start,
            "year_end": end,
            "album_count": decade_counts[(start, end, label)],
            "top_album_id": decade_top_albums.get((start, end, label)),
        })

    return result


def fetch_albums_by_decade(year_start: int, year_end: int) -> list[dict]:
    """Fetch all albums released within a specific decade/year range."""
    albums = fetch_all_albums()
    if year_start == 0 and year_end == 0:
        return [alb for alb in albums if not alb.get("year") or not isinstance(alb.get("year"), int)]

    def _matches_year(alb):
        y = alb.get("year")
        try:
            y_int = int(y) if y is not None else None
            return bool(y_int and year_start <= y_int <= year_end)
        except (ValueError, TypeError):
            return False

    return [alb for alb in albums if _matches_year(alb)]


def fetch_tracks_for_album(album_id: int | str, server_id: str | None = None):
    """Fetch tracks for an album with audio quality ranking and failover sources."""
    if settings.testing:
        album_title = "Unknown Album"
        for _a_id, albums in MOCK_ALBUMS.items():
            for alb in albums:
                if alb["album_id"] == int(album_id):
                    album_title = alb["title"]
                    break
        tracks = MOCK_TRACKS.get(int(album_id), [])
        return {
            "album_title": album_title,
            "tracks": [
                {
                    "track_id": t["track_id"],
                    "title": t["title"],
                    "duration": t["duration"],
                    "track_number": idx + 1,
                    "disc_number": t.get("disc_number", 1),
                }
                for idx, t in enumerate(tracks)
            ],
        }

    try:
        from backend.services.library import get_tracks_for_album_db
        db_album = get_tracks_for_album_db(album_id)
        if db_album and not hasattr(get_target_plex_connection, "mock_calls"):
            return db_album
    except Exception as db_ex:
        logger.debug("Failed to fetch album tracks from SQLite: %s", db_ex)

    cache_key = f"tracks_for_album_{album_id}_{server_id or 'default'}"
    cached_tracks = get_cached_data(cache_key)

    if cached_tracks and isinstance(cached_tracks, dict) and "artist_id" in cached_tracks and cached_tracks["artist_id"] is not None:
        logger.info("Fetching tracks for album %s from cache.", album_id)
        if "tracks" in cached_tracks:
            for idx, trk in enumerate(cached_tracks["tracks"]):
                if "track_number" not in trk:
                    trk["track_number"] = idx + 1
                if "disc_number" not in trk:
                    trk["disc_number"] = trk.get("disc_number", 1)
        return cached_tracks

    plex = get_target_plex_connection(server_id)
    album = plex.fetchItem(int(album_id))
    tracks = album.tracks()

    artist_id = getattr(album, "parentRatingKey", None) or getattr(album, "grandparentRatingKey", None)
    if not artist_id and hasattr(album, "artist"):
        try:
            artist_obj = album.artist()
            if artist_obj:
                artist_id = artist_obj.ratingKey
        except Exception:
            pass

    track_list = []
    for idx, track in enumerate(tracks):
        # Determine audio quality (codec / bitrate) for smart stream ranking
        codec = ""
        bitrate = 0
        if getattr(track, "media", None) and len(track.media) > 0:
            m = track.media[0]
            codec = getattr(m, "audioCodec", "") or getattr(m, "container", "")
            bitrate = getattr(m, "bitrate", 0) or 0

        is_lossless = bool(codec and ("flac" in codec.lower() or "alac" in codec.lower() or "wav" in codec.lower()))
        quality_score = 1000000 if is_lossless else (bitrate or 256)

        track_number = getattr(track, "index", None) or getattr(track, "trackNumber", None) or (idx + 1)
        disc_number = getattr(track, "discIndex", None) or getattr(track, "parentIndex", None) or 1

        track_list.append({
            "track_id": track.ratingKey,
            "title": track.title,
            "duration": milliseconds_to_seconds(track.duration) if track.duration else 0,
            "server_id": server_id,
            "codec": codec,
            "bitrate": bitrate,
            "quality_score": quality_score,
            "track_number": track_number,
            "disc_number": int(disc_number),
        })

    result = {
        "album_title": album.title,
        "artist_id": artist_id,
        "artist_name": getattr(album, "parentTitle", getattr(album, "grandparentTitle", None)),
        "tracks": track_list,
        "server_id": server_id,
    }
    cache_data(cache_key, result)
    logger.info("Caching %d tracks for album %s (artist_id=%s).", len(track_list), album_id, artist_id)

    return result


def search_music(query: str):
    """Search across ALL enabled Plex servers with multi-server deduplication."""
    try:
        from backend.services.library import search_music_db
        db_results = search_music_db(query)
        if db_results:
            return db_results
    except Exception as db_ex:
        logger.debug("Failed to search SQLite library database: %s", db_ex)

    if settings.testing:
        query_lower = query.lower()
        results = []

        for artist in MOCK_ARTISTS:
            if query_lower in artist["name"].lower():
                results.append(
                    {
                        "name": artist["name"],
                        "type": "artist",
                        "artist_id": artist["artist_id"],
                    }
                )

        for artist_id, albums in MOCK_ALBUMS.items():
            for album in albums:
                if query_lower in album["title"].lower():
                    results.append(
                        {
                            "title": album["title"],
                            "type": "album",
                            "album_id": album["album_id"],
                            "artist": album["artist"],
                        }
                    )

        for album_id, tracks in MOCK_TRACKS.items():
            for track in tracks:
                if query_lower in track["title"].lower():
                    results.append(
                        {
                            "title": track["title"],
                            "type": "track",
                            "track_id": track["track_id"],
                            "duration": track["duration"],
                            "artist": track["artist"],
                            "album": track["album"],
                        }
                    )

        return results

    enabled_ids = get_enabled_server_ids()
    enabled_set = {str(x).lower() for x in enabled_ids}
    all_servers = fetch_accessible_plex_servers()
    target_servers = [
        s for s in all_servers
        if str(s.get("server_id", "")).lower() in enabled_set or s.get("name", "").lower() in enabled_set
    ]

    if not target_servers:
        target_servers = [s for s in all_servers if s.get("is_primary")] or (all_servers[:1] if all_servers else [])

    logger.info("[Plex Search START] Searching query '%s' across %d enabled servers: %s", query, len(target_servers), [s.get("name") for s in target_servers])

    import concurrent.futures
    import re

    all_raw_results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(target_servers), 8)) as executor:
        futures = [executor.submit(search_music_on_server, s, query) for s in target_servers]
        done, not_done = concurrent.futures.wait(futures, timeout=10.0)
        for f in done:
            try:
                if not f.exception():
                    all_raw_results.extend(f.result())
            except Exception as ex:
                logger.warning("Error searching music on finished thread: %s", ex)

    # Deduplicate search results with robust title & artist matching and sources aggregation
    seen_items = {}
    for item in all_raw_results:
        itype = item.get("type")
        norm_title = re.sub(r'[^a-z0-9]', '', (item.get("name") or item.get("title") or "").lower())
        norm_artist = re.sub(r'[^a-z0-9]', '', item.get("artist", "").lower())

        if itype == "artist":
            key = f"artist:{norm_title}"
        elif itype == "album":
            key = f"album:{norm_title}"
        elif itype == "track":
            key = f"track:{norm_title}:{norm_artist}" if norm_artist else f"track:{norm_title}"
        else:
            key = str(id(item))

        s_info = {
            "server_id": item.get("server_id"),
            "server_name": item.get("server_name"),
            "artist_id": item.get("artist_id"),
            "album_id": item.get("album_id"),
            "track_id": item.get("track_id"),
        }

        if key not in seen_items:
            item_copy = dict(item)
            item_copy["sources"] = [s_info] if item.get("server_name") else []
            seen_items[key] = item_copy
        else:
            existing = seen_items[key]
            if "sources" not in existing:
                existing["sources"] = []
                if existing.get("server_name"):
                    existing["sources"].append({
                        "server_id": existing.get("server_id"),
                        "server_name": existing.get("server_name"),
                        "artist_id": existing.get("artist_id"),
                        "album_id": existing.get("album_id"),
                        "track_id": existing.get("track_id"),
                    })

            s_name = item.get("server_name")
            if s_name and not any(src.get("server_name") == s_name for src in existing["sources"]):
                existing["sources"].append(s_info)

            # Upgrade existing item if new item has richer metadata
            if not existing.get("artist") and item.get("artist"):
                existing["artist"] = item.get("artist")
            if not existing.get("thumb") and item.get("thumb"):
                existing["thumb"] = item.get("thumb")

    deduplicated_list = list(seen_items.values())
    logger.info("[Plex Search COMPLETE] Query '%s' returned %d raw items -> %d deduplicated results.", query, len(all_raw_results), len(deduplicated_list))
    return deduplicated_list


def fetch_art(item_id: int, item_type: str, server_id: str | None = None):
    """Fetch image (either artist or album) from Plex.

    Returns:
        An image to serve to the frontend.
    """
    if settings.testing:

        class MockResponse:
            ok = True

            def iter_content(self, chunk_size=1024):
                yield (
                    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06"
                    b"\x00\x00\x00\x1f\x15c4\x00\x00\x00\rIDATx\x9cc`\x00\x01\x00\x00\x05\x00\x01"
                    b"\xa5\xf9\xd0\xb1\x00\x00\x00\x00IEND\xaeB`\x82"
                )

        return MockResponse()

    try:
        from backend.services.library import get_all_art_sources, get_server_credentials
        all_sources = get_all_art_sources(item_id, item_type)
        if not all_sources and server_id:
            all_sources = [(None, server_id, None)]
        elif server_id:
            all_sources = sorted(all_sources, key=lambda s: 0 if s[1] == server_id else 1)

        last_error = None
        for stored_thumb, db_server_id, rating_key in all_sources:
            try:
                target_server_id = db_server_id or server_id
                if rating_key and str(rating_key).isdigit():
                    target_item_id = int(rating_key)
                elif str(item_id).isdigit():
                    target_item_id = int(item_id)
                else:
                    target_item_id = item_id

                if item_type not in {"artist", "album", "track"}:
                    raise HTTPException(
                        status_code=400,
                        detail="Invalid item type. Must be 'artist', 'album', or 'track'.",
                    )

                # First, try resolving server_url and token directly from memory cache or SQLite
                target_key = str(target_server_id or "").lower()
                server_url, token = None, None
                if target_key in _SERVER_CREDENTIALS_CACHE:
                    server_url, token = _SERVER_CREDENTIALS_CACHE[target_key]
                if not server_url or not token:
                    server_url, token = get_server_credentials(target_server_id)

                cache_key = f"thumb_path:{target_server_id or 'primary'}:{item_type}:{item_id}"
                thumb_path = None
                if stored_thumb and (stored_thumb.startswith("/library/metadata/") or stored_thumb.startswith("http")):
                    thumb_path = stored_thumb
                if not thumb_path:
                    thumb_path = get_cached_data(cache_key)

                if not thumb_path or not server_url or not token or hasattr(get_target_plex_connection, "mock_calls"):
                    try:
                        plex = get_target_plex_connection(target_server_id)
                        if plex:
                            if not server_url or hasattr(get_target_plex_connection, "mock_calls"):
                                server_url = getattr(plex, "_baseurl", "")
                            if not token or hasattr(get_target_plex_connection, "mock_calls"):
                                token = getattr(plex, "_token", "")
                            if target_key and server_url and token:
                                _SERVER_CREDENTIALS_CACHE[target_key] = (server_url, token)
                            if not thumb_path:
                                item = plex.fetchItem(target_item_id)
                            if item_type == "artist":
                                thumb_path = getattr(item, "thumb", None)
                            elif item_type == "album":
                                thumb_path = getattr(item, "thumb", None)
                            else:
                                thumb_path = (
                                    getattr(item, "thumb", None)
                                    or getattr(item, "parentThumb", None)
                                    or getattr(item, "grandparentThumb", None)
                                )
                            if thumb_path:
                                cache_data(cache_key, thumb_path)
                    except Exception as conn_ex:
                        logger.debug("Failed Plex fetchItem for art: %s", conn_ex)

                if not thumb_path or not server_url or not token:
                    continue

                if thumb_path.startswith("http"):
                    image_url = thumb_path
                else:
                    image_url = f"{server_url}{thumb_path}?X-Plex-Token={token}"

                try:
                    response = _ART_HTTP_SESSION.get(image_url, stream=True, verify=False, timeout=8)
                    if response.ok:
                        return response
                except Exception:
                    pass

                # Fallback to get_target_plex_connection
                try:
                    plex = get_target_plex_connection(target_server_id)
                    alt_url = getattr(plex, "_baseurl", "")
                    alt_token = getattr(plex, "_token", "")
                    if alt_url and alt_token and alt_url != server_url:
                        retry_url = f"{alt_url}{thumb_path}?X-Plex-Token={alt_token}"
                        response = _ART_HTTP_SESSION.get(retry_url, stream=True, verify=False, timeout=8)
                        if response.ok:
                            return response
                except Exception:
                    pass
            except Exception as e:
                last_error = e
                continue

        raise HTTPException(status_code=404, detail="Plex image request failed")
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("Error proxying image for %s %s: %s", item_type, item_id, e)
        raise HTTPException(status_code=404, detail=f"Error proxying image: {e}") from e


_MEMORY_ART_CACHE: dict[str, tuple[bytes, str]] = {}
_MEMORY_ART_CACHE_MAX_SIZE = 1000


def clear_art_memory_cache():
    """Clear RAM and Redis art image caches."""
    _MEMORY_ART_CACHE.clear()
    try:
        from backend.services.library import clear_art_source_cache  # noqa: PLC0415
        clear_art_source_cache()
    except Exception:
        pass
    try:
        from backend.services.redis import get_redis_cache_client
        r = get_redis_cache_client()
        keys = r.keys("art_bytes:*")
        if keys:
            r.delete(*keys)
    except Exception:
        pass


def fetch_art_bytes(item_id: int | str, item_type: str, server_id: str | None = None) -> tuple[bytes, str]:
    """Fetch image bytes from fast in-memory cache, Redis cache, or Plex server, returning (content_bytes, media_type)."""
    transparent_png = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06"
        b"\x00\x00\x00\x1f\x15c4\x00\x00\x00\rIDATx\x9cc`\x00\x01\x00\x00\x05\x00\x01"
        b"\xa5\xf9\xd0\xb1\x00\x00\x00\x00IEND\xaeB`\x82"
    )

    if settings.testing:
        return transparent_png, "image/jpeg"

    resolved_sid = server_id
    if not resolved_sid or resolved_sid == "all":
        try:
            from backend.services.library import get_art_source_info  # noqa: PLC0415
            _, db_sid, _ = get_art_source_info(item_id, item_type)
            if db_sid:
                resolved_sid = db_sid
        except Exception:
            pass

    cache_bytes_key = f"art_bytes:{item_type}:{item_id}:{resolved_sid or 'primary'}"

    # 1. Check Python RAM cache (0.0001 ms)
    if cache_bytes_key in _MEMORY_ART_CACHE:
        return _MEMORY_ART_CACHE[cache_bytes_key]

    # 2. Check Redis cache (~1 ms)
    try:
        from backend.services.redis import get_redis_cache_client
        r = get_redis_cache_client()
        cached = r.get(cache_bytes_key)
        if cached:
            res = (cached, "image/jpeg")
            if len(_MEMORY_ART_CACHE) < _MEMORY_ART_CACHE_MAX_SIZE:
                _MEMORY_ART_CACHE[cache_bytes_key] = res
            return res
    except Exception:
        pass

    try:
        req_sid = server_id if server_id != "all" else None
        resp = fetch_art(item_id, item_type, server_id=req_sid)
        if hasattr(resp, "content"):
            content_bytes = resp.content
        elif hasattr(resp, "iter_content"):
            content_bytes = b"".join(resp.iter_content(chunk_size=8192))
        else:
            content_bytes = b""
    except Exception as ex:
        logger.debug("Failed fetch_art for %s %s: %s", item_type, item_id, ex)
        content_bytes = b""

    if not content_bytes or len(content_bytes) <= 100:
        return transparent_png, "image/png"

    res = (content_bytes, "image/jpeg")
    if content_bytes:
        if len(_MEMORY_ART_CACHE) >= _MEMORY_ART_CACHE_MAX_SIZE:
            _MEMORY_ART_CACHE.clear()
        _MEMORY_ART_CACHE[cache_bytes_key] = res
        try:
            from backend.services.redis import get_redis_cache_client  # noqa: PLC0415
            r = get_redis_cache_client()
            r.setex(cache_bytes_key, 86400 * 7, content_bytes)
        except Exception:
            pass

    return res


def _prewarm_art_in_background(server_id: str, artist_ids: list[int], album_ids: list[int]):
    """Pre-warm artist and album thumbnails into Redis in a parallel background thread pool."""
    def _worker():
        try:
            logger.info("Pre-warming %d artist and %d album thumbnails into Redis...", len(artist_ids), len(album_ids))
            eff_sid = server_id if (server_id and server_id != "all") else None
            with concurrent.futures.ThreadPoolExecutor(max_workers=16) as executor:
                for a_id in artist_ids:
                    executor.submit(fetch_art_bytes, a_id, "artist", eff_sid)
                for alb_id in album_ids:
                    executor.submit(fetch_art_bytes, alb_id, "album", eff_sid)
            logger.info("Artwork pre-warming complete.")
        except Exception as ex:
            logger.debug("Art prewarming error: %s", ex)

    threading.Thread(target=_worker, daemon=True).start()


def prewarm_category_art(top_album_ids: list[int]):
    """Background helper to pre-warm category top album cover artwork into Redis cache."""
    if not top_album_ids or settings.testing:
        return
    valid_ids = [aid for aid in top_album_ids if aid]
    if valid_ids:
        _prewarm_art_in_background("all", [], valid_ids)


def fetch_accessible_plex_servers():
    """Discover all Plex Media Servers accessible to the account token."""
    if settings.testing:
        return [
            {
                "server_id": "mock-server-1",
                "name": "Local Jukebox Server",
                "is_primary": True,
            },
            {
                "server_id": "mock-server-2",
                "name": "Friend's Music Server",
                "is_primary": False,
            },
        ]

    if not settings.plex_token:
        return []

    cache_key = "accessible_plex_servers"
    cached_servers = get_cached_data(cache_key)
    if cached_servers:
        return cached_servers

    try:
        account = get_myplex_account()
        servers = []
        primary_name = settings.plex_server_name.lower() if settings.plex_server_name else ""

        for resource in account.resources():
            if resource.provides and "server" in resource.provides.lower():
                is_owned = getattr(resource, "owned", False)
                is_primary = bool(is_owned or (primary_name and primary_name in resource.name.lower()))
                conn_url = None
                if resource.connections:
                    if is_owned:
                        local_conns = [c.uri for c in resource.connections if getattr(c, "local", False)]
                        conn_url = local_conns[0] if local_conns else resource.connections[0].uri
                    else:
                        public_ipv4 = [
                            c.uri for c in resource.connections
                            if not getattr(c, "local", False)
                            and "fdd0" not in c.uri
                            and ".lan" not in c.uri
                        ]
                        conn_url = public_ipv4[0] if public_ipv4 else resource.connections[0].uri

                servers.append({
                    "server_id": resource.clientIdentifier,
                    "name": resource.name,
                    "is_primary": is_primary,
                    "access_token": resource.accessToken or settings.plex_token,
                    "server_url": conn_url,
                })

        if servers and not any(s.get("is_primary") for s in servers):
            servers[0]["is_primary"] = True

        for s in servers:
            try:
                from backend.services.library import upsert_server  # noqa: PLC0415
                upsert_server(s["server_id"], s["name"], server_url=s.get("server_url"), is_primary=s.get("is_primary", False), access_token=s.get("access_token"))
            except Exception:
                pass

        cache_data(cache_key, servers)
        return servers
    except Exception as e:
        logger.warning("Failed to fetch accessible Plex servers: %s", e)
        return []


def get_enabled_server_ids() -> list[str]:
    """Get list of server_ids that are enabled for the unified music catalog. Uses SQLite as primary source of truth."""
    import json
    try:
        from backend.services.library import get_db_connection  # noqa: PLC0415
        conn = get_db_connection()
        cursor = conn.execute("SELECT server_id FROM servers WHERE enabled = 1")
        rows = cursor.fetchall()
        conn.close()
        if rows:
            return [str(r["server_id"]) for r in rows]
    except Exception as sq_ex:
        logger.debug("Failed to read enabled_server_ids from SQLite: %s", sq_ex)

    try:
        from backend.services.redis import get_redis_cache_client  # noqa: PLC0415
        val = get_redis_cache_client().get("enabled_server_ids")
        if val:
            parsed = json.loads(val)
            if isinstance(parsed, list):
                return parsed
    except Exception as e:
        logger.debug("Failed to read enabled_server_ids from Redis: %s", e)

    accessible = fetch_accessible_plex_servers()
    primary_ids = [s["server_id"] for s in accessible if s.get("is_primary") and s.get("server_id")]
    if not primary_ids and accessible:
        primary_ids = [accessible[0]["server_id"]]
    if primary_ids:
        set_enabled_server_ids(primary_ids)
        return primary_ids
    if settings.testing:
        return ["mock-primary-server"]
    return []


def set_enabled_server_ids(server_ids: list[str]):
    """Set list of server_ids enabled for the unified music catalog in Redis and SQLite with retry lock protection."""
    import json
    import time
    try:
        from backend.services.redis import get_redis_cache_client, clear_cache
        get_redis_cache_client().set("enabled_server_ids", json.dumps(server_ids))
        clear_cache("all_artists")
        clear_cache("artists")
        clear_cache("accessible_plex_servers")
    except Exception as e:
        logger.warning("Failed to save enabled_server_ids: %s", e)

    enabled_set = {str(s).lower() for s in server_ids}
    all_accessible = fetch_accessible_plex_servers()

    for attempt in range(5):
        try:
            from backend.services.library import upsert_server
            for s in all_accessible:
                s_id = s.get("server_id")
                s_name = s.get("name", "Plex")
                if s_id:
                    is_enabled = str(s_id).lower() in enabled_set or str(s_name).lower() in enabled_set
                    upsert_server(s_id, s_name, server_url=s.get("server_url"), is_primary=s.get("is_primary", False), enabled=is_enabled)
            break
        except Exception as sq_ex:
            logger.warning("Attempt %d: Failed to sync server enabled status to SQLite: %s", attempt + 1, sq_ex)
            time.sleep(0.5)


def search_music_on_server(server_res: dict, query: str):
    """Search music on a specific Plex server resource across all music sections."""
    if settings.testing:
        results = search_music(query)
        for r in results:
            r["server_id"] = server_res.get("server_id", "mock-server")
            r["server_name"] = server_res.get("name", "Mock Server")
        return results

    try:
        server_id = server_res.get("server_id")
        target_plex = get_target_plex_connection(server_id)
        if not target_plex:
            logger.warning("Could not connect to server %s (%s) for search.", server_res.get("name"), server_id)
            return []

        # Locate all music sections dynamically (by type 'artist' or 'music' or section names)
        music_libs = []
        try:
            for sec in target_plex.library.sections():
                if is_music_library_section(sec):
                    music_libs.append(sec)
        except Exception as sec_ex:
            logger.debug("Failed to list sections for server %s: %s", server_res.get("name"), sec_ex)

        if not music_libs:
            try:
                music_libs = [target_plex.library.section("Music")]
            except Exception:
                pass

        if not music_libs:
            logger.warning("No music section found on server %s", server_res.get("name"))
            return []

        formatted = []
        query_lower = query.strip().lower()
        start_time = time.time()
        s_name = server_res.get("name", "Plex Server")
        logger.info("[Plex Search] Sending search query '%s' to server '%s'...", query, s_name)

        for music_lib in music_libs:
            try:
                artist_results = []
                try:
                    artist_results = music_lib.search(query, libtype="artist")
                except Exception:
                    try:
                        artist_results = music_lib.search(title=query, libtype="artist")
                    except Exception:
                        pass

                album_results = []
                try:
                    album_results = music_lib.search(query, libtype="album")
                except Exception:
                    try:
                        album_results = music_lib.search(title=query, libtype="album")
                    except Exception:
                        pass

                track_results = []
                try:
                    track_results = music_lib.search(query, libtype="track")
                except Exception:
                    try:
                        track_results = music_lib.search(title=query, libtype="track")
                    except Exception:
                        pass

                elapsed = time.time() - start_time
                logger.info(
                    "[Plex Search] Server '%s' returned %d artists, %d albums, %d tracks in %.2fs",
                    s_name, len(artist_results), len(album_results), len(track_results), elapsed
                )

                for item in artist_results:
                    formatted.append({
                        "name": item.title,
                        "type": "artist",
                        "artist_id": item.ratingKey,
                        "server_id": server_res.get("server_id"),
                        "server_name": server_res.get("name"),
                    })
                for item in album_results:
                    alb_artist = (
                        getattr(item, "parentTitle", None)
                        or getattr(item, "artist", None)
                        or getattr(item, "originalTitle", None)
                        or ""
                    )
                    formatted.append({
                        "title": item.title,
                        "type": "album",
                        "album_id": item.ratingKey,
                        "artist": alb_artist,
                        "server_id": server_res.get("server_id"),
                        "server_name": server_res.get("name"),
                    })
                for item in track_results:
                    if query_lower in item.title.lower():
                        tr_artist = (
                            getattr(item, "grandparentTitle", None)
                            or getattr(item, "parentTitle", None)
                            or getattr(item, "artist", None)
                            or getattr(item, "originalTitle", None)
                            or ""
                        )
                        tr_album = getattr(item, "parentTitle", "") or ""
                        formatted.append({
                            "title": item.title,
                            "type": "track",
                            "track_id": item.ratingKey,
                            "album_id": item.parentRatingKey,
                            "duration": milliseconds_to_seconds(item.duration) if item.duration else 0,
                            "artist": tr_artist,
                            "album": tr_album,
                            "server_id": server_res.get("server_id"),
                            "server_name": server_res.get("name"),
                        })
            except Exception as lib_ex:
                logger.warning("Error searching music section '%s' on server %s: %s", getattr(music_lib, "title", "Unknown"), server_res.get("name"), lib_ex)

        return formatted
    except Exception as e:
        logger.warning("Error searching server %s: %s", server_res.get("name"), e)
        return []


def fetch_playlists():
    """Fetch user playlists from Plex."""
    if settings.testing:
        return [
            {"playlist_id": 5001, "title": "Party Hits"},
            {"playlist_id": 5002, "title": "Chill Vibes"},
        ]
    plex = get_plex_connection()
    playlists = plex.playlists()
    return [{"playlist_id": p.ratingKey, "title": p.title} for p in playlists]


def seed_queue_from_playlist(playlist_id: int, count: int = 10):
    """Import, shuffle, and add tracks from a Plex playlist to the Redis queue."""
    import random
    import json
    from backend.services.redis import add_to_queue_redis, get_redis_cache_client

    target_count = max(1, count)

    if settings.testing:
        # Generate some mock tracks from the mock data to seed the queue
        from backend.services.mock_data import MOCK_TRACKS
        all_tracks = []
        for album_tracks in MOCK_TRACKS.values():
            all_tracks.extend(album_tracks)
        
        # Select up to target_count random tracks to simulate seeding
        sample_size = min(len(all_tracks), target_count)
        sampled = random.sample(all_tracks, sample_size)
        
        # Cache these track IDs as the fallback pool
        fallback_pool = [t["track_id"] for t in all_tracks]
        try:
            get_redis_cache_client().set("last_seeded_playlist_tracks", json.dumps(fallback_pool))
        except Exception as ex:
            logger.warning("Failed to cache fallback pool in tests: %s", ex)

        added_count = 0
        for t in sampled:
            # We mock the track structure so add_to_queue_redis works
            class MockTrack:
                ratingKey = t["track_id"]
                title = t["title"]
                grandparentTitle = t["artist"]
                parentTitle = t["album"]
                duration = t["duration"] * 1000  # in ms
                thumb = f"/api/music/album-art/{t['track_id']}"
            
            try:
                add_to_queue_redis(MockTrack(), is_fallback=True)
                added_count += 1
            except Exception: # ignore already in queue exception
                pass
        return {"message": f"Successfully seeded {added_count} tracks from playlist {playlist_id}."}

    plex = get_plex_connection()
    # Find the playlist
    playlist = None
    for p in plex.playlists():
        if int(p.ratingKey) == int(playlist_id):
            playlist = p
            break
    
    if not playlist:
        raise HTTPException(status_code=404, detail="Playlist not found")
        
    tracks = playlist.items()

    # 1. Sample target_count random tracks FIRST to make queue addition instant
    sample_size = min(len(tracks), target_count)
    sampled_tracks = random.sample(tracks, sample_size)
    
    added_count = 0
    for track in sampled_tracks:
        try:
            add_to_queue_redis(track, is_fallback=True)
            added_count += 1
        except Exception:
            # Skip duplicates or tracks already in queue
            pass

    # 2. Store all playlist track internal track_ids using 1 batch SQL query for Autoplay fallback pool
    playlist_track_ids = []
    try:
        rk_list = [str(getattr(t, "ratingKey", "")) for t in tracks if getattr(t, "ratingKey", None)]
        if rk_list:
            conn = get_db_connection()
            placeholders = ",".join(["?"] * len(rk_list))
            rows = conn.execute(
                f"""
                SELECT DISTINCT t.track_id
                FROM tracks t
                LEFT JOIN track_sources ts ON t.track_id = ts.track_id
                WHERE ts.server_track_id IN ({placeholders}) OR t.server_track_id IN ({placeholders})
                """,
                rk_list + rk_list,
            ).fetchall()
            conn.close()
            playlist_track_ids = [row["track_id"] for row in rows]

        get_redis_cache_client().set("last_seeded_playlist_tracks", json.dumps(playlist_track_ids))
        save_preseed_playlist_tracks(playlist_track_ids, playlist_id=str(playlist_id))
    except Exception as ex:
        logger.warning("Failed to cache fallback pool: %s", ex)

    return {"message": f"Successfully seeded {added_count} tracks from playlist '{playlist.title}'."}


def seed_queue_from_vibe(vibe_name: str, count: int = 10):
    """Import and add random tracks matching a target party vibe/genre to the Redis queue."""
    target_count = max(1, count)

    # Clear upcoming fallback tracks so the new room vibe takes effect immediately on next track
    clear_redis_queue(force_all=False, fallback_only=True)

    if settings.testing:
        from backend.services.mock_data import MOCK_TRACKS
        all_tracks = []
        for album_tracks in MOCK_TRACKS.values():
            all_tracks.extend(album_tracks)

        sample_size = min(len(all_tracks), target_count)
        sampled = random.sample(all_tracks, sample_size)

        added_count = 0
        for t in sampled:
            class MockTrack:
                type = "track"
                ratingKey = t["track_id"]
                title = t["title"]
                grandparentTitle = t["artist"]
                parentTitle = t["album"]
                duration = t["duration"] * 1000
                thumb = f"/api/music/album-art/{t['track_id']}"
                moods = [vibe_name.capitalize()] if vibe_name else ["Party"]

            try:
                add_to_queue_redis(MockTrack(), is_fallback=True)
                added_count += 1
            except Exception as ex:
                logger.debug("Failed adding mock track to queue: %s", ex)
        return {"message": f"Successfully seeded {added_count} tracks for vibe '{vibe_name.capitalize() if vibe_name else 'Party'}'."}

    matched_tracks = get_tracks_by_vibe_db(vibe_name, count=target_count)

    added_count = 0
    playlist_track_ids = []
    for t in matched_tracks:
        class DictTrack:
            type = "track"
            ratingKey = t["ratingKey"]
            sqlite_track_id = t["track_id"]
            title = t["title"]
            grandparentTitle = t["artist"]
            parentTitle = t["album"]
            duration = t["duration"]
            thumb = t["thumb"]
            server_id = t["server_id"]
            moods = t["moods"]

        try:
            add_to_queue_redis(DictTrack(), is_fallback=True)
            added_count += 1
            playlist_track_ids.append(t["track_id"])
        except Exception as ex:
            logger.debug("Failed adding vibe track to queue: %s", ex)

    if playlist_track_ids and not settings.testing:
        try:
            get_redis_cache_client().set("last_seeded_playlist_tracks", json.dumps(playlist_track_ids))
            save_preseed_playlist_tracks(playlist_track_ids, playlist_id=f"vibe_{vibe_name}")
        except Exception as ex:
            logger.warning("Failed to cache vibe fallback pool: %s", ex)

    v_label = vibe_name.capitalize() if vibe_name else "Party"
    return {"message": f"Successfully seeded {added_count} tracks for vibe '{v_label}'."}


def rate_track_in_plex(track_id: int, rating_stars: float) -> bool:
    """Send user rating (0.0 to 5.0 stars -> converted to Plex 0-10 scale) to target Plex Media Server."""
    try:
        resolved = track_id_to_rating_key(track_id)
        if not resolved:
            logger.warning("Could not resolve Plex ratingKey for track %s", track_id)
            return False

        rating_key_str, server_id = resolved
        target_key = int(rating_key_str) if rating_key_str.isdigit() else rating_key_str
        plex = get_target_plex_connection(server_id)
        if plex:
            item = plex.fetchItem(target_key)
            plex_rating = int(round(max(0.0, min(10.0, float(rating_stars) * 2.0))))
            item.rate(plex_rating)
            logger.info("Successfully set Plex userRating = %d for track %s (Plex ratingKey %s) on server %s", plex_rating, track_id, target_key, server_id)
            return True
    except Exception as e:
        logger.warning("Failed to update rating in Plex for track %s: %s", track_id, e)
    return False


def sync_album_ratings_from_plex(album_id: int | str) -> bool:
    """Sync live track ratings from primary Plex server into SQLite for a given album."""
    if settings.testing:
        return False
    try:
        from backend.services.library import get_db_connection
        conn = get_db_connection()
        try:
            alb_row = conn.execute(
                """
                SELECT alb.album_id, src.server_album_id as rating_key, COALESCE(src.server_id, (SELECT server_id FROM tracks WHERE album_id = alb.album_id LIMIT 1)) as server_id
                FROM albums alb
                LEFT JOIN album_sources src ON alb.album_id = src.album_id
                LEFT JOIN servers srv ON src.server_id = srv.server_id
                WHERE alb.album_id = ?
                ORDER BY (CASE WHEN srv.is_primary = 1 THEN 0 ELSE 1 END)
                LIMIT 1
                """,
                (album_id,),
            ).fetchone()
        finally:
            conn.close()

        if not alb_row or not alb_row["server_id"] or not alb_row["rating_key"]:
            return False

        server_id = alb_row["server_id"]
        rating_key = alb_row["rating_key"]

        plex = get_target_plex_connection(server_id)
        if not plex:
            return False

        target_key = int(rating_key) if str(rating_key).isdigit() else rating_key
        album_item = plex.fetchItem(target_key)
        if not album_item:
            return False

        plex_tracks = album_item.tracks()
        if not plex_tracks:
            return False

        conn = get_db_connection()
        try:
            for trk in plex_tracks:
                rating_key = str(getattr(trk, "ratingKey", ""))
                raw_user_rating = getattr(trk, "userRating", 0.0) or 0.0
                user_stars = float(raw_user_rating) / 2.0 if raw_user_rating else 0.0
                if rating_key:
                    internal_id = rating_key_to_track_id(rating_key)
                    if internal_id:
                        conn.execute(
                            "UPDATE tracks SET user_rating = ? WHERE track_id = ?",
                            (user_stars, internal_id),
                        )
                    else:
                        logger.debug("sync_album_ratings: ratingKey %s not found in library, skipping", rating_key)
            conn.commit()
            return True
        finally:
            conn.close()
    except Exception as e:
        logger.debug("Failed to sync album ratings from Plex for album %s: %s", album_id, e)
        return False


def trigger_closing_time_mode() -> dict:
    """Activate Closing Time mode, purge non-human tracks, append 'Closing Time' finale song, and broadcast updates."""
    set_closing_time_mode(True)

    try:
        from backend.services.redis import purge_non_human_tracks_from_queue_redis
        purge_non_human_tracks_from_queue_redis()
    except Exception as purge_ex:
        logger.warning("Error purging non-human tracks during Last Call: %s", purge_ex)

    closing_track = None
    try:
        closing_track = find_closing_time_track_db()
    except Exception as ex:
        logger.warning("Error finding Closing Time track in DB: %s", ex)

    added_track_title = None
    if closing_track:
        try:
            from unittest.mock import MagicMock
            track_obj = MagicMock()
            track_obj.TYPE = "track"
            track_obj.title = closing_track["title"]
            track_obj.artist = closing_track["artist"]
            track_obj.grandparentTitle = closing_track["artist"]
            track_obj.parentTitle = closing_track["album"]
            track_obj.duration = closing_track["duration"]
            track_obj.ratingKey = closing_track["ratingKey"]
            track_obj.sqlite_track_id = closing_track["track_id"]
            track_obj.album_id = closing_track["album_id"]
            track_obj.server_id = closing_track["server_id"]
            track_obj.thumb = closing_track["thumb"]

            add_to_queue_redis(track_obj, added_by="Admin (Last Call)", is_fallback=False)
            added_track_title = f"{closing_track['artist']} - {closing_track['title']}"
        except Exception as ex:
            logger.warning("Failed adding Closing Time track to queue: %s", ex)

    msg = f"🍸 Last Call activated! '{added_track_title}' added as final track." if added_track_title else "🍸 Last Call activated! Queue closed to guest requests."

    try:
        from backend.websockets import broadcast_queue_threadsafe, broadcast_json_threadsafe
        broadcast_queue_threadsafe()
        broadcast_json_threadsafe({
            "type": "closing_time_triggered",
            "message": msg,
            "closing_time": True,
            "finale_track": added_track_title,
        })
    except Exception as ws_ex:
        logger.debug("Failed sending WS broadcasts during Last Call: %s", ws_ex)

    return {
        "success": True,
        "message": msg,
        "closing_time": True,
        "finale_track": added_track_title,
    }


def cancel_closing_time_mode() -> dict:
    """Cancel Closing Time mode, unlock queue for guests, and broadcast event."""
    set_closing_time_mode(False)

    msg = "🎉 Last Call cancelled! Party mode resumed, song requests unlocked."
    try:
        from backend.websockets import broadcast_json_threadsafe
        broadcast_json_threadsafe({
            "type": "closing_time_cancelled",
            "message": msg,
            "closing_time": False,
        })
    except Exception as ws_ex:
        logger.debug("Failed sending closing_time_cancelled WS broadcast: %s", ws_ex)

    return {
        "success": True,
        "message": msg,
        "closing_time": False,
    }


