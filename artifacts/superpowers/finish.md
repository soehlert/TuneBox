# Superpowers Finish Summary: Single-Server Artist Deduplication Fix

## Root Cause
- Prior indexing passes populated SQLite `artists` and `albums` tables using an older `_norm()` function that preserved spaces (e.g. `norm_name = "aaron neville"`).
- When `_norm()` was updated to strip non-alphanumeric characters (`norm_name = "aaronneville"`), `ON CONFLICT(norm_name)` failed to match old space-containing keys, inserting 642 duplicate artist entries (2,053 total rows instead of 1,411 unique artists) and 1,781 duplicate album entries.

## Key Changes
- **`backend/services/library.py`**:
  - Implemented `clean_library_deduplication()` to consolidate duplicate artists and albums, reassigning `artist_sources`, `album_sources`, `albums`, and `tracks` foreign keys, combining play counts, and updating `norm_name` / `norm_title_artist` keys.
  - Added `GROUP BY a.artist_id` to `get_indexed_artists()` to guarantee 1 row per unique artist ID.
- **`backend/main.py`**:
  - Added automatic execution of `clean_library_deduplication()` inside the FastAPI application startup `lifespan`.
- **`backend/tests/test_library_db.py`**:
  - Added unit test `test_clean_library_deduplication()` verifying single-server duplicate consolidation.

## Verification
- **Automated Tests**: Passed 110/110 tests (`uv run python -m pytest`).
- **Database Cleanup Result**:
  - `removed_artists`: 642 duplicate rows removed (consolidated down to 1,411 unique artists).
  - `removed_albums`: 1,781 duplicate rows removed (consolidated down to 3,040 unique albums).
  - Remaining `norm_name` duplicates: 0.
- **Docker Stack**: Rebuilt and started (`docker compose up -d --build`).

## Follow-ups / Manual Validation
- Reload the TuneBox web interface (`/artists`) to verify the artist catalog lists exactly 1,411 clean, non-duplicated artists.
