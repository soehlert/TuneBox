# Finish Summary - RatingKey Isolation & Test Suite Expansion

## Verification Results
- **Pytest Test Suite**: Executed full backend test suite (`uv run python -m pytest`).
  - **Result**: **143 passed in 16.92s** (up from 137 passed).
- **Docker Compose Stack**: Rebuilt and restarted (`docker compose up -d --build`).
  - **Result**: `tunebox-backend-1` and `tunebox-frontend-1` recreated and running cleanly.

---

## Summary of Changes
1. **Mock Data Seeder (`mock_data.py`)**:
   - Updated `server_artist_id`, `server_album_id`, `server_track_id` in `mock_data.py` to realistic distinct 5-digit numeric strings (`19587+`, `28402+`, `34911+`).
   - Ensures internal SQLite primary keys (`1`, `2`, `3`...) never numerically collide with mock Plex server ratingKeys in test data.

2. **Dedicated ID Isolation Test Suite (`test_id_isolation.py`)**:
   - Added unit tests enforcing `GEMINI.md` testing standards:
     - `test_get_albums_for_artist_db_queries_strictly_by_internal_artist_id`: Verifies DB queries filter strictly `WHERE artist_id = ?`.
     - `test_get_art_source_info_translates_sql_id_to_server_rating_key`: Verifies `get_art_source_info` translates internal SQL IDs to `server_track_id` ratingKeys without falling back to internal SQL IDs.
     - `test_get_tracks_for_album_db_exposes_internal_track_id`: Verifies API exposes internal `track_id`.

3. **Domain Test Suite Expansion**:
   - **`test_homepage_views.py`**: Added `test_decades_and_genres_include_top_album_id_and_prewarm` verifying `top_album_id` extraction and category art pre-warming.
   - **`test_the_sorting.py`**: Added `test_get_indexed_artists_and_albums_plays_sorting` verifying `plays_asc` (Least Played) sorting for artists and albums, and updated `library.py` SQL ORDER BY clauses.
   - **`test_server_resolution.py`**: Added `test_disabled_server_filters_exclusive_catalog_items` verifying `servers.enabled = 0` isolation.

4. **Service & Router Refactoring (`library.py`, `plex.py`, `music.py`, `TrackList.tsx`)**:
   - Removed `COALESCE(rating_key, internal_id)` fallbacks in `get_all_art_sources` and `rate_album_in_plex`.
   - Updated `music.py` and `TrackList.tsx` to prefer internal `track_id` over `server_track_id` when processing track payloads.

---

## Manual Verification Steps
1. Open TuneBox in your web browser with cache disabled (`Cmd + Shift + R`).
2. Click on **“Weird Al” Yankovic** in the Artists view.
   - Verify header says **“Weird Al” Yankovic** and lists only Weird Al's 2 albums (*Bad Hair Day*, *The Essential “Weird Al” Yankovic*).
3. Check **Decades** & **Genres** views.
   - Verify cards render top album cover art.
4. Toggle **Most Played / Least Played** on Artists and Albums views.
   - Verify items re-sort cleanly in ascending vs descending play counts.
