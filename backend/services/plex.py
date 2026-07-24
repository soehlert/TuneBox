"""Interact with our Plex server."""

import asyncio
import concurrent.futures
import logging
import re
import time
from functools import lru_cache

import requests
import urllib3
from fastapi import HTTPException
from plexapi.exceptions import PlexApiException
from plexapi.myplex import MyPlexAccount

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
)
from backend.utils import TrackTimeTracker, milliseconds_to_seconds

HEARTBEAT_INTERVAL = 5
DRIFT_THRESHOLD = 8.0

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
for _log_name in ("plexapi", "plexapi.myplex", "plexapi.server", "urllib3", "urllib3.connectionpool", "requests"):
    logging.getLogger(_log_name).setLevel(logging.CRITICAL)


logger = logging.getLogger(__name__)


track_time_tracker = TrackTimeTracker()
# Declare the global variable to manage playback state
playback_active = False
_cached_active_player = None
_cached_active_player_name = None


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


def reinitialize_plex():
    """Clear cached connection and force connection reload."""
    global _cached_active_player, _cached_active_player_name, playback_active
    get_myplex_account.cache_clear()
    get_plex_connection.cache_clear()
    _cached_active_player = None
    _cached_active_player_name = None
    playback_active = False
    try:
        from backend.services.redis import clear_cache, clear_redis_queue
        track_time_tracker.stop()
        clear_redis_queue()
        clear_cache("artists")
        clear_cache("all_artists")
        clear_cache("now_playing")
        clear_cache("queue")
    except Exception as e:
        logger.debug("Failed to purge Redis cache on reinitialize: %s", e)
    logger.info("Plex connection cache, playback state, and Redis keys cleared for reinitialization.")


def pre_warm_all_caches():
    """Trigger cache pre-warming for resources and artists in background."""
    try:
        from backend.config import settings
        from backend.services.redis import clear_cache

        # 1. Warm resources if plex token is configured
        if settings.plex_token:
            logger.info("Background warming Plex resources cache...")
            from backend.routers.auth import fetch_and_cache_resources
            fetch_and_cache_resources(refresh=True)

        # 2. Warm artists only for enabled servers
        if settings.plex_token:
            logger.info("Background warming Plex artists cache for enabled servers...")
            fetch_all_artists()
            logger.info("Background cache pre-warming complete.")
    except Exception as e:
        logger.error("Failed to pre-warm caches: %s", e)


def get_current_playing_track():
    """Fetch the currently playing track details from cache and the local tracker.

    Returns:
        The current track info or None if nothing is playing or stopped.
    """
    if track_time_tracker.state == "stopped":
        return None

    cached_track = get_cached_data("now_playing")
    if not cached_track:
        return None

    # Track time info is calculated dynamically from the tracker
    elapsed = track_time_tracker.elapsed_time
    total_time = cached_track.get("duration", 0)  # duration in seconds

    # Safeguard bounds
    elapsed = max(elapsed, 0)
    elapsed = min(elapsed, total_time) if total_time > 0 else elapsed

    remaining_time = max(total_time - elapsed, 0) if total_time > 0 else 0
    remaining_percentage = (remaining_time / total_time * 100) if total_time > 0 else 0

    return {
        "item_id": cached_track.get("item_id"),
        "server_id": cached_track.get("server_id"),
        "title": cached_track["title"],
        "artist": cached_track.get("artist", "Unknown Artist"),
        "album": cached_track.get("album", "Unknown Album"),
        "track_state": "playing" if track_time_tracker.is_playing else "paused",
        "total_time": total_time,
        "elapsed_time": elapsed,
        "remaining_time": remaining_time,
        "remaining_percentage": remaining_percentage,
    }


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
        return _cached_active_player

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


def get_track(item_id):
    """Get track ID from plex based on song.

    Returns:
        A track object from Plex.
    """
    if settings.testing:
        found_track = None
        for album_id, tracks in MOCK_TRACKS.items():
            for t in tracks:
                if str(t["track_id"]) == str(item_id):
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

    plex = get_plex_connection()
    logger.debug("Fetching track: %s", item_id)
    track = plex.fetchItem(item_id)
    logger.debug("Fetched track: %s", track.title)

    return track


def play_song(player, song, server_token=None, server_url=None):
    """Play a specific song on the Plex player."""
    s_name = getattr(song, "server_name", None) or settings.plex_server_name or "plex-so"
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

    if hasattr(player, "createPlayQueue"):
        try:
            player.createPlayQueue(target_plex, song)
            logger.info("Successfully started playback via createPlayQueue on %s", player.title)
        except Exception as e:
            logger.warning("Failed to play via createPlayQueue: %s. Falling back to playMedia.", e)
            player.playMedia(song)
    else:
        player.playMedia(song)

    # Store track details in Redis under "now_playing"
    song_data = {
        "item_id": song.ratingKey,
        "title": song.title,
        "artist": getattr(song, "grandparentTitle", "Unknown Artist"),
        "album": getattr(song, "parentTitle", "Unknown Album"),
        "duration": milliseconds_to_seconds(song.duration) if song.duration else 0,
        "album_art": song.thumb if hasattr(song, "thumb") else None,
        "server_name": getattr(song, "server_name", None),
    }
    cache_data("now_playing", song_data)
    add_to_history(song.ratingKey)

    track_time_tracker.start(song.title)
    logger.info("Song %s started playing on player: %s", song.title, player.title)





async def play_queue_on_device():
    """Start playing the entire queue on the active Plex device."""
    global playback_active
    playback_active = True

    if track_time_tracker.state == "paused":
        try:
            player = await asyncio.to_thread(get_active_player)
            if player:
                logger.info("Resuming playback on player: %s", player.title)
                await asyncio.to_thread(player.play)
                track_time_tracker.resume()
                from backend.websockets import send_current_playing  # noqa: PLC0415
                await send_current_playing()
                return
        except Exception as e:
            logger.warning("Failed to resume player: %s", e)

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

        s_url = top_item.get("server_address")
        s_token = top_item.get("server_token")
        if s_url and s_token and not settings.testing:
            try:
                from plexapi.server import PlexServer
                t_plex = PlexServer(s_url, s_token, timeout=5)
                item_id_val = int(top_item["item_id"]) if str(top_item["item_id"]).isdigit() else top_item["item_id"]
                song_obj = await asyncio.to_thread(t_plex.fetchItem, item_id_val)
                song_obj.server_name = top_item.get("server_name")
                await asyncio.to_thread(play_song, player, song_obj, s_token, s_url)
            except Exception as ex:
                logger.warning("Failed to load multi-server track %s from %s: %s", top_item["item_id"], s_url, ex)
                song_obj = await asyncio.to_thread(get_track, top_item["item_id"])
                await asyncio.to_thread(play_song, player, song_obj)
        else:
            song_obj = await asyncio.to_thread(get_track, top_item["item_id"])
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
    from backend.services.redis import get_playback_history, get_redis_cache_client, add_to_queue_redis

    logger.info("Triggering Autoplay track generation.")
    
    # 1. Fetch recent playback history
    history = get_playback_history()
    
    # If in testing mode or history is empty, fall back
    if settings.testing or not history:
        # We try to load cached playlist tracks as fallback pool
        try:
            cached = get_redis_cache_client().get("last_seeded_playlist_tracks")
            if cached:
                fallback_pool = json.loads(cached)
                # Sample up to 10 tracks
                sampled_ids = random.sample(fallback_pool, min(len(fallback_pool), 10))
                for tid in sampled_ids:
                    track = get_track(tid)
                    try:
                        add_to_queue_redis(track, is_fallback=True)
                    except Exception:
                        pass
                logger.info("Autoplay seeded queue using cached playlist fallback.")
                return
        except Exception as ex:
            logger.warning("Failed to retrieve cached playlist tracks for autoplay fallback: %s", ex)
            
        # Hard fallback to MOCK_TRACKS if cached playlist is unavailable
        if settings.testing:
            from backend.services.mock_data import MOCK_TRACKS
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

    # 2. Select up to 3 distinct seeds from the history
    seeds = list(set(history))[:3]
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
    
    # If we have no/few candidates, fall back to cached playlist tracks
    if len(filtered_candidates) < 10:
        try:
            cached = get_redis_cache_client().get("last_seeded_playlist_tracks")
            if cached:
                fallback_pool = json.loads(cached)
                needed = 10 - len(filtered_candidates)
                sampled_ids = random.sample(fallback_pool, min(len(fallback_pool), needed))
                for tid in sampled_ids:
                    try:
                        # Skip if already in history
                        if tid in history:
                            continue
                        track = get_track(tid)
                        filtered_candidates.append(track)
                    except Exception:
                        pass
        except Exception as ex:
            logger.warning("Autoplay fallback pool lookup failed: %s", ex)
            
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
    global playback_active
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

            # 1. Drive the queue if nothing is currently playing
            if playback_active:
                queue = get_redis_queue()
                if len(queue) <= 5 and is_autoplay_enabled():
                    await asyncio.to_thread(generate_autoplay_tracks)
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

                            if s_id and not settings.testing:
                                t_plex = await asyncio.to_thread(get_target_plex_connection, s_id)
                                item_id_val = int(next_song["item_id"]) if str(next_song["item_id"]).isdigit() else next_song["item_id"]
                                track = await asyncio.to_thread(t_plex.fetchItem, item_id_val)
                                track.server_name = next_song.get("server_name")
                            else:
                                track = await asyncio.to_thread(get_track, next_song["item_id"])

                            if s_url and s_token and not settings.testing:
                                await asyncio.to_thread(play_song, player, track, s_token, s_url)
                            else:
                                await asyncio.to_thread(play_song, player, track)

                            # Lazy import websockets to avoid circular imports
                            from backend.websockets import (
                                send_current_playing,
                                send_queue,
                            )  # noqa: PLC0415

                            await send_queue()
                            await send_current_playing()
                        except PlexApiException as pae:
                            logger.warning("Playback control disabled or no player active: %s. Pausing queue playback.", pae)
                            playback_active = False
                        except Exception:
                            logger.exception("Error playing next song from queue")
                            # To prevent infinite looping on failure, we can remove the item
                            remove_from_redis_queue(next_song["item_id"])
                            from backend.websockets import send_queue  # noqa: PLC0415

                            await send_queue()
                    else:
                        # Queue finished
                        playback_active = False
                        clear_cache("now_playing")
                        from backend.websockets import send_current_playing, reset_skip_votes  # noqa: PLC0415
                        await reset_skip_votes()
                        await send_current_playing()

                # 2. Check for natural track completion
                elif track_time_tracker.is_playing:
                    elapsed = track_time_tracker.elapsed_time
                    cached_track = get_cached_data("now_playing")
                    if cached_track:
                        total_time = cached_track.get("duration", 0)
                        if total_time > 0 and elapsed >= total_time:
                            logger.info(
                                "Track %s finished. Advancing queue.",
                                cached_track["title"],
                            )
                            # Stop current tracking
                            track_time_tracker.stop()
                            # Remove finished track
                            remove_from_redis_queue(cached_track["item_id"])

                            from backend.websockets import (
                                send_current_playing,
                                send_queue,
                                reset_skip_votes,
                            )  # noqa: PLC0415

                            await reset_skip_votes()
                            await send_queue()
                            await send_current_playing()

            # 3. Perform low-frequency resync check
            tick_count += 1
            if tick_count >= HEARTBEAT_INTERVAL:
                tick_count = 0
                await check_plexamp_resync()

        except Exception:
            logger.exception("Error in playback orchestrator")

        await asyncio.sleep(1)


async def check_plexamp_resync(force_align: bool = False):
    """Align local playback state and timer with actual Plexamp sessions to catch drift and manual interactions."""
    global playback_active

    # In testing mode there is no real Plex connection, so skip the resync entirely.
    if settings.testing:
        return

    # Skip resync if Plex isn't fully configured yet to prevent logs/connection spam.
    if not settings.plex_token and not (
        settings.plex_username and settings.plex_password
    ):
        return
    if not settings.plex_server_name:
        return

    try:
        try:
            plex = get_plex_connection()
        except PlexConnectionError as e:
            logger.debug("Plex connection offline during background resync check: %s", e)
            return

        try:
            player = await asyncio.to_thread(get_active_player)
        except Exception:  # noqa: BLE001

            # No active player is reachable right now
            return

        # Look for a session running on our active player
        active_session = None

        # Try querying the player timeline directly for real-time offset (zero lag)
        if type(player).__name__ not in ("MagicMock", "Mock"):
            try:
                timeline = await asyncio.to_thread(getattr, player, "timeline", None)
                if timeline and timeline.state != "stopped":
                    rating_key = getattr(timeline, "ratingKey", None)
                    if rating_key:
                        class MockSession:
                            pass

                        mock_sess = MockSession()
                        mock_sess.ratingKey = rating_key
                        mock_sess.viewOffset = timeline.time
                        mock_sess.duration = timeline.duration

                        class MockPlayer:
                            state = timeline.state
                            machineIdentifier = player.machineIdentifier
                        mock_sess.player = MockPlayer()

                        # Resolve track metadata details
                        cached_track = get_cached_data("now_playing")
                        if cached_track and str(cached_track.get("item_id")) == str(rating_key):
                            mock_sess.title = cached_track["title"]
                            mock_sess.grandparentTitle = cached_track["artist"]
                            mock_sess.parentTitle = cached_track["album"]
                            mock_sess.thumb = cached_track["album_art"]
                        else:
                            # Fetch full track metadata from Plex
                            track = await asyncio.to_thread(get_track, rating_key)
                            if track:
                                mock_sess.title = track.title
                                mock_sess.grandparentTitle = getattr(track, "grandparentTitle", "Unknown Artist")
                                mock_sess.parentTitle = getattr(track, "parentTitle", "Unknown Album")
                                mock_sess.thumb = getattr(track, "thumb", None)
                            else:
                                mock_sess.title = "Unknown Track"
                                mock_sess.grandparentTitle = "Unknown Artist"
                                mock_sess.parentTitle = "Unknown Album"
                                mock_sess.thumb = None

                        active_session = mock_sess
                        logger.debug("Successfully read direct player timeline for %s at %sms (state=%s)", mock_sess.title, mock_sess.viewOffset, timeline.state)
            except Exception as e:
                logger.warning("Could not poll player timeline directly: %s. Falling back to PMS sessions.", e)
                # Invalidate player cache on direct connection failure
                global _cached_active_player, _cached_active_player_name
                _cached_active_player = None
                _cached_active_player_name = None

        if not active_session:
            sessions = await asyncio.to_thread(plex.sessions)
            for session in sessions:
                if (
                    getattr(session, "player", None)
                    and session.player.machineIdentifier == player.machineIdentifier
                ):
                    active_session = session
                    break

        # Lazy import websockets
        from backend.websockets import send_current_playing  # noqa: PLC0415

        if active_session:
            # We found an active session on the player!
            session_title = active_session.title
            session_state = (
                active_session.player.state
            )  # 'playing', 'paused', 'stopped'
            session_duration = (
                milliseconds_to_seconds(active_session.duration)
                if active_session.duration
                else 0
            )

            # Check elapsed time from Plex session
            plex_elapsed = (
                milliseconds_to_seconds(active_session.viewOffset)
                if getattr(active_session, "viewOffset", None)
                else 0
            )

            # 1. Check if track changed (manual skip/change on Plexamp)
            cached_track = get_cached_data("now_playing")
            if not cached_track or cached_track.get("title") != session_title:
                logger.info(
                    "Detected track change on Plexamp: '%s'. Resynced.", session_title
                )
                from backend.websockets import reset_skip_votes  # noqa: PLC0415
                await reset_skip_votes()

                # Fetch details and cache them
                song_data = {
                    "item_id": active_session.ratingKey,
                    "title": session_title,
                    "artist": getattr(
                        active_session, "grandparentTitle", "Unknown Artist"
                    ),
                    "album": getattr(active_session, "parentTitle", "Unknown Album"),
                    "duration": session_duration,
                    "album_art": getattr(active_session, "thumb", None),
                }
                cache_data("now_playing", song_data)

                # Update tracker to match Plexamp
                track_time_tracker.stop()
                track_time_tracker.start(session_title)

                # If Plex is playing, resume tracker, else pause
                if session_state == "paused":
                    track_time_tracker.pause()
                elif session_state == "playing":
                    track_time_tracker.resume()

                # Align elapsed time
                track_time_tracker.accumulated_elapsed = float(plex_elapsed)
                track_time_tracker.last_resume_time = (
                    time.time() if session_state == "playing" else None
                )

                await send_current_playing()

            # 2. Check if play/pause state changed on Plexamp
            else:
                state_changed = False
                if session_state == "playing" and not track_time_tracker.is_playing:
                    logger.info("Plexamp resumed playback. Resynced state.")
                    track_time_tracker.resume()
                    state_changed = True
                elif session_state == "paused" and track_time_tracker.is_playing:
                    logger.info("Plexamp paused playback. Resynced state.")
                    track_time_tracker.pause()
                    state_changed = True

                # 3. Check for elapsed time drift
                local_elapsed = track_time_tracker.elapsed_time
                if force_align or abs(local_elapsed - plex_elapsed) > DRIFT_THRESHOLD:
                    logger.info(
                        "Detected drift of %.1fs between local timer and Plexamp (force_align=%s). Adjusting.",
                        local_elapsed - plex_elapsed,
                        force_align,
                    )
                    # Align elapsed time
                    track_time_tracker.accumulated_elapsed = float(plex_elapsed)
                    track_time_tracker.last_resume_time = (
                        time.time() if session_state == "playing" else None
                    )
                    state_changed = True

                if state_changed:
                    await send_current_playing()

        else:
            # If we recently started or resumed a track locally, give Plex a chance to start up (e.g. 10s grace period)
            is_recent = False
            if track_time_tracker.state == "playing" and track_time_tracker.last_resume_time:
                if time.time() - track_time_tracker.last_resume_time < 10.0:
                    is_recent = True

            if not is_recent:
                cached_track = get_cached_data("now_playing")
                if cached_track or track_time_tracker.state != "stopped":
                    logger.info("No active Plexamp session found. Resynced to stopped.")
                    track_time_tracker.stop()
                    clear_cache("now_playing")
                    playback_active = False
                    await send_current_playing()

    except Exception:
        logger.exception("Failed to execute Plexamp resync")


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


def fetch_all_artists(target_server_ids: list[str] | None = None) -> list[dict]:
    """Fetch all artists across specified or enabled Plex servers, merging duplicates with quality ranking."""
    if settings.testing:
        return MOCK_ARTISTS

    cache_key = "all_artists"
    if not target_server_ids:
        cached = get_cached_data(cache_key)
        if cached:
            return cached

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

    return artist_list


_plex_connection_cache: dict[str, tuple[any, float]] = {}
_failed_connection_cache: dict[str, float] = {}


def get_target_plex_connection(server_id: str | None = None):
    """Connect to a target Plex server (local or remote shared server) with negative caching and SSL verification fallback."""
    if not server_id or settings.testing:
        return get_plex_connection()

    primary_plex = get_plex_connection()
    if getattr(primary_plex, "machineIdentifier", None) == server_id:
        return primary_plex

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
        return conn

    _failed_connection_cache[server_id] = now
    logger.error("[Plex Connection ERROR] All connection methods FAILED for server '%s' (ID: %s). Last error: %s", server_name, server_id, last_error)
    return None


def fetch_albums_for_artist(artist_id: int, server_id: str | None = None):
    """Fetch albums for an artist across linked servers with Redis caching & deduplication."""
    if settings.testing:
        return MOCK_ALBUMS.get(int(artist_id), [])

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
                res.append({
                    "album_id": album.ratingKey,
                    "artist": artist_item.title,
                    "title": album.title,
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


def fetch_tracks_for_album(album_id: int, server_id: str | None = None):
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
                }
                for t in tracks
            ],
        }

    cache_key = f"tracks_for_album_{album_id}_{server_id or 'default'}"
    cached_tracks = get_cached_data(cache_key)

    if cached_tracks and isinstance(cached_tracks, dict) and "artist_id" in cached_tracks and cached_tracks["artist_id"] is not None:
        logger.info("Fetching tracks for album %s from cache.", album_id)
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
    for track in tracks:
        # Determine audio quality (codec / bitrate) for smart stream ranking
        codec = ""
        bitrate = 0
        if getattr(track, "media", None) and len(track.media) > 0:
            m = track.media[0]
            codec = getattr(m, "audioCodec", "") or getattr(m, "container", "")
            bitrate = getattr(m, "bitrate", 0) or 0

        is_lossless = bool(codec and ("flac" in codec.lower() or "alac" in codec.lower() or "wav" in codec.lower()))
        quality_score = 1000000 if is_lossless else (bitrate or 256)

        track_list.append({
            "track_id": track.ratingKey,
            "title": track.title,
            "duration": milliseconds_to_seconds(track.duration) if track.duration else 0,
            "server_id": server_id,
            "codec": codec,
            "bitrate": bitrate,
            "quality_score": quality_score,
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
        plex = get_target_plex_connection(server_id)

        if item_type not in {"artist", "album", "track"}:
            raise HTTPException(
                status_code=400,
                detail="Invalid item type. Must be 'artist', 'album', or 'track'.",
            )

        cache_key = f"thumb_path:{server_id or 'primary'}:{item_type}:{item_id}"
        thumb_path = get_cached_data(cache_key)
        if not thumb_path:
            item = plex.fetchItem(item_id)
            if item_type == "artist":
                thumb_path = getattr(item, "thumb", None)
                if not thumb_path and hasattr(item, "albums"):
                    try:
                        for alb in item.albums():
                            if getattr(alb, "thumb", None):
                                thumb_path = alb.thumb
                                break
                    except Exception:
                        pass
            elif item_type == "album":
                thumb_path = getattr(item, "thumb", None)
            else:
                thumb_path = (
                    getattr(item, "thumb", None)
                    or getattr(item, "parentThumb", None)
                    or getattr(item, "grandparentThumb", None)
                )

            if not thumb_path:
                raise HTTPException(
                    status_code=404, detail=f"No image available for this {item_type}."
                )
            cache_data(cache_key, thumb_path)

        # Get the server URL and token from the established connection
        # ruff: noqa: SLF001
        server_url = getattr(plex, "_baseurl", "")
        # ruff: noqa: SLF001
        token = getattr(plex, "_token", "")
        image_url = f"{server_url}{thumb_path}?X-Plex-Token={token}"

        # ruff: noqa: S501
        response = requests.get(image_url, stream=True, verify=False, timeout=12)
        if not response.ok:
            raise HTTPException(
                status_code=404, detail=f"Image not found on Plex for {item_type}."
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=404, detail=f"Image not accessible for {item_type}: {e}"
        ) from e
    else:
        return response


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
                    conn_url = resource.connections[0].uri
                    for conn in resource.connections:
                        if not conn.local:
                            conn_url = conn.uri
                            break

                servers.append({
                    "server_id": resource.clientIdentifier,
                    "name": resource.name,
                    "is_primary": is_primary,
                    "access_token": resource.accessToken or settings.plex_token,
                    "server_url": conn_url,
                })

        if servers and not any(s.get("is_primary") for s in servers):
            servers[0]["is_primary"] = True

        cache_data(cache_key, servers)
        return servers
    except Exception as e:
        logger.warning("Failed to fetch accessible Plex servers: %s", e)
        return []


def get_enabled_server_ids() -> list[str]:
    """Get list of server_ids that are enabled for the unified music catalog. Defaults to primary server on fresh boot."""
    import json
    try:
        from backend.services.redis import get_redis_cache_client
        val = get_redis_cache_client().get("enabled_server_ids")
        if val:
            parsed = json.loads(val)
            if isinstance(parsed, list) and len(parsed) > 0:
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
    """Set list of server_ids enabled for the unified music catalog."""
    import json
    try:
        from backend.services.redis import get_redis_cache_client, clear_cache
        get_redis_cache_client().set("enabled_server_ids", json.dumps(server_ids))
        clear_cache("all_artists")
        clear_cache("artists")
        clear_cache("accessible_plex_servers")
    except Exception as e:
        logger.warning("Failed to save enabled_server_ids: %s", e)


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
    # Store all playlist track ratingKeys in cache as a fallback pool for Autoplay
    playlist_track_ids = [int(t.ratingKey) for t in tracks]
    try:
        get_redis_cache_client().set("last_seeded_playlist_tracks", json.dumps(playlist_track_ids))
    except Exception as ex:
        logger.warning("Failed to cache fallback pool: %s", ex)

    # Select target_count random tracks (or entire playlist if count exceeds len(tracks))
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
            
    return {"message": f"Successfully seeded {added_count} tracks from playlist '{playlist.title}'."}
