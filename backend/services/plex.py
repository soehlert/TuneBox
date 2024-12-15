import asyncio
import logging

from fastapi import HTTPException
from plexapi.server import PlexServer
from plexapi.exceptions import PlexApiException
from backend.config import settings
import requests
from backend.utils import TrackTimeTracker, milliseconds_to_seconds
from backend.services.redis import get_redis_queue, cache_data, get_cached_data, remove_from_redis_queue

import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


track_time_tracker = TrackTimeTracker()


def get_plex_connection():
    """Establish a connection to the Plex server."""
    try:
        session = requests.Session()
        session.verify = False
        plex = PlexServer(settings.plex_base_url, settings.plex_token, session=session)
        return plex
    except Exception as e:
        logging.error(f"Plex connection error: {e}")
        raise


def get_current_playing_track():
    """Fetch the currently playing track on the active player."""
    plex = get_plex_connection()
    player = get_active_player().machineIdentifier
    sessions = plex.sessions()

    if not sessions:
        logging.debug("No active sessions found.")
        return None

    for session in sessions:
        if session.player.machineIdentifier == player:
            total_time = milliseconds_to_seconds(session.duration)
            view_offset = milliseconds_to_seconds(session.viewOffset)
            track_state = session.player.state
            elapsed_time = track_time_tracker.get_elapsed_time(session.title)

            # Ensure that elapsed_time doesn't go negative or exceed total_time
            if elapsed_time < 0:
                elapsed_time = 0
            if elapsed_time > total_time:
                elapsed_time = total_time

            remaining_time = total_time - elapsed_time

            if total_time > 0:
                remaining_percentage = (remaining_time / total_time) * 100
            else:
                remaining_percentage = 0

            current_track = {
                'title': session.title,
                'artist': session.grandparentTitle,
                'album': session.parentTitle,
                'total_time': total_time,
                'track_state': track_state,
                'remaining_time': remaining_time,
                'offset': view_offset,
                'remaining_percentage': remaining_percentage,
                'elapsed_time': elapsed_time,
            }
            track_time_tracker.update(current_track)
            return current_track

    return None


def get_all_players():
    """Fetch all available Plex players."""
    try:
        plex = get_plex_connection()
        players = plex.clients()

        if not players:
            raise PlexApiException("No active players found.")

        return [{"player_id": player.machineIdentifier, "name": player.title, "device": player.device} for player in players]
    except PlexApiException as e:
        logging.error(f"Error fetching active players: {e}")
        raise


def get_active_player(client_name: str = None):
    """Get the first active Plex player."""
    plex = get_plex_connection()
    players = plex.clients()

    if not players:
        raise PlexApiException("No active players found.")

    client_name = client_name or settings.client_name

    if client_name:
        active_player = next((p for p in players if p.title == client_name), None)
        if active_player:
            return active_player
        else:
            logging.debug(f"No player found with name {client_name}, falling back to first player.")

    # Select the first available player otherwise
    active_player = players[0]
    logging.debug(f"Active player found: {active_player.title}")
    return active_player


def get_track(item_id):
    """Get track ID from plex based on song."""
    plex = get_plex_connection()
    try:
        logging.debug(f"Fetching track: {item_id}")
        item = plex.fetchItem(item_id)
        logging.debug(f"Fetched track: {item.title}")
        return item
    except PlexApiException as e:
        logging.error(f"Error adding item to playback queue: {e}")
        raise


def play_song(player, song):
    """Play a specific song on the Plex player."""
    try:
        logging.info(f"Attempting to play song: {song.title} on player: {player.title}")
        player.playMedia(song)
        track_time_tracker.start(song.title)
        logging.info(f"Song {song.title} started playing on player: {player.title}")
    except Exception as e:
        logging.error(f"Error playing media: {e}")
        raise


async def play_queue_on_device():
    """Play the entire queue on the active Plex device."""
    try:
        player = get_active_player()
        if not player:
            logging.error("No active player found.")
            raise HTTPException(status_code=400, detail="No active player found.")
        else:
            logging.debug(f"Active player found: {player.title}")

        playback_queue = get_redis_queue()

        if not playback_queue:
            logging.warning("Playback queue is empty.")
            return

        logging.debug(f"Playback queue: {playback_queue}")

        # Play each track in the queue
        for song in playback_queue:
            item_id = song["item_id"]
            track = get_track(item_id)
            if not track:
                logging.error(f"Track with item_id {item_id} not found. Skipping track.")
                continue
            else:
                logging.debug(f"Track found: {track.title}")

            if hasattr(track, 'duration'):
                total_time = milliseconds_to_seconds(track.duration)
            else:
                logging.error(f"Track {track.title} has no 'duration' attribute. Skipping track.")
                continue

            if total_time <= 0:
                logging.error(f"Invalid total_time for {track.title}. Skipping track.")
                continue

            logging.debug(f"Starting playback of {track.title} on {player.title}")
            await asyncio.to_thread(play_song, player, track)

            await monitor_song_progress(track, total_time)

            remove_from_redis_queue(item_id)
    except Exception as e:
        logging.error(f"Error playing queue on device: {e}")
        raise

async def monitor_song_progress(track, total_time):
    """Monitor the progress of the song without blocking the event loop."""
    while track_time_tracker.is_playing:
        elapsed_time = track_time_tracker.get_elapsed_time(track.title)
        if elapsed_time >= total_time:
            logging.debug(f"Finished playing {track.title}. Moving to the next song.")
            track_time_tracker.stop()  # Stop tracking when the song finishes
            break
        await asyncio.sleep(1)

def stop_playback():
    """Stop the currently playing track on the active Plex player."""
    try:
        player = get_active_player()
        if player:
            logging.info(f"Stopping playback on {player.title}")
            player.stop(mtype="music")
            return {"message": "Playback stopped successfully."}
        else:
            logging.error("No active player found.")
            raise HTTPException(status_code=400, detail="No active player found.")
    except Exception as e:
        logging.error(f"Error stopping playback: {e}")
        raise HTTPException(status_code=500, detail=f"Error stopping playback: {e}")



def fetch_all_artists():
    """Fetch all artists from the Plex music library with Redis caching."""
    cache_key = "all_artists"
    cached_artists = get_cached_data(cache_key)

    if cached_artists:
        logging.info("Fetching artists from cache.")
        return cached_artists

    try:
        plex = get_plex_connection()
        music_library = plex.library.section("Music")
        artists = music_library.all(libtype="artist")
        artist_list = [
            {
                "artist_id": artist.ratingKey,
                "name": artist.title,
            } for artist in artists]

        # Cache the result in Redis
        cache_data(cache_key, artist_list)
        logging.info(f"Caching artists: {len(artist_list)}")

        return artist_list
    except Exception as e:
        logging.error(f"Error fetching all artists: {e}")
        raise

def fetch_albums_for_artist(artist_id):
    """Fetch albums for a specific artist by their ID with Redis caching."""
    cache_key = f"albums_for_artist_{artist_id}"
    cached_albums = get_cached_data(cache_key)

    if cached_albums:
        logging.info(f"Fetching albums for artist {artist_id} from cache.")
        return cached_albums

    try:
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

        # Cache the result in Redis
        cache_data(cache_key, album_list)
        logging.info(f"Caching {len(album_list)} albums for artist {artist_id}.")

        return album_list
    except Exception as e:
        logging.error(f"Error fetching albums for artist {artist_id}: {e}")
        raise


def fetch_tracks_for_album(album_id):
    """Fetch tracks for a specific album by its ID with Redis caching."""
    cache_key = f"tracks_for_album_{album_id}"
    cached_tracks = get_cached_data(cache_key)

    if cached_tracks:
        logging.info(f"Fetching tracks for album {album_id} from cache.")
        return cached_tracks

    try:
        plex = get_plex_connection()
        album = plex.fetchItem(album_id)
        tracks = album.tracks()
        track_list = {
            "album_title": album.title,
            "tracks": [
                {
                    "track_id": track.ratingKey,
                    "title": track.title,
                    "duration": milliseconds_to_seconds(track.duration) if track.duration else 0
                }
                for track in tracks
            ]
        }

        # Cache the result in Redis
        cache_data(cache_key, track_list)
        logging.info(f"Caching tracks for album {album_id}.")

        return track_list
    except Exception as e:
        logging.error(f"Error fetching tracks for album {album_id}: {e}")
        raise


def search_music(query):
    """Search for artists, albums, and tracks in Plex."""
    try:
        plex = get_plex_connection()
        music_library = plex.library.section("Music")

        artist_results = music_library.search(query, libtype="artist")
        album_results = music_library.search(query, libtype="album")
        track_results = music_library.search(query, libtype="track")

        formatted_results = []
        for item in artist_results:
            formatted_results.append({"name": item.title, "type": item.type, "artist_id": item.ratingKey})
        for item in album_results:
            formatted_results.append({"title": item.title, "type": item.type, "album_id": item.ratingKey, "artist": item.parentTitle})
        for item in track_results:
            formatted_results.append({
                "title": item.title, "type": item.type, "track_id": item.ratingKey,
                "duration": milliseconds_to_seconds(item.duration) if item.duration else 0,
                "artist": item.grandparentTitle, "album": item.parentTitle
            })

        return formatted_results
    except Exception as e:
        logging.error(f"Error searching music library: {e}")
        raise


def fetch_art(item_id: int, item_type: str):
    """Fetch image (either artist or album) from Plex securely."""
    try:
        plex = get_plex_connection()

        # Fetch the item (artist or album) based on the item_type
        if item_type == "artist":
            item = plex.fetchItem(item_id)
        elif item_type == "album":
            item = plex.fetchItem(item_id)
        else:
            raise HTTPException(status_code=400, detail="Invalid item type. Must be 'artist' or 'album'.")

        # Check if the item has a thumbnail
        if not item.thumb:
            raise HTTPException(status_code=404, detail=f"No image available for this {item_type}.")

        # Construct the URL to fetch the image from Plex
        image_url = f"{settings.plex_base_url}{item.thumb}?X-Plex-Token={settings.plex_token}"

        # Fetch the image
        response = requests.get(image_url, stream=True, verify=False)  # Disable SSL verification if needed
        if not response.ok:
            raise HTTPException(status_code=500, detail=f"Error fetching {item_type} image from Plex.")

        # Return the image response
        return response

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching {item_type} image: {e}")

