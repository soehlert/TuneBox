"""Handle interaction with redis queue and caching."""

import json
import logging

from fastapi import HTTPException, status

from backend.config import settings
from backend.services.library import get_db_connection, rating_key_to_track_id, validate_track_id
from backend.services.redis_client import get_redis_cache_client, get_redis_queue_client
from backend.utils import is_song_in_queue, is_track_object

logger = logging.getLogger(__name__)

CACHE_TTL = 21600


def add_to_queue_redis(song, server_id=None, server_name=None, server_token=None, server_address=None, is_fallback=False, added_by=None):
    """Add a song to the Redis queue with optional multi-server connection metadata."""
    if not is_track_object(song):
        msg = "Only songs can be added to the queue."
        raise ValueError(msg)

    target_server_id = server_id or getattr(song, "server_id", None)

    internal_track_id = getattr(song, "sqlite_track_id", None)
    if hasattr(internal_track_id, "_mock_name") or hasattr(internal_track_id, "return_value"):
        internal_track_id = None
    raw_album_id = getattr(song, "album_id", None)
    if hasattr(raw_album_id, "_mock_name") or hasattr(raw_album_id, "return_value"):
        raw_album_id = None

    album_id_val = raw_album_id
    if not settings.testing:
        resolved_id = None
        if internal_track_id:
            resolved_id = validate_track_id(internal_track_id)
        else:
            rk_val = getattr(song, "ratingKey", None)
            if rk_val:
                resolved_id = rating_key_to_track_id(rk_val)
        if resolved_id:
            internal_track_id = resolved_id
            try:
                conn = get_db_connection()
                row = conn.execute("SELECT album_id FROM tracks WHERE track_id = ? LIMIT 1", (resolved_id,)).fetchone()
                conn.close()
                if row:
                    album_id_val = row["album_id"]
            except Exception:
                pass

    if internal_track_id and hasattr(song, "__dict__"):
        song.sqlite_track_id = internal_track_id

    if is_song_in_queue(song, server_id=target_server_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Song {song.title} is already in the queue.",
        )

    moods = [m.tag if hasattr(m, "tag") else str(m) for m in getattr(song, "moods", [])] if hasattr(song, "moods") else []

    # Cascade to Album and Artist level for moods if track level is empty and attributes are pre-cached (not network calls)
    if not moods and not is_fallback:
        try:
            album_attr = getattr(song, "album", None)
            if album_attr and not callable(album_attr) and hasattr(album_attr, "moods") and album_attr.moods:
                moods = [m.tag if hasattr(m, "tag") else str(m) for m in album_attr.moods]
        except Exception:
            pass

    if not moods and not is_fallback:
        try:
            artist_attr = getattr(song, "artist", None)
            if artist_attr and not callable(artist_attr) and hasattr(artist_attr, "moods") and artist_attr.moods:
                moods = [m.tag if hasattr(m, "tag") else str(m) for m in artist_attr.moods]
        except Exception:
            pass

    def _str_or_none(v):
        if v is None or hasattr(v, "_mock_name") or hasattr(v, "return_value"):
            return None
        return str(v)

    song_data = {
        "item_id": str(internal_track_id or getattr(song, "ratingKey", "")),
        "album_id": str(album_id_val) if album_id_val else str(getattr(song, "parentRatingKey", song.ratingKey)),
        "title": song.title,
        "artist": getattr(song, "grandparentTitle", getattr(song, "artist", "Unknown Artist")),
        "duration": song.duration,
        "album_art": song.thumb if (hasattr(song, "thumb") and not hasattr(getattr(song, "thumb"), "_mock_name")) else None,
        "server_id": _str_or_none(target_server_id),
        "server_name": _str_or_none(server_name or getattr(song, "server_name", None)),
        "server_token": _str_or_none(server_token or getattr(song, "server_token", None)),
        "server_address": _str_or_none(server_address or getattr(song, "server_address", None)),
        "is_fallback": is_fallback,
        "moods": moods,
        "added_by": added_by or ("System" if is_fallback else "Guest"),
    }

    client = get_redis_queue_client()
    if is_fallback:
        # If it's fallback, just append it to the end of the queue
        client.rpush("playback_queue", json.dumps(song_data))
        logger.info("Added fallback track %s to Redis queue.", song.title)
    else:
        # If it's a guest song, check if fallback songs exist in the queue
        queue = client.lrange("playback_queue", 0, -1)
        fallback_indices = []
        for i, item_bytes in enumerate(queue):
            item = json.loads(item_bytes)
            if item.get("is_fallback"):
                fallback_indices.append(i)
        
        if fallback_indices:
            # Only allow leapfrogging fallback tracks that are not currently playing (index >= 1)
            candidate_indices = [idx for idx in fallback_indices if idx >= 1]
            if candidate_indices:
                first_fallback_idx = candidate_indices[0]
                first_fallback_data = queue[first_fallback_idx]
                client.linsert("playback_queue", "BEFORE", first_fallback_data, json.dumps(song_data))
                
                # Drop the last fallback track in the queue to maintain queue size
                last_fallback_idx = fallback_indices[-1]
                last_fallback_data = queue[last_fallback_idx]
                client.lrem("playback_queue", -1, last_fallback_data)
                logger.info("Inserted guest song %s before first non-playing fallback and dropped last fallback.", song.title)
            else:
                # If the only fallback track is at index 0 (currently playing), append to the end
                client.rpush("playback_queue", json.dumps(song_data))
                logger.info("Added guest song %s to end of Redis queue (playing track is fallback).", song.title)
        else:
            # If no fallback tracks exist, just append to the end as normal
            client.rpush("playback_queue", json.dumps(song_data))
            logger.info("Added guest song %s to Redis queue.", song.title)


def remove_from_redis_queue(item_id):
    """Remove a song from the Redis playback queue by its item_id.

    Returns:
        A message about the song in the queue.
    """
    client = get_redis_queue_client()
    queue = client.lrange("playback_queue", 0, -1)

    for song_data in queue:
        try:
            song_str = song_data.decode("utf-8") if isinstance(song_data, bytes) else song_data
            song = json.loads(song_str)
        except Exception:
            continue

        s_item_id = str(song.get("item_id") or song.get("id") or "")
        if s_item_id == str(item_id):
            removed_count = client.lrem("playback_queue", 0, song_data)
            if removed_count == 0:
                if isinstance(song_data, bytes):
                    try:
                        client.lrem("playback_queue", 0, song_data.decode("utf-8"))
                    except Exception:
                        pass
                elif isinstance(song_data, str):
                    try:
                        client.lrem("playback_queue", 0, song_data.encode("utf-8"))
                    except Exception:
                        pass
            logger.info("Removed %s from the Redis playback queue.", song.get("title", "track"))
            return {"message": f"Removed {song.get('title', 'track')} from the queue."}

    logger.warning("Song with item_id %s not found in the Redis queue.", item_id)
    return {"message": "Song not found in the queue."}


def get_redis_queue():
    """Get all songs in the Redis playback queue (metadata only).

    Returns:
        The redis queue as a list.
    """
    queue = get_redis_queue_client().lrange("playback_queue", 0, -1)

    queue_items = []
    for item_data in queue:
        song_metadata = json.loads(item_data)
        queue_items.append(song_metadata)
    return queue_items


def clear_redis_queue(force_all: bool = False, fallback_only: bool = False):
    """Clear the Redis playback queue, saving a before_clear snapshot of user tracks first.

    If force_all is True, delete the entire queue including index 0.
    If fallback_only is True, remove upcoming fallback tracks (is_fallback=True) while preserving index 0 and guest requested tracks.
    If force_all is False and fallback_only is False, preserve index 0.

    Returns:
        A cleared redis queue message.
    """
    client = get_redis_queue_client()
    from backend.services.plex import track_time_tracker, clear_cache  # noqa: PLC0415

    # Perform queue clear
    if force_all or (not track_time_tracker.is_playing and track_time_tracker.state != "paused" and not fallback_only):
        client.delete("playback_queue")
        if force_all:
            clear_cache("now_playing")
            track_time_tracker.stop()
        logger.info("The Redis playback queue has been completely cleared.")
    elif fallback_only:
        queue = client.lrange("playback_queue", 0, -1)
        if queue:
            items = [json.loads(item_str) for item_str in queue]
            kept_items = []
            for idx, item in enumerate(items):
                if idx == 0:
                    kept_items.append(queue[0])
                elif not item.get("is_fallback", False):
                    kept_items.append(queue[idx])

            client.delete("playback_queue")
            for raw_item in kept_items:
                client.rpush("playback_queue", raw_item)
            logger.info("Cleared upcoming fallback tracks, preserving active track and guest requests.")
        else:
            client.delete("playback_queue")
    else:
        queue = client.lrange("playback_queue", 0, -1)
        if queue:
            first_item = queue[0]
            client.delete("playback_queue")
            client.rpush("playback_queue", first_item)
            logger.info("The Redis playback queue has been cleared, keeping the active playing track.")
        else:
            client.delete("playback_queue")
            logger.info("The Redis playback queue was empty and has been cleared.")

    return {"message": "The queue has been cleared."}


_guest_vibe_changing_memory_state: bool = True


def is_guest_vibe_changing_enabled() -> bool:
    """Check if guests are allowed to change the room party vibe."""
    global _guest_vibe_changing_memory_state
    try:
        val = get_redis_cache_client().get("guest_vibe_changing_enabled")
        if val is None or not isinstance(val, (str, bytes)):
            return _guest_vibe_changing_memory_state
        return bool(json.loads(val))
    except Exception:
        return _guest_vibe_changing_memory_state


def set_guest_vibe_changing_enabled(enabled: bool):
    """Set whether guests are allowed to change the room party vibe."""
    global _guest_vibe_changing_memory_state
    _guest_vibe_changing_memory_state = bool(enabled)
    try:
        get_redis_cache_client().set("guest_vibe_changing_enabled", json.dumps(bool(enabled)))
    except Exception:
        pass


def reorder_redis_queue(from_index: int, to_index: int):
    """Reorder a track in the Redis queue from from_index to to_index.

    Indices 0 (currently playing track) cannot be moved or replaced.

    Returns:
        Dict status message.
    """
    client = get_redis_queue_client()
    queue = client.lrange("playback_queue", 0, -1)

    if not queue:
        return {"message": "Queue is empty."}

    if from_index < 1 or from_index >= len(queue):
        raise ValueError(f"Invalid from_index {from_index} for queue length {len(queue)}")

    if to_index < 1 or to_index >= len(queue):
        raise ValueError(f"Invalid to_index {to_index} for queue length {len(queue)}")

    if from_index == to_index:
        return {"message": "No queue movement required."}

    item = queue.pop(from_index)
    queue.insert(to_index, item)

    client.delete("playback_queue")
    client.rpush("playback_queue", *queue)

    logger.info("Reordered Redis playback queue: item from index %d to %d", from_index, to_index)
    return {"message": "Queue reordered successfully."}


def purge_non_human_tracks_from_queue_redis():
    """Remove non-human added tracks (is_fallback=True or autoplay/vibe-seeded) from the queue, except currently playing (index 0)."""
    client = get_redis_queue_client()
    raw_queue = client.lrange("playback_queue", 0, -1)
    if not raw_queue or len(raw_queue) <= 1:
        return

    new_queue = [raw_queue[0]]
    for item_raw in raw_queue[1:]:
        item_str = item_raw.decode("utf-8") if isinstance(item_raw, bytes) else item_raw
        item = json.loads(item_str)
        is_fallback = bool(item.get("is_fallback"))
        added_by = str(item.get("added_by", "")).lower()

        is_human = not is_fallback and not any(k in added_by for k in ["autoplay", "vibe seed", "seed", "tunebox", "smart"])
        if is_human:
            new_queue.append(item_raw)

    client.delete("playback_queue")
    if new_queue:
        client.rpush("playback_queue", *new_queue)
    logger.info("Purged non-human tracks from playback queue. %d tracks remaining.", len(new_queue))


def ensure_queue_synced_with_now_playing(song_data: dict):
    """Ensure that index 0 of the Redis playback queue matches the currently active now_playing track."""
    if not isinstance(song_data, dict) or not song_data.get("title"):
        return

    from backend.services.plex import track_time_tracker, playback_active  # noqa: PLC0415
    if not playback_active and not track_time_tracker.is_playing and track_time_tracker.state != "paused":
        return

    try:
        client = get_redis_queue_client()
        raw_q = client.lrange("playback_queue", 0, -1)
        target_id = str(song_data.get("item_id") or "")
        target_title = str(song_data.get("title") or "")
        target_artist = str(song_data.get("artist") or "")

        if not raw_q:
            client.rpush("playback_queue", json.dumps(song_data))
            logger.info("Pushed active track '%s' to index 0 of empty Redis queue.", target_title)
            return

        first_item = json.loads(raw_q[0])
        same_id = bool(target_id and str(first_item.get("item_id")) == target_id)
        same_title = bool(first_item.get("title") == target_title and first_item.get("artist") == target_artist)

        if same_id or same_title:
            return

        logger.info("Queue index 0 ('%s') mismatch with active track ('%s'). Syncing queue.", first_item.get("title"), target_title)

        q_items = [json.loads(x) for x in raw_q]
        match_idx = -1
        for idx, item in enumerate(q_items):
            if (target_id and str(item.get("item_id")) == target_id) or (item.get("title") == target_title and item.get("artist") == target_artist):
                match_idx = idx
                break

        if match_idx > 0:
            for _ in range(match_idx):
                client.lpop("playback_queue")
        else:
            q_items[0] = song_data
            client.delete("playback_queue")
            for item in q_items:
                client.rpush("playback_queue", json.dumps(item))

        # Update 30-minute sliding idle TTL based on track_state (paused vs playing)
        state_val = song_data.get("track_state", "playing") if isinstance(song_data, dict) else "playing"
        update_queue_idle_ttl(state_val)

    except Exception as ex:
        logger.warning("Failed to sync queue with now_playing: %s", ex)


IDLE_QUEUE_EXPIRATION_SECONDS = 1800  # 30 minutes


def update_queue_idle_ttl(track_state: str, idle_seconds: int = IDLE_QUEUE_EXPIRATION_SECONDS):
    """Manage 30-minute idle TTL on Redis queue and now_playing keys.

    - When track_state is 'playing': Remove expiration so queue persists indefinitely during active music.
    - When track_state is 'paused' or 'stopped': Apply a 30-minute sliding TTL so stale queues expire cleanly.
    """
    try:
        q_client = get_redis_queue_client()
        c_client = get_redis_cache_client()

        if track_state == "playing":
            if hasattr(q_client, "persist"):
                q_client.persist("playback_queue")
            if hasattr(c_client, "persist"):
                c_client.persist("now_playing")
            logger.debug("Active music playing: persisted Redis queue and now_playing keys.")
        else:
            if hasattr(q_client, "expire"):
                q_client.expire("playback_queue", idle_seconds)
            if hasattr(c_client, "expire"):
                c_client.expire("now_playing", idle_seconds)
            logger.info("Music state '%s': set 30-minute sliding idle TTL on Redis queue and now_playing.", track_state)
    except Exception as ex:
        logger.warning("Error updating queue idle TTL: %s", ex)


def move_to_top_redis_queue(from_index: int):
    """Move a track at from_index to position 1 (next track after current playing track).

    Returns:
        Dict status message.
    """
    return reorder_redis_queue(from_index, 1)


def cache_data(key, data, ttl: int = CACHE_TTL):
    """Cache data in Redis with custom TTL."""
    try:
        get_redis_cache_client().setex(key, ttl, json.dumps(data))
        logger.info("Cached data under key: %s (TTL: %d)", key, ttl)
        if key == "now_playing" and isinstance(data, dict):
            update_queue_idle_ttl(data.get("track_state", "playing"))
    except Exception as e:
        logger.warning("Redis cache write error for key %s: %s", key, e)


def get_cached_data(key):
    """Retrieve cached data from Redis.

    Returns:
        Cached data from Redis.
    """
    try:
        cached_data = get_redis_cache_client().get(key)
        if cached_data:
            try:
                return json.loads(cached_data)
            except json.JSONDecodeError:
                return None
    except Exception as e:
        logger.warning("Redis cache read error for key %s: %s", key, e)
    return None


def clear_cache(key: str):
    """Clear a specific cache key in Redis.

    Returns:
        A message about a cleared cache.
    """
    try:
        get_redis_cache_client().delete(key)
        logger.info("Cache cleared for key: %s", key)
    except Exception as e:
        logger.warning("Redis cache clear error for key %s: %s", key, e)
    return {"message": f"Cache cleared for key: {key}"}


def add_to_history(track: dict):
    """Add a track dict to playback history list in Redis (capped at 20 items, deduplicated)."""
    try:
        client = get_redis_queue_client()
        track_obj = track

        item_id = track_obj.get("item_id")

        # Deduplicate existing items with matching item_id
        if item_id:
            try:
                raw_history = client.lrange("playback_history", 0, -1)
                for item in raw_history:
                    item_str = item.decode("utf-8") if isinstance(item, bytes) else item
                    if isinstance(item_str, str):
                        try:
                            parsed = json.loads(item_str)
                            if parsed.get("item_id") == item_id:
                                client.lrem("playback_history", 0, item_str)
                        except Exception:
                            pass
            except Exception as d_ex:
                logger.debug("Failed to remove old duplicate from history: %s", d_ex)

        track_json = json.dumps(track_obj)
        client.lpush("playback_history", track_json)
        client.ltrim("playback_history", 0, 19)

        # Log playback event to SQLite database
        try:
            from backend.services.library import log_playback_event_db, validate_track_id, rating_key_to_track_id
            raw_id = track_obj.get("item_id")
            resolved_id = validate_track_id(raw_id) if raw_id else None
            if not resolved_id and raw_id:
                resolved_id = rating_key_to_track_id(raw_id)
            if resolved_id:
                log_playback_event_db(
                    track_id=resolved_id,
                    username=track_obj.get("added_by") or "Guest"
                )
        except Exception as db_log_ex:
            logger.debug("Failed logging playback event to SQLite: %s", db_log_ex)

        artist_name = track_obj.get("artist") or track_obj.get("grandparentTitle")
        if artist_name:
            client.zincrby("stats:artist_play_counts", 1, str(artist_name).lower())
            try:
                from backend.services.library import increment_artist_play_count_db
                increment_artist_play_count_db(str(artist_name))
            except Exception as db_ex:
                logger.debug("Failed to increment SQLite artist play count: %s", db_ex)

        album_title = track_obj.get("album") or track_obj.get("parentTitle")
        if album_title:
            client.zincrby("stats:album_play_counts", 1, str(album_title).lower())
            try:
                from backend.services.library import increment_album_play_count_db
                increment_album_play_count_db(str(album_title))
            except Exception as db_ex:
                logger.debug("Failed to increment SQLite album play count: %s", db_ex)

        update_cached_play_counts(artist_name=artist_name, album_title=album_title)

        logger.info("Added track %s to playback history.", track_obj.get("title", track_obj.get("item_id")))
    except Exception as e:
        logger.warning("Failed to update playback history: %s", e)


def update_cached_play_counts(artist_name: str | None = None, album_title: str | None = None):
    """Mutate cached artist and album records directly in Redis when a track plays."""
    try:
        cache_client = get_redis_cache_client()

        # Update cached all_artists
        if artist_name:
            norm_artist = str(artist_name).strip().lower()
            cached_artists_raw = cache_client.get("all_artists")
            if cached_artists_raw:
                try:
                    artists = json.loads(cached_artists_raw)
                    updated = False
                    for a in artists:
                        if str(a.get("name", "")).strip().lower() == norm_artist:
                            a["play_count"] = (a.get("play_count", 0) or 0) + 1
                            updated = True
                    if updated:
                        cache_client.set("all_artists", json.dumps(artists), keepttl=True)
                except Exception as ex:
                    logger.warning("Failed to update cached all_artists play count: %s", ex)

        # Update cached all_albums
        if album_title:
            norm_album = str(album_title).strip().lower()
            cached_albums_raw = cache_client.get("all_albums")
            if cached_albums_raw:
                try:
                    albums = json.loads(cached_albums_raw)
                    updated = False
                    for alb in albums:
                        if str(alb.get("title", "")).strip().lower() == norm_album:
                            alb["play_count"] = (alb.get("play_count", 0) or 0) + 1
                            updated = True
                    if updated:
                        cache_client.set("all_albums", json.dumps(albums), keepttl=True)
                except Exception as ex:
                    logger.warning("Failed to update cached all_albums play count: %s", ex)
    except Exception as e:
        logger.warning("Error updating cached play counts: %s", e)


def get_playback_history() -> list[dict]:
    """Retrieve recent playback history track objects from Redis (deduplicated by item_id)."""
    try:
        client = get_redis_queue_client()
        raw_history = client.lrange("playback_history", 0, -1)
        res = []
        seen_ids = set()
        for item in raw_history:
            if isinstance(item, bytes):
                item = item.decode("utf-8")
            if isinstance(item, str):
                try:
                    parsed = json.loads(item)
                    tid = parsed.get("item_id")
                    if tid and tid in seen_ids:
                        continue
                    if tid:
                        seen_ids.add(tid)
                    res.append(parsed)
                except Exception:
                    pass
            elif isinstance(item, dict):
                tid = item.get("item_id")
                if tid and tid in seen_ids:
                    continue
                if tid:
                    seen_ids.add(tid)
                res.append(item)
        return res
    except Exception as e:
        logger.warning("Failed to fetch playback history: %s", e)
        return []


def get_playback_history_ids() -> list[int]:
    """Retrieve recent playback history track IDs for autoplay generation."""
    history = get_playback_history()
    ids = []
    for h in history:
        tid = h.get("item_id")
        if tid and str(tid).isdigit():
            ids.append(int(tid))
    return ids


def is_autoplay_enabled() -> bool:
    """Check if autoplay mode is enabled in Redis."""
    try:
        val = get_redis_queue_client().get("autoplay_enabled")
        return val in ("true", b"true")
    except Exception:
        return False


def set_autoplay_enabled(enabled: bool):
    """Set the autoplay mode state in Redis."""
    try:
        get_redis_queue_client().set("autoplay_enabled", "true" if enabled else "false")
    except Exception as e:
        logger.warning("Failed to set autoplay state: %s", e)


def get_artist_play_counts() -> dict[str, int]:
    """Retrieve artist play counts from Redis zset."""
    try:
        client = get_redis_queue_client()
        plays = client.zrange("stats:artist_play_counts", 0, -1, withscores=True)
        res = {}
        for m, s in plays:
            name = m.decode("utf-8") if isinstance(m, bytes) else m
            res[str(name).lower()] = int(s)
        return res
    except Exception as e:
        logger.warning("Failed to fetch artist play counts from Redis: %s", e)
        return {}


def get_album_play_counts() -> dict[str, int]:
    """Retrieve album play counts from Redis zset."""
    try:
        client = get_redis_queue_client()
        plays = client.zrange("stats:album_play_counts", 0, -1, withscores=True)
        res = {}
        for m, s in plays:
            name = m.decode("utf-8") if isinstance(m, bytes) else m
            res[str(name).lower()] = int(s)
        return res
    except Exception as e:
        logger.warning("Failed to fetch album play counts from Redis: %s", e)
        return {}


def get_closing_time_mode() -> bool:
    """Check if closing time mode is enabled in Redis."""
    try:
        val = get_redis_queue_client().get("closing_time_mode")
        return val in ("true", b"true")
    except Exception:
        return False


def set_closing_time_mode(enabled: bool):
    """Set the closing time mode state in Redis."""
    try:
        get_redis_queue_client().set("closing_time_mode", "true" if enabled else "false")
    except Exception as e:
        logger.warning("Failed to set closing time mode state: %s", e)



