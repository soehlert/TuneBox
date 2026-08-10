# Superpowers Implementation Plan: Missing Artwork Inspector Modal

## Goal
Make the "Missing Artist Art" and "Missing Album Art" metric cards in Settings clickable to open an interactive modal (`MissingArtworkModal`) listing all primary server items missing artwork, with search filtering, a "Copy Name" button, and 1-click artwork re-syncing from Plex.

## Assumptions
- Missing artwork inspection is strictly scoped to items on the user's Primary/Admin Plex server (`srv.is_primary = 1`).
- Items lacking artwork have `(thumb IS NULL OR thumb = '' OR thumb LIKE '/api/music/%')`.
- Forced artwork re-sync queries the primary server's Plex API for updated thumbnail URLs and clears Redis art cache.

## Plan

### Step 1: Backend API Endpoints for Missing Artwork & Re-sync
- **Files**: `backend/services/library.py`, `backend/routers/stats.py`, `backend/tests/test_stats.py`
- **Change**:
  - Implement `get_missing_artwork_items(item_type: str, query: str | None = None, db_path=None)` in `backend/services/library.py`. Returns items on primary server missing artwork.
  - Add `GET /api/stats/missing-artwork?type=artist|album&query=...` in `backend/routers/stats.py`.
  - Add `POST /api/stats/refetch-artwork` (`type=artist|album`, `id=123`) in `backend/routers/stats.py` to trigger Plex artwork re-fetch and Redis cache purge.
  - Add unit tests in `backend/tests/test_stats.py`.
- **Verify**: `uv run python -m pytest backend/tests/test_stats.py`

### Step 2: Create `MissingArtworkModal` Component
- **Files**: `frontend/src/components/MissingArtworkModal.tsx`, `frontend/src/components/MissingArtworkModal.css`
- **Change**:
  - Build modal accepting `type: "artist" | "album"` and `onClose: () => void`.
  - Features:
    - Search input to filter missing items by title/artist.
    - Item row listing title and artist name.
    - **"Copy Name" button**: copies item title to clipboard with 2s checkmark feedback.
    - **"Re-Sync Artwork" button**: calls `/api/stats/refetch-artwork`, showing inline spinner and refreshing item list on success.
- **Verify**: `npm run build` inside `frontend/`

### Step 3: Wire Metric Card Click Handlers in `SettingsModal`
- **Files**: `frontend/src/App.tsx`
- **Change**:
  - Add state `missingArtModalType: "artist" | "album" | null`.
  - Make **Missing Artist Art** and **Missing Album Art** metric cards in Section 5 clickable (`cursor: "pointer"`, hover glow effect).
  - Clicking opens `MissingArtworkModal`.
- **Verify**: `npm run build` inside `frontend/`

### Step 4: Verification & Live Docker Rebuild
- **Files**: None
- **Change**: Run full test suite, rebuild Docker images, restart stack.
- **Verify**:
  - `uv run python -m pytest backend/tests/`
  - `docker compose up -d --build`
  - `docker compose restart`

## Risks & mitigations
- **Large Missing Item Counts**: If hundreds of items lack artwork, returning all items could slow down rendering.
  - *Mitigation*: Cap initial endpoint response to 200 items sorted alphabetically, with search filtering on the backend.

## Rollback plan
If issues arise, revert `backend/services/library.py`, `backend/routers/stats.py`, and `frontend/src/App.tsx` to commit `e514eba`.
