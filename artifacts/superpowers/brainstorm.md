# Brainstorm: Critical Core Test Suite for TuneBox

## Goal
Establish a comprehensive, highly reliable, and trustworthy suite of core integration tests covering essential TuneBox application features: queue management, playback controls, catalog resolution, server filtering, and real-time state sync.

## Constraints
- Focus on single-server operation by default, while supporting overridable `server_id` parameters for future multi-server tests.
- Strictly forbid mock data or sample fallbacks outside of explicit automated test execution (`settings.testing`).
- Maintain strict database and Redis state isolation between tests.
- Never merge feature/test branches into `main` without explicit user approval.

## Known Context & Currently Verified Tests (Phase 0)
Currently on branch `feature/critical-core-tests`. The following 11 verified core tests are already in place and passing:

1. **[test_core_playback_flow.py](file:///Users/soehlert/projects/testing/TuneBox/backend/tests/test_core_playback_flow.py)**:
   - `test_1_adding_to_queue_works`: Adding tracks to queue via API.
   - `test_2_playing_song_works`: Orchestrator starting track playback.
   - `test_3_song_plays_til_end_and_moves_to_next_track`: Track finishing and advancing to next queued item.
   - `test_4_force_skip_works`: Force skip / skip endpoint functionality.
   - `test_5_play_pause_toggles_playback_preserving_queue`: Play/pause toggling without mutating queue.
   - `test_6_stops_when_out_of_tracks_in_queue`: Stopped state transition when queue is empty.

2. **[test_queue_isolation.py](file:///Users/soehlert/projects/testing/TuneBox/backend/tests/test_queue_isolation.py)**:
   - `test_clear_queue_endpoint_removes_all_items_and_stops_playback`: Complete queue clearing + playback stop.
   - `test_only_user_added_songs_exist_in_queue`: Queue isolation ensuring only explicitly added tracks exist.
   - `test_autoplay_does_not_seed_when_disabled`: Autoplay exit when disabled.

3. **[test_server_resolution.py](file:///Users/soehlert/projects/testing/TuneBox/backend/tests/test_server_resolution.py)**:
   - `test_get_art_source_info_resolves_server_track_id`: Resolution of Plex ratingKeys (`server_track_id`).
   - `test_search_music_db_includes_server_id_and_server_name`: Search results metadata (`server_id`, `server_name`).

## Risks
- Synthetic mocks masking integration flaws between API endpoints, Redis queue storage, and Plex service layer.
- Lingering Redis state or autoplay fallback loops polluting test runs if fixtures do not reset state completely.

## Options & Next Steps (2–4)
- **Option 1: Queue Mutation & Reordering Suite (`test_queue_mutations.py`)**
  Focus on testing track removal, queue reordering ("Move to Top"), and queuing full albums in track order.
- **Option 2: Playback Controls & Position Scrobbling Suite (`test_playback_controls.py`)**
  Focus on testing pause/resume position preservation, seeking/scrobbling to specific offsets, and previous/restart track logic (>3s vs <3s).
- **Option 3: Catalog Resolution & Server Filtering Suite (`test_catalog_filtering.py`)**
  Focus on testing search/browse server filtering (enabled vs. disabled servers) and artwork proxying without dummy fallbacks.
- **Option 4: Comprehensive Phased Rollout (Recommended)**
  Implement Options 1 through 3 sequentially in focused modules, culminating in real-time WebSocket state verification.

## Recommendation
Execute **Option 4** (Comprehensive Phased Rollout):
1. **Phase 1**: Queue Mutation & Reordering (`test_queue_mutations.py`)
2. **Phase 2**: Playback Controls & Position Scrobbling (`test_playback_controls.py`)
3. **Phase 3**: Catalog Resolution & Server Filtering (`test_catalog_filtering.py`)
4. **Phase 4**: Real-Time WebSocket & State Sync (`test_websocket_state.py`)

## Acceptance criteria
- Each test module targets a single behavior per test with exact assertions.
- Tests run against clean, isolated SQLite and Redis test contexts.
- Full test suite passes via `uv run pytest` with zero warnings or unexpected side effects.
