"""High-performance query engine and indexing service for SQLite library database."""

import time
import re
import sqlite3
import logging
from backend.db.library_db import get_db_connection

logger = logging.getLogger(__name__)


def _norm(text: str) -> str:
    """Normalize string for deduplication across Plex servers.

    Rules applied in order:
      1. Lowercase
      2. Treat '&' as 'and'  — so 'Simon & Garfunkel' == 'Simon and Garfunkel'
      3. Strip leading 'the ' — so 'The Beatles' == 'Beatles'
      4. Strip all non-alphanumeric characters and collapse whitespace
    """
    if not text:
        return ""
    t = text.lower().strip()
    t = re.sub(r"\s*&\s*", " and ", t)   # & -> and
    t = re.sub(r"^the\s+", "", t)        # strip leading "the "
    return re.sub(r"[^a-z0-9]", "", t) or t


def upsert_server(server_id: str, name: str, server_url: str | None = None, is_primary: bool = False, enabled: bool | None = None, access_token: str | None = None, db_path: str | None = None):
    """Insert or update a target Plex server in the servers registry."""
    conn = get_db_connection(db_path)
    try:
        if enabled is None:
            conn.execute(
                """
                INSERT INTO servers (server_id, name, server_url, access_token, is_primary, enabled, last_indexed_at)
                VALUES (?, ?, ?, ?, ?, 1, 0)
                ON CONFLICT(server_id) DO UPDATE SET
                    name = excluded.name,
                    server_url = COALESCE(excluded.server_url, servers.server_url),
                    access_token = COALESCE(excluded.access_token, servers.access_token),
                    is_primary = excluded.is_primary
                """,
                (server_id, name, server_url, access_token, 1 if is_primary else 0),
            )
        else:
            conn.execute(
                """
                INSERT INTO servers (server_id, name, server_url, access_token, is_primary, enabled, last_indexed_at)
                VALUES (?, ?, ?, ?, ?, ?, 0)
                ON CONFLICT(server_id) DO UPDATE SET
                    name = excluded.name,
                    server_url = COALESCE(excluded.server_url, servers.server_url),
                    access_token = COALESCE(excluded.access_token, servers.access_token),
                    is_primary = excluded.is_primary,
                    enabled = excluded.enabled
                """,
                (server_id, name, server_url, access_token, 1 if is_primary else 0, 1 if enabled else 0),
            )
        conn.commit()
    finally:
        conn.close()


def set_server_enabled_status(server_id: str, enabled: bool, db_path: str | None = None):
    """Toggle a server enabled status in SQLite without deleting its indexed data."""
    conn = get_db_connection(db_path)
    try:
        conn.execute("UPDATE servers SET enabled = ? WHERE server_id = ?", (1 if enabled else 0, server_id))
        conn.commit()
    finally:
        conn.close()


def upsert_artist(name: str, guid: str | None = None, thumb: str | None = None, play_count: int = 0, server_id: str | None = None, server_artist_id: str | None = None, db_path: str | None = None, conn: sqlite3.Connection | None = None) -> int:
    """Upsert an artist into SQLite library with multi-server mapping."""
    norm_name = _norm(name)
    now = int(time.time())
    should_close = False
    if conn is None:
        conn = get_db_connection(db_path)
        should_close = True
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO artists (norm_name, name, guid, thumb, play_count, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(norm_name) DO UPDATE SET
                name = excluded.name,
                guid = COALESCE(excluded.guid, artists.guid),
                thumb = COALESCE(excluded.thumb, artists.thumb),
                play_count = MAX(artists.play_count, excluded.play_count),
                updated_at = excluded.updated_at
            """,
            (norm_name, name, guid, thumb, play_count, now),
        )
        cursor.execute("SELECT artist_id FROM artists WHERE norm_name = ?", (norm_name,))
        artist_id = cursor.fetchone()["artist_id"]

        if server_id and server_artist_id:
            cursor.execute(
                """
                INSERT INTO artist_sources (artist_id, server_id, server_artist_id, thumb)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(artist_id, server_id) DO UPDATE SET
                    server_artist_id = excluded.server_artist_id,
                    thumb = COALESCE(excluded.thumb, artist_sources.thumb)
                """,
                (artist_id, server_id, str(server_artist_id), thumb),
            )

        if should_close:
            conn.commit()
        return artist_id
    finally:
        if should_close:
            conn.close()


def upsert_album(title: str, artist_name: str, artist_id: int | None = None, year: int | None = None, genre: str | None = None, thumb: str | None = None, play_count: int = 0, guid: str | None = None, server_id: str | None = None, server_album_id: str | None = None, db_path: str | None = None, conn: sqlite3.Connection | None = None) -> int:
    """Upsert an album into SQLite library with multi-server mapping."""
    norm_key = f"{_norm(title)}::{_norm(artist_name)}"
    now = int(time.time())
    should_close = False
    if conn is None:
        conn = get_db_connection(db_path)
        should_close = True
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO albums (norm_title_artist, artist_id, artist_name, title, year, genre, thumb, play_count, guid, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(norm_title_artist) DO UPDATE SET
                artist_name = excluded.artist_name,
                title = excluded.title,
                year = COALESCE(excluded.year, albums.year),
                genre = COALESCE(excluded.genre, albums.genre),
                thumb = COALESCE(excluded.thumb, albums.thumb),
                play_count = MAX(albums.play_count, excluded.play_count),
                guid = COALESCE(excluded.guid, albums.guid),
                updated_at = excluded.updated_at
            """,
            (norm_key, artist_id, artist_name, title, year, genre or "Uncategorized", thumb, play_count, guid, now),
        )
        cursor.execute("SELECT album_id FROM albums WHERE norm_title_artist = ?", (norm_key,))
        album_id = cursor.fetchone()["album_id"]

        if server_id and server_album_id:
            cursor.execute(
                """
                INSERT INTO album_sources (album_id, server_id, server_album_id, thumb)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(album_id, server_id) DO UPDATE SET
                    server_album_id = excluded.server_album_id,
                    thumb = COALESCE(excluded.thumb, album_sources.thumb)
                """,
                (album_id, server_id, str(server_album_id), thumb),
            )

        if should_close:
            conn.commit()
        return album_id
    finally:
        if should_close:
            conn.close()


def upsert_track(
    album_id: int,
    server_id: str,
    server_track_id: str,
    artist_name: str,
    album_title: str,
    title: str,
    duration: int,
    url: str | None = None,
    thumb: str | None = None,
    play_count: int = 0,
    user_rating: float = 0.0,
    bitrate: int = 0,
    codec: str | None = None,
    sample_rate: int = 0,
    bit_depth: int = 16,
    db_path: str | None = None,
    conn: sqlite3.Connection | None = None,
) -> int:
    """Upsert a track and its per-server track source into SQLite library."""
    now = int(time.time())
    safe_url = str(url) if (url is not None and not callable(url)) else None
    should_close = False
    if conn is None:
        conn = get_db_connection(db_path)
        should_close = True
    try:
        cursor = conn.cursor()
        # 1. Check if source already linked in track_sources
        existing_src = cursor.execute(
            "SELECT track_id FROM track_sources WHERE server_id = ? AND server_track_id = ? LIMIT 1",
            (server_id, str(server_track_id)),
        ).fetchone()

        track_id = existing_src["track_id"] if existing_src else None

        # 2. If not linked by source, check if track exists by album_id and title
        if not track_id:
            existing_track = cursor.execute(
                "SELECT track_id FROM tracks WHERE album_id = ? AND title = ? LIMIT 1",
                (album_id, title),
            ).fetchone()
            if existing_track:
                track_id = existing_track["track_id"]
            elif server_id:
                # Legacy fallback match
                existing_legacy = cursor.execute(
                    "SELECT track_id FROM tracks WHERE server_id = ? AND server_track_id = ? LIMIT 1",
                    (server_id, str(server_track_id)),
                ).fetchone()
                if existing_legacy:
                    track_id = existing_legacy["track_id"]

        if track_id:
            cursor.execute(
                """
                UPDATE tracks
                SET album_id = ?, artist_name = ?, album_title = ?, title = ?, duration = ?, url = COALESCE(?, url), thumb = COALESCE(?, thumb), play_count = MAX(play_count, ?), user_rating = CASE WHEN ? > 0 THEN ? ELSE user_rating END, updated_at = ?
                WHERE track_id = ?
                """,
                (album_id, artist_name, album_title, title, duration, safe_url, thumb, play_count, float(user_rating or 0.0), float(user_rating or 0.0), now, track_id),
            )
        else:
            cursor.execute(
                """
                INSERT INTO tracks (album_id, server_id, server_track_id, artist_name, album_title, title, duration, url, thumb, play_count, user_rating, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (album_id, server_id, str(server_track_id), artist_name, album_title, title, duration, safe_url, thumb, play_count, float(user_rating or 0.0), now),
            )
            track_id = cursor.lastrowid

        # 3. Upsert entry into track_sources table
        cursor.execute(
            """
            INSERT INTO track_sources (track_id, server_id, server_track_id, bitrate, codec, sample_rate, bit_depth, thumb, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(track_id, server_id) DO UPDATE SET
                server_track_id = excluded.server_track_id,
                bitrate = CASE WHEN excluded.bitrate > 0 THEN excluded.bitrate ELSE track_sources.bitrate END,
                codec = COALESCE(excluded.codec, track_sources.codec),
                sample_rate = CASE WHEN excluded.sample_rate > 0 THEN excluded.sample_rate ELSE track_sources.sample_rate END,
                bit_depth = CASE WHEN excluded.bit_depth > 0 THEN excluded.bit_depth ELSE track_sources.bit_depth END,
                thumb = COALESCE(excluded.thumb, track_sources.thumb),
                updated_at = excluded.updated_at
            """,
            (track_id, server_id, str(server_track_id), int(bitrate or 0), codec, int(sample_rate or 0), int(bit_depth or 16), thumb, now),
        )

        if should_close:
            conn.commit()
        return track_id
    finally:
        if should_close:
            conn.close()


def rate_track_db(track_id: int | str, rating: float, db_path: str | None = None):
    """Update user_rating (0.0 - 5.0) for a track in SQLite."""
    conn = get_db_connection(db_path)
    try:
        conn.execute(
            "UPDATE tracks SET user_rating = ? WHERE track_id = ?",
            (float(rating), track_id),
        )
        conn.commit()
    finally:
        conn.close()


def is_track_on_primary_server(track_id: int | str, db_path: str | None = None) -> bool:
    """Check if a track is hosted on an enabled primary Plex server."""
    conn = get_db_connection(db_path)
    try:
        row = conn.execute(
            """
            SELECT srv.is_primary
            FROM tracks t
            JOIN track_sources ts ON t.track_id = ts.track_id
            JOIN servers srv ON ts.server_id = srv.server_id
            WHERE t.track_id = ? AND srv.enabled = 1
            ORDER BY (CASE WHEN srv.is_primary = 1 THEN 0 ELSE 1 END)
            LIMIT 1
            """,
            (track_id,),
        ).fetchone()
        if not row:
            row = conn.execute(
                """
                SELECT srv.is_primary
                FROM tracks t
                JOIN servers srv ON t.server_id = srv.server_id
                WHERE t.track_id = ? AND srv.enabled = 1
                LIMIT 1
                """,
                (track_id,),
            ).fetchone()
        return bool(row and row["is_primary"])
    finally:
        conn.close()


def log_playback_event_db(track_id: int | str, username: str = "Admin", db_path: str | None = None):
    """Append a playback event to the historical playback_history log in SQLite."""
    now = int(time.time())
    conn = get_db_connection(db_path)
    try:
        row = conn.execute(
            "SELECT track_id, artist_name, album_title, title FROM tracks WHERE track_id = ? LIMIT 1",
            (track_id,),
        ).fetchone()
        if row:
            conn.execute(
                """
                INSERT INTO playback_history (track_id, artist_name, album_title, track_title, username, played_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (row["track_id"], row["artist_name"], row["album_title"], row["title"], username, now),
            )
            conn.commit()
    finally:
        conn.close()


def clean_library_deduplication(db_path: str | None = None) -> dict:
    """Consolidate duplicate artists and albums into primary entries to clean unified library view."""
    try:
        conn = get_db_connection(db_path)
        cursor = conn.cursor()
        removed_artists = 0
        removed_albums = 0
    except Exception as ex:
        logger.warning("Database error opening SQLite connection for deduplication: %s", ex)
        return {"removed_artists": 0, "removed_albums": 0}

    try:
        # Helper to rank thumbs (real Plex metadata paths first, then http, then mock /api/ strings)
        def _thumb_rank(thumb_val: str | None) -> int:
            if not thumb_val:
                return 3
            if thumb_val.startswith("/library/metadata/") or thumb_val.startswith("http"):
                return 0
            if thumb_val.startswith("/api/music/"):
                return 2
            return 1

        # 1. Consolidate Artists
        artists = cursor.execute("SELECT artist_id, name, norm_name, thumb, play_count FROM artists ORDER BY artist_id ASC").fetchall()
        norm_artist_groups: dict[str, list[dict]] = {}
        for a in artists:
            curr_norm = _norm(a["name"])
            norm_artist_groups.setdefault(curr_norm, []).append(dict(a))

        for norm_key, group in norm_artist_groups.items():
            # Sort group so entries with real thumbs come first
            group.sort(key=lambda item: _thumb_rank(item.get("thumb")))
            primary = group[0]
            primary_id = primary["artist_id"]
            primary_thumb = primary.get("thumb")

            for secondary in group[1:]:
                sec_id = secondary["artist_id"]
                sec_thumb = secondary.get("thumb")

                # If primary lacks a real thumb, adopt secondary's real thumb
                if _thumb_rank(primary_thumb) > _thumb_rank(sec_thumb):
                    primary_thumb = sec_thumb
                    cursor.execute("UPDATE artists SET thumb = ? WHERE artist_id = ?", (primary_thumb, primary_id))

                # Move sources
                cursor.execute(
                    "UPDATE OR IGNORE artist_sources SET artist_id = ? WHERE artist_id = ?",
                    (primary_id, sec_id),
                )
                cursor.execute("DELETE FROM artist_sources WHERE artist_id = ?", (sec_id,))

                # Move albums
                cursor.execute("UPDATE albums SET artist_id = ? WHERE artist_id = ?", (primary_id, sec_id))

                # Combine play count
                cursor.execute(
                    "UPDATE artists SET play_count = MAX(play_count, ?) WHERE artist_id = ?",
                    (secondary["play_count"], primary_id),
                )

                # Delete duplicate artist
                cursor.execute("DELETE FROM artists WHERE artist_id = ?", (sec_id,))
                removed_artists += 1

            # Update norm_name AFTER removing duplicates
            cursor.execute("UPDATE artists SET norm_name = ? WHERE artist_id = ?", (norm_key, primary_id))

        # 2. Consolidate Albums
        albums = cursor.execute("SELECT album_id, artist_name, title, norm_title_artist, thumb, play_count FROM albums ORDER BY album_id ASC").fetchall()
        norm_album_groups: dict[str, list[dict]] = {}
        for alb in albums:
            curr_norm = f"{_norm(alb['title'])}::{_norm(alb['artist_name'])}"
            norm_album_groups.setdefault(curr_norm, []).append(dict(alb))

        for norm_key, group in norm_album_groups.items():
            # Sort group so entries with real thumbs come first
            group.sort(key=lambda item: _thumb_rank(item.get("thumb")))
            primary = group[0]
            primary_id = primary["album_id"]
            primary_thumb = primary.get("thumb")

            for secondary in group[1:]:
                sec_id = secondary["album_id"]
                sec_thumb = secondary.get("thumb")

                # If primary lacks a real thumb, adopt secondary's real thumb
                if _thumb_rank(primary_thumb) > _thumb_rank(sec_thumb):
                    primary_thumb = sec_thumb
                    cursor.execute("UPDATE albums SET thumb = ? WHERE album_id = ?", (primary_thumb, primary_id))

                # Move album sources
                cursor.execute(
                    "UPDATE OR IGNORE album_sources SET album_id = ? WHERE album_id = ?",
                    (primary_id, sec_id),
                )
                cursor.execute("DELETE FROM album_sources WHERE album_id = ?", (sec_id,))

                # Move tracks
                cursor.execute("UPDATE tracks SET album_id = ? WHERE album_id = ?", (primary_id, sec_id))

                # Combine play count
                cursor.execute(
                    "UPDATE albums SET play_count = MAX(play_count, ?) WHERE album_id = ?",
                    (secondary["play_count"], primary_id),
                )

                # Delete duplicate album
                cursor.execute("DELETE FROM albums WHERE album_id = ?", (sec_id,))
                removed_albums += 1

            # Update norm_title_artist AFTER removing duplicates
            cursor.execute("UPDATE albums SET norm_title_artist = ? WHERE album_id = ?", (norm_key, primary_id))

        # 3. Backfill album thumbs from tracks if album thumb is missing or mock
        cursor.execute("""
            UPDATE albums
            SET thumb = (
                SELECT thumb FROM tracks
                WHERE tracks.album_id = albums.album_id AND (tracks.thumb LIKE '/library/metadata/%' OR tracks.thumb LIKE 'http%')
                LIMIT 1
            )
            WHERE (thumb LIKE '/api/music/%' OR thumb IS NULL OR thumb = '')
              AND EXISTS (
                SELECT 1 FROM tracks
                WHERE tracks.album_id = albums.album_id AND (tracks.thumb LIKE '/library/metadata/%' OR tracks.thumb LIKE 'http%')
            )
        """)

        # 4. Backfill artist thumbs from albums if artist thumb is missing or mock
        cursor.execute("""
            UPDATE artists
            SET thumb = (
                SELECT thumb FROM albums
                WHERE albums.artist_id = artists.artist_id AND (albums.thumb LIKE '/library/metadata/%' OR albums.thumb LIKE 'http%')
                LIMIT 1
            )
            WHERE (thumb LIKE '/api/music/%' OR thumb IS NULL OR thumb = '')
              AND EXISTS (
                SELECT 1 FROM albums
                WHERE albums.artist_id = artists.artist_id AND (albums.thumb LIKE '/library/metadata/%' OR albums.thumb LIKE 'http%')
            )
        """)

        conn.commit()
        if removed_artists > 0 or removed_albums > 0:
            logger.info("Cleaned library database: consolidated %d duplicate artists, %d duplicate albums", removed_artists, removed_albums)

        # Clear art RAM and Redis caches
        try:
            from backend.services.plex import clear_art_memory_cache  # noqa: PLC0415
            clear_art_memory_cache()
        except Exception:
            pass

        return {"removed_artists": removed_artists, "removed_albums": removed_albums}
    except Exception as ex:
        logger.warning("Error running library deduplication: %s", ex)
        return {"removed_artists": 0, "removed_albums": 0}
    finally:
        try:
            conn.close()
        except Exception:
            pass


def get_indexed_artists(sort_mode: str = "name_asc", db_path: str | None = None) -> list[dict]:
    """Fetch all unique artists linked to currently enabled servers."""
    from backend.config import settings  # noqa: PLC0415
    conn = get_db_connection(db_path)
    try:
        order_clause = "a.play_count DESC, a.name COLLATE NOCASE ASC" if sort_mode == "plays_desc" else (
            "a.name COLLATE NOCASE DESC" if sort_mode == "name_desc" else "a.name COLLATE NOCASE ASC"
        )
        query = f"""
            SELECT a.artist_id, a.name, a.guid, a.thumb, a.play_count
            FROM artists a
            JOIN artist_sources src ON a.artist_id = src.artist_id
            JOIN servers srv ON src.server_id = srv.server_id
            WHERE srv.enabled = 1
            GROUP BY a.artist_id
            ORDER BY {order_clause}
        """
        cursor = conn.execute(query)
        return [dict(r) for r in cursor.fetchall()]
    finally:
        conn.close()


def get_indexed_albums(sort_mode: str = "name_asc", db_path: str | None = None) -> list[dict]:
    """Fetch all unique albums linked to currently enabled servers."""
    conn = get_db_connection(db_path)
    try:
        order_clause = "alb.play_count DESC, alb.title COLLATE NOCASE ASC" if sort_mode == "plays_desc" else (
            "alb.title COLLATE NOCASE DESC" if sort_mode == "name_desc" else "alb.title COLLATE NOCASE ASC"
        )
        query = f"""
            SELECT alb.album_id, alb.artist_id, alb.artist_name as artist, alb.title, alb.year, alb.genre, alb.thumb, alb.play_count
            FROM albums alb
            JOIN album_sources src ON alb.album_id = src.album_id
            JOIN servers srv ON src.server_id = srv.server_id
            WHERE srv.enabled = 1 AND alb.title != '' AND alb.title IS NOT NULL
            GROUP BY alb.album_id
            ORDER BY {order_clause}
        """
        cursor = conn.execute(query)
        return [dict(r) for r in cursor.fetchall()]
    finally:
        conn.close()


def increment_artist_play_count_db(artist_name: str, db_path: str | None = None):
    """Increment play_count in SQLite for an artist when a song finishes playing."""
    norm_name = _norm(artist_name)
    if not norm_name:
        return
    conn = get_db_connection(db_path)
    try:
        conn.execute("UPDATE artists SET play_count = play_count + 1 WHERE norm_name = ?", (norm_name,))
        conn.commit()
    finally:
        conn.close()


def increment_album_play_count_db(album_title: str, db_path: str | None = None):
    """Increment play_count in SQLite for an album when a song finishes playing."""
    norm_title = _norm(album_title)
    if not norm_title:
        return
    conn = get_db_connection(db_path)
    try:
        conn.execute("UPDATE albums SET play_count = play_count + 1 WHERE norm_title_artist LIKE ?", (f"{norm_title}::%",))
        conn.commit()
    finally:
        conn.close()


def get_all_genres_db(db_path: str | None = None) -> list[dict]:
    """Fetch all music genres with album counts from SQLite."""
    conn = get_db_connection(db_path)
    try:
        cursor = conn.execute(
            """
            SELECT COALESCE(NULLIF(TRIM(alb.genre), ''), 'Uncategorized') as genre, COUNT(DISTINCT alb.album_id) as album_count
            FROM albums alb
            JOIN album_sources src ON alb.album_id = src.album_id
            JOIN servers srv ON src.server_id = srv.server_id
            WHERE srv.enabled = 1 AND alb.title != '' AND alb.title IS NOT NULL
            GROUP BY genre
            ORDER BY album_count DESC, genre ASC
            """
        )
        return [dict(r) for r in cursor.fetchall()]
    finally:
        conn.close()


def get_albums_by_genre_db(genre_name: str, db_path: str | None = None) -> list[dict]:
    """Fetch all albums matching a specific genre from SQLite."""
    conn = get_db_connection(db_path)
    try:
        cursor = conn.execute(
            """
            SELECT DISTINCT alb.album_id, alb.artist_id, alb.artist_name as artist, alb.title, alb.year, alb.genre, alb.thumb, alb.play_count
            FROM albums alb
            JOIN album_sources src ON alb.album_id = src.album_id
            JOIN servers srv ON src.server_id = srv.server_id
            WHERE srv.enabled = 1 AND alb.title != '' AND alb.title IS NOT NULL
              AND (LOWER(COALESCE(NULLIF(TRIM(alb.genre), ''), 'Uncategorized')) = LOWER(?))
            GROUP BY alb.album_id
            ORDER BY alb.title COLLATE NOCASE ASC
            """,
            (genre_name.strip(),),
        )
        return [dict(r) for r in cursor.fetchall()]
    finally:
        conn.close()
def get_all_decades_db(db_path: str | None = None) -> list[dict]:
    """Fetch decade breakdown (e.g. 1960s, 1970s...) with album counts from enabled servers in SQLite."""
    conn = get_db_connection(db_path)
    try:
        cursor = conn.execute(
            """
            SELECT 
                CASE 
                    WHEN alb.year IS NULL OR alb.year < 1920 OR alb.year > 2030 THEN 0
                    ELSE (alb.year / 10) * 10 
                END as year_start,
                CASE 
                    WHEN alb.year IS NULL OR alb.year < 1920 OR alb.year > 2030 THEN 0
                    ELSE ((alb.year / 10) * 10) + 9 
                END as year_end,
                CASE 
                    WHEN alb.year IS NULL OR alb.year < 1920 OR alb.year > 2030 THEN 'Unknown Era'
                    ELSE CAST((alb.year / 10) * 10 AS TEXT) || 's'
                END as decade,
                COUNT(DISTINCT alb.album_id) as album_count
            FROM albums alb
            JOIN album_sources src ON alb.album_id = src.album_id
            JOIN servers srv ON src.server_id = srv.server_id
            WHERE srv.enabled = 1 AND alb.title != '' AND alb.title IS NOT NULL
            GROUP BY year_start, year_end, decade
            ORDER BY year_start ASC
            """
        )
        return [dict(r) for r in cursor.fetchall()]
    finally:
        conn.close()


def get_albums_by_decade_db(year_start: int, year_end: int, db_path: str | None = None) -> list[dict]:
    """Fetch all albums within a specific decade from enabled servers in SQLite."""
    conn = get_db_connection(db_path)
    try:
        if year_start == 0 and year_end == 0:
            query = """
                SELECT DISTINCT alb.album_id, alb.artist_id, alb.artist_name as artist, alb.title, alb.year, alb.genre, alb.thumb, alb.play_count
                FROM albums alb
                JOIN album_sources src ON alb.album_id = src.album_id
                JOIN servers srv ON src.server_id = srv.server_id
                WHERE srv.enabled = 1 AND alb.title != '' AND alb.title IS NOT NULL
                  AND (alb.year IS NULL OR alb.year < 1920 OR alb.year > 2030)
                GROUP BY alb.album_id
                ORDER BY alb.title COLLATE NOCASE ASC
            """
            cursor = conn.execute(query)
        else:
            query = """
                SELECT DISTINCT alb.album_id, alb.artist_id, alb.artist_name as artist, alb.title, alb.year, alb.genre, alb.thumb, alb.play_count
                FROM albums alb
                JOIN album_sources src ON alb.album_id = src.album_id
                JOIN servers srv ON src.server_id = srv.server_id
                WHERE srv.enabled = 1 AND alb.title != '' AND alb.title IS NOT NULL
                  AND alb.year >= ? AND alb.year <= ?
                GROUP BY alb.album_id
                ORDER BY alb.title COLLATE NOCASE ASC
            """
            cursor = conn.execute(query, (year_start, year_end))
        return [dict(r) for r in cursor.fetchall()]
    finally:
        conn.close()


def search_music_db(query_str: str, db_path: str | None = None) -> list[dict]:
    """Search artists, albums, and tracks in SQLite database instantly."""
    if not query_str:
        return []
    term = f"%{query_str.strip().lower()}%"
    conn = get_db_connection(db_path)
    try:
        res = []
        # Search Artists
        cursor = conn.execute(
            """
            SELECT DISTINCT a.artist_id, a.artist_id as id, a.name, a.name as title, 'artist' as type, a.thumb
            FROM artists a
            JOIN artist_sources src ON a.artist_id = src.artist_id
            JOIN servers srv ON src.server_id = srv.server_id
            WHERE srv.enabled = 1 AND LOWER(a.name) LIKE ?
            LIMIT 10
            """,
            (term,),
        )
        res.extend([dict(r) for r in cursor.fetchall()])

        # Search Albums
        cursor = conn.execute(
            """
            SELECT DISTINCT alb.album_id, alb.album_id as id, alb.title, 'album' as type, alb.artist_name as artist, alb.artist_name, alb.thumb
            FROM albums alb
            JOIN album_sources src ON alb.album_id = src.album_id
            JOIN servers srv ON src.server_id = srv.server_id
            WHERE srv.enabled = 1 AND alb.title != '' AND alb.title IS NOT NULL
              AND LOWER(alb.title) LIKE ?
            ORDER BY alb.title COLLATE NOCASE ASC
            LIMIT 30
            """,
            (term,),
        )
        res.extend([dict(r) for r in cursor.fetchall()])

        # Search Tracks (strictly match track title, not artist or album title)
        cursor = conn.execute(
            """
            SELECT DISTINCT t.track_id as item_id, t.track_id, t.track_id as id, t.album_id, t.title, 'track' as type, t.artist_name as artist, t.album_title as album, t.duration, t.url, t.thumb
            FROM tracks t
            JOIN servers srv ON t.server_id = srv.server_id
            WHERE srv.enabled = 1 AND LOWER(t.title) LIKE ?
            LIMIT 15
            """,
            (term,),
        )
        res.extend([dict(r) for r in cursor.fetchall()])
        return res
    finally:
        conn.close()


def get_all_art_sources(item_id: int | str, item_type: str, db_path: str | None = None) -> list[tuple[str | None, str | None, str | None]]:
    """Resolve all (stored_thumb, server_id, rating_key) sources for a given item, prioritizing primary server."""
    conn = get_db_connection(db_path)
    sources = []
    try:
        resolved_id = item_id
        if item_type == "artist":
            r_row = conn.execute(
                "SELECT a.artist_id FROM artists a LEFT JOIN artist_sources src ON a.artist_id = src.artist_id WHERE a.artist_id = ? OR src.server_artist_id = ? OR a.norm_name = ? LIMIT 1",
                (item_id, str(item_id), str(item_id).lower()),
            ).fetchone()
            if r_row:
                resolved_id = r_row["artist_id"]

            cursor = conn.execute(
                """
                SELECT COALESCE(src.thumb, a.thumb) as thumb, src.server_id, src.server_artist_id as rating_key, COALESCE(srv.is_primary, 0) as is_primary
                FROM artists a
                LEFT JOIN artist_sources src ON a.artist_id = src.artist_id
                LEFT JOIN servers srv ON src.server_id = srv.server_id
                WHERE a.artist_id = ? AND (srv.enabled = 1 OR srv.enabled IS NULL)
                ORDER BY (CASE WHEN srv.server_id NOT LIKE 'mock%' THEN 0 ELSE 1 END), is_primary DESC
                """,
                (resolved_id,),
            )
            for row in cursor.fetchall():
                thumb_val = row["thumb"]
                if thumb_val and thumb_val.startswith("/api/music/"):
                    thumb_val = None
                if not thumb_val:
                    album_row = conn.execute(
                        "SELECT thumb FROM albums WHERE artist_id = ? AND thumb IS NOT NULL AND thumb != '' AND thumb NOT LIKE '/api/music/%' LIMIT 1",
                        (resolved_id,),
                    ).fetchone()
                    if album_row:
                        thumb_val = album_row["thumb"]
                sources.append((thumb_val, row["server_id"], row["rating_key"]))

        elif item_type == "album":
            r_row = conn.execute(
                "SELECT alb.album_id FROM albums alb LEFT JOIN album_sources src ON alb.album_id = src.album_id WHERE alb.album_id = ? LIMIT 1",
                (item_id,),
            ).fetchone()
            if r_row:
                resolved_id = r_row["album_id"]
            else:
                tr_row = conn.execute(
                    "SELECT album_id FROM tracks WHERE track_id = ? LIMIT 1",
                    (item_id,),
                ).fetchone()
                if tr_row:
                    resolved_id = tr_row["album_id"]

            cursor = conn.execute(
                """
                SELECT COALESCE(src.thumb, alb.thumb) as thumb, src.server_id, src.server_album_id as rating_key, COALESCE(srv.is_primary, 0) as is_primary
                FROM albums alb
                LEFT JOIN album_sources src ON alb.album_id = src.album_id
                LEFT JOIN servers srv ON src.server_id = srv.server_id
                WHERE alb.album_id = ? AND (srv.enabled = 1 OR srv.enabled IS NULL)
                ORDER BY (CASE WHEN srv.server_id NOT LIKE 'mock%' THEN 0 ELSE 1 END), is_primary DESC
                """,
                (resolved_id,),
            )
            for row in cursor.fetchall():
                thumb_val = row["thumb"]
                if thumb_val and thumb_val.startswith("/api/music/"):
                    thumb_val = None
                if not thumb_val:
                    tr_row = conn.execute(
                        "SELECT thumb FROM tracks WHERE album_id = ? AND thumb IS NOT NULL AND thumb != '' AND thumb NOT LIKE '/api/music/%' LIMIT 1",
                        (resolved_id,),
                    ).fetchone()
                    if tr_row:
                        thumb_val = tr_row["thumb"]
                sources.append((thumb_val, row["server_id"], row["rating_key"]))

        elif item_type == "track":
            r_row = conn.execute(
                "SELECT t.track_id FROM tracks t WHERE t.track_id = ? LIMIT 1",
                (item_id,),
            ).fetchone()
            if r_row:
                resolved_id = r_row["track_id"]

            cursor = conn.execute(
                """
                SELECT COALESCE(ts.thumb, t.thumb) as thumb, ts.server_id, ts.server_track_id as rating_key, COALESCE(srv.is_primary, 0) as is_primary
                FROM tracks t
                JOIN track_sources ts ON t.track_id = ts.track_id
                JOIN servers srv ON ts.server_id = srv.server_id
                WHERE t.track_id = ? AND srv.enabled = 1
                ORDER BY (CASE WHEN srv.is_primary = 1 THEN 0 ELSE 1 END), ts.bitrate DESC
                """,
                (resolved_id,),
            )
            for row in cursor.fetchall():
                thumb_val = row["thumb"]
                if thumb_val and thumb_val.startswith("/api/music/"):
                    thumb_val = None
                sources.append((thumb_val, row["server_id"], row["rating_key"]))

            if not sources:
                cursor_base = conn.execute(
                    """
                    SELECT t.thumb, t.server_id, t.server_track_id as rating_key, COALESCE(srv.is_primary, 0) as is_primary
                    FROM tracks t
                    LEFT JOIN servers srv ON t.server_id = srv.server_id
                    WHERE t.track_id = ? AND (srv.enabled = 1 OR srv.enabled IS NULL)
                    ORDER BY (CASE WHEN srv.is_primary = 1 THEN 0 ELSE 1 END)
                    """,
                    (resolved_id,),
                )
                for row in cursor_base.fetchall():
                    thumb_val = row["thumb"]
                    if thumb_val and thumb_val.startswith("/api/music/"):
                        thumb_val = None
                    sources.append((thumb_val, row["server_id"], row["rating_key"]))

        return sources if sources else [(None, None, None)]
    finally:
        conn.close()


_ART_SOURCE_MEM_CACHE: dict[str, tuple[str | None, str | None, str | None]] = {}
_ART_SOURCE_MEM_CACHE_MAX_SIZE = 5000


def get_art_source_info(item_id: int | str, item_type: str, db_path: str | None = None) -> tuple[str | None, str | None, str | None]:
    """Resolve stored thumb URL, server_id, and Plex server ratingKey from SQLite for a given SQLite item_id or ratingKey."""
    cache_key = f"{item_type}:{item_id}"
    if cache_key in _ART_SOURCE_MEM_CACHE:
        return _ART_SOURCE_MEM_CACHE[cache_key]

    sources = get_all_art_sources(item_id, item_type, db_path=db_path)
    res = sources[0] if sources else (None, None, None)

    if len(_ART_SOURCE_MEM_CACHE) >= _ART_SOURCE_MEM_CACHE_MAX_SIZE:
        _ART_SOURCE_MEM_CACHE.clear()
    _ART_SOURCE_MEM_CACHE[cache_key] = res
    return res


def get_albums_for_artist_db(artist_id: int | str, db_path: str | None = None) -> list[dict]:
    """Fetch all albums belonging to an artist from SQLite database."""
    conn = get_db_connection(db_path)
    try:
        artist_name = None
        if str(artist_id).isdigit():
            row = conn.execute(
                """
                SELECT a.name FROM artists a
                LEFT JOIN artist_sources src ON a.artist_id = src.artist_id
                WHERE a.artist_id = ? OR src.server_artist_id = ?
                LIMIT 1
                """,
                (int(artist_id), str(artist_id)),
            ).fetchone()
            if row:
                artist_name = row["name"]

        norm_name = _norm(artist_name) if artist_name else _norm(str(artist_id))

        query = """
            SELECT DISTINCT alb.album_id, alb.artist_id, alb.artist_name as artist, alb.title, alb.year, alb.genre, alb.thumb, alb.play_count
            FROM albums alb
            JOIN album_sources src ON alb.album_id = src.album_id
            JOIN servers srv ON src.server_id = srv.server_id
            WHERE srv.enabled = 1 AND alb.title != '' AND alb.title IS NOT NULL AND (alb.artist_id = ? OR src.server_album_id = ? OR LOWER(alb.artist_name) = ? OR alb.norm_title_artist LIKE ?)
            ORDER BY alb.year DESC, alb.title COLLATE NOCASE ASC
        """
        cursor = conn.execute(query, (artist_id, str(artist_id), (artist_name or str(artist_id)).lower(), f"%::{norm_name}"))
        return [dict(r) for r in cursor.fetchall()]
    finally:
        conn.close()


def get_tracks_for_album_db(album_id: int | str, db_path: str | None = None) -> dict | None:
    """Fetch tracks for an album from SQLite database using album_id or server_album_id."""
    conn = get_db_connection(db_path)
    try:
        cursor = conn.execute(
            """
            SELECT alb.album_id, alb.artist_id, alb.title, alb.artist_name, alb.thumb, srv.name as server_name, src.server_id, srv.enabled
            FROM albums alb
            LEFT JOIN album_sources src ON alb.album_id = src.album_id
            LEFT JOIN servers srv ON src.server_id = srv.server_id
            WHERE (alb.album_id = ? OR src.server_album_id = ?) AND (srv.enabled = 1 OR srv.enabled IS NULL)
            ORDER BY COALESCE(srv.is_primary, 0) DESC
            """,
            (album_id, str(album_id)),
        )
        alb_rows = cursor.fetchall()
        if not alb_rows:
            return None

        alb_row = alb_rows[0]
        resolved_album_id = alb_row["album_id"]
        server_sources = [{"server_id": r["server_id"], "server_name": r["server_name"]} for r in alb_rows if r["server_id"] and r["server_name"]]

        cursor = conn.execute(
            """
            SELECT t.track_id, t.title, t.duration, t.artist_name as artist, t.album_title as album, t.url, t.thumb, t.user_rating, srv.name as server_name, COALESCE(srv.is_primary, 0) as is_primary, t.server_id
            FROM tracks t
            JOIN servers srv ON t.server_id = srv.server_id
            WHERE srv.enabled = 1 AND t.album_id = ?
            ORDER BY is_primary DESC, t.track_id ASC
            """,
            (resolved_album_id,),
        )
        rows = cursor.fetchall()
        if not rows:
            return None

        seen_titles = set()
        deduped_rows = []
        for r in rows:
            norm_t = (r["title"] or "").strip().lower()
            if norm_t and norm_t in seen_titles:
                continue
            if norm_t:
                seen_titles.add(norm_t)
            deduped_rows.append(r)

        tracks = [
            {
                "track_id": r["track_id"],
                "item_id": r["track_id"],
                "title": r["title"],
                "duration": r["duration"],
                "artist": r["artist"],
                "album": r["album"],
                "track_number": idx + 1,
                "url": r["url"],
                "thumb": r["thumb"],
                "user_rating": float(r["user_rating"] or 0.0),
                "is_primary": bool(r["is_primary"]),
                "server_name": r["server_name"],
                "server_id": r["server_id"],
            }
            for idx, r in enumerate(deduped_rows)
        ]

        return {
            "album_title": alb_row["title"],
            "artist_id": alb_row["artist_id"],
            "artist_name": alb_row["artist_name"],
            "thumb": alb_row["thumb"],
            "server_name": alb_row["server_name"],
            "sources": server_sources,
            "tracks": tracks,
        }
    finally:
        conn.close()


def get_server_credentials(server_id: str | None = None, db_path: str | None = None) -> tuple[str | None, str | None]:
    """Fetch Plex server base URL and per-server access token from SQLite servers table and settings."""
    conn = get_db_connection(db_path)
    try:
        server_url = None
        token = None
        if server_id:
            cursor = conn.execute("SELECT server_url, access_token FROM servers WHERE server_id = ?", (server_id,))
            row = cursor.fetchone()
            if row:
                server_url = row["server_url"]
                token = row["access_token"]

        if not server_url or not token:
            cursor = conn.execute("SELECT server_url, access_token FROM servers WHERE (enabled = 1 OR enabled IS NULL) AND access_token IS NOT NULL LIMIT 1")
            row = cursor.fetchone()
            if row:
                server_url = server_url or row["server_url"]
                token = token or row["access_token"]

        if not token:
            from backend.config import settings
            token = getattr(settings, "plex_token", None) or os.getenv("PLEX_TOKEN")

        return server_url, token
    finally:
        conn.close()


def get_library_health_stats(db_path: str | None = None) -> dict:
    """Fetch library statistics, missing artwork counts, and per-server indexed item counts."""
    conn = get_db_connection(db_path)
    try:
        total_artists = conn.execute("SELECT COUNT(*) FROM artists").fetchone()[0]
        total_albums = conn.execute("SELECT COUNT(*) FROM albums").fetchone()[0]
        total_tracks = conn.execute("SELECT COUNT(*) FROM tracks").fetchone()[0]

        missing_artist_art = conn.execute(
            """
            SELECT COUNT(DISTINCT a.artist_id)
            FROM artists a
            JOIN artist_sources src ON a.artist_id = src.artist_id
            JOIN servers srv ON src.server_id = srv.server_id
            WHERE srv.is_primary = 1 AND (a.thumb IS NULL OR a.thumb = '' OR a.thumb LIKE '/api/music/%')
            """
        ).fetchone()[0]
        missing_album_art = conn.execute(
            """
            SELECT COUNT(DISTINCT alb.album_id)
            FROM albums alb
            JOIN album_sources src ON alb.album_id = src.album_id
            JOIN servers srv ON src.server_id = srv.server_id
            WHERE srv.is_primary = 1 AND (alb.thumb IS NULL OR alb.thumb = '' OR alb.thumb LIKE '/api/music/%')
            """
        ).fetchone()[0]

        servers = conn.execute(
            "SELECT server_id, name, enabled, is_primary FROM servers WHERE server_id != 'mock' AND LOWER(name) NOT LIKE '%mock%' ORDER BY enabled DESC, is_primary DESC, name ASC"
        ).fetchall()

        server_stats = []
        for s in servers:
            s_id = s["server_id"]
            s_name = s["name"]
            s_enabled = bool(s["enabled"])
            s_primary = bool(s["is_primary"])

            art_cnt = conn.execute("SELECT COUNT(DISTINCT artist_id) FROM artist_sources WHERE server_id = ?", (s_id,)).fetchone()[0]
            alb_cnt = conn.execute("SELECT COUNT(DISTINCT album_id) FROM album_sources WHERE server_id = ?", (s_id,)).fetchone()[0]

            trk_cnt = conn.execute("SELECT COUNT(*) FROM tracks WHERE server_id = ?", (s_id,)).fetchone()[0]
            if trk_cnt == 0:
                try:
                    trk_cnt = conn.execute("SELECT COUNT(*) FROM track_sources WHERE server_id = ?", (s_id,)).fetchone()[0]
                except Exception:
                    pass

            server_stats.append({
                "server_id": s_id,
                "server_name": s_name,
                "enabled": s_enabled,
                "is_primary": s_primary,
                "artist_count": art_cnt,
                "album_count": alb_cnt,
                "track_count": trk_cnt,
            })

        return {
            "total_artists": total_artists,
            "total_albums": total_albums,
            "total_tracks": total_tracks,
            "missing_artist_art": missing_artist_art,
            "missing_album_art": missing_album_art,
            "servers": server_stats,
        }
    finally:
        conn.close()

