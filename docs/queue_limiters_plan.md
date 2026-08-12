# Queue-Based Limiters & Fair Play System Implementation Plan

## Goal
Implement a lightweight, transparent fair-play queue management system in TuneBox that balances guest requests, prevents rapid duplicate song requests, notifies guests of estimated wait times upon queuing, and gives each guest one "Play Next" bump per session.

---

> [!WARNING]
> ### Design & Complexity Constraint
> **Avoid Complex "Black-Box" Queue Algorithms!**
> The queue must remain **simple, transparent, and predictable**. Guests should always understand why their song is placed where it is without feeling like a mysterious algorithm is manipulating the queue. Every rule must be explicit, minimal, and easy to explain.

---

## Assumptions
1. Guest identity is tracked by `username` in local storage / headers (`getLocalUsername()`).
2. Queue order and session state are managed in Redis (`playback_queue`, `session_stats`, `history`).
3. Automated autoplay/vibe-seeded tracks always sit below human-requested tracks.
4. No code will be written or branches created until explicitly requested.

---

## Key Refinements & Features

### 1. Duplicate Request Cooldown Window (10 Minutes)
- Songs played within the last **10 minutes** cannot be re-requested by any guest.
- Attempts to re-request return a clear 400 Bad Request error toast: `"This song was played recently. Duplicate cooldown active for X more minutes."`

### 2. Fair-Share Priority for New Queuers & Unplayed Artists
- **First-Time Queuers**: Requests from guests who haven't queued a song yet in the current party session receive higher placement priority among standard guest tracks.
- **Unplayed Artists**: Tracks from artists who haven't been played yet in the current session receive a slight priority boost over artists played recently.

### 3. Light Rate-Limiting for Heavy Queuers
- When a guest has requested > 3 songs in the session, their *newest* (4th+) requests are placed with slightly lower insertion priority so requests from new/infrequent queuers insert naturally ahead of them.
- Existing queued tracks are **never** demoted or pushed down retroactively.

### 4. Session "Play Next" Bump Allowance (1 Per Session)
- Each guest gets **1 single "Play Next" bump token** per session.
- Using the bump token gives the track **higher insertion priority** (placing it above standard guest requests), while still respecting currently playing and host-pinned tracks.
- It does **not** forcefully leapfrog to absolute #1.

### 5. Queue ETA in Confirmation Toast (Not Persistent in UI)
- Do **not** display continuous ETA badges in `Queue.tsx`.
- Instead, calculate estimated wait time on the backend and display it **only inside the confirmation toast notification** when a guest adds a song:
  *`"Track added to queue! Estimated play in ~12 min"`*

---

## Plan

### Step 1: Backend Session & Cooldown Service
- **Files**: `backend/services/redis.py`, `backend/services/library.py`
- **Change**:
  - Add 10-minute duplicate song cooldown tracking in Redis (`song_cooldown:{track_id}`, TTL: 600s).
  - Track per-user request counts (`user_request_count:{username}`).
  - Add session artist history lookup (`played_artists_session`).
- **Verify**:
  - `uv run pytest backend/tests/test_queue_limiters.py`

### Step 2: Transparent Queue Insertion Logic
- **Files**: `backend/services/redis.py`, `backend/routers/music.py`
- **Change**:
  - Refactor `add_to_queue_redis()` to determine insertion index based on explicit priority rules:
    1. Reject if song was played in the last 10 minutes (HTTP 400).
    2. Apply higher insertion priority for "Play Next" bumped tracks.
    3. Apply higher priority for first-time queuers and unplayed artists.
    4. Place 4th+ requests from heavy queuers after requests from new/infrequent queuers.
- **Verify**:
  - Unit tests verifying insertion order across mixed queuers and unplayed artists.

### Step 3: Session "Play Next" Bump Endpoint
- **Files**: `backend/services/redis.py`, `backend/routers/music.py`
- **Change**:
  - Track single-use bump tokens per session (`user_bump_used:{username}`).
  - Add `POST /api/music/queue/{item_id}/bump` endpoint that validates token availability, consumes the token, and inserts track with high priority.
- **Verify**:
  - Test verifying bump succeeds on first use and returns HTTP 400 on subsequent attempts.

### Step 4: ETA Toast & Frontend Integration
- **Files**: `backend/routers/music.py`, `frontend/src/components/TrackList.tsx`, `frontend/src/components/ArtistList.tsx`
- **Change**:
  - Include `estimated_wait_minutes` in `POST /api/music/queue` response.
  - Update confirmation snackbars to display: `"Track added to queue! Estimated play in ~X min"`.
  - Add "⚡ Play Next (1 Left)" button in track action menus.
- **Verify**:
  - Manual UI check in browser verifying toast message and bump button behavior.

---

## Risks & Mitigations
- **Risk**: Algorithmic complexity making queue order feel unpredictable.
  - **Mitigation**: Strictly follow simple, deterministic rules. Keep the currently playing track untouched.

---

## Rollback Plan
- Revert commit or feature branch `feature/queue-limiters` back to `main`.
