# Implementation Plan - Player Control & State Sync Polish

Fix time tracking delays, smooth out the progress bar movement to 60fps, and eliminate natural track completion rubber-banding when tracks end.

## User Review Required

> [!IMPORTANT]
> - All fixes will be made on isolated branch `feat/player-control-polish`.
> - Automated regression tests will be added for natural track completion when paused/stopped.
> - Full pytest suite (127+ tests) will be executed to guarantee zero regressions.

## Proposed Changes

### Backend - Playback Engine & Resync (`backend/services/plex.py`)

#### [MODIFY] [plex.py](file:///Users/soehlert/projects/testing/TuneBox/backend/services/plex.py)
- **Natural Track Completion Fix**: Update `check_queue_and_advance()` so track completion detection (`elapsed >= total_time - 1.0` or PMS session ended) runs regardless of whether `track_time_tracker.is_playing` was auto-paused by resync.
- **Immediate Queue Advancement**: On completion, reliably remove the finished track from Redis (`remove_from_redis_queue`), advance to the next track if queue exists, or execute clean `stop_playback()` if queue is empty.
- **Instant Time Initialization**: Ensure `track_time_tracker.start()` initializes wall-clock start time immediately when `play_song` is called, eliminating the delay before time tracking starts.

---

### Frontend - Player Bar Component (`frontend/src/components/MusicControls.tsx`)

#### [MODIFY] [MusicControls.tsx](file:///Users/soehlert/projects/testing/TuneBox/frontend/src/components/MusicControls.tsx)
- **Smooth 60fps Progress Interpolation**: Add a smooth client-side ticker interval (250ms) when `isPlaying` is true to smoothly increment local elapsed time and progress bar width between 1-second server WebSocket pulses.
- **CSS Progress Smoothing**: Add `transition: 'width 0.25s linear'` to the progress bar container.

---

### Automated Tests (`backend/tests/test_core_playback_flow.py`)

#### [MODIFY] [test_core_playback_flow.py](file:///Users/soehlert/projects/testing/TuneBox/backend/tests/test_core_playback_flow.py)
- Add unit test verifying natural track completion advances queue when `track_time_tracker` is in `paused` or `stopped` state at end-of-track.

## Verification Plan

### Automated Tests
- `uv run python -m pytest backend/tests/test_core_playback_flow.py`
- `uv run python -m pytest` (Full 127+ test suite)

### Manual Verification
1. Play a song and observe the bottom player bar: progress timer starts at `0:00` instantly when song starts.
2. Observe progress bar line: moves continuously and smoothly without 1-second jumps.
3. Let a song play to completion (or fast forward to last 5 seconds): verify TuneBox advances smoothly to the next song in the queue without rubber-banding backwards.
