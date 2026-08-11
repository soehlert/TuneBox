# Implementation Plan - Admin Queue Clear Controls & Styling

Refactor queue clearing behavior and UI controls in TuneBox Admin Settings so that **Clear Upcoming Queue** preserves the currently playing song (`queue[0]`), and **Stop & Empty Queue** halts playback and clears all tracks with matching semi-transparent button styling.

## Proposed Changes

### Branch Creation
- Branch `feature/admin-queue-clear-controls` created.

### Backend Logic & API Routes
- Modify `backend/routers/music.py`:
  - `@router.post("/clear-queue")`: remove `stop_playback()` & `track_time_tracker.stop()`, call `clear_redis_queue(force_all=False)` to preserve `queue[0]`.
  - `@router.post("/stop-queue")`: keep `stop_playback()`, `track_time_tracker.stop()`, call `clear_redis_queue(force_all=True)`.

### Frontend UI & Admin Controls
- Modify `frontend/src/App.tsx`:
  - Rename button `"Clear Full Queue"` to `"Stop & Empty Queue"`.
  - Style `"Stop & Empty Queue"` with semi-transparent red (`rgba(255, 77, 77, 0.15)`) background and border matching amber button layout.
  - Update confirmation modal text and toast notifications.

### Automated Tests
- Modify `backend/tests/test_queue_isolation.py`: Update tests for `/clear-queue` preserving `queue[0]` and `/stop-queue` wiping all items.
