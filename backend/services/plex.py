"""Interact with our Plex server."""

import asyncio
import logging
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
)
from backend.utils import TrackTimeTracker, milliseconds_to_seconds

HEARTBEAT_INTERVAL = 5
DRIFT_THRESHOLD = 8.0

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


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

        # 2. Warm artists if plex connection works
        if settings.plex_token:
            logger.info("Background warming Plex artists cache...")
            clear_cache("all_artists")
            fetch_all_artists()
            logger.info("Background cache pre-warming complete.")
    except Exception as e:
        logger.error("Failed to pre-warm caches: %s", e)


def get_current_playing_track():
    """Fetch the currently playing track details from cache and the local tracker.

    Returns:
        The current track info or None if nothing is playing.
    """
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
                if t["track_id"] == int(item_id):
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
    logger.info("Attempting to play song: %s on player: %s", getattr(song, "title", "Track"), player.title)
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

    track_time_tracker.start(song.title)
    logger.info("Song %s started playing on player: %s", song.title, player.title)


# ruff: noqa: C901
def ensure_playback_active():
    """Ensure the playback orchestrator loop is active when tracks are in the queue."""
    global playback_active
    queue = get_redis_queue()
    if queue and not playback_active:
        logger.info("Enabling playback_active for newly queued track.")
        playback_active = True


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
                song_obj = await asyncio.to_thread(t_plex.fetchItem, top_item["item_id"])
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
                if (
                    not track_time_tracker.is_playing
                    and track_time_tracker.state != "paused"
                ):
                    # Get the current queue
                    queue = get_redis_queue()
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
                                track = await asyncio.to_thread(t_plex.fetchItem, int(next_song["item_id"]))
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
        plex = get_plex_connection()
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

    try:
        player = get_active_player()
        if player:
            logger.info("Stopping playback on %s", player.title)
            # Modern Plexamp clients often require pause instead of stop, or standard stop/pause without type constraints.
            # We attempt stop first, and fall back to other commands if needed.
            stop_success = False
            for cmd in [
                lambda: player.pause(mtype="music"),
                lambda: player.stop(mtype="music"),
                lambda: player.pause(),
                lambda: player.stop()
            ]:
                try:
                    cmd()
                    stop_success = True
                    break
                except Exception as ex:
                    logger.debug("Playback control command fallback failed: %s", ex)
            
            if not stop_success:
                logger.warning("All playback control stop/pause commands failed on player '%s'", player.title)

            playback_active = False

            # Instead of resetting the tracker and clearing cache completely:
            # We keep the current track but mark it as stopped/paused with 0 elapsed.
            cached_track = get_cached_data("now_playing")
            if cached_track:
                cached_track["track_state"] = "paused"
                cache_data("now_playing", cached_track)
            
            # Reset tracker to paused state at 0 elapsed
            track_time_tracker.state = "paused"
            track_time_tracker.accumulated_elapsed = 0.0
            track_time_tracker.last_resume_time = None
            return {"message": "Playback stopped successfully."}
        raise HTTPException(status_code=400, detail="No active player found.")
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


def fetch_all_artists():
    """Fetch all artists from the Plex music library with Redis caching.

    Returns:
        A list of all the artists in a Plex music library.
    """
    if settings.testing:
        return MOCK_ARTISTS

    cache_key = "all_artists"
    cached_artists = get_cached_data(cache_key)

    if cached_artists:
        logger.info("Fetching artists from cache.")
        return cached_artists

    plex = get_plex_connection()
    music_library = plex.library.section("Music")
    artists = music_library.all(libtype="artist")
    artist_list = []
    for artist in artists:
        artist_list.append({
            "artist_id": artist.ratingKey,
            "name": artist.title,
        })
        if getattr(artist, "thumb", None):
            cache_data(f"thumb_path:artist:{artist.ratingKey}", artist.thumb)

    cache_data(cache_key, artist_list)

    return artist_list


_plex_connection_cache = {}  # { server_id: (plex_instance, timestamp) }


def get_target_plex_connection(server_id: str | None = None):
    """Connect to a specific target Plex server by server_id, or fallback to primary connection."""
    if not server_id or settings.testing:
        return get_plex_connection()

    primary_plex = get_plex_connection()
    if hasattr(primary_plex, "machineIdentifier") and primary_plex.machineIdentifier == server_id:
        return primary_plex

    now = time.time()
    if server_id in _plex_connection_cache:
        cached_instance, cached_time = _plex_connection_cache[server_id]
        if now - cached_time < 300:
            return cached_instance

    all_servers = fetch_accessible_plex_servers()
    target_res = next((s for s in all_servers if s["server_id"] == server_id), None)
    if not target_res or target_res.get("is_primary"):
        return primary_plex

    server_name = target_res.get("name")
    conn = None
    if server_name:
        try:
            account = get_myplex_account()
            res = account.resource(server_name)
            conn = res.connect(timeout=5)
        except Exception as ex:
            logger.debug("Failed MyPlex connect for %s: %s", server_name, ex)

    if not conn and target_res.get("server_url"):
        try:
            from plexapi.server import PlexServer
            t_token = target_res.get("access_token") or settings.plex_token
            conn = PlexServer(target_res["server_url"], t_token, timeout=5)
        except Exception as ex:
            logger.debug("Failed direct URL connect for %s: %s", server_name, ex)

    if conn:
        _plex_connection_cache[server_id] = (conn, now)
        return conn

    return primary_plex


def fetch_albums_for_artist(artist_id: int, server_id: str | None = None):
    """Fetch albums for a specific artist by their ID with Redis caching.

    Returns:
        A list of albums for an artist.
    """
    if settings.testing:
        return MOCK_ALBUMS.get(int(artist_id), [])

    cache_key = f"albums_for_artist_{artist_id}_{server_id or 'default'}"
    cached_albums = get_cached_data(cache_key)

    if cached_albums:
        logger.info("Fetching albums for artist %s from cache.", artist_id)
        return cached_albums

    plex = get_target_plex_connection(server_id)
    artist = plex.fetchItem(int(artist_id))
    albums = artist.albums()
    album_list = []
    for album in albums:
        album_list.append({
            "album_id": album.ratingKey,
            "artist": artist.title,
            "title": album.title,
            "server_id": server_id,
        })
        if getattr(album, "thumb", None):
            cache_data(f"thumb_path:album:{album.ratingKey}", album.thumb)

    cache_data(cache_key, album_list)
    logger.info("Caching %d albums for artist %s.", len(album_list), artist_id)

    return album_list


def fetch_tracks_for_album(album_id: int, server_id: str | None = None):
    """Fetch tracks for a specific album by its ID with Redis caching.

    Returns:
        A list of tracks for an album.
    """
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

    track_list = [
        {
            "track_id": track.ratingKey,
            "title": track.title,
            "duration": milliseconds_to_seconds(track.duration)
            if track.duration
            else 0,
            "server_id": server_id,
        }
        for track in tracks
    ]

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


def search_music(query):
    """Search for artists, albums, and tracks in Plex.

    Returns:
        A list of artists, albums, and/or tracks.
    """
    if settings.testing:
        query_lower = query.lower()
        results = []

        # 1. Search artists
        for artist in MOCK_ARTISTS:
            if query_lower in artist["name"].lower():
                results.append(
                    {
                        "name": artist["name"],
                        "type": "artist",
                        "artist_id": artist["artist_id"],
                    }
                )

        # 2. Search albums
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

        # 3. Search tracks
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

    plex = get_plex_connection()
    music_library = plex.library.section("Music")

    artist_results = music_library.search(query, libtype="artist")
    album_results = music_library.search(query, libtype="album")
    track_results = music_library.search(query, libtype="track")

    query_lower = query.strip().lower()
    formatted_results = []
    for item in artist_results:
        formatted_results.append(
            {"name": item.title, "type": item.type, "artist_id": item.ratingKey}
        )
    for item in album_results:
        formatted_results.append(
            {
                "title": item.title,
                "type": item.type,
                "album_id": item.ratingKey,
                "artist": item.parentTitle,
            }
        )
    for item in track_results:
        if query_lower in item.title.lower():
            formatted_results.append(
                {
                    "title": item.title,
                    "type": item.type,
                    "track_id": item.ratingKey,
                    "album_id": item.parentRatingKey,
                    "duration": milliseconds_to_seconds(item.duration)
                    if item.duration
                    else 0,
                    "artist": item.grandparentTitle,
                    "album": item.parentTitle,
                }
            )

    return formatted_results


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
            thumb_path = (
                getattr(item, "thumb", None)
                or getattr(item, "parentThumb", None)
                or getattr(item, "grandparentThumb", None)
            )
            if not thumb_path and hasattr(item, "album"):
                try:
                    alb = item.album()
                    if alb:
                        thumb_path = getattr(alb, "thumb", None)
                except Exception:
                    pass

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
                is_primary = bool(primary_name and resource.name.lower() == primary_name)
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

        cache_data(cache_key, servers)
        return servers
    except Exception as e:
        logger.warning("Failed to fetch accessible Plex servers: %s", e)
        return []


def search_music_on_server(server_res: dict, query: str):
    """Search music on a specific Plex server resource."""
    if settings.testing:
        results = search_music(query)
        for r in results:
            r["server_id"] = server_res.get("server_id", "mock-server")
            r["server_name"] = server_res.get("name", "Mock Server")
        return results

    try:
        server_id = server_res.get("server_id")
        target_plex = get_target_plex_connection(server_id)

        # Locate music section dynamically (by name or by section type 'artist')
        music_lib = None
        try:
            music_lib = target_plex.library.section("Music")
        except Exception:
            for sec in target_plex.library.sections():
                if sec.type == "artist":
                    music_lib = sec
                    break

        if not music_lib:
            logger.warning("No music section found on server %s", server_res.get("name"))
            return []

        artist_results = music_lib.search(query, libtype="artist")
        album_results = music_lib.search(query, libtype="album")
        track_results = music_lib.search(query, libtype="track")

        query_lower = query.strip().lower()
        formatted = []
        for item in artist_results:
            formatted.append({
                "name": item.title,
                "type": item.type,
                "artist_id": item.ratingKey,
                "server_id": server_res.get("server_id"),
                "server_name": server_res.get("name"),
            })
        for item in album_results:
            formatted.append({
                "title": item.title,
                "type": item.type,
                "album_id": item.ratingKey,
                "artist": getattr(item, "parentTitle", ""),
                "server_id": server_res.get("server_id"),
                "server_name": server_res.get("name"),
            })
        for item in track_results:
            if query_lower in item.title.lower():
                formatted.append({
                    "title": item.title,
                    "type": item.type,
                    "track_id": item.ratingKey,
                    "album_id": item.parentRatingKey,
                    "duration": milliseconds_to_seconds(item.duration) if item.duration else 0,
                    "artist": getattr(item, "grandparentTitle", ""),
                    "album": getattr(item, "parentTitle", ""),
                    "server_id": server_res.get("server_id"),
                    "server_name": server_res.get("name"),
                })
        return formatted
    except Exception as e:
        logger.warning("Error searching server %s: %s", server_res.get("name"), e)
        return []
