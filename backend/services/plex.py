import asyncio

from plexapi.server import PlexServer
from plexapi.exceptions import PlexApiException
from backend.config import settings
import requests
from backend.state import playback_queue
from backend.utils import TrackTimeTracker, milliseconds_to_seconds

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
            view_offset = session.viewOffset
            track_state = session.player.state
            elapsed_time = track_time_tracker.get_elapsed_time(session.title)
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


def add_to_local_queue(song):
    """Add a song to the local playback queue."""
    if not any(track.ratingKey == song.ratingKey for track in playback_queue):
        playback_queue.append(song)  # Add the track object directly
        logging.info(f"Added {song.title} to the local playback queue.")
    else:
        logging.info(f"{song.title} is already in the queue.")


def remove_from_local_queue(song):
    """Remove an item from the local playback queue."""
    track_to_remove = None
    for track in playback_queue:
        if track.ratingKey == song.ratingKey:
            track_to_remove = track
            break

    if track_to_remove:
        playback_queue.remove(track_to_remove)
        logging.info(f"Removed {track_to_remove.title} from the local playback queue.")
    else:
        logging.warning(f"{song.title} not found in the queue.")


# Clear the local playback queue
def clear_local_queue():
    """Clear the entire local playback queue."""
    playback_queue.clear()
    logging.info("The local playback queue has been cleared.")


import logging

def get_local_playback_queue():
    """Get the current local playback queue."""
    try:
        logging.debug(f"Fetching playback queue. Current queue size: {len(playback_queue)}")

        if not playback_queue:
            logging.warning("The playback queue is empty.")
            return []

        queue_items = []
        for song in playback_queue:
            try:
                item_details = {
                    "item_id": song.ratingKey,
                    "title": song.title,
                    "artist": getattr(song, "grandparentTitle", "Unknown Artist"),
                    "duration": getattr(song, "duration", 0)
                }
                queue_items.append(item_details)
            except AttributeError as e:
                logging.error(f"Error processing item {song}: {e}. This item might be missing required attributes.")
                continue

        if not queue_items:
            logging.warning("No valid items found in the queue.")
            return []

        return queue_items

    except Exception as e:
        logging.error(f"An error occurred while fetching the playback queue: {e}")
        raise Exception(f"Error fetching the queue: {e}")


def play_song(player, song):
    """Play a specific song on the Plex player."""
    try:
        logging.info(f"Playing song: {song.title} on player: {player.title}")
        player.playMedia(song)
        track_time_tracker.start(song.title)
    except Exception as e:
        logging.error(f"Error playing media: {e}")
        raise

async def play_queue_on_device():
    """Play the entire queue on the active Plex device."""
    try:
        player = get_active_player()

        if not playback_queue:
            logging.warning("Playback queue is empty.")
            return

        # Play each track in the queue
        for track in playback_queue:
            if hasattr(track, 'duration'):
                total_time = milliseconds_to_seconds(track.duration)
            else:
                logging.error(f"Track {track.title} has no 'duration' attribute. Skipping track.")
                continue

            # Ensure the track has a valid total_time
            if total_time <= 0:
                logging.error(f"Invalid total_time for {track.title}. Skipping track.")
                continue

            logging.debug(f"Starting playback of {track.title} on {player.title}")
            await asyncio.to_thread(play_song, player, track)

            # Monitor song progress asynchronously using asyncio.create_task
            await monitor_song_progress(track, total_time)

            logging.debug(f"Finished playing {track.title}. Moving to the next song.")
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

def fetch_all_artists():
    """Fetch all artists from the Plex music library."""
    try:
        plex = get_plex_connection()
        music_library = plex.library.section("Music")
        artists = music_library.all(libtype="artist")
        return [{"artist_id": artist.ratingKey, "name": artist.title} for artist in artists]
    except Exception as e:
        logging.error(f"Error fetching all artists: {e}")
        raise

def fetch_albums_for_artist(artist_id):
    """Fetch albums for a specific artist by their ID."""
    try:
        plex = get_plex_connection()
        artist = plex.fetchItem(artist_id)
        albums = artist.albums()
        return [
            {
                "album_id": album.ratingKey,
                "title": album.title,
                "thumb": f"{settings.plex_base_url}{album.thumb}?X-Plex-Token={settings.plex_token}" if album.thumb else None
            }
            for album in albums
        ]
    except Exception as e:
        logging.error(f"Error fetching albums for artist {artist_id}: {e}")
        raise

def fetch_tracks_for_album(album_id):
    """Fetch tracks for a specific album by its ID."""
    try:
        plex = get_plex_connection()
        album = plex.fetchItem(album_id)
        tracks = album.tracks()
        return {
            "album_title": album.title,
            "thumb": f"{settings.plex_base_url}{album.thumb}?X-Plex-Token={settings.plex_token}" if album.thumb else None,
            "tracks": [
                {
                    "track_id": track.ratingKey,
                    "title": track.title,
                    "duration": milliseconds_to_seconds(track.duration) if track.duration else 0
                }
                for track in tracks
            ]
        }
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
            formatted_results.append({"title": item.title, "type": item.type, "artist_id": item.ratingKey})
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
