# Brainstorm - Fix Playlist Preseed Latency & Real-Time Queue Update Delay

## Goal
Eliminate the 35+ second latency when seeding playlist tracks into the playback queue, making preseed operations near-instant (under 500ms), and ensuring immediate real-time WebSocket queue updates and toast notifications without requiring a page refresh.

## Constraints
- **Strict Track ID Standardization**: Convert external Plex `ratingKey`s to internal SQLite `track_id`s upfront using `rating_key_to_track_id`.
- Do NOT make unnecessary cascading external HTTP network calls to Plex during queue seeding.
- Global imports only in backend Python files per project directives.
- Preserve existing queue priority rules (guest tracks leapfrog fallback tracks, playing track at index 0 remains active).

## Known Context
- `POST /api/music/playlists/{playlist_id}/seed?count=10` currently takes 35+ seconds to complete 10 tracks.
- **Root Cause 1 (Network Latency)**: `seed_queue_from_playlist` fetches Plex objects via `plexapi`. When `add_to_queue_redis` is called on each `plexapi.audio.Track` object, accessing lazy properties `song.moods`, `song.album()`, and `song.artist()` triggers 4–5 synchronous HTTP GET requests to Plex per track (40+ blocking network calls for 10 tracks). This completely blocks the FastAPI event loop for 35+ seconds.
- **Root Cause 2 (UI/WebSocket Update Delay)**: In `backend/routers/music.py`, `seed_playlist` schedules `send_queue` via `background_tasks.add_task(send_queue)` without `await`. Furthermore, `send_current_playing()` is not called, causing WebSocket subscribers to miss immediate state updates until a manual page refresh.
- **Root Cause 3 (UI Toast Scope)**: In `frontend/src/App.tsx`, `handleSeedJukebox` sets `setMsg(...)` which is rendered in the `SettingsModal` footer. Because the API hangs for 35 seconds, users close the modal or refresh before the response finishes.

## Risks
- If a playlist track is not yet indexed in local SQLite, falling back gracefully to basic Plex track attributes without triggering cascading `.album()` / `.artist()` network calls is required.
- Ensuring `send_queue()` and `send_current_playing()` are awaited directly ensures all connected clients (web app, kiosk, player controls) update in real time.

## Options

### Option 1: Optimize Track Property Extraction & Direct WebSocket Awaits (Recommended)
- In `add_to_queue_redis`: Avoid triggering cascading `song.album()` / `song.artist()` network property lookups on `plexapi` objects when resolving moods, especially during fallback/preseed operations. Use direct attributes or local SQLite DB queries.
- In `seed_queue_from_playlist`: Look up internal SQLite track details first using `rating_key_to_track_id`.
- In `seed_playlist` (`music.py`): Explicitly `await send_queue()` and `await send_current_playing()` so WebSocket clients update instantly.
- In `App.tsx`: Ensure toast state and queue state update immediately upon response.

### Option 2: Async Preseed Background Task with Item Streaming
- Offload preseed seeding to a background worker and push WebSocket updates per item.
- *Drawback*: Unnecessary complexity for 10–50 tracks when local DB lookup can execute synchronously in <100ms.

### Option 3: Pure SQLite Playlist Track Seeding
- Load playlist track IDs directly from `preseed_playlist_tracks` or `tracks` SQLite table, bypassing `plexapi` network calls completely during seeding.
- *Drawback*: If a playlist was updated on Plex after the last library sync, newly added Plex tracks wouldn't appear until re-indexed.

## Recommendation
**Option 1** is recommended:
1. Refactor `add_to_queue_redis` in `backend/services/redis.py` to prevent cascading network calls (`song.album()`, `song.artist()`) on `plexapi` objects.
2. Refactor `seed_queue_from_playlist` in `backend/services/plex.py` to use local SQLite track data via `rating_key_to_track_id`.
3. Update `seed_playlist` endpoint in `backend/routers/music.py` to `await send_queue()` and `await send_current_playing()`.
4. Update `App.tsx` toast notification handling for preseed actions.

## Acceptance Criteria
- `POST /api/music/playlists/{id}/seed?count=10` completes in under 500ms (down from 35+ seconds).
- No cascading HTTP requests to Plex per track during queue seeding.
- Preseeding immediately updates the Queue UI in real-time over WebSocket without requiring a page refresh.
- Settings modal displays the success toast ("✓ Successfully seeded 10 tracks...") immediately upon completion.
- All unit and integration tests (`uv run python -m pytest`) pass.
