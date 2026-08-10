## Step 1: Backend API Endpoints for Missing Artwork & Re-sync
- **Files**:
  - `backend/services/library.py`
  - `backend/routers/stats.py`
  - `backend/tests/test_stats.py`
- **What Changed**:
  - Implemented `get_missing_artwork_items()` and `refetch_item_artwork()` in `backend/services/library.py`.
  - Exposed `GET /api/stats/missing-artwork` and `POST /api/stats/refetch-artwork` endpoints in `backend/routers/stats.py`.
  - Added unit test `test_get_missing_artwork_endpoint` in `backend/tests/test_stats.py`.
- **Verification Command**: `uv run python -m pytest backend/tests/test_stats.py`
- **Result**: PASSED (3 passed in 0.25s)

## Step 2 & 3: MissingArtworkModal Component & Metric Card Click Handlers
- **Files**:
  - `frontend/src/components/MissingArtworkModal.tsx`
  - `frontend/src/components/MissingArtworkModal.css`
  - `frontend/src/utils.ts`
  - `frontend/src/App.tsx`
- **What Changed**:
  - Built `MissingArtworkModal` React component with live search filtering, "Copy Name" button with checkmark feedback, and "Re-Sync Artwork" button calling `/api/stats/refetch-artwork`.
  - Exported `getApiUrl` utility in `frontend/src/utils.ts`.
  - Made Missing Artist Art and Missing Album Art cards clickable (`cursor: "pointer"`, hover glow effect) opening `MissingArtworkModal`.
- **Verification Command**: `npm run build` inside `frontend/`
- **Result**: PASSED (built in 865ms)
