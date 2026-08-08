"""High-performance query engine and indexing service for SQLite library database."""

import time
import re
import logging
from backend.db.library_db import get_db_connection

logger = logging.getLogger(__name__)


def _norm(text: str) -> str:
    """Normalize string for deduplication (strip special chars & lowercase)."""
    if not text:
        return ""
    return re.sub(r"[^a-z0-9]", "", text.lower()) or text.lower()


def upsert_server(server_id: str, name: str, server_url: str | None = None, is_primary: bool = False, enabled: bool = True, db_path: str | None = None):
    """Insert or update a target Plex server in the servers registry."""
    conn = get_db_connection(db_path)
    try:
        conn.execute(
            """
            INSERT INTO servers (server_id, name, server_url, is_primary, enabled, last_indexed_at)
            VALUES (?, ?, ?, ?, ?, 0)
            ON CONFLICT(server_id) DO UPDATE SET
                name = excluded.name,
                server_url = COALESCE(excluded.server_url, servers.server_url),
                is_primary = excluded.is_primary,
                enabled = excluded.enabled
            """,
            (server_id, name, server_url, 1 if is_primary else 0, 1 if enabled else 0),
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


def upsert_artist(name: str, guid: str | None = None, thumb: str | None = None, play_count: int = 0, server_id: str | None = None, server_artist_id: str | None = None, db_path: str | None = None) -> int:
    """Upsert an artist into SQLite library with multi-server mapping."""
    norm_name = _norm(name)
    now = int(time.time())
    conn = get_db_connection(db_path)
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
                INSERT INTO artist_sources (artist_id, server_id, server_artist_id)
                VALUES (?, ?, ?)
                ON CONFLICT(artist_id, server_id) DO UPDATE SET server_artist_id = excluded.server_artist_id
                """,
                (artist_id, server_id, str(server_artist_id)),
            )

        conn.commit()
        return artist_id
    finally:
        conn.close()


def upsert_album(title: str, artist_name: str, artist_id: int | None = None, year: int | None = None, genre: str | None = None, thumb: str | None = None, play_count: int = 0, guid: str | None = None, server_id: str | None = None, server_album_id: str | None = None, db_path: str | None = None) -> int:
    """Upsert an album into SQLite library with multi-server mapping."""
    norm_key = f"{_norm(title)}::{_norm(artist_name)}"
    now = int(time.time())
    conn = get_db_connection(db_path)
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
                INSERT INTO album_sources (album_id, server_id, server_album_id)
                VALUES (?, ?, ?)
                ON CONFLICT(album_id, server_id) DO UPDATE SET server_album_id = excluded.server_album_id
                """,
                (album_id, server_id, str(server_album_id)),
            )

        conn.commit()
        return album_id
    finally:
        conn.close()


def upsert_track(album_id: int, server_id: str, server_track_id: str, artist_name: str, album_title: str, title: str, duration: int, url: str | None = None, thumb: str | None = None, play_count: int = 0, db_path: str | None = None) -> int:
    """Upsert a track into SQLite library."""
    now = int(time.time())
    safe_url = str(url) if (url is not None and not callable(url)) else None
    conn = get_db_connection(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO tracks (album_id, server_id, server_track_id, artist_name, album_title, title, duration, url, thumb, play_count, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (album_id, server_id, str(server_track_id), artist_name, album_title, title, duration, safe_url, thumb, play_count, now),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def get_indexed_artists(sort_mode: str = "name_asc", db_path: str | None = None) -> list[dict]:
    """Fetch all unique artists linked to currently enabled servers."""
    conn = get_db_connection(db_path)
    try:
        order_clause = "a.play_count DESC, a.name COLLATE NOCASE ASC" if sort_mode == "plays_desc" else (
            "a.name COLLATE NOCASE DESC" if sort_mode == "name_desc" else "a.name COLLATE NOCASE ASC"
        )
        query = f"""
            SELECT DISTINCT a.artist_id, a.name, a.guid, a.thumb, a.play_count
            FROM artists a
            JOIN artist_sources src ON a.artist_id = src.artist_id
            JOIN servers srv ON src.server_id = srv.server_id
            WHERE srv.enabled = 1
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
            WHERE srv.enabled = 1 AND alb.title != '' AND alb.title IS NOT NULL AND (LOWER(alb.title) LIKE ? OR LOWER(alb.artist_name) LIKE ?)
            LIMIT 10
            """,
            (term, term),
        )
        res.extend([dict(r) for r in cursor.fetchall()])

        # Search Tracks
        cursor = conn.execute(
            """
            SELECT DISTINCT t.track_id as item_id, t.track_id, t.track_id as id, t.title, 'track' as type, t.artist_name as artist, t.album_title as album, t.duration, t.url, t.thumb
            FROM tracks t
            JOIN servers srv ON t.server_id = srv.server_id
            WHERE srv.enabled = 1 AND (LOWER(t.title) LIKE ? OR LOWER(t.artist_name) LIKE ? OR LOWER(t.album_title) LIKE ?)
            LIMIT 15
            """,
            (term, term, term),
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
                SELECT a.thumb, src.server_id, src.server_artist_id as rating_key, COALESCE(srv.is_primary, 0) as is_primary
                FROM artists a
                LEFT JOIN artist_sources src ON a.artist_id = src.artist_id
                LEFT JOIN servers srv ON src.server_id = srv.server_id
                WHERE a.artist_id = ?
                ORDER BY is_primary DESC
                """,
                (resolved_id,),
            )
            for row in cursor.fetchall():
                sources.append((row["thumb"], row["server_id"], row["rating_key"]))

        elif item_type == "album":
            r_row = conn.execute(
                "SELECT alb.album_id FROM albums alb LEFT JOIN album_sources src ON alb.album_id = src.album_id WHERE alb.album_id = ? OR src.server_album_id = ? LIMIT 1",
                (item_id, str(item_id)),
            ).fetchone()
            if r_row:
                resolved_id = r_row["album_id"]

            cursor = conn.execute(
                """
                SELECT alb.thumb, src.server_id, src.server_album_id as rating_key, COALESCE(srv.is_primary, 0) as is_primary
                FROM albums alb
                LEFT JOIN album_sources src ON alb.album_id = src.album_id
                LEFT JOIN servers srv ON src.server_id = srv.server_id
                WHERE alb.album_id = ?
                ORDER BY is_primary DESC
                """,
                (resolved_id,),
            )
            for row in cursor.fetchall():
                sources.append((row["thumb"], row["server_id"], row["rating_key"]))

        elif item_type == "track":
            r_row = conn.execute(
                "SELECT t.track_id FROM tracks t WHERE t.track_id = ? OR t.server_track_id = ? LIMIT 1",
                (item_id, str(item_id)),
            ).fetchone()
            if r_row:
                resolved_id = r_row["track_id"]

            cursor = conn.execute(
                """
                SELECT t.thumb, t.server_id, t.server_track_id as rating_key, COALESCE(srv.is_primary, 0) as is_primary
                FROM tracks t
                LEFT JOIN servers srv ON t.server_id = srv.server_id
                WHERE t.track_id = ?
                ORDER BY is_primary DESC
                """,
                (resolved_id,),
            )
            for row in cursor.fetchall():
                sources.append((row["thumb"], row["server_id"], row["rating_key"]))

        return sources if sources else [(None, None, None)]
    finally:
        conn.close()


def get_art_source_info(item_id: int | str, item_type: str, db_path: str | None = None) -> tuple[str | None, str | None, str | None]:
    """Resolve stored thumb URL, server_id, and Plex server ratingKey from SQLite for a given SQLite item_id or ratingKey."""
    sources = get_all_art_sources(item_id, item_type, db_path=db_path)
    return sources[0] if sources else (None, None, None)


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
            SELECT alb.album_id, alb.title, alb.artist_name, alb.thumb, srv.name as server_name, src.server_id
            FROM albums alb
            LEFT JOIN album_sources src ON alb.album_id = src.album_id
            LEFT JOIN servers srv ON src.server_id = srv.server_id
            WHERE alb.album_id = ? OR src.server_album_id = ?
            ORDER BY COALESCE(srv.is_primary, 0) DESC
            """,
            (album_id, str(album_id)),
        )
        alb_rows = cursor.fetchall()
        if not alb_rows:
            return None

        alb_row = alb_rows[0]
        resolved_album_id = alb_row["album_id"]
        server_sources = [{"server_id": r["server_id"], "server_name": r["server_name"]} for r in alb_rows if r["server_id"]]

        cursor = conn.execute(
            """
            SELECT t.track_id, t.title, t.duration, t.artist_name as artist, t.album_title as album, t.url, t.thumb, srv.name as server_name, COALESCE(srv.is_primary, 0) as is_primary
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
                "server_name": r["server_name"],
            }
            for idx, r in enumerate(deduped_rows)
        ]

        return {
            "album_title": alb_row["title"],
            "artist_name": alb_row["artist_name"],
            "thumb": alb_row["thumb"],
            "server_name": alb_row["server_name"],
            "sources": server_sources,
            "tracks": tracks,
        }
    finally:
        conn.close()


def get_server_credentials(server_id: str | None = None, db_path: str | None = None) -> tuple[str | None, str | None]:
    """Fetch Plex server base URL and token from SQLite servers table and settings."""
    conn = get_db_connection(db_path)
    try:
        server_url = None
        if server_id:
            cursor = conn.execute("SELECT server_url FROM servers WHERE server_id = ?", (server_id,))
            row = cursor.fetchone()
            if row and row["server_url"]:
                server_url = row["server_url"]

        if not server_url:
            cursor = conn.execute("SELECT server_url FROM servers WHERE enabled = 1 LIMIT 1")
            row = cursor.fetchone()
            if row and row["server_url"]:
                server_url = row["server_url"]

        from backend.config import settings
        token = getattr(settings, "plex_token", None) or os.getenv("PLEX_TOKEN")
        return server_url, token
    finally:
        conn.close()
