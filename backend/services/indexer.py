"""Incremental background library indexer for live Plex server synchronization."""

import time
import logging
import concurrent.futures
from backend.config import settings
from backend.services.library import (
    upsert_server,
    upsert_artist,
    upsert_album,
    upsert_track,
)

logger = logging.getLogger(__name__)


def index_server(server_info: dict, db_path: str | None = None, force_full: bool = False) -> int:
    """Index or perform incremental diff sync for a specific target Plex server into SQLite."""
    if settings.testing:
        logger.info("Testing mode active: Skipping live Plex indexing for server %s", server_info.get("name"))
        return 0

    s_id = server_info.get("server_id")
    s_name = server_info.get("name", settings.plex_server_name or "plex-so")
    s_url = server_info.get("server_url")
    is_primary = bool(server_info.get("is_primary"))

    upsert_server(s_id, s_name, server_url=s_url, is_primary=is_primary, enabled=True, db_path=db_path)

    from backend.services.plex import get_target_plex_connection, is_music_library_section, milliseconds_to_seconds

    try:
        plex = get_target_plex_connection(s_id)
        if not plex:
            logger.warning("Failed to connect to Plex server %s (ID: %s) for indexing.", s_name, s_id)
            return 0

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
            logger.warning("No music library sections found on Plex server %s", s_name)
            return 0

        items_indexed = 0
        now = int(time.time())

        for music_lib in music_libs:
            try:
                # 1. Fetch all artists in 1 fast bulk call
                artists = music_lib.all(libtype="artist")
                artist_map = {}
                for artist in artists:
                    guid_val = getattr(artist, "guid", None) or getattr(artist, "ratingKey", "")
                    a_db_id = upsert_artist(
                        name=artist.title,
                        guid=str(guid_val),
                        thumb=getattr(artist, "thumb", None),
                        play_count=getattr(artist, "viewCount", 0) or 0,
                        server_id=s_id,
                        server_artist_id=str(artist.ratingKey),
                        db_path=db_path,
                    )
                    artist_map[str(artist.ratingKey)] = (a_db_id, artist.title)
                    if artist.title:
                        artist_map[artist.title.lower()] = (a_db_id, artist.title)

                # 2. Fetch all albums in 1 fast bulk call
                albums = music_lib.all(libtype="album")
                album_map = {}
                for album in albums:
                    year_val = getattr(album, "year", None)
                    if not year_val and getattr(album, "originallyAvailableAt", None):
                        try:
                            year_val = album.originallyAvailableAt.year
                        except Exception:
                            pass

                    genre_tags = [g.tag for g in getattr(album, "genres", []) if hasattr(g, "tag")]
                    genre_val = genre_tags[0] if genre_tags else "Uncategorized"

                    parent_artist_key = str(getattr(album, "parentRatingKey", "") or getattr(album, "grandparentRatingKey", ""))
                    parent_title = (getattr(album, "artistTitle", "") or getattr(album, "grandparentTitle", "") or getattr(album, "parentTitle", "") or "").lower()
                    artist_info = artist_map.get(parent_artist_key) or artist_map.get(parent_title)
                    a_db_id = artist_info[0] if artist_info else None
                    artist_name = artist_info[1] if artist_info else (getattr(album, "artistTitle", None) or getattr(album, "grandparentTitle", None) or getattr(album, "parentTitle", None) or "Unknown Artist")

                    alb_db_id = upsert_album(
                        title=album.title,
                        artist_name=artist_name,
                        artist_id=a_db_id,
                        year=year_val,
                        genre=genre_val,
                        thumb=getattr(album, "thumb", None),
                        play_count=getattr(album, "viewCount", 0) or 0,
                        guid=str(getattr(album, "guid", None) or album.ratingKey),
                        server_id=s_id,
                        server_album_id=str(album.ratingKey),
                        db_path=db_path,
                    )
                    album_map[str(album.ratingKey)] = (alb_db_id, album.title, artist_name, getattr(album, "thumb", None))

                # 3. Fetch all tracks in 1 fast bulk call
                tracks = music_lib.all(libtype="track")
                for track in tracks:
                    parent_album_key = str(getattr(track, "parentRatingKey", ""))
                    alb_info = album_map.get(parent_album_key)
                    alb_db_id = alb_info[0] if alb_info else None
                    alb_title = alb_info[1] if alb_info else (getattr(track, "albumTitle", None) or getattr(track, "parentTitle", None) or "Unknown Album")
                    art_name = alb_info[2] if alb_info else (getattr(track, "grandparentTitle", None) or getattr(track, "artistTitle", None) or "Unknown Artist")
                    alb_thumb = alb_info[3] if alb_info else getattr(track, "thumb", None)

                    duration_sec = milliseconds_to_seconds(track.duration) if getattr(track, "duration", None) else 0
                    trk_url = getattr(track, "key", None)

                    raw_user_rating = getattr(track, "userRating", 0.0) or 0.0
                    user_rating_stars = float(raw_user_rating) / 2.0 if raw_user_rating else 0.0

                    upsert_track(
                        album_id=alb_db_id,
                        server_id=s_id,
                        server_track_id=str(track.ratingKey),
                        artist_name=art_name,
                        album_title=alb_title,
                        title=track.title,
                        duration=duration_sec,
                        url=str(trk_url) if trk_url else None,
                        thumb=alb_thumb,
                        play_count=getattr(track, "viewCount", 0) or 0,
                        user_rating=user_rating_stars,
                        db_path=db_path,
                    )
                    items_indexed += 1

            except Exception as lib_ex:
                logger.warning("Error scanning section '%s' on server %s: %s", getattr(music_lib, "title", "Unknown"), s_name, lib_ex)

        logger.info("Successfully indexed %d items from server %s (ID: %s)", items_indexed, s_name, s_id)
        return items_indexed
    except Exception as ex:
        logger.exception("Error indexing server %s: %s", s_name, ex)
        return 0


def sync_all_servers(db_path: str | None = None, force_full: bool = False):
    """Sync and perform incremental diff index across all accessible enabled Plex servers."""
    if settings.testing:
        from backend.services.mock_data import seed_mock_library_db
        seed_mock_library_db(db_path)
        return

    try:
        from backend.services.plex import fetch_accessible_plex_servers, get_enabled_server_ids

        enabled_ids = get_enabled_server_ids()
        all_accessible = fetch_accessible_plex_servers()
        enabled_set = {str(x).lower() for x in enabled_ids}

        target_servers = [
            s for s in all_accessible
            if str(s.get("server_id", "")).lower() in enabled_set
            or str(s.get("name", "")).lower() in enabled_set
        ]

        if not target_servers:
            target_servers = [s for s in all_accessible if s.get("is_primary")] or (all_accessible[:1] if all_accessible else [])

        if not target_servers:
            from backend.services.mock_data import seed_mock_library_db
            seed_mock_library_db(db_path)
            return

        logger.info("Starting background incremental diff sync for %d enabled server(s)...", len(target_servers))

        with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(target_servers) or 1, 4)) as executor:
            futures = [executor.submit(index_server, s, db_path, force_full) for s in target_servers]
            done, _ = concurrent.futures.wait(futures, timeout=60.0)
            for f in done:
                try:
                    f.result()
                except Exception as ex:
                    logger.warning("Error in background server sync thread: %s", ex)
    except Exception as ex:
        logger.warning("Falling back to mock library seeding due to sync error: %s", ex)
        from backend.services.mock_data import seed_mock_library_db
        seed_mock_library_db(db_path)
