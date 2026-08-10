# Implementation Plan: Expandable Library Statistics & Missing Artwork Inspector

Add an expandable "Library Statistics & Health" section inside the Settings Modal displaying missing artwork counters and per-server catalog breakdowns.

## Goal
Provide instant (< 10ms), clear visibility into catalog counts (Artists, Albums, Tracks), missing artwork counts (Artists, Albums), and per-server indexed item counts directly inside the Settings Modal.

## Assumptions
- SQLite database `library.db` contains authoritative `artists`, `albums`, `tracks`, `artist_sources`, `album_sources`, `track_sources`, and `servers`.
- Stats queries run as lightweight SQLite `COUNT(*)` aggregations taking < 5ms.
- Settings Modal UI will render an expandable accordion section.

---

## Plan

### Step 1: Add Backend Library Health Statistics Query & Endpoint
- **Files**:
  - `backend/services/library.py`
  - `backend/routers/stats.py`
  - `backend/tests/test_stats.py`
- **Change**:
  - Implement `get_library_health_stats(db_path=None)` in `backend/services/library.py` returning `total_artists`, `total_albums`, `total_tracks`, `missing_artist_art`, `missing_album_art`, and `servers` list (with per-server artist, album, and track counts).
  - Add `@router.get("/library")` endpoint in `backend/routers/stats.py`.
  - Write unit test `test_get_library_health_stats` in `backend/tests/test_stats.py`.
- **Verify**:
  - `uv run pytest backend/tests/test_stats.py`

### Step 2: Add Expandable "Library Statistics & Health" Section in Settings Modal
- **Files**:
  - `frontend/src/components/SettingsModal.tsx`
- **Change**:
  - Add collapsible accordion UI section with an analytics icon ("Library Statistics & Health").
  - Fetch `/api/stats/library` when accordion is expanded.
  - Render metric cards for Total Catalog Summary and Missing Artwork counters (Artists & Albums).
  - Render a clean per-server breakdown table showing server name, enabled status, primary badge, artist count, album count, and track count.
- **Verify**:
  - `cd frontend && npm run build`

### Step 3: Live Docker Rebuild & Manual Verification Instructions
- **Files**: None
- **Change**:
  - Run `docker compose up -d --build` and `docker compose restart`.
- **Verify**:
  - Run full test suite: `uv run pytest backend/tests/`.
  - Manual verification instructions provided to the user.

---

## Risks & mitigations
- **Risk**: Database lock during active indexing when fetching stats.
- **Mitigation**: Use read-only SQLite transaction connections (`get_db_connection()`) with WAL mode.

## Rollback plan
- Revert commits on feature branch with `git reset --hard HEAD~1`.
- Restart stack with `docker compose restart`.
