# Implementation Plan - Instant Playlist Preseeding & Full-Broadcast Queue Updates

Fix the 15-second preseed delay, event loop GIL freezing, missing toast notifications, and queue update delays by sampling preseed tracks upfront, replacing sequential SQLite loop queries with a single batch SQL query, and broadcasting queue updates to all active WebSocket connections.

## Proposed Changes

### Branch Creation
- Branch `feature/fast-playlist-preseed` active.

### Backend Services & WebSockets
- Modify `backend/services/plex.py`:
  - `seed_queue_from_playlist`: sample `target_count` tracks FIRST; resolve fallback pool with 1 batch SQL query (`WHERE server_track_id IN (...)`).
- Modify `backend/websockets.py`:
  - `send_queue`: broadcast queue payload to all active WebSocket connections via `send_json_to_all`.

### Automated Tests
- Modify `backend/tests/test_queue_isolation.py`: verify batch SQL preseed performance and WebSocket broadcasts.
