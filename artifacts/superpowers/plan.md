## Goal
1. Change the "Connecting" / "Enabled" status badge color in the Server Choice settings section to blue (`#3498db`, `rgba(52, 152, 219, 0.15)`, `1px solid rgba(52, 152, 219, 0.4)` and `🔵 Connecting` / `🔵 Enabled`).
2. Make the number of tracks added during playlist pre-seeding configurable via UI input and backend API parameter `count` (defaulting to 10).
3. Change the queue seeding button label back to "Preseed Queue" (and "Preseeding..." while active).
4. Handle cases where the configured count exceeds playlist length gracefully by seeding the entire playlist (`sample_size = min(len(tracks), count)`) without throwing an error.
5. Remove the "⏹️ Stop" button from the Queue header component, leaving the Stop Queue button exclusively in Host Settings next to "Clear Queue".

## Assumptions
- Host settings modal in `frontend/src/App.tsx` can maintain a local `preseedCount` state (default 10) with an input field in the Queue Management section.
- `POST /api/music/playlists/{playlist_id}/seed` accepts an optional `count` query parameter (default 10).
- In `backend/services/plex.py`, capping `sample_size = min(len(tracks), max(1, count))` ensures no index or sampling errors occur regardless of requested count.
- In `frontend/src/components/Queue.tsx`, removing the header `<button>` preserves the "Up Next" title styling while leaving the stop action in Host Settings.

## Plan

### Step 1: Backend Configurable Preseed Count & Safe Capping
- **Files**: `backend/routers/music.py`, `backend/services/plex.py`
- **Change**:
  - Update `seed_queue_from_playlist(playlist_id: int, count: int = 10)` in `backend/services/plex.py` to sample `min(len(tracks), max(1, count))` items.
  - Update `@router.post("/playlists/{playlist_id}/seed")` in `backend/routers/music.py` to accept `count: int = 10`.
- **Verify**: `uv run python -m pytest backend/tests/test_mock_music.py`

### Step 2: Server Choice Status Badge Blue Styling
- **Files**: `frontend/src/App.tsx`
- **Change**:
  - Update server status badge styling in the Server Choice section of `App.tsx` to use blue theme for `connecting` / `enabled` state (`#3498db`, `rgba(52, 152, 219, 0.15)`, `1px solid rgba(52, 152, 219, 0.4)`, badge label `🔵 Connecting` / `🔵 Enabled`).
- **Verify**: Inspect `App.tsx` JSX styling and ensure clean compilation.

### Step 3: Frontend Configurable Preseed UI & Button Renaming
- **Files**: `frontend/src/App.tsx`
- **Change**:
  - Add `preseedCount` state (default 10) to `App.tsx`.
  - Add a "Preseed Track Count" number input field in the Queue Management section.
  - Rename the action button from "Seed Queue" to "Preseed Queue" (and "Preseeding..." while loading).
  - Update API call to `/api/music/playlists/${selectedPlaylistId}/seed?count=${preseedCount}`.
- **Verify**: Build/test frontend component state and endpoints.

### Step 4: Remove Stop Button from Queue Header Component
- **Files**: `frontend/src/components/Queue.tsx`
- **Change**:
  - Remove the `<button>` element with `⏹️ Stop` from the Queue header bar (`Up Next`), leaving the Stop action exclusively in the Host Settings Queue Management modal next to Clear Queue.
- **Verify**: Build frontend and verify Queue header JSX.

### Step 5: Unit Test Updates for Preseed Count
- **Files**: `backend/tests/test_mock_music.py`
- **Change**:
  - Add test case verifying custom `count` query parameter in `POST /api/music/playlists/{playlist_id}/seed` and verifying `count > playlist_len` handles entire playlist safely.
- **Verify**: `uv run python -m pytest backend/tests`

## Risks & mitigations
- **Risk**: User specifies a preseed count larger than playlist size.
- **Mitigation**: Capping sample size via `min(len(tracks), max(1, count))` safely seeds all tracks in the playlist without raising ValueError or out-of-range sampling errors.

## Rollback plan
- Revert changes via `git checkout` on modified files (`App.tsx`, `Queue.tsx`, `music.py`, `plex.py`, `test_mock_music.py`).
