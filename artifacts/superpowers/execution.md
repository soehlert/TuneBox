# Execution Log: Genre Sort Pills & Artwork Speed Optimizations

## Step 1: Backend Window Function SQL Query & 24h HTTP Art Caching
- **Files**: `backend/services/library.py`, `backend/routers/music.py`
- **Changes**:
  - Replaced correlated subquery in `get_all_genres_db()` with single-pass SQLite Window Function (`ROW_NUMBER() OVER`).
  - Increased artwork Cache-Control header to 24 hours (`max-age=86400`).
- **Verification**: `uv run python -m pytest backend/tests/test_homepage_views.py` -> PASSED (8 passed in 0.47s)
- **Result**: PASSED

## Step 2: Frontend Dual Sort Pills & Image Lazy Loading
- **Files**: `frontend/src/components/BrowseViews.tsx`
- **Changes**:
  - Replaced dropdown select with dual `.sort-pill-btn` buttons matching Artist page (`A-Z`/`Z-A` & `Most Albums`/`Least Albums`).
  - Added `loading="lazy"` to `<FallbackImage>` in `GenresGridView` cards.
- **Verification**: `cd frontend && npm run build` -> PASSED (built in 1.01s)
- **Result**: PASSED
