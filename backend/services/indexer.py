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

    acc_token = server_info.get("access_token")
    upsert_server(s_id, s_name, server_url=s_url, is_primary=is_primary, enabled=None, access_token=acc_token, db_path=db_path)

    from backend.services.plex import get_target_plex_connection, is_music_library_section, milliseconds_to_seconds

    # Check if this server is already indexed in SQLite
    server_track_count = 0
    try:
        from backend.db.library_db import get_db_connection  # noqa: PLC0415
        conn = get_db_connection(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM tracks WHERE server_id = ?;", (s_id,))
        server_track_count = cursor.fetchone()[0]
        conn.close()

        if server_track_count > 0 and not force_full:
            logger.info("Server '%s' (ID: %s) is already indexed in SQLite (%d tracks). Skipping network re-indexing.", s_name, s_id, server_track_count)
            return server_track_count
    except Exception as ex:
        logger.debug("Failed checking existing track count for server %s: %s", s_name, ex)

    is_initial = (server_track_count == 0)

    try:
        from backend.websockets import broadcast_indexing_status_threadsafe  # noqa: PLC0415
        broadcast_indexing_status_threadsafe(is_indexing=True, is_initial=is_initial, server_name=s_name, message=f"Indexing artists on {s_name}")
    except Exception as ws_ex:
        logger.debug("Could not send indexing status start: %s", ws_ex)

    try:
        plex = get_target_plex_connection(s_id)
        if not plex:
            logger.warning("Failed to connect to Plex server %s (ID: %s) for indexing.", s_name, s_id)
            try:
                from backend.websockets import broadcast_indexing_status_threadsafe  # noqa: PLC0415
                broadcast_indexing_status_threadsafe(is_indexing=False, is_initial=is_initial, server_name=s_name, items_indexed=0, message=f"Plex server '{s_name}' is unreachable or offline.", is_error=True)
            except Exception:
                pass
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
            try:
                from backend.websockets import broadcast_indexing_status_threadsafe  # noqa: PLC0415
                broadcast_indexing_status_threadsafe(is_indexing=False, is_initial=is_initial, server_name=s_name, items_indexed=0, message=f"No Music libraries found on Plex server '{s_name}'.", is_error=True)
            except Exception:
                pass
            return 0

        items_indexed = 0
        now = int(time.time())

        items_indexed = 0
        from backend.db.library_db import get_db_connection  # noqa: PLC0415

        def _is_cancelled() -> bool:
            from backend.services.plex import get_enabled_server_ids  # noqa: PLC0415
            if s_id not in get_enabled_server_ids():
                logger.info("Indexing for server %s (ID: %s) was cancelled because server was disabled by user.", s_name, s_id)
                try:
                    from backend.websockets import broadcast_indexing_status_threadsafe  # noqa: PLC0415
                    broadcast_indexing_status_threadsafe(is_indexing=False, is_initial=is_initial, server_name=s_name, items_indexed=0, message=f"Indexing cancelled for {s_name}.")
                except Exception:
                    pass
                return True
            return False

        for music_lib in music_libs:
            try:
                # 1. Bulk fetch all artists for section over network
                if _is_cancelled():
                    return 0

                try:
                    from backend.websockets import broadcast_indexing_status_threadsafe  # noqa: PLC0415
                    broadcast_indexing_status_threadsafe(is_indexing=True, is_initial=is_initial, server_name=s_name, message=f"Indexing artists on {s_name}")
                except Exception:
                    pass

                logger.info("Bulk fetching artists for section '%s' on server %s...", getattr(music_lib, "title", "Music"), s_name)
                artist_map: dict[str, int] = {}  # ratingKey -> artist_db_id
                artist_name_map: dict[str, str] = {}  # ratingKey -> artist_name

                json_artists = fetch_section_json_batched(plex, music_lib, item_type=8)
                conn = get_db_connection(db_path)
                try:
                    if json_artists is not None:
                        logger.info("Fetched %d artists via fast JSON batching for %s.", len(json_artists), s_name)
                        for idx, art in enumerate(json_artists):
                            try:
                                a_db_id = upsert_artist(
                                    name=art.get("title") or "Unknown Artist",
                                    guid=str(art.get("guid") or art.get("ratingKey")),
                                    thumb=art.get("thumb"),
                                    play_count=int(art.get("viewCount", 0) or 0),
                                    server_id=s_id,
                                    server_artist_id=str(art.get("ratingKey")),
                                    db_path=db_path,
                                    conn=conn,
                                )
                                r_key = str(art.get("ratingKey"))
                                artist_map[r_key] = a_db_id
                                artist_name_map[r_key] = art.get("title") or "Unknown Artist"
                                if idx > 0 and idx % 500 == 0:
                                    conn.commit()
                            except Exception as a_ex:
                                logger.debug("Failed to upsert JSON artist %s: %s", art.get("title"), a_ex)
                        conn.commit()
                    else:
                        logger.info("Fallback: fetching artists via plexapi for section '%s' on %s...", getattr(music_lib, "title", "Music"), s_name)
                        artists = music_lib.all(libtype="artist")
                        for idx, artist in enumerate(artists):
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
                                if idx > 0 and idx % 500 == 0:
                                    conn.commit()
                            except Exception as a_ex:
                                logger.debug("Failed to upsert artist %s: %s", getattr(artist, "title", "Unknown"), a_ex)
                        conn.commit()
                finally:
                    conn.close()
                logger.info("Bulk upserted %d artists for server %s.", len(artist_map), s_name)

                # 2. Bulk fetch all albums for section over network
                if _is_cancelled():
                    return 0

                try:
                    from backend.websockets import broadcast_indexing_status_threadsafe  # noqa: PLC0415
                    broadcast_indexing_status_threadsafe(is_indexing=True, is_initial=is_initial, server_name=s_name, message=f"Indexing albums on {s_name}")
                except Exception:
                    pass

                logger.info("Bulk fetching albums for section '%s' on server %s", getattr(music_lib, "title", "Music"), s_name)
                album_map: dict[str, int] = {}  # album ratingKey -> album_db_id

                json_albums = fetch_section_json_batched(plex, music_lib, item_type=9)
                conn = get_db_connection(db_path)
                try:
                    if json_albums is not None:
                        logger.info("Fetched %d albums via fast JSON batching for %s.", len(json_albums), s_name)
                        for idx, alb in enumerate(json_albums):
                            try:
                                year_val = alb.get("year")
                                genre_list = alb.get("Genre", [])
                                genre_val = genre_list[0].get("tag") if genre_list and isinstance(genre_list, list) and isinstance(genre_list[0], dict) else "Uncategorized"
                                p_key = str(alb.get("parentRatingKey", ""))
                                a_db_id = artist_map.get(p_key)
                                a_name = alb.get("parentTitle") or artist_name_map.get(p_key, "Unknown Artist")

                                alb_db_id = upsert_album(
                                    title=alb.get("title") or "Unknown Album",
                                    artist_name=a_name,
                                    artist_id=a_db_id,
                                    year=year_val,
                                    genre=genre_val,
                                    thumb=alb.get("thumb"),
                                    play_count=int(alb.get("viewCount", 0) or 0),
                                    guid=str(alb.get("guid") or alb.get("ratingKey")),
                                    server_id=s_id,
                                    server_album_id=str(alb.get("ratingKey")),
                                    db_path=db_path,
                                    conn=conn,
                                )
                                album_map[str(alb.get("ratingKey"))] = alb_db_id
                                if idx > 0 and idx % 500 == 0:
                                    conn.commit()
                            except Exception as alb_ex:
                                logger.debug("Failed to upsert JSON album %s: %s", alb.get("title"), alb_ex)
                        conn.commit()
                    else:
                        logger.info("Fallback: fetching albums via plexapi for section '%s' on %s...", getattr(music_lib, "title", "Music"), s_name)
                        albums = music_lib.all(libtype="album")
                        for idx, album in enumerate(albums):
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
                                if idx > 0 and idx % 500 == 0:
                                    conn.commit()
                            except Exception as alb_ex:
                                logger.debug("Failed to upsert album %s: %s", getattr(album, "title", "Unknown"), alb_ex)
                        conn.commit()
                finally:
                    conn.close()
                logger.info("Bulk upserted %d albums for server %s.", len(album_map), s_name)

                # 3. Bulk fetch all tracks for section over network
                if _is_cancelled():
                    return 0

                try:
                    from backend.websockets import broadcast_indexing_status_threadsafe  # noqa: PLC0415
                    broadcast_indexing_status_threadsafe(is_indexing=True, is_initial=is_initial, server_name=s_name, message=f"Indexing tracks on {s_name}")
                except Exception:
                    pass

                logger.info("Bulk fetching tracks for section '%s' on server %s", getattr(music_lib, "title", "Music"), s_name)
                json_tracks = fetch_section_json_batched(plex, music_lib, item_type=10)
                conn = get_db_connection(db_path)
                try:
                    if json_tracks is not None:
                        logger.info("Fetched %d tracks via fast JSON batching for %s.", len(json_tracks), s_name)
                        for trk in json_tracks:
                            try:
                                dur = (int(trk.get("duration", 0) or 0)) // 1000
                                raw_rating = float(trk.get("userRating", 0.0) or 0.0)
                                p_alb_key = str(trk.get("parentRatingKey", ""))
                                alb_db_id = album_map.get(p_alb_key)

                                media = trk.get("Media", [{}])[0] if trk.get("Media") else {}
                                bitrate = int(media.get("bitrate", 0) or 0)
                                codec = media.get("audioCodec") or media.get("container")

                                upsert_track(
                                    album_id=alb_db_id,
                                    server_id=s_id,
                                    server_track_id=str(trk.get("ratingKey")),
                                    artist_name=trk.get("grandparentTitle") or "Unknown Artist",
                                    album_title=trk.get("parentTitle") or "Unknown Album",
                                    title=trk.get("title") or "Unknown Track",
                                    duration=dur,
                                    url=trk.get("key"),
                                    thumb=trk.get("parentThumb") or trk.get("thumb"),
                                    play_count=int(trk.get("viewCount", 0) or 0),
                                    user_rating=raw_rating / 2.0 if raw_rating else 0.0,
                                    bitrate=bitrate,
                                    codec=codec,
                                    db_path=db_path,
                                    conn=conn,
                                )
                                items_indexed += 1
                            except Exception as trk_ex:
                                logger.debug("Failed to upsert JSON track %s: %s", trk.get("title"), trk_ex)
                        conn.commit()
                    else:
                        logger.info("Fallback: fetching tracks via plexapi for section '%s' on %s...", getattr(music_lib, "title", "Music"), s_name)
                        tracks = music_lib.all(libtype="track")
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
                                media = getattr(track, "media", [None])[0] if getattr(track, "media", None) else None
                                bitrate = getattr(media, "bitrate", 0) if media else 0
                                codec = getattr(media, "audioCodec", None) if media else None

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
                                    bitrate=int(bitrate or 0),
                                    codec=str(codec) if codec else None,
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
                try:
                    from backend.websockets import broadcast_indexing_status_threadsafe  # noqa: PLC0415
                    broadcast_indexing_status_threadsafe(
                        is_indexing=False,
                        is_initial=is_initial,
                        server_name=s_name,
                        items_indexed=0,
                        message=f"Indexing failed for '{s_name}': {lib_ex}",
                        is_error=True,
                    )
                except Exception:
                    pass
                return 0

        logger.info("Successfully indexed %d items from server %s (ID: %s)", items_indexed, s_name, s_id)
        try:
            from backend.websockets import broadcast_indexing_status_threadsafe  # noqa: PLC0415
            broadcast_indexing_status_threadsafe(is_indexing=False, is_initial=is_initial, server_name=s_name, items_indexed=items_indexed, message=f"Indexing complete for {s_name}!")
        except Exception as ws_ex:
            logger.debug("Could not send indexing status complete: %s", ws_ex)

        # Pre-warm top thumbnails into Redis in background
        if artist_map or album_map:
            _prewarm_art_in_background(s_id, list(artist_map.values()), list(album_map.values()))

        return items_indexed
    except Exception as ex:
        logger.exception("Error indexing server %s: %s", s_name, ex)
        try:
            from backend.websockets import broadcast_indexing_status_threadsafe  # noqa: PLC0415
            broadcast_indexing_status_threadsafe(
                is_indexing=False,
                is_initial=is_initial,
                server_name=s_name,
                items_indexed=0,
                message=f"Indexing failed for '{s_name}': {ex}",
                is_error=True,
            )
        except Exception:
            pass
        return 0


def fetch_section_json_batched(plex_conn, music_lib, item_type: int = 10, batch_size: int = 5000) -> list[dict] | None:
    """Fetch all items from a music section using fast paginated JSON requests (5,000 items per batch)."""
    try:
        import json
        import urllib.request
        import ssl

        server_url = getattr(plex_conn, "_baseurl", None)
        token = getattr(plex_conn, "_token", None)
        sec_key = getattr(music_lib, "key", None)

        if not server_url or not token or not sec_key:
            return None

        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

        all_items = []
        start = 0

        while True:
            url = f"{server_url}/library/sections/{sec_key}/all?type={item_type}&X-Plex-Token={token}&X-Plex-Container-Start={start}&X-Plex-Container-Size={batch_size}"
            req = urllib.request.Request(url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=30, context=ctx) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                mc = data.get("MediaContainer", {})
                items = mc.get("Metadata", [])
                if not items:
                    break
                all_items.extend(items)
                start += len(items)
                if len(items) < batch_size:
                    break
        return all_items
    except Exception as ex:
        logger.debug("Fast JSON batching failed for type %d, falling back to plexapi: %s", item_type, ex)
        return None


def _prewarm_art_in_background(server_id: str, artist_ids: list[int], album_ids: list[int]):
    """Pre-warm artist and album thumbnails into Redis in a parallel background thread pool."""
    def _worker():
        try:
            from backend.services.plex import fetch_art_bytes
            logger.info("Pre-warming %d artist and %d album thumbnails into Redis for server %s...", len(artist_ids), len(album_ids), server_id)
            
            with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
                for a_id in artist_ids:
                    executor.submit(fetch_art_bytes, a_id, "artist", server_id)
                for alb_id in album_ids:
                    executor.submit(fetch_art_bytes, alb_id, "album", server_id)
                    
            logger.info("Artwork pre-warming complete for server %s.", server_id)
        except Exception as ex:
            logger.debug("Art prewarming error for server %s: %s", server_id, ex)

    import threading
    threading.Thread(target=_worker, daemon=True).start()


def sync_all_servers(db_path: str | None = None, force_full: bool = False):
    """Sync and perform incremental diff index across all accessible enabled Plex servers."""
    if not _sync_lock.acquire(blocking=True, timeout=10):
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
            if settings.testing:
                from backend.services.mock_data import seed_mock_library_db  # noqa: PLC0415
                seed_mock_library_db(db_path)
            else:
                logger.info("No enabled target Plex servers found to index. Skipping background indexing.")
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
