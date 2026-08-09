# Implementation Plan: Track ID Disambiguation & `track_sources` Multi-Server Schema

Fix track resolution so that adding a song to the queue, playing a song, or requesting track details always selects the exact intended track (`track_id`) and never resolves to an unintended track whose Plex ratingKey (`server_track_id`) collides with SQLite's internal autoincrement `track_id`.

## Goal
Implement a dedicated `track_sources` table linking each unified track to its per-server rating keys and audio quality metrics. Refactor backend query services to strictly consume TuneBox's primary `track_id` and resolve streams using an enabled-server, best-quality audio selection algorithm.

## Assumptions
- No backwards-compatibility hacks will be used; TuneBox internal `track_id` is the single source of truth across all API endpoints and frontend components.
- The `library.db` SQLite database can be re-indexed cleanly in ~25 seconds.
- Multi-server library deduplication links multiple server sources to a single `track_id`.

## Plan

### Step 1: Add `track_sources` Table to `backend/db/library_db.py`
- **Files**: `backend/db/library_db.py`
- **Change**: Add `track_sources` schema (`source_id`, `track_id`, `server_id`, `server_track_id`, `bitrate`, `codec`, `sample_rate`, `bit_depth`, `updated_at`) with indexes on `(track_id, server_id)` and `(server_id)`.
- **Verify**: `uv run python -c "from backend.db.library_db import init_db; init_db()"`

### Step 2: Update `upsert_track` & Indexer for `track_sources` Population
- **Files**: `backend/services/library.py`, `backend/services/indexer.py`
- **Change**: Update `upsert_track` to insert/update rows in `track_sources` with per-server rating keys (`server_track_id`), bitrates, and audio codecs. Update `fetch_section_json_batched` to include audio stream metadata.
- **Verify**: `uv run python -m pytest backend/tests/test_indexer.py`

### Step 3: Refactor Database Query Helpers in `backend/services/library.py`
- **Files**: `backend/services/library.py`
- **Change**: Refactor `get_track_details`, `get_all_art_sources`, `upsert_track_rating`, and `get_album_tracks` to strictly query `WHERE t.track_id = ?` joined with `track_sources ts JOIN servers srv ON srv.server_id = ts.server_id WHERE srv.enabled = 1`. Remove all ambiguous `OR server_track_id = ?` clauses.
- **Verify**: `uv run python -m pytest backend/tests/test_library_db.py`

### Step 4: Implement Best-Quality Audio Source Resolver in `backend/services/plex.py`
- **Files**: `backend/services/plex.py`, `backend/routers/music.py`
- **Change**: Update `play_track` and `/api/music/queue/add` to query `track_sources` for enabled servers (`srv.enabled = 1`), ordered by `(CASE WHEN srv.is_primary = 1 THEN 0 ELSE 1 END), bitrate DESC`. Select the highest-quality available source stream for playback.
- **Verify**: `uv run python -m pytest backend/tests/test_plex.py backend/tests/test_queue_history.py`

### Step 5: Full Test Suite Verification & Docker Stack Restart
- **Files**: `backend/tests/`
- **Change**: Run the complete automated test suite to ensure zero regressions, rebuild Docker images, and restart the Docker compose stack live.
- **Verify**: `uv run python -m pytest backend/tests/` and `docker compose restart`.

## Risks & mitigations
- **Risk**: Existing tests might pass raw ratingKey strings to `get_track_details`.
- **Mitigation**: Update test mocks to populate `track_sources` and use standard `track_id` integers.

## Rollback plan
- If issues arise, switch back to branch `main` (`git checkout main`) and restart the Docker stack (`docker compose restart`).
