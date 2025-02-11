"""Interact with our Plex server."""

import asyncio
import logging
import uuid
from functools import lru_cache

import requests
import urllib3
from fastapi import HTTPException
from plexapi.exceptions import PlexApiException
from plexapi.myplex import MyPlexAccount
from plexapi.myplex import MyPlexPinLogin

from backend.config import settings
from backend.exceptions import PlexConnectionError
from backend.services.redis import cache_data, get_cached_data, get_redis_queue, remove_from_redis_queue, get_setting
from backend.utils import TrackTimeTracker, milliseconds_to_seconds

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger(__name__)


track_time_tracker = TrackTimeTracker()
# Declare the global variable to manage playback state
playback_active = False

# Dictionary to store PIN login instances and their status
pin_logins = {}

def start_plex_pin_login():
    """Starts a PIN login process and returns the PIN and a unique identifier."""
    try:
        pin_login = MyPlexPinLogin()
        identifier = str(uuid.uuid4())
        pin_logins[identifier] = {"login": pin_login, "status": "pending", "token": None}
        return pin_login.pin, identifier
    except Exception as e:
        raise Exception(f"Error starting PIN login: {e}")


def check_plex_pin_login(identifier):
    """Checks the status of a PIN login process."""
    try:
        login_data = pin_logins.get(identifier)
        if not login_data:
            raise Exception("Invalid identifier")

        if login_data["status"] == "success":
            return "success", login_data["token"]
        elif login_data["status"] == "failed":
            return "failed", None

        if login_data["login"].checkLogin():
            login_data["status"] = "success"
            token = login_data["login"].token
            account = MyPlexAccount(token=token)
            login_data["account"] = account
            return "success", token
        elif login_data["login"].expired:
            login_data["status"] = "failed"
            return "failed", None
        else:
            return "pending", None

    except Exception as e:
        raise Exception(f"Error checking PIN login: {e}")


@lru_cache
def get_plex_connection(identifier=None):
    """Establish a connection to the Plex server.

    Args:
        identifier (str, optional): The identifier used for PIN login. If provided,
            the function will attempt to use the cached account associated with this identifier.

    Returns:
        A PlexServer instance.
    """
    try:
        session = requests.Session()
        session.verify = False  # Not recommended for production

        pin_login = MyPlexPinLogin()
        pin = pin_login.pin
        print(f"Enter this PIN at https://plex.tv/link: {pin}")

        token = pin_login.waitForLogin() # Wait for user to login

        if token:
            account = MyPlexAccount(token=token)
            server_name = get_setting("plex_server_name")
            plex_server = account.resource(server_name).connect()
            logger.info("Connected to Plex server %s", plex_server)
            return plex_server
        else:
            raise PlexConnectionError("PIN login failed or timed out.")


    except Exception as e:
        raise PlexConnectionError(original_error=e) from e


def calculate_playback_state(session):
    """Calculate the playback state including elapsed time, remaining time, and progress.

    Returns:
        A dictionary of the current playback state and times.
    """
    total_time = milliseconds_to_seconds(session.duration)

    elapsed_time = track_time_tracker.get_elapsed_time(session.title)

    # Ensure that elapsed_time doesn't go negative or exceed total_time
    elapsed_time = max(elapsed_time, 0)
    elapsed_time = min(elapsed_time, total_time)

    remaining_time = total_time - elapsed_time

    if total_time > 0:
        remaining_percentage = (remaining_time / total_time) * 100
    else:
        remaining_percentage = 0

    return {
        "total_time": total_time,
        "elapsed_time": elapsed_time,
        "remaining_time": remaining_time,
        "remaining_percentage": remaining_percentage,
    }


def get_current_playing_track():
    """Fetch the currently playing track on the active player.

    Returns:
        The current song playing on the active player.
    """
    plex = get_plex_connection()
    player = get_active_player().machineIdentifier
    sessions = plex.sessions()
    logger.debug("Plex sessions: %s", sessions)

    if not sessions:
        logger.debug("No active sessions found.")
        return None

    for session in sessions:
        if session.player.machineIdentifier == player:
            playback_state = calculate_playback_state(session)

            current_track = {
                "title": session.title,
                "artist": session.grandparentTitle,
                "album": session.parentTitle,
                "track_state": session.player.state,
                "total_time": playback_state["total_time"],
                "elapsed_time": playback_state["elapsed_time"],
                "remaining_time": playback_state["remaining_time"],
                "remaining_percentage": playback_state["remaining_percentage"],
            }

            track_time_tracker.update(current_track)
            logger.debug("Current track: %s", current_track)
            return current_track

    return None


def get_all_players():
    """Fetch all available Plex players.

    Returns:
        A list of all available Plex players.
    """
    plex = get_plex_connection()
    players = plex.clients()

    if not players:
        msg = "No active players found."
        raise PlexApiException(msg)

    return [
        {"player_id": player.machineIdentifier, "name": player.title, "device": player.device} for player in players
    ]


def get_active_player(client_name: str | None = None):
    """Get the first active Plex player.

    Returns:
        The active player according to plex.
    """
    plex = get_plex_connection()
    players = plex.clients()

    if not players:
        msg = "No active Plex players found."
        raise PlexApiException(msg)

    client_name = client_name or settings.client_name

    if client_name:
        active_player = next((p for p in players if p.title == client_name), None)
        if active_player:
            return active_player
        logger.debug("No player found with name %s, falling back to first player.", client_name)

    # Select the first available player otherwise
    active_player = players[0]
    logger.debug("Active player found: %s", active_player.title)
    return active_player


def get_track(item_id):
    """Get track ID from plex based on song.

    Returns:
        A track object from Plex.
    """
    plex = get_plex_connection()
    logger.debug("Fetching track: %s", item_id)
    track = plex.fetchItem(item_id)
    logger.debug("Fetched track: %s", track.title)

    return track


def play_song(player, song):
    """Play a specific song on the Plex player."""
    logger.info("Attempting to play song: %s on player: %s", song.title, player.title)
    player.playMedia(song)
    track_time_tracker.start(song.title)
    logger.info("Song %s started playing on player: %s", song.title, player.title)


# ruff: noqa: C901
async def play_queue_on_device():
    """Play the entire queue on the active Plex device."""
    global playback_active

    if playback_active:
        logger.info("Playback already active. Skipping queue start.")
        return

    playback_active = True

    player = get_active_player()
    if not player:
        raise HTTPException(status_code=400, detail="No active player found.")
    logger.debug("Active player found: %s", player.title)

    playback_queue = get_redis_queue()

    if not playback_queue:
        logger.warning("Playback queue is empty.")
        playback_active = False
        return

    for song in playback_queue:
        if not playback_active:
            logger.info("Playback stopped by the user, breaking out of the queue loop.")
            break

        item_id = song["item_id"]
        track = get_track(item_id)
        if not track:
            continue

        logger.debug("Track found: %s", track.title)

        if hasattr(track, "duration"):
            total_time = milliseconds_to_seconds(track.duration)
        else:
            continue

        if total_time <= 0:
            continue

        logger.debug("Starting playback of %s on %s", track.title, player.title)
        await asyncio.to_thread(play_song, player, track)

        await monitor_song_progress(track, total_time)

        remove_from_redis_queue(item_id)


async def monitor_song_progress(track, total_time):
    """Monitor the progress of the song without blocking the event loop."""
    while track_time_tracker.is_playing:
        elapsed_time = track_time_tracker.get_elapsed_time(track.title)
        if elapsed_time >= total_time:
            logger.debug("Finished playing %s. Moving to the next song.", track.title)
            track_time_tracker.stop()
            break
        await asyncio.sleep(1)


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
            return {"message": "Playback stopped successfully."}
        raise HTTPException(status_code=400, detail="No active player found.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error stopping playback: {e}") from e


def fetch_all_artists():
    """Fetch all artists from the Plex music library with Redis caching.

    Returns:
        A list of all the artists in a Plex music library.
    """
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
                "duration": milliseconds_to_seconds(track.duration) if track.duration else 0,
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
    plex = get_plex_connection()
    music_library = plex.library.section("Music")

    artist_results = music_library.search(query, libtype="artist")
    album_results = music_library.search(query, libtype="album")
    track_results = music_library.search(query, libtype="track")

    formatted_results = []
    for item in artist_results:
        formatted_results.append({"name": item.title, "type": item.type, "artist_id": item.ratingKey})
    for item in album_results:
        formatted_results.append({
            "title": item.title,
            "type": item.type,
            "album_id": item.ratingKey,
            "artist": item.parentTitle,
        })
    for item in track_results:
        formatted_results.append({
            "title": item.title,
            "type": item.type,
            "track_id": item.ratingKey,
            "duration": milliseconds_to_seconds(item.duration) if item.duration else 0,
            "artist": item.grandparentTitle,
            "album": item.parentTitle,
        })

    return formatted_results


def fetch_art(item_id: int, item_type: str):
    """Fetch image (either artist or album) from Plex.

    Returns:
        An image to serve to the frontend.
    """
    try:
        plex = get_plex_connection()

        if item_type in {"artist", "album"}:
            item = plex.fetchItem(item_id)
        else:
            raise HTTPException(status_code=400, detail="Invalid item type. Must be 'artist' or 'album'.")

        if not item.thumb:
            raise HTTPException(status_code=404, detail=f"No image available for this {item_type}.")

        # Get the server URL and token from the established connection
        # ruff: noqa: SLF001
        server_url = plex._baseurl
        # ruff: noqa: SLF001
        token = plex._token
        image_url = f"{server_url}{item.thumb}?X-Plex-Token={token}"

        # ruff: noqa: S501
        response = requests.get(image_url, stream=True, verify=False, timeout=5)
        if not response.ok:
            raise HTTPException(status_code=500, detail=f"Error fetching {item_type} image from Plex.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching {item_type} image: {e}") from e
    else:
        return response
