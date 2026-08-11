# Implementation Plan - Party Vibe Selector & Dynamic Mood Queue Generator

Add an interactive **Party Vibe Selector** to TuneBox that allows hosts and guests to pick room vibes (*🎉 Party, ⚡ Energetic, ☕ Chill, 🎷 Groovy, 🎸 Rock, 🎧 Electronic*) and dynamically pre-seed or update the queue with matching tracks from the local music library, capped at a configurable track limit (10–50).

## Proposed Changes

### Branch Creation
- Branch `feature/party-vibe-selector` active.

### Backend Services & Routers
- `backend/services/library.py`: Add `get_tracks_by_vibe_db(vibe_name, count)` to sample matching tracks from SQLite.
- `backend/services/plex.py`: Add `seed_queue_from_vibe(vibe_name, count)` to push fallback tracks to Redis.
- `backend/routers/music.py`: Add `GET /api/music/vibes` and `POST /api/music/vibe/seed`.

### Frontend Components
- `frontend/src/components/Queue.tsx`: Add interactive Party Vibe chip bar above the Queue list.
- `frontend/src/App.tsx`: Add "Preseed by Vibe" section in `SettingsModal` under Admin Controls.

### Automated Tests
- `backend/tests/test_vibe_seeding.py`: Unit tests for `GET /api/music/vibes` and `POST /api/music/vibe/seed`.
