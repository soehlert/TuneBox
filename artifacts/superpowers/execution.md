- **Step 1: Include `album_id` in Redis Queue Payload**
  - Files: `backend/services/redis.py`
  - Changes: Added `"album_id": getattr(song, "album_id", getattr(song, "parentRatingKey", None))` to `song_data` dict in `add_to_queue_redis`.
  - Verification: `uv run python -m pytest backend/tests/test_redis.py` (16/16 passed).
  - Status: PASS

- **Step 2: Add Album Navigation to Queue Component**
  - Files: `frontend/src/components/Queue.tsx`, `frontend/src/components/Queue.css`
  - Changes: Imported `useNavigate` from `react-router-dom`. Created `handleTrackClick` to navigate to `/albums/${track.album_id}/tracks`. Attached click handler to queue and history items with `e.stopPropagation()` on action buttons and drag handles. Added hover highlight and slide-right animation in `Queue.css`.
  - Verification: `npm run build` in `frontend/` (succeeded) and `uv run python -m pytest backend/tests/` (113/113 passed).
  - Status: PASS

- **Step 3: Add Unit Test for `album_id` Serialization**
  - Files: `backend/tests/test_redis.py`, `backend/tests/conftest.py`
  - Changes: Updated `mock_plex_track` fixture to include `album_id` and `parentRatingKey`. Added `assert track_data["album_id"] == "6789"` to `test_add_to_queue_redis` test case.
  - Verification: `uv run python -m pytest backend/tests/test_redis.py` (16/16 passed).
  - Status: PASS
