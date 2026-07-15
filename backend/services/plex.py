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

HEARTBEAT_INTERVAL = 12
DRIFT_THRESHOLD = 3.0

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


logger = logging.getLogger(__name__)


track_time_tracker = TrackTimeTracker()
# Declare the global variable to manage playback state
playback_active = False


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
    get_myplex_account.cache_clear()
    get_plex_connection.cache_clear()
    logger.info("Plex connection cache cleared for reinitialization.")


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
    """Get the first active Plex player.

    Returns:
        The active player according to plex.
    """
    if settings.testing:

        class MockPlayer:
            title = client_name or settings.client_name or "Mock Jukebox Player"

            def playMedia(self, media):
                pass

        return MockPlayer()

    client_name = client_name or settings.client_name

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


def play_song(player, song):
    """Play a specific song on the Plex player."""
    logger.info("Attempting to play song: %s on player: %s", song.title, player.title)
    player.playMedia(song)

    # Store track details in Redis under "now_playing"
    song_data = {
        "item_id": song.ratingKey,
        "title": song.title,
        "artist": getattr(song, "grandparentTitle", "Unknown Artist"),
        "album": getattr(song, "parentTitle", "Unknown Album"),
        "duration": milliseconds_to_seconds(song.duration) if song.duration else 0,
        "album_art": song.thumb if hasattr(song, "thumb") else None,
    }
    cache_data("now_playing", song_data)

    track_time_tracker.start(song.title)
    logger.info("Song %s started playing on player: %s", song.title, player.title)


# ruff: noqa: C901
async def play_queue_on_device():
    """Start playing the entire queue on the active Plex device."""
    global playback_active
    playback_active = True

    # If nothing is playing, trigger immediately instead of waiting for the orchestrator tick
    if not track_time_tracker.is_playing and track_time_tracker.state != "paused":
        queue = get_redis_queue()
        if queue:
            next_song = queue[0]
            try:
                player = get_active_player()
                track = get_track(next_song["item_id"])
                await asyncio.to_thread(play_song, player, track)

                # Lazy import websockets to avoid circular imports
                from backend.websockets import send_current_playing, send_queue  # noqa: PLC0415

                await send_queue()
                await send_current_playing()
            except Exception:
                logger.exception("Immediate play failed")


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
            if not settings.plex_token and not (
                settings.plex_username and settings.plex_password
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
                            player = get_active_player()
                            track = get_track(next_song["item_id"])

                            # Run play in thread pool to avoid blocking async loop
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
                        from backend.websockets import send_current_playing  # noqa: PLC0415

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
                            )  # noqa: PLC0415

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


async def check_plexamp_resync():
    """Align local playback state and timer with actual Plexamp sessions to catch drift and manual interactions."""
    global playback_active

    # In testing mode there is no real Plex connection, so skip the resync entirely.
    if settings.testing:
        return

    try:
        plex = get_plex_connection()
        try:
            player = get_active_player()
        except Exception:  # noqa: BLE001

            # No active player is reachable right now
            return

        sessions = await asyncio.to_thread(plex.sessions)

        # Look for a session running on our active player
        active_session = None
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

                playback_active = True
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
                if abs(local_elapsed - plex_elapsed) > DRIFT_THRESHOLD:
                    logger.info(
                        "Detected drift of %.1fs between local timer and Plexamp. Adjusting.",
                        local_elapsed - plex_elapsed,
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
            # No session found on the active player.
            # If we thought we were playing/paused, but there's no session, it means playback stopped on Plexamp.
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
            player.stop(mtype="music")

            playback_active = False

            # Reset playback state
            track_time_tracker.reset()
            clear_cache("now_playing")
            return {"message": "Playback stopped successfully."}
        raise HTTPException(status_code=400, detail="No active player found.")
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error stopping playback: {e}"
        ) from e


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
    artist_list = [
        {
            "artist_id": artist.ratingKey,
            "name": artist.title,
        }
        for artist in artists
    ]

    cache_data(cache_key, artist_list)

    return artist_list


def fetch_albums_for_artist(artist_id):
    """Fetch albums for a specific artist by their ID with Redis caching.

    Returns:
        A list of albums for an artist.
    """
    if settings.testing:
        return MOCK_ALBUMS.get(int(artist_id), [])

    cache_key = f"albums_for_artist_{artist_id}"
    cached_albums = get_cached_data(cache_key)

    if cached_albums:
        logger.info("Fetching albums for artist %s from cache.", artist_id)
        return cached_albums

    plex = get_plex_connection()
    artist = plex.fetchItem(artist_id)
    albums = artist.albums()
    album_list = [
        {
            "album_id": album.ratingKey,
            "artist": artist.title,
            "title": album.title,
        }
        for album in albums
    ]

    cache_data(cache_key, album_list)
    logger.info("Caching %d albums for artist %d.", len(album_list), artist_id)

    return album_list


def fetch_tracks_for_album(album_id):
    """Fetch tracks for a specific album by its ID with Redis caching.

    Returns:
        A list of tracks for an album.
    """
    if settings.testing:
        album_title = "Unknown Album"
        for artist_id, albums in MOCK_ALBUMS.items():
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

    cache_key = f"tracks_for_album_{album_id}"
    cached_tracks = get_cached_data(cache_key)

    if cached_tracks:
        logger.info("Fetching tracks for album %d from cache.", album_id)
        return cached_tracks

    plex = get_plex_connection()
    album = plex.fetchItem(album_id)
    tracks = album.tracks()
    track_list = {
        "album_title": album.title,
        "tracks": [
            {
                "track_id": track.ratingKey,
                "title": track.title,
                "duration": milliseconds_to_seconds(track.duration)
                if track.duration
                else 0,
            }
            for track in tracks
        ],
    }

    cache_data(cache_key, track_list)
    logger.info("Caching tracks for album %d", album_id)

    return track_list


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
        formatted_results.append(
            {
                "title": item.title,
                "type": item.type,
                "track_id": item.ratingKey,
                "duration": milliseconds_to_seconds(item.duration)
                if item.duration
                else 0,
                "artist": item.grandparentTitle,
                "album": item.parentTitle,
            }
        )

    return formatted_results


def fetch_art(item_id: int, item_type: str):
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
        plex = get_plex_connection()

        if item_type in {"artist", "album"}:
            item = plex.fetchItem(item_id)
        else:
            raise HTTPException(
                status_code=400,
                detail="Invalid item type. Must be 'artist' or 'album'.",
            )

        if not item.thumb:
            raise HTTPException(
                status_code=404, detail=f"No image available for this {item_type}."
            )

        # Get the server URL and token from the established connection
        # ruff: noqa: SLF001
        server_url = plex._baseurl
        # ruff: noqa: SLF001
        token = plex._token
        image_url = f"{server_url}{item.thumb}?X-Plex-Token={token}"

        # ruff: noqa: S501
        response = requests.get(image_url, stream=True, verify=False, timeout=5)
        if not response.ok:
            raise HTTPException(
                status_code=500, detail=f"Error fetching {item_type} image from Plex."
            )
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error fetching {item_type} image: {e}"
        ) from e
    else:
        return response
