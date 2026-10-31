"""Incremental background library indexer for live Plex server synchronization."""

import asyncio
from collections import Counter
import logging
import concurrent.futures
import threading
import json
import urllib.request
import ssl

from backend.config import settings
from backend.services.library import (
    MOOD_MAPPINGS,
    upsert_server,
    upsert_artist,
    upsert_album,
    upsert_track,
)
from backend.db.library_db import get_db_connection
from backend.services.plex import (
    get_target_plex_connection,
    is_music_library_section,
    milliseconds_to_seconds,
    get_enabled_server_ids,
    fetch_art_bytes,
    fetch_accessible_plex_servers,
    sync_all_curated_vibes_from_plex,
)
from backend.websockets import broadcast_indexing_status_threadsafe
from backend.services.mock_data import seed_mock_library_db

logger = logging.getLogger(__name__)

_sync_lock = threading.Lock()

_UNCATEGORIZED_ALBUM_GENRES = {"", "uncategorized"}
_PRIMARY_GENRES_LOWER = {
    g.lower(): g
    for g in (
        "Rock",
        "Pop",
        "Indie",
        "Hip-Hop",
        "Electronic",
        "Jazz",
        "Blues",
        "Classical",
        "Country",
        "Folk",
        "R&B",
        "Metal",
        "Punk",
        "Reggae",
        "Latin",
        "Soul",
        "Dance",
    )
}


def resolve_album_genre_from_tracks(
    current_album_genre: str | None,
    track_genres: list[str],
    tagged_track_count: int = 0,
) -> str | None:
    """Resolve an album genre from track-level genres (Subgenre -> Primary Genre -> Pop/Rock)."""
    norm_current = (current_album_genre or "").strip().lower()

    cleaned = [g.strip() for g in track_genres if g and g.strip() and g.strip().lower() != "uncategorized"]
    if not cleaned:
        return None

    resolved_genre: str | None = None

    subgenre_candidates = [
        g
        for g in cleaned
        if g.lower() not in _PRIMARY_GENRES_LOWER and g.lower() != "pop/rock"
    ]
    if subgenre_candidates:
        top_sub, top_sub_count = Counter(subgenre_candidates).most_common(1)[0]
        if tagged_track_count == 0 or top_sub_count >= tagged_track_count / 2:
            resolved_genre = top_sub

    if resolved_genre is None:
        primary_candidates = [
            _PRIMARY_GENRES_LOWER[g.lower()]
            for g in cleaned
            if g.lower() in _PRIMARY_GENRES_LOWER
        ]
        if primary_candidates:
            top_prim, top_prim_count = Counter(primary_candidates).most_common(1)[0]
            if tagged_track_count == 0 or top_prim_count >= tagged_track_count / 2:
                resolved_genre = top_prim

    if resolved_genre is None:
        resolved_genre = "Pop/Rock"

    if norm_current not in _UNCATEGORIZED_ALBUM_GENRES:
        if resolved_genre.lower() == "pop/rock" and norm_current != "pop/rock":
            return None
        if norm_current == resolved_genre.lower():
            return None

    return resolved_genre


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

    # Check if this server is already indexed in SQLite
    server_track_count = 0
    try:
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
        broadcast_indexing_status_threadsafe(is_indexing=True, is_initial=is_initial, server_name=s_name, message=f"Indexing artists on {s_name}")
    except Exception as ws_ex:
        logger.debug("Could not send indexing status start: %s", ws_ex)

    try:
        plex = get_target_plex_connection(s_id)
        if not plex:
            logger.warning("Failed to connect to Plex server %s (ID: %s) for indexing.", s_name, s_id)
            try:
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
                broadcast_indexing_status_threadsafe(is_indexing=False, is_initial=is_initial, server_name=s_name, items_indexed=0, message=f"No Music libraries found on Plex server '{s_name}'.", is_error=True)
            except Exception:
                pass
            return 0

        items_indexed = 0

        def _is_cancelled() -> bool:
            if s_id not in get_enabled_server_ids():
                logger.info("Indexing for server %s (ID: %s) was cancelled because server was disabled by user.", s_name, s_id)
                try:
                    broadcast_indexing_status_threadsafe(is_indexing=False, is_initial=is_initial, server_name=s_name, items_indexed=0, message=f"Indexing cancelled for '{s_name}'.")
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
                    broadcast_indexing_status_threadsafe(is_indexing=True, is_initial=is_initial, server_name=s_name, message=f"Fetching artist catalog from {s_name}")
                except Exception:
                    pass

                logger.info("Bulk fetching artists for section '%s' on server %s", getattr(music_lib, "title", "Music"), s_name)
                artist_map: dict[str, int] = {}  # ratingKey -> artist_db_id
                artist_name_map: dict[str, str] = {}  # ratingKey -> artist_name

                json_artists = fetch_section_json_batched(plex, music_lib, item_type=8)
                conn = get_db_connection(db_path)
                try:
                    if json_artists is not None:
                        total_art_count = len(json_artists)
                        logger.info("Fetched %d artists via fast JSON batching for %s.", total_art_count, s_name)
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
                                if idx > 0 and idx % 200 == 0:
                                    conn.commit()
                                    pct = min(100, int((idx / max(1, total_art_count)) * 100))
                                    try:
                                        broadcast_indexing_status_threadsafe(
                                            is_indexing=True,
                                            is_initial=is_initial,
                                            server_name=s_name,
                                            items_indexed=idx,
                                            total_items=total_art_count,
                                            percentage=pct,
                                            message=f"Indexing artists on {s_name} • {pct}% ({idx:,} / {total_art_count:,})",
                                        )
                                    except Exception:
                                        pass
                            except Exception as a_ex:
                                logger.debug("Failed to upsert JSON artist %s: %s", art.get("title"), a_ex)
                        conn.commit()
                    else:
                        logger.info("Fallback: fetching artists via plexapi for section '%s' on %s", getattr(music_lib, "title", "Music"), s_name)
                        artists = music_lib.all(libtype="artist")
                        total_art_count = len(artists)
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
                                if idx > 0 and idx % 200 == 0:
                                    conn.commit()
                                    pct = min(100, int((idx / max(1, total_art_count)) * 100))
                                    try:
                                        broadcast_indexing_status_threadsafe(
                                            is_indexing=True,
                                            is_initial=is_initial,
                                            server_name=s_name,
                                            items_indexed=idx,
                                            total_items=total_art_count,
                                            percentage=pct,
                                            message=f"Indexing artists on {s_name} • {pct}% ({idx:,} / {total_art_count:,})",
                                        )
                                    except Exception:
                                        pass
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
                    broadcast_indexing_status_threadsafe(is_indexing=True, is_initial=is_initial, server_name=s_name, message=f"Fetching album catalog from {s_name}")
                except Exception:
                    pass

                logger.info("Bulk fetching albums for section '%s' on server %s", getattr(music_lib, "title", "Music"), s_name)
                album_map: dict[str, int] = {}  # album ratingKey -> album_db_id
                album_genre_map: dict[int, str] = {}  # album_db_id -> album genre

                json_albums = fetch_section_json_batched(plex, music_lib, item_type=9)
                conn = get_db_connection(db_path)
                try:
                    if json_albums is not None:
                        total_alb_count = len(json_albums)
                        logger.info("Fetched %d albums via fast JSON batching for %s.", total_alb_count, s_name)
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
                                album_genre_map[alb_db_id] = genre_val
                                if idx > 0 and idx % 200 == 0:
                                    conn.commit()
                                    pct = min(100, int((idx / max(1, total_alb_count)) * 100))
                                    try:
                                        broadcast_indexing_status_threadsafe(
                                            is_indexing=True,
                                            is_initial=is_initial,
                                            server_name=s_name,
                                            items_indexed=idx,
                                            total_items=total_alb_count,
                                            percentage=pct,
                                            message=f"Indexing albums on {s_name} • {pct}% ({idx:,} / {total_alb_count:,})",
                                        )
                                    except Exception:
                                        pass
                            except Exception as alb_ex:
                                logger.debug("Failed to upsert JSON album %s: %s", alb.get("title"), alb_ex)
                        conn.commit()
                    else:
                        logger.info("Fallback: fetching albums via plexapi for section '%s' on %s", getattr(music_lib, "title", "Music"), s_name)
                        albums = music_lib.all(libtype="album")
                        total_alb_count = len(albums)
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
                                album_genre_map[alb_db_id] = genre_val
                                if idx > 0 and idx % 200 == 0:
                                    conn.commit()
                                    pct = min(100, int((idx / max(1, total_alb_count)) * 100))
                                    try:
                                        broadcast_indexing_status_threadsafe(
                                            is_indexing=True,
                                            is_initial=is_initial,
                                            server_name=s_name,
                                            items_indexed=idx,
                                            total_items=total_alb_count,
                                            percentage=pct,
                                            message=f"Indexing albums on {s_name} • {pct}% ({idx:,} / {total_alb_count:,})",
                                        )
                                    except Exception:
                                        pass
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
                    broadcast_indexing_status_threadsafe(is_indexing=True, is_initial=is_initial, server_name=s_name, message=f"Fetching track catalog from {s_name}")
                except Exception:
                    pass

                logger.info("Bulk fetching tracks for section '%s' on server %s", getattr(music_lib, "title", "Music"), s_name)
                album_track_genres: dict[int, list[str]] = {}
                album_tagged_track_counts: dict[int, int] = {}
                json_tracks = fetch_section_json_batched(plex, music_lib, item_type=10)
                conn = get_db_connection(db_path)
                try:
                    if json_tracks is not None:
                        total_trk_count = len(json_tracks)
                        logger.info("Fetched %d tracks via fast JSON batching for %s.", total_trk_count, s_name)
                        for trk_idx, trk in enumerate(json_tracks):
                            try:
                                dur = (int(trk.get("duration", 0) or 0)) // 1000
                                raw_rating = float(trk.get("userRating", 0.0) or 0.0)
                                p_alb_key = str(trk.get("parentRatingKey", ""))
                                alb_db_id = album_map.get(p_alb_key)

                                media = trk.get("Media", [{}])[0] if trk.get("Media") else {}
                                bitrate = int(media.get("bitrate", 0) or 0)
                                codec = media.get("audioCodec") or media.get("container")
                                raw_bpm = trk.get("bpm")
                                trk_bpm = int(raw_bpm or 0) if raw_bpm else 0

                                raw_moods = trk.get("Mood", [])
                                track_moods = []
                                if isinstance(raw_moods, list):
                                    for m in raw_moods:
                                        if isinstance(m, dict) and m.get("tag"):
                                            track_moods.append(str(m.get("tag")).strip())
                                        elif isinstance(m, str) and m.strip():
                                            track_moods.append(m.strip())

                                if alb_db_id is not None:
                                    raw_genres = trk.get("Genre", [])
                                    if isinstance(raw_genres, list):
                                        seen_tags = []
                                        for g in raw_genres:
                                            tag = g.get("tag") if isinstance(g, dict) else (g if isinstance(g, str) else None)
                                            if tag and str(tag).strip() and str(tag).strip() not in seen_tags:
                                                seen_tags.append(str(tag).strip())
                                        if seen_tags:
                                            album_track_genres.setdefault(alb_db_id, []).extend(seen_tags)
                                            album_tagged_track_counts[alb_db_id] = album_tagged_track_counts.get(alb_db_id, 0) + 1

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
                                    bpm=trk_bpm,
                                    bitrate=bitrate,
                                    codec=codec,
                                    moods=track_moods,
                                    db_path=db_path,
                                    conn=conn,
                                )
                                items_indexed += 1
                                if trk_idx > 0 and trk_idx % 500 == 0:
                                    conn.commit()
                                    pct = min(100, int((trk_idx / max(1, total_trk_count)) * 100))
                                    msg = f"Indexing tracks on {s_name} • {pct}% ({trk_idx:,} / {total_trk_count:,})"
                                    try:
                                        broadcast_indexing_status_threadsafe(
                                            is_indexing=True,
                                            is_initial=is_initial,
                                            server_name=s_name,
                                            items_indexed=trk_idx,
                                            total_items=total_trk_count,
                                            percentage=pct,
                                            message=msg,
                                        )
                                    except Exception:
                                        pass
                            except Exception as trk_ex:
                                logger.debug("Failed to upsert JSON track %s: %s", trk.get("title"), trk_ex)
                        conn.commit()
                    else:
                        logger.info("Fallback: fetching tracks via plexapi for section '%s' on %s", getattr(music_lib, "title", "Music"), s_name)
                        tracks = music_lib.all(libtype="track")
                        total_trk_count = len(tracks)
                        for trk_idx, track in enumerate(tracks):
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
                                trk_bpm = int(getattr(track, "bpm", 0) or 0)
                                track_moods = [m.tag for m in getattr(track, "moods", []) if hasattr(m, "tag")]

                                if alb_db_id is not None:
                                    seen_tags = []
                                    for g in getattr(track, "genres", []):
                                        tag = getattr(g, "tag", None)
                                        if tag and str(tag).strip() and str(tag).strip() not in seen_tags:
                                            seen_tags.append(str(tag).strip())
                                    if seen_tags:
                                        album_track_genres.setdefault(alb_db_id, []).extend(seen_tags)
                                        album_tagged_track_counts[alb_db_id] = album_tagged_track_counts.get(alb_db_id, 0) + 1

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
                                    bpm=trk_bpm,
                                    bitrate=int(bitrate or 0),
                                    codec=str(codec) if codec else None,
                                    moods=track_moods,
                                    db_path=db_path,
                                    conn=conn,
                                )
                                items_indexed += 1
                                if trk_idx > 0 and trk_idx % 500 == 0:
                                    conn.commit()
                                    pct = min(100, int((trk_idx / max(1, total_trk_count)) * 100))
                                    msg = f"Indexing tracks on {s_name} • {pct}% ({trk_idx:,} / {total_trk_count:,})"
                                    try:
                                        broadcast_indexing_status_threadsafe(
                                            is_indexing=True,
                                            is_initial=is_initial,
                                            server_name=s_name,
                                            items_indexed=trk_idx,
                                            total_items=total_trk_count,
                                            percentage=pct,
                                            message=msg,
                                        )
                                    except Exception:
                                        pass
                            except Exception as trk_ex:
                                logger.debug("Failed to upsert track %s: %s", getattr(track, "title", "Unknown"), trk_ex)
                        conn.commit()

                    if album_track_genres:
                        genre_updates = []
                        for alb_db_id, trk_genres in album_track_genres.items():
                            resolved = resolve_album_genre_from_tracks(
                                album_genre_map.get(alb_db_id),
                                trk_genres,
                                tagged_track_count=album_tagged_track_counts.get(alb_db_id, 0),
                            )
                            if resolved:
                                genre_updates.append((resolved, alb_db_id))
                        if genre_updates:
                            conn.executemany(
                                "UPDATE albums SET genre = ? WHERE album_id = ?;",
                                genre_updates,
                            )
                            conn.commit()
                            logger.info("Rolled up track genres to %d albums for server %s.", len(genre_updates), s_name)
                finally:
                    conn.close()

                try:
                    sync_plex_track_moods(plex, music_lib, s_id, db_path=db_path)
                except Exception as mood_sync_ex:
                    logger.debug("Non-fatal error in sync_plex_track_moods: %s", mood_sync_ex)

                try:
                    sync_all_curated_vibes_from_plex(db_path=db_path)
                except Exception as vibe_sync_ex:
                    logger.debug("Non-fatal error in sync_all_curated_vibes_from_plex: %s", vibe_sync_ex)

            except Exception as lib_ex:
                logger.warning("Error scanning section '%s' on server %s: %s", getattr(music_lib, "title", "Unknown"), s_name, lib_ex)
                try:
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


def sync_plex_track_moods(plex_conn, music_lib, server_id: str, db_path: str | None = None) -> int:
    """Fetch track mood tag assignments from Plex and update tracks.moods in SQLite."""
    try:
        server_url = getattr(plex_conn, "_baseurl", None)
        token = getattr(plex_conn, "_token", None)
        sec_key = getattr(music_lib, "key", None)
        if not server_url or not token or not sec_key:
            return 0

        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

        moods_url = f"{server_url}/library/sections/{sec_key}/mood?X-Plex-Token={token}"
        req = urllib.request.Request(moods_url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            items = data.get("MediaContainer", {}).get("Directory", [])

        if not items:
            return 0

        all_target_moods = set()
        for v in MOOD_MAPPINGS.values():
            for m in v.get("moods", []):
                all_target_moods.add(m.lower())

        matched_moods = []
        for it in items:
            title = it.get("title", "").strip()
            if title.lower() in all_target_moods or any(tm in title.lower() for tm in all_target_moods):
                matched_moods.append((title, it["key"]))

        track_to_moods: dict[str, set[str]] = {}
        for title, key in matched_moods:
            u = f"{server_url}/library/sections/{sec_key}/all?type=10&mood={key}&X-Plex-Token={token}"
            r = urllib.request.Request(u, headers={"Accept": "application/json"})
            try:
                with urllib.request.urlopen(r, timeout=15, context=ctx) as resp:
                    d = json.loads(resp.read().decode("utf-8"))
                    trks = d.get("MediaContainer", {}).get("Metadata", [])
                    for trk in trks:
                        rk = str(trk.get("ratingKey"))
                        if rk not in track_to_moods:
                            track_to_moods[rk] = set()
                        track_to_moods[rk].add(title)
            except Exception as mood_fetch_ex:
                logger.debug("Failed fetching tracks for mood %s: %s", title, mood_fetch_ex)

        if not track_to_moods:
            return 0

        update_data = [
            (", ".join(sorted(m_set)), server_id, rk)
            for rk, m_set in track_to_moods.items()
        ]

        conn = get_db_connection(db_path)
        try:
            conn.executemany(
                "UPDATE tracks SET moods = ? WHERE server_id = ? AND server_track_id = ?",
                update_data,
            )
            conn.commit()
            logger.info("Synced mood tags for %d tracks from Plex section %s", len(track_to_moods), getattr(music_lib, "title", "Music"))
            return len(track_to_moods)
        finally:
            conn.close()
    except Exception as ex:
        logger.warning("Failed syncing Plex track moods for server %s: %s", server_id, ex)
        return 0


def _prewarm_art_in_background(server_id: str, artist_ids: list[int], album_ids: list[int]):
    """Pre-warm artist and album thumbnails into Redis in a parallel background thread pool."""
    def _worker():
        try:
            logger.info("Pre-warming %d artist and %d album thumbnails into Redis for server %s", len(artist_ids), len(album_ids), server_id)
            
            with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
                for a_id in artist_ids:
                    executor.submit(fetch_art_bytes, a_id, "artist", server_id)
                for alb_id in album_ids:
                    executor.submit(fetch_art_bytes, alb_id, "album", server_id)
                    
            logger.info("Artwork pre-warming complete for server %s.", server_id)
        except Exception as ex:
            logger.debug("Art prewarming error for server %s: %s", server_id, ex)

    threading.Thread(target=_worker, daemon=True).start()


def sync_all_servers(db_path: str | None = None, force_full: bool = False):
    """Sync and perform incremental diff index across all accessible enabled Plex servers."""
    if not _sync_lock.acquire(blocking=True, timeout=10):
        logger.info("Library index sync is already in progress. Skipping redundant concurrent request.")
        return

    try:
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
                seed_mock_library_db(db_path)
            else:
                logger.info("No enabled target Plex servers found to index. Skipping background indexing.")
            return

        # Prioritize unindexed servers (0 tracks in SQLite) first so new server banners show immediately
        def _server_priority(s: dict) -> tuple[int, int]:
            s_id = s.get("server_id")
            count = 0
            try:
                conn = get_db_connection(db_path)
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

        logger.info("Starting sync for %d server(s): first='%s', remaining=%d", len(sorted_targets), first_batch[0].get("name") if first_batch else "", len(remaining_batch))

        # 1. Index first target server (unindexed new server or primary) FIRST
        for s in first_batch:
            try:
                logger.info("Indexing server '%s' first", s.get("name"))
                index_server(s, db_path, force_full)
            except Exception as ex:
                logger.warning("Error indexing server %s: %s", s.get("name"), ex)

        # 2. Index remaining servers sequentially to prevent SQLite database lock contention
        if remaining_batch:
            logger.info("Indexing %d remaining server(s) sequentially", len(remaining_batch))
            for s in remaining_batch:
                try:
                    logger.info("Indexing server '%s'", s.get("name"))
                    index_server(s, db_path, force_full)
                except Exception as ex:
                    logger.warning("Error indexing server %s: %s", s.get("name"), ex)
    except Exception as ex:
        logger.warning("Error in sync_all_servers: %s", ex)
    finally:
        _sync_lock.release()


async def periodic_library_indexer():
    """Background task to run sync_all_servers periodically based on settings.index_interval_hours."""
    if settings.index_interval_hours <= 0:
        logger.info("Periodic library indexing is disabled (INDEX_INTERVAL_HOURS <= 0).")
        return

    interval_seconds = settings.index_interval_hours * 3600
    logger.info(
        "Periodic library indexer initialized. Scheduling auto-sync every %d hour(s).",
        settings.index_interval_hours,
    )

    while True:
        try:
            await asyncio.sleep(interval_seconds)
            logger.info("Triggering scheduled periodic library index sync for enabled servers")
            await asyncio.to_thread(sync_all_servers)
        except asyncio.CancelledError:
            logger.info("Periodic library indexer task cancelled.")
            break
        except Exception as ex:
            logger.warning("Error in periodic_library_indexer loop: %s", ex)

