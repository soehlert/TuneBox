from plexapi.server import PlexServer
from plexapi.exceptions import PlexApiException
from backend.config import settings
import logging
import requests
from backend.state import playback_queue


import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def format_duration(milliseconds):
    """Convert duration in milliseconds to a mm:ss string format."""
    seconds = milliseconds // 1000
    minutes = seconds // 60
    remaining_seconds = seconds % 60
    return f"{minutes}:{remaining_seconds:02}"


def fetch_item_by_rating_key(rating_key):
    """Fetch an item by its ratingKey from the Plex library."""
    try:
        plex = get_plex_connection()
        music_library = plex.library.section("Music")

        track_results = music_library.search(rating_key, libtype="track")

        logging.debug(f"Fetched item: {track_results.title}")
        return track_results
    except Exception as e:
        logging.error(f"Error fetching item with ratingKey {rating_key}: {e}")
        raise


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


def get_active_session():
    """Get the active session for the player; this returns the actively playing Track."""
    plex = get_plex_connection()
    active_player = get_active_player()

    # Retrieve active sessions and find the one that corresponds to the active player
    sessions = plex.sessions()
    for session in sessions:
        if session.player.machineIdentifier == active_player.machineIdentifier:
            return session

    logging.error("No active session found for the player.")
    raise Exception("No active session found for the player.")


def get_current_playing_track():
    """Fetch the currently playing track on the active player."""
    plex = get_plex_connection()
    player = get_active_player().machineIdentifier
    sessions = plex.sessions()

    if not sessions:
        logging.debug("No active sessions found.")
        return None

    # Find the first session where media is currently playing
    for session in sessions:
        if session.player.machineIdentifier == player:
            if session.player.state == 'playing':
                # Extract the media (track) information from the session
                current_track = {
                    'title': session.title,
                    'artist': session.grandparentTitle,
                    'album': session.parentTitle
                }
                return current_track

    logging.debug("No media is currently playing.")
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
        item = plex.fetchItem(item_id)
        return item
    except PlexApiException as e:
        logging.error(f"Error adding item to playback queue: {e}")
        raise


# Add an item to the local playback queue
def add_to_local_queue(item):
    """Add a song to the local playback queue."""
    if item not in playback_queue:
        playback_queue.append(item)
        logging.info(f"Added {item.title} to the local playback queue.")
    else:
        logging.info(f"{item.title} is already in the queue.")


# Remove an item from the local playback queue
def remove_from_local_queue(item):
    """Remove an item from the local playback queue."""
    if item in playback_queue:
        playback_queue.remove(item)
        logging.info(f"Removed {item.title} from the local playback queue.")
    else:
        logging.warning(f"{item.title} not found in the queue.")


# Clear the local playback queue
def clear_local_queue():
    """Clear the entire local playback queue."""
    playback_queue.clear()
    logging.info("The local playback queue has been cleared.")


import logging

def get_local_playback_queue():
    """Get the current local playback queue."""
    try:
        # Log the state of the playback queue
        logging.debug(f"Fetching playback queue. Current queue size: {len(playback_queue)}")

        if not playback_queue:
            logging.warning("The playback queue is empty.")
            return []

        queue_items = []
        for item in playback_queue:
            try:
                # Attempt to fetch item details and ensure it's well-formed
                item_details = {
                    "item_id": item.ratingKey,
                    "title": item.title,
                    "artist": getattr(item, "grandparentTitle", "Unknown Artist")  # Fallback to 'Unknown Artist' if no artist field
                }
                queue_items.append(item_details)
            except AttributeError as e:
                logging.error(f"Error processing item {item}: {e}. This item might be missing required attributes.")
                continue  # Skip this item if it doesn't have the expected structure

        if not queue_items:
            logging.warning("No valid items found in the queue.")
            return []

        return queue_items

    except Exception as e:
        logging.error(f"An error occurred while fetching the playback queue: {e}")
        raise Exception(f"Error fetching the queue: {e}")



def play_media_on_player(player, media):
    """Play the specified media on the provided Plex player."""
    try:
        player.playMedia(media)  # This line assumes 'player' has a method `playMedia`
        logging.info(f"Playing media: {media.title} on {player.title}")
    except Exception as e:
        logging.error(f"Error playing media: {e}")
        raise

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
                    "duration": format_duration(track.duration) if track.duration else "0:00"
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
                "duration": format_duration(item.duration) if item.duration else None,
                "artist": item.grandparentTitle, "album": item.parentTitle
            })

        return formatted_results
    except Exception as e:
        logging.error(f"Error searching music library: {e}")
        raise
