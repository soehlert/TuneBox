import os
import sqlite3
import logging
from backend.services.redis import get_redis_queue_client

logger = logging.getLogger(__name__)

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "stats.db")

def init_db():
    """Initialize the SQLite database schema for all-time statistics."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS adds (
                username TEXT PRIMARY KEY,
                count INTEGER DEFAULT 0
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS skips_cast (
                username TEXT PRIMARY KEY,
                count INTEGER DEFAULT 0
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS skips_received (
                username TEXT PRIMARY KEY,
                count INTEGER DEFAULT 0
            )
            """
        )
        conn.commit()
        conn.close()
        logger.info("Stats SQLite database initialized successfully at %s", DB_PATH)
    except Exception as e:
        logger.exception("Failed to initialize stats database: %s", e)


def increment_adds(username: str):
    """Increment song addition counts for a username in both SQLite and Redis."""
    if not username or username.lower() == "admin":
        return
    
    # 1. Update SQLite (All-Time)
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO adds (username, count) VALUES (?, 1) ON CONFLICT(username) DO UPDATE SET count = count + 1",
            (username,),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.warning("Failed to increment SQLite adds for %s: %s", username, e)

    # 2. Update Redis (Session)
    try:
        client = get_redis_queue_client()
        client.zincrby("stats:adds:session", 1, username)
    except Exception as e:
        logger.warning("Failed to increment Redis adds for %s: %s", username, e)


def increment_skips_cast(username: str):
    """Increment cast skips counts for a username in both SQLite and Redis."""
    if not username or username.lower() == "admin":
        return

    # 1. Update SQLite (All-Time)
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO skips_cast (username, count) VALUES (?, 1) ON CONFLICT(username) DO UPDATE SET count = count + 1",
            (username,),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.warning("Failed to increment SQLite skips_cast for %s: %s", username, e)

    # 2. Update Redis (Session)
    try:
        client = get_redis_queue_client()
        client.zincrby("stats:skips_cast:session", 1, username)
    except Exception as e:
        logger.warning("Failed to increment Redis skips_cast for %s: %s", username, e)


def increment_skips_received(username: str):
    """Increment skips received counts for a username in both SQLite and Redis."""
    if not username or username.lower() == "admin":
        return

    # 1. Update SQLite (All-Time)
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO skips_received (username, count) VALUES (?, 1) ON CONFLICT(username) DO UPDATE SET count = count + 1",
            (username,),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.warning("Failed to increment SQLite skips_received for %s: %s", username, e)

    # 2. Update Redis (Session)
    try:
        client = get_redis_queue_client()
        client.zincrby("stats:skips_received:session", 1, username)
    except Exception as e:
        logger.warning("Failed to increment Redis skips_received for %s: %s", username, e)


def clear_session_stats():
    """Clear all session metrics in Redis."""
    try:
        client = get_redis_queue_client()
        client.delete("stats:adds:session", "stats:skips_cast:session", "stats:skips_received:session")
        logger.info("Session stats have been cleared in Redis.")
    except Exception as e:
        logger.warning("Failed to clear session stats in Redis: %s", e)


def get_session_stats() -> dict:
    """Fetch sorted session leaderboard rankings from Redis."""
    stats = {"adds": [], "skips_cast": [], "skips_received": []}
    try:
        client = get_redis_queue_client()
        
        # Redis returns a list of tuples (member, score)
        adds = client.zrevrange("stats:adds:session", 0, -1, withscores=True)
        stats["adds"] = [{"username": m.decode("utf-8") if isinstance(m, bytes) else m, "count": int(s)} for m, s in adds]
        
        skips_cast = client.zrevrange("stats:skips_cast:session", 0, -1, withscores=True)
        stats["skips_cast"] = [{"username": m.decode("utf-8") if isinstance(m, bytes) else m, "count": int(s)} for m, s in skips_cast]
        
        skips_received = client.zrevrange("stats:skips_received:session", 0, -1, withscores=True)
        stats["skips_received"] = [{"username": m.decode("utf-8") if isinstance(m, bytes) else m, "count": int(s)} for m, s in skips_received]
    except Exception as e:
        logger.warning("Failed to fetch Redis session stats: %s", e)
    
    return stats


def get_alltime_stats() -> dict:
    """Fetch sorted all-time leaderboard rankings from SQLite."""
    stats = {"adds": [], "skips_cast": [], "skips_received": []}
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute("SELECT username, count FROM adds ORDER BY count DESC")
        stats["adds"] = [{"username": row[0], "count": row[1]} for row in cursor.fetchall()]
        
        cursor.execute("SELECT username, count FROM skips_cast ORDER BY count DESC")
        stats["skips_cast"] = [{"username": row[0], "count": row[1]} for row in cursor.fetchall()]
        
        cursor.execute("SELECT username, count FROM skips_received ORDER BY count DESC")
        stats["skips_received"] = [{"username": row[0], "count": row[1]} for row in cursor.fetchall()]
        
        conn.close()
    except Exception as e:
        logger.warning("Failed to fetch SQLite all-time stats: %s", e)
        
    return stats

# Initialize database on module import
init_db()
