## Goal
Investigate and resolve why duplicate artists are displaying in the TuneBox library catalog when only a single Plex server is enabled.

## Assumptions
1. Only one Plex server is enabled (`servers.enabled = 1`).
2. The user is seeing multiple entries for the same artist in the artist list view (`/artists`).
3. Potential root causes to investigate:
   - SQL query join behavior in `get_indexed_artists` (`JOIN artist_sources src` returning duplicate rows per artist when multiple `artist_sources` entries exist without `GROUP BY a.artist_id`).
   - Normalization or GUID differences during Plex indexer synchronization (e.g., `upsert_artist` failing to merge artist entries because of trailing whitespace, punctuation, or Plex GUID variants).
   - Frontend state or request duplication when fetching `/api/music/artists`.

## Plan

### Step 1: Inspect SQLite Database & Audit Single-Server Artist Rows
- **Files**: `backend/scripts/audit_deduplication.py`, `backend/services/library.py`
- **Change**: Run diagnostic SQL queries against `library.db` to compare raw `artists` table rows vs returned `get_indexed_artists()` results, identifying exact duplicate artist names and their source mappings.
- **Verify**: Run `uv run python -c "from backend.services.library import get_db_connection; conn=get_db_connection(); print(conn.execute('SELECT name, COUNT(*) FROM artists GROUP BY norm_name HAVING COUNT(*) > 1').fetchall())"`

### Step 2: Fix Query Duplication in `get_indexed_artists` & `get_indexed_albums`
- **Files**: `backend/services/library.py`
- **Change**: Ensure `GROUP BY a.artist_id` is applied to `get_indexed_artists()` (matching `get_indexed_albums()`) so `JOIN artist_sources` never produces multi-row duplicate returns per artist.
- **Verify**: `uv run python -m pytest backend/tests/test_library_db.py`

### Step 3: Audit Indexer Normalization & Single-Server Deduplication Logic
- **Files**: `backend/services/library.py`, `backend/services/indexer.py`
- **Change**: Verify `_norm()` normalization behavior during `upsert_artist()` and `upsert_album()` to ensure single-server artist variants (e.g., trailing whitespace or case differences) collapse into the same `norm_name` primary key.
- **Verify**: `uv run python -m pytest backend/tests/test_deduplication.py`

### Step 4: End-to-End Verification
- **Files**: Backend test suite & Docker containers
- **Change**: Verify `/api/music/artists` endpoint returns zero duplicates and all tests pass cleanly.
- **Verify**: `uv run python -m pytest` and `npm run build`

## Risks & mitigations
- **Risk**: Adding `GROUP BY a.artist_id` might mask actual unmerged `artists` records stored in SQLite.
- **Mitigation**: Perform a preliminary SQL audit (`SELECT norm_name, COUNT(*) FROM artists GROUP BY norm_name HAVING COUNT(*) > 1`) before modifying query logic.

## Rollback plan
- Revert changes using `git checkout`.
