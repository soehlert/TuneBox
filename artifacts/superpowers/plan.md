# Implementation Plan: Genre View Enhancements (Blue Theme, Custom Sorting & Cover Artwork)

## Goal
Enhance the **Genres View** by matching the Decades view's sleek blue color palette, adding a sort dropdown control (A-Z, Z-A, Most Albums, Least Albums), and rendering top album artwork thumbnails for visual differentiation across genres.

## Assumptions
- `get_all_genres_db()` can include `top_album_id` for top-performing album artwork in each genre.
- Sort control is client-side instant toggle.

## Plan
1. **Backend Top Album Artwork Query**
   - Files: `backend/services/library.py`
   - Change: Include `top_album_id` subquery in `get_all_genres_db()`.
   - Verify: `uv run python -m pytest backend/tests/test_homepage_views.py`

2. **Frontend Blue Styling, Sort Dropdown & Artwork Cards**
   - Files: `frontend/src/components/BrowseViews.tsx`
   - Change: Update `GenresGridView` with Decades blue gradients (`#0077b6`), add sort dropdown toggle, and render top album artwork cover thumbnails.
   - Verify: `cd frontend && npm run build`

3. **Live Docker Verification & Stack Restart**
   - Files: Docker Compose environment
   - Change: Restart Docker stack and manually test Genres view on `http://localhost:3000`.
   - Verify: Visual inspection in browser.

## Risks & Mitigations
- **Risk**: Missing album art for obscure genres.
- **Mitigation**: FallbackImage component renders styled music icon placeholder when no cover art exists.

## Rollback Plan
- Revert changes via `git checkout main`.
