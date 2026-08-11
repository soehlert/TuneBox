# Implementation Plan - Decades Artwork & Plays Sorting Fix

## Plan Overview
1. Update `get_all_decades_db` in `backend/services/library.py` and `DecadesGridView` in `BrowseViews.tsx` to return and display `top_album_id` artwork for each decade card using the same ranking algorithm as genres.
2. Fix "Most Played / Least Played" sort toggle and comparator logic in `ArtistList.tsx` and `BrowseViews.tsx` (`AlbumsGridView`).
3. Verify backend tests with `uv run python -m pytest` and rebuild Docker frontend container.

## Steps
- **Step 1**: Update `get_all_decades_db` in `backend/services/library.py` to calculate `top_album_id` for each decade via ROW_NUMBER window query and update `DecadesGridView` in `BrowseViews.tsx`.
- **Step 2**: Fix `sortBy === "plays"` sorting comparator and button toggle handler in `ArtistList.tsx` and `AlbumsGridView` (`BrowseViews.tsx`) to support cycling between "Most Played" (`desc`) and "Least Played" (`asc`).
- **Step 3**: Execute tests and rebuild Docker container (`docker compose up -d --build`).
