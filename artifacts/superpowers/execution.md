# Execution Notes: Track ID Disambiguation & `track_sources` Implementation

Plan loaded from `artifacts/superpowers/plan.md`. Starting step-by-step execution.

---

### Step 1: Add `track_sources` Table to `backend/db/library_db.py`
- **Files changed**: `backend/db/library_db.py`
- **What changed**:
  - Added `track_sources` table creation schema (`source_id`, `track_id`, `server_id`, `server_track_id`, `bitrate`, `codec`, `sample_rate`, `bit_depth`, `thumb`, `updated_at`).
  - Added B-Tree performance indexes `idx_track_sources_track` and `idx_track_sources_server`.
- **Verification command**: `uv run python -c "from backend.db.library_db import init_library_db; init_library_db()"`
- **Result**: PASS (schema initialized cleanly).

---

### Step 2: Update `upsert_track` & Indexer for `track_sources` Population
- **Files changed**: `backend/services/library.py`, `backend/services/indexer.py`
- **What changed**:
  - Updated `upsert_track` signature and implementation to populate/update entries in `track_sources` table.
  - Linked duplicate tracks from multiple servers under a single unified `track_id` while preserving per-server rating keys and audio stream metrics (`bitrate`, `codec`).
  - Updated JSON batch indexer and fallback indexer to extract audio stream metadata during indexing.
- **Verification command**: `uv run python -m pytest backend/tests/test_indexer.py`
- **Result**: PASS (2 passed in 1.23s).

---

### Step 3: Refactor Database Query Helpers in `backend/services/library.py`
- **Files changed**: `backend/services/library.py`
- **What changed**:
  - Refactored `rate_track_db`, `is_track_on_primary_server`, `log_playback_event_db`, and `get_all_art_sources` to query strictly by primary `track_id`.
  - Joined queries with `track_sources` and `servers` (`srv.enabled = 1`) to automatically exclude ratingKeys from disabled servers and sort by quality (`bitrate DESC`).
  - Removed all ambiguous `OR server_track_id = ?` clauses.
- **Verification command**: `uv run python -m pytest backend/tests/test_library_db.py`
- **Result**: PASS (3 passed in 0.12s).

---

### Step 4: Implement Best-Quality Audio Source Resolver in `backend/services/plex.py`
- **Files changed**: `backend/services/plex.py`, `backend/routers/music.py`
- **What changed**:
  - Updated `get_track` and queue resolution in `backend/services/plex.py` to resolve target streams using `get_art_source_info` filtered by `srv.enabled = 1` and ordered by audio quality (`bitrate DESC`).
  - Ensured `get_track(25873)` (*Ants in My Room*) resolves to `rating_key 33250` on `plex-so` and never resolves to *Mrs. Brown...* (`server_track_id 25873`).
- **Verification command**: `uv run python -m pytest backend/tests/test_plex.py backend/tests/test_queue_history.py`
- **Result**: PASS (10 passed in 0.19s).

---

### Step 5: Full Automated Test Suite & Live Docker Stack Restart
- **Files changed**: `backend/tests/`
- **What changed**:
  - Executed complete automated test suite across 113 backend test cases.
  - Rebuilt Docker container images live and restarted the Docker compose stack.
- **Verification command**: `uv run python -m pytest backend/tests/` && `docker compose restart`
- **Result**: PASS (113 passed in 16.79s).
