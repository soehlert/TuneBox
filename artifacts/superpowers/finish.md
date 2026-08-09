# Finish Summary: Track ID Disambiguation & `track_sources` Implementation

All 5 implementation plan steps have been executed and verified.

---

## 1. Summary of Changes

### 🗄️ Database Migration (`track_sources` Table)
- Added `track_sources` schema (`source_id`, `track_id`, `server_id`, `server_track_id`, `bitrate`, `codec`, `sample_rate`, `bit_depth`, `thumb`, `updated_at`) with performance B-Tree indexes in `backend/db/library_db.py`.
- Multi-server library deduplication automatically maps all copies of a song across enabled servers to a single, unified TuneBox `track_id`.

### ⚡ Indexer & Service Updates
- Updated `upsert_track` signature in `backend/services/library.py` and JSON batch indexers in `backend/services/indexer.py` to extract and populate per-server rating keys and audio stream quality metrics (`bitrate`, `codec`).

### 🎯 Strict `track_id` Query Resolution
- Refactored `rate_track_db`, `is_track_on_primary_server`, `log_playback_event_db`, and `get_all_art_sources` to strictly query `WHERE t.track_id = ?`.
- Removed all ambiguous `OR server_track_id = ?` SQL clauses, completely eliminating ID collisions between internal `track_id` values and Plex ratingKeys.

### 🎧 Enabled Server & Best-Quality Audio Selection
- Updated `get_track` and stream selection in `backend/services/plex.py` to query `track_sources` joined with `servers WHERE srv.enabled = 1`, ordering available streams by audio quality (`bitrate DESC`) and local server preference.
- Disabled servers are automatically excluded from stream selection (`srv.enabled = 1`).

---

## 2. Automated Test Verification

| Test Suite | Command | Result |
| :--- | :--- | :--- |
| **Database Schema** | `uv run python -c "from backend.db.library_db import init_library_db; init_library_db()"` | PASS |
| **Indexer Integration** | `uv run python -m pytest backend/tests/test_indexer.py` | PASS (2 passed) |
| **Library DB Queries** | `uv run python -m pytest backend/tests/test_library_db.py` | PASS (3 passed) |
| **Plex & Queue Resolution** | `uv run python -m pytest backend/tests/test_plex.py backend/tests/test_queue_history.py` | PASS (10 passed) |
| **Full Pytest Suite** | `uv run python -m pytest backend/tests/` | **PASS (113 passed in 16.79s)** |

---

## 3. Manual Verification Steps

1. Open TuneBox at `http://localhost:3000`.
2. Go to the album view for **Ants in My Room** by Carter Vail (`track_id = 25873`).
3. Click **Add to Queue**.
4. **Verify**: The Up Next queue panel displays **Ants in My Room** by Carter Vail, never *Mrs. Brown...* (`server_track_id = 25873`).
5. Open Settings, toggle servers ON/OFF, and save.
6. **Verify**: Playing tracks always selects streams from enabled servers, picking high-bitrate lossless audio when available.
