# Implementation Plan: Genre Sort Pills & Artwork Speed Optimizations

## Goal
1. Replace single Genre sort dropdown with dual `.sort-pill-btn` buttons matching the Artist page (A-Z toggle & Most/Least Albums toggle).
2. Speed up Genre page and artwork load times via single-pass window function SQL query, image lazy loading, and 24h HTTP browser caching.

## Plan
1. **Backend Window Function & Cache Tuning**
   - Files: `backend/services/library.py`, `backend/routers/music.py`
   - Change: Single-pass `ROW_NUMBER() OVER` in `get_all_genres_db()`, increase artwork Cache-Control to 24h.
   - Verify: `uv run python -m pytest backend/tests/test_homepage_views.py`

2. **Frontend Dual Sort Pills & Image Lazy Loading**
   - Files: `frontend/src/components/BrowseViews.tsx`
   - Change: Render `.sort-pill-btn` buttons for A-Z and Most/Least Albums, add `loading="lazy"` to genre fallback images.
   - Verify: `cd frontend && npm run build`

3. **Live Docker Verification & Stack Restart**
   - Files: Docker Compose environment
   - Change: Restart Docker stack and test Genres view on `http://localhost:3000`.
   - Verify: Visual inspection in browser.

## Rollback Plan
- Revert via `git checkout main`.
