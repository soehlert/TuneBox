# Implementation Plan: Artist Connected Libraries Pill & Subtle Pink Theme

## Goal
Add the Connected Libraries pill badge to the Artist albums page header (showing which servers the artist's library is available on, using subtle pink styling and multi-line formatting), and update album card badges on the artist view to match the subtle pink palette.

## Assumptions
- Changes touch `backend/services/library.py` and `frontend/src/components/ArtistAlbums.tsx`.

## Plan
1. **Backend Distinct Album & Artist Sources**
   - Files: `backend/services/library.py`
   - Change: Include deduplicated `sources` for each album returned by `get_albums_for_artist_db()`.
   - Verify: `uv run python -m pytest backend/tests/`

2. **Frontend Artist Header & Card Badges**
   - Files: `frontend/src/components/ArtistAlbums.tsx`
   - Change: Add multi-line Connected Libraries pill badge under Artist header, restyle card badges in subtle pink (`#ff4d94`, `rgba(191, 9, 94, 0.15)`).
   - Verify: `cd frontend && npm run build`

3. **Live Docker Verification & Stack Restart**
   - Files: Docker Compose environment
   - Change: Restart Docker stack and test Artist Albums page on `http://localhost:3000`.
   - Verify: Visual inspection on `http://localhost:3000`.

## Risks & mitigations
- **Risk**: None.
- **Mitigation**: Verified via pytest and TypeScript build.

## Rollback plan
- Revert via `git checkout main`.
