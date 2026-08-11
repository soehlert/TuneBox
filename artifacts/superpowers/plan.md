# Implementation Plan - Prevent Duplicate Tracks in Playback Queue

Fix duplicate track queueing by standardizing track IDs upfront. External Plex `ratingKey`s will be converted to internal SQLite `track_id`s before performing duplicate checks or storing items in the Redis queue.

## Proposed Changes

### Branch Creation
- Create and checkout a new branch `fix/prevent-duplicate-queue-tracks` from `main`.

### Backend Logic & Utilities
- Modify `backend/utils.py`:
  - Global imports for `settings` and `rating_key_to_track_id`.
  - Add helper `get_canonical_track_id(item)`.
  - Update `is_song_in_queue(item, server_id=None)` to convert to canonical `track_id` upfront and compare against Redis queue items.
- Modify `backend/services/redis.py`:
  - Move resolution of `internal_track_id` to top of `add_to_queue_redis` before `is_song_in_queue`.

### Automated Tests
- Modify `backend/tests/test_utils.py`: Test `is_song_in_queue` with ratingKey conversion.
- Modify `backend/tests/test_redis.py`: Test `add_to_queue_redis` raises HTTP 400 for duplicate tracks.
- Modify `backend/tests/test_queue_mutations.py`: Test `POST /api/music/queue/{item_id}` returns 400 for duplicate tracks.

### Stack Restart & Verification
- Run `uv run python -m pytest`.
- Restart Docker stack via `docker compose up -d --build`.
