## Step 1: Add Backend Library Health Statistics Query & Endpoint
- **Files**:
  - `backend/services/library.py`
  - `backend/routers/stats.py`
  - `backend/tests/test_stats.py`
- **What Changed**:
  - Implemented `get_library_health_stats(db_path=None)` in `backend/services/library.py` returning overall totals, missing artwork counts, and per-server artist/album/track breakdowns.
  - Added `@router.get("/library")` endpoint in `backend/routers/stats.py`.
  - Created unit test suite `backend/tests/test_stats.py`.
- **Verification Command**: `uv run python -m pytest backend/tests/test_stats.py`
- **Result**: PASSED (2 passed in 0.16s)

## Step 2: Add Expandable "Library Statistics & Health" Section in Settings Modal
- **Files**:
  - `frontend/src/App.tsx`
- **What Changed**:
  - Added `sectionsOpen.health` accordion state and `fetchHealthStats()` helper.
  - Rendered Section 5: **📊 Library Statistics & Health** inside `SettingsModal`.
  - Added total catalog count card, missing artist/album artwork metric cards, and per-server indexed catalog breakdown table.
- **Verification Command**: `npm run build` in `frontend/`
- **Result**: PASSED (built in 1.01s)
