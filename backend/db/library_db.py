"""SQLite database management for TuneBox music library indexing and stats."""

import os
import sqlite3
import logging
import json
import time

logger = logging.getLogger(__name__)

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "library.db")


def get_db_connection(db_path: str | None = None) -> sqlite3.Connection:
    """Connect to SQLite database with WAL mode enabled for high concurrency."""
    target_path = db_path or DB_PATH
    try:
        conn = sqlite3.connect(target_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA busy_timeout=30000;")
        conn.execute("PRAGMA foreign_keys=ON;")
        return conn
    except (sqlite3.DatabaseError, sqlite3.OperationalError) as ex:
        if "malformed" in str(ex).lower() or "disk image" in str(ex).lower() or "integrity check" in str(ex).lower():
            logger.warning("Corrupted SQLite database detected at %s (%s). Recreating clean database...", target_path, ex)
            try:
                if os.path.exists(target_path):
                    os.remove(target_path)
                wal_file = f"{target_path}-wal"
                shm_file = f"{target_path}-shm"
                if os.path.exists(wal_file):
                    os.remove(wal_file)
                if os.path.exists(shm_file):
                    os.remove(shm_file)
            except Exception as rm_ex:
                logger.warning("Could not remove corrupted database files: %s", rm_ex)

            conn = sqlite3.connect(target_path, timeout=30.0)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA foreign_keys=ON;")
            init_library_db(db_path=target_path)
            return conn
        else:
            raise ex


def init_library_db(db_path: str | None = None):
    """Initialize the SQLite database schema and B-Tree indexes for library indexing."""
    conn = get_db_connection(db_path)
    try:
        cursor = conn.cursor()

        # 1. Servers Table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS servers (
                server_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                server_url TEXT,
                access_token TEXT,
                is_primary INTEGER DEFAULT 0,
                enabled INTEGER DEFAULT 1,
                last_indexed_at INTEGER DEFAULT 0
            )
            """
        )
        cursor.execute("PRAGMA table_info(servers)")
        server_cols = [c[1] for c in cursor.fetchall()]
        if "access_token" not in server_cols:
            cursor.execute("ALTER TABLE servers ADD COLUMN access_token TEXT")

        # 2. Artists Table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS artists (
                artist_id INTEGER PRIMARY KEY AUTOINCREMENT,
                norm_name TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                guid TEXT,
                thumb TEXT,
                play_count INTEGER DEFAULT 0,
                updated_at INTEGER NOT NULL
            )
            """
        )

        # Artist Source Mapping
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS artist_sources (
                artist_id INTEGER NOT NULL,
                server_id TEXT NOT NULL,
                server_artist_id TEXT NOT NULL,
                thumb TEXT,
                PRIMARY KEY (artist_id, server_id),
                FOREIGN KEY (artist_id) REFERENCES artists(artist_id) ON DELETE CASCADE
            )
            """
        )
        cursor.execute("PRAGMA table_info(artist_sources)")
        art_src_cols = [c[1] for c in cursor.fetchall()]
        if "thumb" not in art_src_cols:
            cursor.execute("ALTER TABLE artist_sources ADD COLUMN thumb TEXT")

        # 3. Albums Table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS albums (
                album_id INTEGER PRIMARY KEY AUTOINCREMENT,
                norm_title_artist TEXT UNIQUE NOT NULL,
                artist_id INTEGER,
                artist_name TEXT NOT NULL,
                title TEXT NOT NULL,
                year INTEGER,
                genre TEXT,
                thumb TEXT,
                play_count INTEGER DEFAULT 0,
                guid TEXT,
                updated_at INTEGER NOT NULL,
                FOREIGN KEY (artist_id) REFERENCES artists(artist_id) ON DELETE CASCADE
            )
            """
        )

        # Album Source Mapping
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS album_sources (
                album_id INTEGER NOT NULL,
                server_id TEXT NOT NULL,
                server_album_id TEXT NOT NULL,
                thumb TEXT,
                PRIMARY KEY (album_id, server_id),
                FOREIGN KEY (album_id) REFERENCES albums(album_id) ON DELETE CASCADE
            )
            """
        )
        cursor.execute("PRAGMA table_info(album_sources)")
        alb_src_cols = [c[1] for c in cursor.fetchall()]
        if "thumb" not in alb_src_cols:
            cursor.execute("ALTER TABLE album_sources ADD COLUMN thumb TEXT")

        # 4. Tracks Table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS tracks (
                track_id INTEGER PRIMARY KEY AUTOINCREMENT,
                album_id INTEGER NOT NULL,
                server_id TEXT NOT NULL,
                server_track_id TEXT NOT NULL,
                artist_name TEXT NOT NULL,
                album_title TEXT NOT NULL,
                title TEXT NOT NULL,
                duration INTEGER NOT NULL,
                url TEXT,
                thumb TEXT,
                play_count INTEGER DEFAULT 0,
                user_rating REAL DEFAULT 0.0,
                bpm INTEGER DEFAULT 0,
                moods TEXT DEFAULT '',
                updated_at INTEGER NOT NULL,
                FOREIGN KEY (album_id) REFERENCES albums(album_id) ON DELETE CASCADE
            )
            """
        )

        # Migration for existing database schemas missing user_rating, bpm, or moods
        try:
            cursor.execute("ALTER TABLE tracks ADD COLUMN user_rating REAL DEFAULT 0.0;")
        except Exception:
            pass
        try:
            cursor.execute("ALTER TABLE tracks ADD COLUMN bpm INTEGER DEFAULT 0;")
        except Exception:
            pass
        try:
            cursor.execute("ALTER TABLE tracks ADD COLUMN moods TEXT DEFAULT '';")
        except Exception:
            pass

        # 4b. Track Source Mapping (Per-server ratingKeys and audio quality metrics)
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS track_sources (
                source_id INTEGER PRIMARY KEY AUTOINCREMENT,
                track_id INTEGER NOT NULL,
                server_id TEXT NOT NULL,
                server_track_id TEXT NOT NULL,
                bitrate INTEGER DEFAULT 0,
                codec TEXT,
                sample_rate INTEGER DEFAULT 0,
                bit_depth INTEGER DEFAULT 16,
                thumb TEXT,
                updated_at INTEGER NOT NULL,
                FOREIGN KEY (track_id) REFERENCES tracks(track_id) ON DELETE CASCADE,
                FOREIGN KEY (server_id) REFERENCES servers(server_id) ON DELETE CASCADE,
                CONSTRAINT unq_track_server UNIQUE (track_id, server_id)
            )
            """
        )

        # 5. Playback History Event Log (Append-only)
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS playback_history (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                track_id INTEGER NOT NULL,
                artist_name TEXT NOT NULL,
                album_title TEXT NOT NULL,
                track_title TEXT NOT NULL,
                username TEXT NOT NULL,
                played_at INTEGER NOT NULL,
                FOREIGN KEY (track_id) REFERENCES tracks(track_id) ON DELETE CASCADE
            )
            """
        )

        # 6. Queue Snapshots Table for persistent crash recovery & admin restore
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS queue_snapshots (
                snapshot_id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at INTEGER NOT NULL,
                trigger_type TEXT NOT NULL,
                queue_data TEXT NOT NULL
            )
            """
        )

        # Indexes for fast B-Tree lookups
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_artists_name ON artists (name COLLATE NOCASE);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_artists_play_count ON artists (play_count DESC);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_albums_title ON albums (title COLLATE NOCASE);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_albums_artist ON albums (artist_name COLLATE NOCASE);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_albums_genre ON albums (genre);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_albums_year ON albums (year);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_albums_play_count ON albums (play_count DESC);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_tracks_album ON tracks (album_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_tracks_moods ON tracks (moods);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_track_sources_track ON track_sources (track_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_track_sources_server ON track_sources (server_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_playback_history_played_at ON playback_history (played_at DESC);")

        # 6. Preseed Playlist Tracks Table for persistent autoplay fallback
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS preseed_playlist_tracks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                playlist_id TEXT,
                tracks_json TEXT NOT NULL,
                updated_at INTEGER NOT NULL
            )
            """
        )

        # 7. Curated Vibe Tracks Table for anchor playlists
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS curated_vibe_tracks (
                vibe TEXT NOT NULL,
                track_id INTEGER NOT NULL,
                source TEXT DEFAULT 'playlist',
                updated_at INTEGER NOT NULL,
                PRIMARY KEY (vibe, track_id),
                FOREIGN KEY (track_id) REFERENCES tracks(track_id) ON DELETE CASCADE
            )
            """
        )
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_curated_vibe_tracks_vibe ON curated_vibe_tracks (vibe);")

        cursor.execute("DELETE FROM servers WHERE server_id = 'mock' OR name LIKE '%Mock%';")

        conn.commit()
        logger.info("Library SQLite schema initialized successfully.")
    except Exception as e:
        logger.exception("Failed to initialize library SQLite database: %s", e)
        raise e
    finally:
        conn.close()


def save_preseed_playlist_tracks(track_ids: list, playlist_id: str = "default", db_path: str | None = None) -> bool:
    """Save preseed playlist track IDs into SQLite for persistent autoplay fallback."""
    if not isinstance(track_ids, list) or not track_ids:
        return False
    conn = get_db_connection(db_path)
    try:
        cursor = conn.cursor()
        now = int(time.time())
        json_str = json.dumps(track_ids)
        cursor.execute(
            "INSERT INTO preseed_playlist_tracks (playlist_id, tracks_json, updated_at) VALUES (?, ?, ?);",
            (str(playlist_id), json_str, now),
        )
        cursor.execute(
            """
            DELETE FROM preseed_playlist_tracks
            WHERE id NOT IN (
                SELECT id FROM preseed_playlist_tracks ORDER BY updated_at DESC LIMIT 5
            );
            """
        )
        conn.commit()
        return True
    except Exception as ex:
        logger.exception("Failed to save preseed playlist tracks to SQLite: %s", ex)
        return False
    finally:
        conn.close()


def get_latest_preseed_playlist_tracks(db_path: str | None = None) -> list | None:
    """Retrieve the most recent preseed playlist track IDs from SQLite."""
    conn = get_db_connection(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT tracks_json FROM preseed_playlist_tracks ORDER BY updated_at DESC LIMIT 1;"
        )
        row = cursor.fetchone()
        if not row:
            return None
        data = json.loads(row["tracks_json"])
        return data if isinstance(data, list) and len(data) > 0 else None
    except Exception as ex:
        logger.exception("Failed to get preseed playlist tracks from SQLite: %s", ex)
        return None
    finally:
        conn.close()


def save_curated_vibe_tracks(vibe: str, track_ids: list[int], source: str = "playlist", replace: bool = True, db_path: str | None = None) -> int:
    """Save curated anchor track IDs for a specific party vibe."""
    clean_vibe = str(vibe).strip()
    conn = get_db_connection(db_path)
    try:
        cursor = conn.cursor()
        if replace:
            cursor.execute("DELETE FROM curated_vibe_tracks WHERE LOWER(vibe) = LOWER(?)", (clean_vibe,))
        if not isinstance(track_ids, list) or not track_ids:
            conn.commit()
            return 0
        now = int(time.time())
        data = [(clean_vibe, tid, source, now) for tid in track_ids]
        cursor.executemany(
            """
            INSERT INTO curated_vibe_tracks (vibe, track_id, source, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(vibe, track_id) DO UPDATE SET
                source = excluded.source,
                updated_at = excluded.updated_at
            """,
            data,
        )
        conn.commit()
        return len(data)
    except Exception as ex:
        logger.exception("Failed to save curated vibe tracks to SQLite: %s", ex)
        return 0
    finally:
        conn.close()


def get_curated_vibe_track_ids(vibe: str, db_path: str | None = None) -> list[int]:
    """Retrieve curated track IDs for a specific party vibe."""
    clean_vibe = str(vibe).strip()
    conn = get_db_connection(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT track_id FROM curated_vibe_tracks WHERE LOWER(vibe) = LOWER(?)",
            (clean_vibe,),
        )
        rows = cursor.fetchall()
        return [row["track_id"] for row in rows]
    except Exception as ex:
        logger.exception("Failed to get curated vibe tracks from SQLite: %s", ex)
        return []
    finally:
        conn.close()


# Auto-initialize database on module import
init_library_db()
