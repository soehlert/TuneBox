# Execution Finish Summary: Missing Artwork Inspector Modal

## Summary of Changes
1. **Backend Service & API Endpoints**:
   - `backend/services/library.py`: Implemented `get_missing_artwork_items()` and `refetch_item_artwork()`.
   - `backend/routers/stats.py`: Added `GET /api/stats/missing-artwork` and `POST /api/stats/refetch-artwork` endpoints.
   - `backend/tests/test_stats.py`: Created unit test verifying endpoints (**117 passing tests**).
2. **Frontend UI Modal**:
   - Created `frontend/src/components/MissingArtworkModal.tsx` and `MissingArtworkModal.css`.
   - Exported `getApiUrl` helper in `frontend/src/utils.ts`.
   - Made Missing Artist Art and Missing Album Art metric cards in Settings Modal clickable (`cursor: "pointer"`, hover glow).
   - Modal supports instant title search filtering, a **"Copy Name"** button with 2s checkmark feedback, and a **"Re-Sync Artwork"** button that re-syncs thumbnail URLs from Plex.

## Verification Commands & Results
- `uv run python -m pytest backend/tests/test_stats.py` -> PASSED (3 passed in 0.25s)
- `cd frontend && npm run build` -> PASSED (built in 865ms)
- `uv run python -m pytest backend/tests/` -> PASSED (117 passed in 17.56s)
- `docker compose up -d --build` & `docker compose restart` -> PASSED (containers active)

## Review Pass
- **Blocker**: None
- **Major**: None
- **Minor**: None
- **Nit**: None

## Manual Verification Steps
1. Open TuneBox in your browser (`http://localhost:3000`).
2. Open Settings (**⚙️**) -> Expand **📊 Library Statistics & Health**.
3. Click either the **Missing Artist Art** or **Missing Album Art** card.
4. Verify the `MissingArtworkModal` opens with items sourced from your primary server.
5. Test the search filter input.
6. Click **Copy Name** to copy the title to your clipboard.
7. Click **Re-Sync** to trigger a targeted Plex artwork re-sync.
