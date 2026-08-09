## Goal
Fix last-track rubber-banding by cleanly stopping playback immediately when the queue ends, while preserving seamless transitions between songs when queued tracks remain.

## Assumptions
1. When the last track in the queue finishes, `current_track: null` should immediately reset the player bar to stopped state ("Start TuneBox") with 0ms delay.
2. Holding track metadata during `current_track: null` should only occur when transitioning between back-to-back songs in an active queue.

## Plan
1. **Differentiate Between "Queue Ended" (Instant Stop) and "Track Transition" in `MusicControls.tsx`**
   - Files: `frontend/src/components/MusicControls.tsx`
   - Change:
     - When receiving `data.message === "Current track update"` with `current_track: null`:
       - If `data.queue_empty` or `data.stopped` is true (or if explicit stop was triggered): Immediately clear state (`currentTrack = null`, `isPlaying = false`, `progress = 0`, `elapsedTime = 00:00`) with 0ms delay.
       - Otherwise, if queued tracks remain, hold previous track display for 2 seconds.
   - Verify: `npm run build` in `frontend/`.

2. **Ensure Backend Broadcasts `stopped: true` when Queue Exhausts in `backend/services/plex.py`**
   - Files: `backend/services/plex.py`, `backend/websockets.py`
   - Change:
     - In `send_current_playing()`, include `"stopped": True` in the message payload when `current_track` is `None` and `playback_active` is `False`.
     - In `playback_orchestrator()`, stop `track_time_tracker` immediately when the queue ends.
   - Verify: `uv run python -m pytest backend/tests/test_queue_end_stopped.py`.

3. **Verify Full Suite**
   - Files: `frontend/src/components/MusicControls.tsx`, `backend/services/plex.py`, `backend/websockets.py`
   - Change: Run production build and backend test suite.
   - Verify: `npm run build` in `frontend/` and `uv run python -m pytest backend/tests/`.

## Risks & mitigations
- **Risk**: None. Stopped state becomes deterministic.

## Rollback plan
- Revert via `git checkout main` or `git restore backend/services/plex.py backend/websockets.py frontend/src/components/MusicControls.tsx`.
