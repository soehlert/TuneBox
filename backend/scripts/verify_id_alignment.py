#!/usr/bin/env python3
"""Database & Queue ID Verification & Alignment Tool for TuneBox.

Scans the SQLite library database, preseed tables, and Redis queue/history to detect
and auto-fix any collisions or mismatches between internal SQLite primary keys (`track_id`)
and external Plex ratingKeys (`server_track_id`).
"""

import sys
import json
import sqlite3
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.db.library_db import DB_PATH
from backend.services.redis_client import get_redis_queue_client


def audit_id_alignment(db_path: str | None = None, auto_fix: bool = True):
    """Scan full database and Redis queue/history for ID collisions and stale ratingKeys."""
    if not db_path:
        db_path = DB_PATH

    print(f"=== TuneBox System-Wide ID Alignment Verification ===")
    print(f"Database Path: {db_path}")

    conn = sqlite3.connect(db_path, timeout=30.0)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL;")

        # 1. Count total tracks and source mappings
        total_tracks = conn.execute("SELECT COUNT(*) as cnt FROM tracks").fetchone()["cnt"]
        total_sources = conn.execute("SELECT COUNT(*) as cnt FROM track_sources").fetchone()["cnt"]
        total_albums = conn.execute("SELECT COUNT(*) as cnt FROM albums").fetchone()["cnt"]
        total_artists = conn.execute("SELECT COUNT(*) as cnt FROM artists").fetchone()["cnt"]
        print(f"Total Indexed Tracks: {total_tracks} | Albums: {total_albums} | Artists: {total_artists}")
        print(f"Total Track Sources: {total_sources}")

        # Build ratingKey -> track_id map from track_sources table ONLY (authoritative mapping)
        rating_key_map = {}
        for row in conn.execute("SELECT server_track_id, track_id FROM track_sources WHERE server_track_id IS NOT NULL").fetchall():
            rating_key_map[str(row["server_track_id"])] = row["track_id"]

        valid_track_ids = set(row["track_id"] for row in conn.execute("SELECT track_id FROM tracks").fetchall())
        print(f"Loaded {len(rating_key_map)} ratingKey mappings into memory.")

        # 2. Check for numeric collisions (where track_id A == server_track_id B of a different track)
        collisions = conn.execute(
            """
            SELECT t1.track_id as sql_track_id,
                   t1.artist_name as sql_artist,
                   t1.title as sql_title,
                   ts2.server_track_id as rating_key,
                   t2.track_id as rating_key_real_sql_id,
                   t2.artist_name as rating_key_artist,
                   t2.title as rating_key_title
            FROM tracks t1
            JOIN track_sources ts2 ON CAST(t1.track_id AS TEXT) = ts2.server_track_id
            JOIN tracks t2 ON ts2.track_id = t2.track_id
            WHERE t1.track_id != t2.track_id
            """
        ).fetchall()

        print(f"\n--- NUMERIC COLLISION ANALYSIS ---")
        print(f"Found {len(collisions)} numeric ID overlaps where SQLite track_id == Plex ratingKey of a different song.")
        if collisions:
            print("Sample Collisions (First 5):")
            for c in collisions[:5]:
                print(f"  ID {c['sql_track_id']}:")
                print(f"    - As SQLite track_id: '{c['sql_artist']} - {c['sql_title']}' (track_id={c['sql_track_id']})")
                print(f"    - As Plex ratingKey:  '{c['rating_key_artist']} - {c['rating_key_title']}' (track_id={c['rating_key_real_sql_id']})")

        # 3. Audit preseed_playlist_tracks Table
        print(f"\n--- PRESEED PLAYLIST TRACKS TABLE AUDIT ---")
        preseed_rows = conn.execute("SELECT id, playlist_id, tracks_json FROM preseed_playlist_tracks").fetchall()
        print(f"Found {len(preseed_rows)} preseed playlist snapshots.")

        stale_preseed_entries = 0
        fixed_playlists = 0

        for r in preseed_rows:
            p_id = r["id"]
            playlist_name = r["playlist_id"]
            try:
                raw_ids = json.loads(r["tracks_json"])
            except Exception:
                continue

            cleaned_ids = []
            mismatch_count = 0

            for val in raw_ids:
                val_int = int(val) if (isinstance(val, (int, str)) and str(val).isdigit()) else None

                # If val_int is ALREADY a valid internal track_id in SQLite, keep it!
                if val_int and val_int in valid_track_ids and str(val_int) not in rating_key_map:
                    cleaned_ids.append(val_int)
                elif str(val) in rating_key_map:
                    resolved_tid = rating_key_map[str(val)]
                    cleaned_ids.append(resolved_tid)
                    if val_int != resolved_tid:
                        mismatch_count += 1
                elif val_int and val_int in valid_track_ids:
                    cleaned_ids.append(val_int)

            if mismatch_count > 0:
                print(f"  Playlist '{playlist_name}' (ID {p_id}): {mismatch_count} stale ratingKeys detected out of {len(raw_ids)} tracks.")
                stale_preseed_entries += mismatch_count

                if auto_fix:
                    conn.execute(
                        "UPDATE preseed_playlist_tracks SET tracks_json = ? WHERE id = ?",
                        (json.dumps(cleaned_ids), p_id),
                    )
                    fixed_playlists += 1

        if auto_fix and fixed_playlists > 0:
            conn.commit()
            print(f"  [Fix] Auto-migrated {fixed_playlists} preseed playlists ({stale_preseed_entries} stale ratingKeys converted to track_ids).")
        else:
            print("  [OK] Preseed playlists are 100% aligned with internal SQLite track_ids.")

        # 4. Audit Redis Playback Queue
        print(f"\n--- REDIS PLAYBACK QUEUE AUDIT ---")
        try:
            r_client = get_redis_queue_client()
            queue_raw = r_client.lrange("playback_queue", 0, -1)
            print(f"Found {len(queue_raw)} items in Redis playback queue.")

            queue_fixed = 0
            new_queue = []

            for item_bytes in queue_raw:
                item_str = item_bytes.decode("utf-8") if isinstance(item_bytes, bytes) else item_bytes
                try:
                    data = json.loads(item_str)
                except Exception:
                    new_queue.append(item_bytes)
                    continue

                item_id = data.get("item_id")
                title = data.get("title")
                artist = data.get("artist")

                real_tid = None
                if title and artist:
                    # Precise lookup by title + artist in SQLite
                    row_exact = conn.execute(
                        "SELECT track_id FROM tracks WHERE title = ? AND artist_name = ? LIMIT 1",
                        (title, artist),
                    ).fetchone()
                    if row_exact:
                        real_tid = row_exact["track_id"]

                if not real_tid and item_id and str(item_id) in rating_key_map:
                    real_tid = rating_key_map[str(item_id)]

                if real_tid and str(real_tid) != str(item_id):
                    print(f"  [Stale Queue ID] Item '{title}' had ratingKey '{item_id}' instead of track_id '{real_tid}'.")
                    data["item_id"] = real_tid
                    data["album_art"] = f"/api/music/track-art/{real_tid}"
                    queue_fixed += 1

                new_queue.append(json.dumps(data))

            if auto_fix and queue_fixed > 0:
                r_client.delete("playback_queue")
                for q_item in new_queue:
                    r_client.rpush("playback_queue", q_item)
                print(f"  [Fix] Auto-migrated {queue_fixed} stale queue items in Redis.")
            else:
                print("  [OK] Redis playback queue items are 100% aligned with internal SQLite track_ids.")
        except Exception as r_ex:
            print(f"  [Notice] Redis queue check skipped or offline: {r_ex}")

        # 5. Audit Redis Playback History
        print(f"\n--- REDIS PLAYBACK HISTORY AUDIT ---")
        try:
            r_client = get_redis_queue_client()
            history_raw = r_client.lrange("playback_history", 0, -1)
            print(f"Found {len(history_raw)} items in Redis playback history.")

            history_fixed = 0
            new_history = []

            for item_bytes in history_raw:
                item_str = item_bytes.decode("utf-8") if isinstance(item_bytes, bytes) else item_bytes
                try:
                    data = json.loads(item_str)
                except Exception:
                    new_history.append(item_bytes)
                    continue

                item_id = data.get("item_id")
                title = data.get("title")
                artist = data.get("artist")

                real_tid = None
                if title and artist:
                    row_exact = conn.execute(
                        "SELECT track_id FROM tracks WHERE title = ? AND artist_name = ? LIMIT 1",
                        (title, artist),
                    ).fetchone()
                    if row_exact:
                        real_tid = row_exact["track_id"]

                if not real_tid and item_id and str(item_id) in rating_key_map:
                    real_tid = rating_key_map[str(item_id)]

                if real_tid and str(real_tid) != str(item_id):
                    data["item_id"] = real_tid
                    history_fixed += 1

                new_history.append(json.dumps(data))

            if auto_fix and history_fixed > 0:
                r_client.delete("playback_history")
                for h_item in new_history:
                    r_client.rpush("playback_history", h_item)
                print(f"  [Fix] Auto-migrated {history_fixed} stale history items in Redis.")
            else:
                print("  [OK] Redis playback history items are 100% aligned with internal SQLite track_ids.")
        except Exception as r_ex:
            print(f"  [Notice] Redis history check skipped or offline: {r_ex}")

        print("\n=== System-Wide Verification Complete ===")
    finally:
        conn.close()


if __name__ == "__main__":
    audit_id_alignment()
