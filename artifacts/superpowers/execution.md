### Step 1: Remove External Plexamp Resync Interference
- **Files changed**: `backend/services/plex.py`
- **What changed**:
  - Simplified `check_plexamp_resync()` to a clean, safe no-op.
  - Stopped background polling of PMS `sessions()` from overwriting active TuneBox queue playback, re-starting finished tracks from 0.0s, or converting stopped states to "paused".
- **Verification command**: `env GIT_CONFIG_GLOBAL=/dev/null uv run python -m pytest backend/tests/test_plex.py`
- **Result**: PASSED (7 passed)

### Step 2: Ensure Clean Natural Queue Advancement
- **Files changed**: `backend/services/plex.py`
- **What changed**:
  - Fixed undefined variable scope in `playback_orchestrator()` using `next_song.get("server_id")` and `next_song.get("album_id")`.
  - Allowed `playback_orchestrator()` to construct `next_song_data` and trigger `play_song()` cleanly on natural track completion without throwing a `NameError`.
- **Verification command**: `env GIT_CONFIG_GLOBAL=/dev/null uv run python -m pytest backend/tests/test_core_playback_flow.py`
- **Result**: PASSED (7 passed)

### Step 3: Clean Stopped State & Queue Exhaustion
- **Files changed**: `backend/services/plex.py`, `backend/services/redis.py`
- **What changed**:
  - Simplified `get_current_playing_track()` to return `None` whenever `total_time > 0` and `remaining_time <= 0`.
  - Ensured WebSocket events emit `current_track: None, stopped: True, queue_empty: True` when queue finishes so the frontend playbar resets cleanly.
- **Verification command**: `env GIT_CONFIG_GLOBAL=/dev/null uv run python -m pytest backend/tests/test_websocket_state.py backend/tests/test_redis.py`
- **Result**: PASSED (21 passed)

### Step 4: Full Suite & Container Verification
- **Files changed**: Entire backend test suite
- **What changed**: Verified full test suite and restarted backend Docker container.
- **Verification command**: `env GIT_CONFIG_GLOBAL=/dev/null uv run python -m pytest` and `docker compose restart backend`
- **Result**: PASSED (128 passed, container restarted & active)
