## Goal
Redesign and re-label the two admin queue control buttons ("Clear Upcoming Queue" and "Clear Full Queue") with tooltips, clear descriptions, consistent app styling, and confirmation popups for both actions.

## Assumptions
1. "Clear Upcoming Queue" calls `POST /api/music/clear-queue` (clears queued tracks 1..N, keeping the currently playing song).
2. "Clear Full Queue" calls `POST /api/music/stop-queue` (stops playback and empties the entire queue including index 0).
3. Both buttons will use custom `ConfirmModal` dialogs styled consistently with the app's dark glassmorphism theme.
4. Tooltips/helper labels will explain the exact distinction between the two buttons.

## Plan
1. **Update Admin Controls UI & Tooltips in App.tsx**
   - Files: `frontend/src/App.tsx`
   - Change:
     - Rename button 1 to **"Clear Upcoming Queue"** (`#f5a623` amber/orange).
     - Rename button 2 to **"Clear Full Queue"** (`#ff4d4d` red).
     - Add `title` tooltips and 1-line helper descriptions underneath each button.
     - Add `confirmStopOpen` state for "Clear Full Queue" so both actions trigger a `ConfirmModal`.
   - Verify: `npm run build` in `frontend/`.

2. **Configure Confirmation Modals for Both Queue Actions**
   - Files: `frontend/src/App.tsx`
   - Change:
     - `ConfirmModal` for Upcoming Queue: *"Clear upcoming tracks (keeps currently playing song)?"*
     - `ConfirmModal` for Full Queue: *"Stop music & clear full queue (stops playback and wipes current track)?"*
   - Verify: `npm run build` in `frontend/`.

3. **Verify End-to-End Build & Backend Test Compatibility**
   - Files: `frontend/src/App.tsx`
   - Change: Verify frontend production build and execute backend test suite.
   - Verify: `npm run build` in `frontend/` and `uv run python -m pytest backend/tests/`.

## Risks & mitigations
- **Risk**: User accidentally clicks full queue stop thinking it only clears up-next songs.
- **Mitigation**: Add distinct red color + explicit modal copy detailing that "Clear Full Queue" stops active music and wipes the current track.

## Rollback plan
- Revert changes via `git checkout main` or `git restore frontend/src/App.tsx`.
