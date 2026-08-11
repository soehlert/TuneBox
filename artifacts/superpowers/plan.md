# Plan - RatingKey Isolation & Test Suite Expansion

## Goal
Enforce strict separation between internal SQLite primary keys (`artist_id`, `album_id`, `track_id`) and external Plex ratingKeys (`server_artist_id`, `server_album_id`, `server_track_id`), and expand test coverage into domain test files.

## Plan Steps

### Step 1: Update Mock Data Seeder with Realistic Distinct RatingKeys
- **Files**: `backend/services/mock_data.py`
- **Change**: Update mock `server_artist_id`, `server_album_id`, `server_track_id` to realistic distinct 5-digit numeric strings (`"19586"`, `"28401"`, `"34910"`), while internal primary keys remain auto-incrementing integers (`1`, `2`, `3`).
- **Verify**: `uv run python -m pytest`

### Step 2: Add Dedicated ID Isolation Unit Test Suite
- **Files**: `backend/tests/test_id_isolation.py` (NEW)
- **Change**: Add unit tests verifying:
  1. `get_albums_for_artist_db` rejects ratingKey strings and queries strictly `WHERE artist_id = ?`.
  2. `get_art_source_info` translates internal SQL IDs to `server_track_id` ratingKeys without falling back to internal SQL IDs.
  3. Play/queue endpoints accept internal `track_id` strictly.
- **Verify**: `uv run python -m pytest backend/tests/test_id_isolation.py`

### Step 3: Add Domain Tests for Feature Gaps in Existing Test Files
- **Files**: `backend/tests/test_homepage_views.py`, `backend/tests/test_the_sorting.py`, `backend/tests/test_server_resolution.py`
- **Change**:
  1. `test_homepage_views.py`: Assert `top_album_id` in Decades & Genres DB responses and test `prewarm_category_art`.
  2. `test_the_sorting.py`: Assert `plays_asc` (Least Played) sorting for artists and albums.
  3. `test_server_resolution.py`: Assert `servers.enabled = 0` hides server-exclusive items while preserving shared items.
- **Verify**: `uv run python -m pytest backend/tests/test_homepage_views.py backend/tests/test_the_sorting.py backend/tests/test_server_resolution.py`

### Step 4: Refactor Library Services (`library.py`)
- **Files**: `backend/services/library.py`
- **Change**: Remove `COALESCE(rating_key, internal_id)` fallbacks from `get_art_source_info`. Update `get_tracks_for_album_db` to set `item_id = r["track_id"]`.
- **Verify**: `uv run python -m pytest backend/tests/test_library_db.py backend/tests/test_id_isolation.py`

### Step 5: Refactor Plex Translation & Routers (`plex.py` & `music.py`)
- **Files**: `backend/services/plex.py`, `backend/routers/music.py`
- **Change**: Translate internal SQL IDs to server ratingKeys strictly via source tables (`track_sources`, `album_sources`, `artist_sources`).
- **Verify**: `uv run python -m pytest backend/tests/test_plex.py backend/tests/test_track_rating.py`

### Step 6: Refactor Frontend Track Payload Selection (`TrackList.tsx`)
- **Files**: `frontend/src/components/TrackList.tsx`
- **Change**: Use `track.track_id` (internal SQL ID) strictly for all frontend play/queue actions.
- **Verify**: `docker compose build --no-cache frontend && docker compose up -d`

### Step 7: Full Suite Verification & Docker Deployment
- **Files**: N/A
- **Change**: Run full backend test suite and rebuild Docker stack.
- **Verify**: `uv run python -m pytest` and `docker compose up -d --build`
