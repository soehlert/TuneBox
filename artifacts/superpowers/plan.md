# Implementation Plan: Fix Two-Way Star Rating Sync with Primary Plex Server

Restore complete two-way star rating synchronization between TuneBox and your primary Plex Media Server:

1. **TuneBox -> Plex (Admin Rates Track in TuneBox)**:
   - When Admin rates a song in TuneBox (0.5 to 5.0 stars in half-star steps), TuneBox sends the rating to your primary Plex server (converted to Plex 1 to 10 scale).
   - Fix Plex `ratingKey` resolution in `get_art_source_info` / `rate_track_in_plex` so TuneBox looks up Plex's actual track `ratingKey` instead of internal SQLite track IDs, allowing Plex to receive and save the rating.

2. **Plex -> TuneBox (Ratings Set/Updated in Plex)**:
   - When tracks are synced during library indexing from your primary Plex server, TuneBox reads `userRating` from Plex and updates `user_rating` (converted to 0.5 - 5.0 stars) directly into TuneBox DB.
   - Fix `upsert_track` SQL update logic so ratings from Plex populate into TuneBox DB.

3. **Primary Owned Server Enforcement**:
   - Rating sync in both directions is strictly restricted to your **primary owned server only** (`srv.is_primary = 1`). Non-primary servers are ignored for rating sync.

## User Review Required

> [!IMPORTANT]
> - Rating sync strictly enforces primary owned server isolation (`is_track_on_primary_server`).
> - Supports 0.5-star precision mapping (0.5 stars in TuneBox = 1 in Plex, 1.0 star = 2 in Plex, 4.5 stars = 9 in Plex, 5.0 stars = 10 in Plex).
> - Fixes Plex track lookup so ratings sent from TuneBox succeed in Plex.
> - Fixes SQLite track upsert so ratings read from Plex update TuneBox DB.

## Proposed Changes

### Backend Database & Query Engine

#### [MODIFY] [`backend/services/library.py`](file:///Users/soehlert/projects/testing/TuneBox/backend/services/library.py)
- Update `upsert_track` SQL `UPDATE` statement to set `user_rating = ?` directly so ratings fetched from Plex populate into TuneBox DB during indexing.
- Update `get_all_art_sources` for `item_type == "track"` to use `COALESCE(ts.server_id, t.server_id)` and `COALESCE(ts.server_track_id, t.server_track_id)` so the primary server ID and Plex ratingKey resolve cleanly even if `track_sources` is unpopulated.

#### [MODIFY] [`backend/services/plex.py`](file:///Users/soehlert/projects/testing/TuneBox/backend/services/plex.py)
- Update `rate_track_in_plex` to resolve the primary server's `server_track_id` (Plex ratingKey).
- Ensure `item.rate(int(plex_rating))` accurately maps half stars (e.g., 4.5 stars -> 9 in Plex, 0.5 stars -> 1 in Plex).

#### [MODIFY] [`backend/routers/music.py`](file:///Users/soehlert/projects/testing/TuneBox/backend/routers/music.py)
- Keep strict `is_track_on_primary_server` check in `rate_track_endpoint` so rating sync only targets the primary server.

#### [MODIFY] [`backend/tests/test_track_rating.py`](file:///Users/soehlert/projects/testing/TuneBox/backend/tests/test_track_rating.py)
- Update test cases to verify 0.5-star precision (e.g. 4.5 stars -> 9 in Plex) and enforcement of primary server restriction.

---

## Verification Plan

### Automated Tests
- Run `env GIT_CONFIG_GLOBAL=/dev/null uv run python -m pytest backend/tests/test_track_rating.py`
- Run full backend test suite: `env GIT_CONFIG_GLOBAL=/dev/null uv run python -m pytest`
- Run frontend TypeScript compilation check: `npx tsc --noEmit`

### Manual Verification
- Rebuild & restart Docker stack (`docker compose up -d --build`).
- In TuneBox UI: Rate a primary server track 4.5 stars as Admin. Verify 200 response and log: `Successfully set Plex userRating = 9 for track ...`.
- In Plex UI: Rate a track 4 stars. Run library index in TuneBox. Verify TuneBox shows 4 stars.
