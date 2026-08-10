## Goal
Eliminate external Plexamp resync interference, fix natural track queue advancement, and ensure clean stopped state when the queue exhausts.

## Assumptions
- TuneBox is the sole controller; users do not interact directly with Plexamp.
- Complex external Plexamp resync polling is removed so `check_plexamp_resync()` no longer overwrites TuneBox playback state or re-starts tracks.
- Monotonic wall-clock progress bar (`track_time_tracker.elapsed_time`) and 1-click play/pause remain intact.
- Tests will be run via `env GIT_CONFIG_GLOBAL=/dev/null uv run python -m pytest`.
- Container will be restarted via `docker compose restart backend`.

## Plan

### Step 1: Remove External Plexamp Resync Interference
- **Files**: [backend/services/plex.py](file:///Users/soehlert/projects/testing/TuneBox/backend/services/plex.py)
- **Change**:
  - Make `check_plexamp_resync()` a safe no-op or pass-through when `playback_active` is `True` or when queue is empty/stopped.
  - Stop `check_plexamp_resync()` from overwriting `now_playing` in Redis or restarting `track_time_tracker` from stale PMS session data.
- **Verify**: `env GIT_CONFIG_GLOBAL=/dev/null uv run python -m pytest backend/tests/test_plex.py`

### Step 2: Ensure Clean Natural Queue Advancement
- **Files**: [backend/services/plex.py](file:///Users/soehlert/projects/testing/TuneBox/backend/services/plex.py)
- **Change**:
  - In `playback_orchestrator()` (when `elapsed >= total_time`), safely construct `next_song_data` using `next_song.get("server_id")` and `next_song.get("album_id")`.
  - Advance playback to `next_song` cleanly and update `now_playing` / `track_time_tracker`.
- **Verify**: `env GIT_CONFIG_GLOBAL=/dev/null uv run python -m pytest backend/tests/test_core_playback_flow.py`

### Step 3: Clean Stopped State & Queue Exhaustion
- **Files**: [backend/services/plex.py](file:///Users/soehlert/projects/testing/TuneBox/backend/services/plex.py), [backend/services/redis.py](file:///Users/soehlert/projects/testing/TuneBox/backend/services/redis.py)
- **Change**:
  - When remaining time reaches 0 (or `elapsed >= total_time`) and the queue is empty, `playback_orchestrator()` sets `playback_active = False`, stops `track_time_tracker`, and purges `now_playing` from Redis.
  - In `get_current_playing_track()`, return `None` when `playback_active` is `False` and queue is empty so WebSocket broadcasts `current_track: null`.
- **Verify**: `env GIT_CONFIG_GLOBAL=/dev/null uv run python -m pytest backend/tests/test_websocket_state.py backend/tests/test_redis.py`

### Step 4: Full Suite & Container Verification
- **Files**: Entire backend test suite
- **Change**: Run full test suite and restart backend container.
- **Verify**:
  - `env GIT_CONFIG_GLOBAL=/dev/null uv run python -m pytest` (128 passed)
  - `docker compose restart backend`

## Risks & mitigations
- **Risk**: Disabling resync polling might affect tests that mock PMS sessions.
  - **Mitigation**: Keep signature and no-op compatibility for tests while disabling state-overwriting logic.

## Rollback plan
- Revert via `git checkout backend/services/plex.py backend/services/redis.py` and restart backend container.
