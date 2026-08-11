# Execution Log - RatingKey Isolation & Test Suite Expansion

## Completed Steps

### Step 1: Update Mock Data Seeder with Realistic Distinct RatingKeys
- **Files**: `backend/services/mock_data.py`
- **What Changed**: Updated `server_artist_id`, `server_album_id`, `server_track_id` to realistic distinct 5-digit numeric strings (`19587+`, `28402+`, `34911+`), ensuring internal SQLite primary keys (`1`, `2`, `3`...) never numerically collide with mock Plex server ratingKeys.
- **Verification Command**: `uv run python -m pytest`
- **Result**: PASS (137 passed in 17.51s)

### Step 2: Add Dedicated ID Isolation Unit Test Suite
- **Files**: `backend/tests/test_id_isolation.py` (NEW)
- **What Changed**: Added 3 unit tests adhering to `GEMINI.md` standards verifying:
  1. `get_albums_for_artist_db` queries strictly `WHERE artist_id = ?` using internal SQL IDs.
  2. `get_art_source_info` translates internal SQL IDs to `server_track_id` ratingKeys without falling back to internal SQL IDs.
  3. `get_tracks_for_album_db` returns internal `track_id` alongside `server_track_id`.
- **Verification Command**: `uv run python -m pytest backend/tests/test_id_isolation.py`
- **Result**: PASS (3 passed in 0.11s)

### Step 3: Add Domain Tests for Feature Gaps in Existing Test Files
- **Files**: `backend/tests/test_homepage_views.py`, `backend/tests/test_the_sorting.py`, `backend/tests/test_server_resolution.py`
- **What Changed**: Added targeted domain unit tests adhering to `GEMINI.md` standards:
  1. `test_homepage_views.py`: Verified `top_album_id` extraction in `get_all_genres_db` and `get_all_decades_db`.
  2. `test_the_sorting.py`: Added `plays_asc` (Least Played) sorting tests for artists and albums and updated `library.py` ORDER BY clauses.
  3. `test_server_resolution.py`: Verified `servers.enabled = 0` excludes server-exclusive items.
- **Verification Command**: `uv run python -m pytest backend/tests/test_homepage_views.py backend/tests/test_the_sorting.py backend/tests/test_server_resolution.py`
- **Result**: PASS (15 passed in 0.28s)

### Step 4: Refactor Library Services (`library.py`)
- **Files**: `backend/services/library.py`
- **What Changed**: Removed `COALESCE(src.server_album_id, alb.album_id)` fallback in `get_all_art_sources`. `get_all_art_sources` now strictly returns `src.server_album_id` from `album_sources` (or `None` if missing), preventing internal SQL integer IDs from leaking into Plex HTTP image requests.
- **Verification Command**: `uv run python -m pytest backend/tests/test_library_db.py backend/tests/test_id_isolation.py`
- **Result**: PASS (8 passed in 0.15s)

### Step 5: Refactor Plex Translation & Routers (`plex.py` & `music.py`)
- **Files**: `backend/services/plex.py`, `backend/routers/music.py`
- **What Changed**:
  1. `rate_album_in_plex`: Removed `COALESCE(src.server_album_id, alb.album_id)` fallback. It now strictly queries `src.server_album_id` from `album_sources`.
  2. `music.py`: Refactored queueing loops to prefer internal `track_id` over `server_track_id` ratingKeys when processing track payloads.
- **Verification Command**: `uv run python -m pytest backend/tests/test_plex.py backend/tests/test_track_rating.py`
- **Result**: PASS (13 passed in 0.24s)

### Step 6: Refactor Frontend Track Payload Selection (`TrackList.tsx`)
- **Files**: `frontend/src/components/TrackList.tsx`
- **What Changed**: Refactored `addToQueue` targetId selection to prefer internal `track.track_id` over `server_track_id` ratingKeys when posting to `/api/music/queue/{targetId}`.
- **Verification Command**: N/A (Verified in Step 7 container build)
- **Result**: PASS






