# Implementation Plan - Fast Playlist Preseeding & Real-Time Queue Updates

Eliminate the 35+ second latency during playlist queue pre-seeding by avoiding cascading network calls in track mood evaluation, and ensure immediate real-time WebSocket queue updates and toast notifications.

## Proposed Changes

### Branch Creation
- Branch `feature/fast-playlist-preseed` created.

### Backend Logic & Router Updates
- Modify `backend/services/redis.py`:
  - `add_to_queue_redis`: avoid cascading `song.album()` / `song.artist()` network calls when resolving moods.
- Modify `backend/routers/music.py`:
  - `@router.post("/playlists/{playlist_id}/seed")`: `await send_queue()` and `await send_current_playing()` directly.

### Automated Tests
- Modify `backend/tests/test_queue_isolation.py`: Add test for fast playlist pre-seeding and WebSocket updates.
