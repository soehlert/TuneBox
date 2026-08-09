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

import threading

logger = logging.getLogger(__name__)

_sync_lock = threading.Lock()


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

    # Check if this server is being indexed for the first time (0 tracks for this server or 0 total artists)
    is_initial = False
    try:
        from backend.db.library_db import get_db_connection  # noqa: PLC0415
        conn = get_db_connection(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM tracks WHERE server_id = ?;", (s_id,))
        server_track_count = cursor.fetchone()[0]
        if server_track_count == 0:
            is_initial = True
        else:
            cursor.execute("SELECT COUNT(*) FROM artists;")
            artist_count = cursor.fetchone()[0]
            is_initial = (artist_count == 0)
        conn.close()
    except Exception:
        pass

    try:
        if is_initial:
            from backend.websockets import broadcast_indexing_status_threadsafe  # noqa: PLC0415
            broadcast_indexing_status_threadsafe(is_indexing=True, is_initial=True, server_name=s_name)
    except Exception as ws_ex:
        logger.debug("Could not send indexing status start: %s", ws_ex)

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

        items_indexed = 0
        from backend.db.library_db import get_db_connection  # noqa: PLC0415

        for music_lib in music_libs:
            try:
                # 1. Bulk fetch all artists for section over network (NO DB lock open)
                logger.info("Bulk fetching artists for section '%s' on server %s...", getattr(music_lib, "title", "Music"), s_name)
                artists = music_lib.all(libtype="artist")
                artist_map: dict[str, int] = {}  # ratingKey -> artist_db_id
                artist_name_map: dict[str, str] = {}  # ratingKey -> artist_name

                # Perform fast DB transaction for artists
                conn = get_db_connection(db_path)
                try:
                    for artist in artists:
                        try:
                            guid_val = getattr(artist, "guid", None) or getattr(artist, "ratingKey", "")
                            a_db_id = upsert_artist(
                                name=artist.title,
                                guid=str(guid_val),
                                thumb=getattr(artist, "thumb", None),
                                play_count=getattr(artist, "viewCount", 0) or 0,
                                server_id=s_id,
                                server_artist_id=str(artist.ratingKey),
                                db_path=db_path,
                                conn=conn,
                            )
                            r_key = str(artist.ratingKey)
                            artist_map[r_key] = a_db_id
                            artist_name_map[r_key] = artist.title
                        except Exception as a_ex:
                            logger.debug("Failed to upsert artist %s: %s", getattr(artist, "title", "Unknown"), a_ex)
                    conn.commit()
                finally:
                    conn.close()
                logger.info("Bulk upserted %d artists for server %s.", len(artist_map), s_name)

                # 2. Bulk fetch all albums for section over network (NO DB lock open)
                logger.info("Bulk fetching albums for section '%s' on server %s...", getattr(music_lib, "title", "Music"), s_name)
                albums = music_lib.all(libtype="album")
                album_map: dict[str, int] = {}  # album ratingKey -> album_db_id

                # Perform fast DB transaction for albums
                conn = get_db_connection(db_path)
                try:
                    for album in albums:
                        try:
                            year_val = getattr(album, "year", None)
                            if not year_val and getattr(album, "originallyAvailableAt", None):
                                try:
                                    year_val = album.originallyAvailableAt.year
                                except Exception:
                                    pass

                            genre_tags = [g.tag for g in getattr(album, "genres", []) if hasattr(g, "tag")]
                            genre_val = genre_tags[0] if genre_tags else "Uncategorized"

                            p_key = str(getattr(album, "parentRatingKey", ""))
                            a_db_id = artist_map.get(p_key)
                            a_name = getattr(album, "parentTitle", None) or artist_name_map.get(p_key, "Unknown Artist")

                            alb_db_id = upsert_album(
                                title=album.title,
                                artist_name=a_name,
                                artist_id=a_db_id,
                                year=year_val,
                                genre=genre_val,
                                thumb=getattr(album, "thumb", None),
                                play_count=getattr(album, "viewCount", 0) or 0,
                                guid=str(getattr(album, "guid", None) or album.ratingKey),
                                server_id=s_id,
                                server_album_id=str(album.ratingKey),
                                db_path=db_path,
                                conn=conn,
                            )
                            album_map[str(album.ratingKey)] = alb_db_id
                        except Exception as alb_ex:
                            logger.debug("Failed to upsert album %s: %s", getattr(album, "title", "Unknown"), alb_ex)
                    conn.commit()
                finally:
                    conn.close()
                logger.info("Bulk upserted %d albums for server %s.", len(album_map), s_name)

                # 3. Bulk fetch all tracks for section over network (NO DB lock open)
                logger.info("Bulk fetching tracks for section '%s' on server %s...", getattr(music_lib, "title", "Music"), s_name)
                tracks = music_lib.all(libtype="track")

                # Perform fast DB transaction for tracks
                conn = get_db_connection(db_path)
                try:
                    for track in tracks:
                        try:
                            duration_sec = milliseconds_to_seconds(track.duration) if getattr(track, "duration", None) else 0
                            trk_url = getattr(track, "key", None)

                            raw_user_rating = getattr(track, "userRating", 0.0) or 0.0
                            user_rating_stars = float(raw_user_rating) / 2.0 if raw_user_rating else 0.0

                            p_alb_key = str(getattr(track, "parentRatingKey", ""))
                            alb_db_id = album_map.get(p_alb_key)

                            artist_name = getattr(track, "grandparentTitle", None) or "Unknown Artist"
                            album_title = getattr(track, "parentTitle", None) or "Unknown Album"

                            upsert_track(
                                album_id=alb_db_id,
                                server_id=s_id,
                                server_track_id=str(track.ratingKey),
                                artist_name=artist_name,
                                album_title=album_title,
                                title=track.title,
                                duration=duration_sec,
                                url=str(trk_url) if trk_url else None,
                                thumb=getattr(track, "parentThumb", None) or getattr(track, "thumb", None),
                                play_count=getattr(track, "viewCount", 0) or 0,
                                user_rating=user_rating_stars,
                                db_path=db_path,
                                conn=conn,
                            )
                            items_indexed += 1
                        except Exception as trk_ex:
                            logger.debug("Failed to upsert track %s: %s", getattr(track, "title", "Unknown"), trk_ex)
                    conn.commit()
                finally:
                    conn.close()

            except Exception as lib_ex:
                logger.warning("Error scanning section '%s' on server %s: %s", getattr(music_lib, "title", "Unknown"), s_name, lib_ex)

        logger.info("Successfully indexed %d items from server %s (ID: %s)", items_indexed, s_name, s_id)
        try:
            from backend.websockets import broadcast_indexing_status_threadsafe  # noqa: PLC0415
            broadcast_indexing_status_threadsafe(is_indexing=False, is_initial=is_initial, server_name=s_name, items_indexed=items_indexed)
        except Exception as ws_ex:
            logger.debug("Could not send indexing status complete: %s", ws_ex)
        return items_indexed
    except Exception as ex:
        logger.exception("Error indexing server %s: %s", s_name, ex)
        return 0


def sync_all_servers(db_path: str | None = None, force_full: bool = False):
    """Sync and perform incremental diff index across all accessible enabled Plex servers."""
    if not _sync_lock.acquire(blocking=False):
        logger.info("Library index sync is already in progress. Skipping redundant concurrent request.")
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
            from backend.services.mock_data import seed_mock_library_db
            seed_mock_library_db(db_path)
            return

        # Prioritize unindexed servers (0 tracks in SQLite) first so new server banners show immediately
        def _server_priority(s: dict) -> tuple[int, int]:
            s_id = s.get("server_id")
            count = 0
            try:
                from backend.db.library_db import get_db_connection  # noqa: PLC0415
                conn = get_db_connection(db_path)
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM tracks WHERE server_id = ?;", (s_id,))
                count = cursor.fetchone()[0]
                conn.close()
            except Exception:
                pass

            if count == 0:
                return (0, 0)
            if s.get("is_primary"):
                return (1, 0)
            return (2, 0)

        sorted_targets = sorted(target_servers, key=_server_priority)
        first_batch = [sorted_targets[0]] if sorted_targets else []
        remaining_batch = sorted_targets[1:] if len(sorted_targets) > 1 else []

        logger.info("Starting sync for %d server(s): first='%s', remaining=%d...", len(sorted_targets), first_batch[0].get("name") if first_batch else "", len(remaining_batch))

        # 1. Index first target server (unindexed new server or primary) FIRST
        for s in first_batch:
            try:
                logger.info("Indexing server '%s' first...", s.get("name"))
                index_server(s, db_path, force_full)
            except Exception as ex:
                logger.warning("Error indexing server %s: %s", s.get("name"), ex)

        # 2. Index remaining servers sequentially to prevent SQLite database lock contention
        if remaining_batch:
            logger.info("Indexing %d remaining server(s) sequentially...", len(remaining_batch))
            for s in remaining_batch:
                try:
                    logger.info("Indexing server '%s'...", s.get("name"))
                    index_server(s, db_path, force_full)
                except Exception as ex:
                    logger.warning("Error indexing server %s: %s", s.get("name"), ex)
    except Exception as ex:
        logger.warning("Error in sync_all_servers: %s", ex)
    finally:
        _sync_lock.release()
