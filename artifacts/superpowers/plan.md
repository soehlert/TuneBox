# Approved Implementation Plan: Essential Fair-Play Queue System

## Goal
Implement a lightweight, transparent queue management system in TuneBox that keeps standard human requests as pure First-Come First-Served (FCFS), leapfrogs human tracks over preseeded fallback tracks, gives each guest 1 "Play Next" bump token per session, enforces a 10-minute duplicate cooldown via Redis TTL, and provides queue play ETA in confirmation toasts.

---

## Steps

### Step 1: Redis Cooldown & Session Bump Tracking
- **Files**: `backend/services/redis.py`
- **Changes**:
  - Implement 10-minute duplicate song cooldown tracking in Redis (`song_cooldown:{track_id}`, TTL: 600s).
  - Implement single-use session "Play Next" bump tracking in Redis (`session_user_bumps:{username}`).

### Step 2: FCFS Queue Insertion & Bump Logic
- **Files**: `backend/services/redis.py`
- **Changes**:
  - Update `add_to_queue_redis()` to:
    1. Reject if song was played in the last 10 minutes (`song_cooldown:{track_id}` key exists) or is in active queue (HTTP 400).
    2. If `bump=True`, verify guest hasn't used session bump yet, insert track at Index 1 (after currently playing track), and record bump usage in Redis.
    3. If `bump=False`, insert track after the last human-requested track (ahead of any automated / vibe fallback tracks).

### Step 3: Queue Router Updates & ETA Calculation
- **Files**: `backend/routers/music.py`
- **Changes**:
  - Update `POST /api/music/queue` to accept optional `bump: bool = False` query/body parameter.
  - Calculate estimated play wait time (`estimated_wait_seconds` and `estimated_wait_minutes`) based on durations of tracks ahead in queue, and include in the queue endpoint response.
  - Add `POST /api/music/queue/{item_id}/bump` endpoint.

### Step 4: Frontend Confirmation Toast ETA & "Play Next" Bump Action
- **Files**: `frontend/src/components/TrackList.tsx`, `frontend/src/components/Queue.tsx`
- **Changes**:
  - Update queue confirmation snackbars in `TrackList.tsx` and `Queue.tsx` to display: `"Track added to queue! Estimated play in ~X min"`.
  - Add "⚡ Play Next (1 Left)" button in track action context menus, disabled if bump has been used.

### Step 5: Automated Unit Tests
- **Files**: `backend/tests/test_queue_limiters.py`
- **Changes**:
  - Add unit tests verifying FCFS queue placement, human leapfrogging over fallback tracks, 10-minute duplicate cooldown rejection, single-use session bump, and ETA calculation.
- **Verification Command**:
  - `uv run python -m pytest backend/tests/test_queue_limiters.py`
