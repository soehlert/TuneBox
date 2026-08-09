# Superpowers Brainstorm: Future Roadmap & Refactoring Plans

## Future Action Items (To Be Addressed Later)

### 1. Full-Scale Function Side-Effect Audit & Refactoring
- **Goal**: Audit every backend helper function across `backend/services/` to identify and decouple implicit side-effects.
- **Scope**: Ensure functions strictly adhere to Single Responsibility. Functions responsible for connection cache invalidation or status queries must never mutate runtime playback state, stop player timers, or purge active user queues.

---

### 2. Full-Scale Test Suite Refactoring
- **Goal**: Overhaul the automated test suite (`backend/tests/`) to increase test reliability and catch real runtime regressions.
- **Scope**:
  - Replace heavy function patching (`@patch`) with un-mocked integration tests running against real SQLite and Redis instances.
  - Add explicit regression assertions verifying that configuration updates and server toggles preserve active queue state.
  - Add multi-thread WebSocket integration tests to catch async event loop thread isolation failures.

---

### 3. Settings Save Latency & Live UI Server Toggle Auto-Refresh

#### Goal
Investigate and resolve why:
1. Saving settings in TuneBox takes ~30 seconds to complete.
2. Toggling Plex servers in Settings requires a manual page reload to update artist/album views.

#### Constraints
- Merge Restrictions: `feat/indexing-and-autoplay-improvements` must remain unmerged into `main`.
- No Production Performance Degradation: Cache warming must not block UI HTTP responses.

#### Known Context
1. **30-Second Settings Save Delay**:
   - `POST /api/auth/settings` calls `reinitialize_plex()` and `pre_warm_all_caches()`.
   - `pre_warm_all_caches()` invokes `fetch_and_cache_resources(refresh=True)` which probes all 7 remote Plex servers on MyPlex sequentially.
   - Offline/unreachable servers (e.g. `alpha`) hit connection retries and timeouts (3s per endpoint across 9 endpoints), creating **25–30 seconds of blocking latency**.
2. **Manual Page Reload Needed for Toggled Content**:
   - `POST /api/auth/libraries` updates server status in SQLite/Redis, but `App.tsx` does not listen for a server toggle WebSocket broadcast or invoke `fetchArtists()` / `fetchAlbums()` when `SettingsModal` saves, requiring a manual browser refresh.

#### Risks
- Probing network connections synchronously during settings save blocks UI feedback.

#### Options
- **Option 1 (Recommended)**:
  1. Make MyPlex server endpoint discovery run in parallel with a strict 2s per-server timeout, offloaded to background tasks so `POST /api/auth/settings` returns in under 1 second.
  2. Broadcast a `server_list_updated` WebSocket event when server enabled status changes so `App.tsx` automatically re-fetches artists/albums dynamically without a page reload.
- **Option 2**: Pure local SQLite server toggle without MyPlex re-probing.

#### Recommendation
Implement **Option 1**.

#### Acceptance Criteria
1. Saving settings completes in under 1.5 seconds.
2. Toggling a server in Settings immediately updates the artist/album grid on the main home view without requiring a manual page refresh.

---

### 4. Accurate Percentage-Based Progress Bar for Library Indexing

#### Goal
Compute real-time, numeric progress percentages (0% to 100%) during multi-step library indexing (Artists → Albums → Tracks) so the UI banner displays a smooth, dynamic linear progress bar for the currently active server.

#### Constraints
- **Zero Pre-Indexing Delay**: Must not add network latency querying total counts before indexing begins.
- **Per-Server Scope**: Progress calculation is calculated independently per server as that server starts indexing. When a server starts, its progress resets and runs from 0% → 100%.

#### Known Context
- `index_server()` runs in 3 sequential stages per server:
  1. **Artists Stage** (Fast metadata upserts)
  2. **Albums Stage** (Medium volume upserts)
  3. **Tracks Stage** (Highest volume upserts, ~80% of total work)
- Plex API HTTP header query `/library/sections/{key}/all?X-Plex-Container-Start=0&X-Plex-Container-Size=0` returns `totalSize` (total items count for that server) in **< 10ms** without loading item bodies.

#### Risks
- If a server disconnects mid-indexing, `totalSize` might differ slightly from processed items. (Handled gracefully by capping percentage at 99% until completion broadcast).

#### Options
- **Option 1: Per-Server 3-Stage Weighted Progress with Fast Metadata `totalSize` (Recommended)**:
  - As each server starts indexing, read `totalSize` from that server's metadata headers (< 10ms).
  - Assign weighted percentages across the 3 stages:
    - **Artists**: 10% weight (0% → 10%)
    - **Albums**: 25% weight (10% → 35%)
    - **Tracks**: 65% weight (35% → 100%)
  - Calculate live progress percentage for the active server:
    $$\text{Progress}\% = \text{StageStart}\% + \left( \frac{\text{ProcessedCount}}{\text{TotalSize}} \times \text{StageWeight}\% \right)$$
  - Broadcast `progress_percentage` over WebSockets on every batch or 5% increment.
- **Option 2: Global Count Pre-Fetch Across All Enabled Servers**:
  - Query total item count across all servers at the very beginning of `sync_all_servers()`.
  - Calculate `ProcessedTotal / GlobalTotal`.
  - **Downside**: If a server is slow or offline, starting indexing is delayed by connection timeouts.

#### Recommendation
Implement **Option 1**.

#### Acceptance Criteria
1. WebSocket `indexing_status` payload includes `progress_percentage` (0.0 to 100.0) for the active server.
2. The UI top banner renders a sleek linear progress bar filling from 0% to 100% in real-time as each server indexes.
3. Progress bar smoothly transitions across Artists (0–10%), Albums (10–35%), and Tracks (35–100%).

---

### 5. Expandable Library Statistics & Missing Artwork Inspector in Settings Modal

#### Goal
Add an expandable "Library Statistics & Health" section inside the Settings Modal displaying:
1. **Missing Artwork Counters**:
   - Total number of artists currently missing artwork (numeric count).
   - Total number of albums currently missing artwork (numeric count).
2. **Per-Server Catalog Counts**:
   - Number of indexed artists, albums, and tracks for each enabled server.
3. **Future Roadmap (Longer-Term)**:
   - A dedicated "Inspect Missing Artwork" button that opens a modal list of all items lacking artwork, with a 1-click "Force Refresh Artwork" action.

#### Constraints
- **Low Overlap & Fast Querying**: Summary count queries must use efficient SQLite `COUNT(*)` queries so expanding the section in Settings renders in < 5ms.
- **No Unrequested Code Changes**: Appended to `brainstorm.md` for roadmap planning without altering current code.

#### Known Context
- SQLite `library.db` contains `artists`, `albums`, `artist_sources`, `album_sources`, `tracks`, and `servers`.
- Missing artwork count can be computed via `SELECT COUNT(*) FROM albums WHERE thumb IS NULL OR thumb = ''`.
- Per-server counts are computed via `GROUP BY server_id` queries on `album_sources`, `artist_sources`, and `tracks`.

#### Options
- **Option 1 (Recommended)**:
  - Add an expandable collapsible accordion inside Settings Modal.
  - Fetch statistics from `GET /api/music/stats` when expanded.
  - Display clean metric cards for missing artwork and a breakdown table for per-server indexed items.
- **Option 2**: Static card embedded at the bottom of Settings.

#### Recommendation
Implement **Option 1**.

#### Acceptance Criteria
1. Clicking the expandable header in Settings reveals numeric counts for missing artwork and per-server indexed items.
2. Section expands instantly without lagging the Settings Modal UI.

---

### 6. Track ID Mismatch & Overlapping RatingKey Resolution

#### Goal
Fix track resolution so that adding a song to the queue, playing a song, or requesting track details always selects the exact intended track and never resolves to an unintended track whose Plex ratingKey (`server_track_id`) collides with SQLite's internal autoincrement `track_id`.

#### Constraints
- **Zero Ambiguity**: Looking up a track by ID must be deterministic and unambiguous across all endpoints (`/api/music/play`, `/api/music/queue/add`, `/api/music/artist-image`, etc.).
- **Backwards Compatibility**: Handle cases where frontend components or WebSocket state pass either SQLite internal `track_id` (integer) or Plex `server_track_id` (ratingKey string).
- **Multi-Server Safety**: Must work cleanly whether 1, 2, or 5 servers are enabled or disabled in TuneBox.

#### Known Context
1. **Root Cause Discovered**:
   - In `backend/services/library.py`, functions like `get_track_details`, `get_art_source_info`, `upsert_track_rating`, and `play_track` contained SQL queries matching:
     `WHERE (t.track_id = ? OR t.server_track_id = ?)`
   - When a second server (`RogNAS`) was enabled, SQLite `tracks` autoincrement `track_id` grew past 25,000 (e.g. `track_id = 25873` for *Ants in My Room*).
   - Simultaneously, local server `plex-so` contained a track (*Mrs. Brown, You’ve Got a Lovely Daughter*) whose Plex `server_track_id` (ratingKey) happened to equal `'25873'`.
   - When the user clicked "Add to Queue" on *Ants in My Room* (`track_id = 25873`), SQLite evaluated the `OR t.server_track_id = ?` clause first and selected *Mrs. Brown...* instead!

#### Options
- **Option 1: Precise Type-Aware & Priority Lookup (Recommended)**:
  - Search by SQLite primary key `WHERE track_id = CAST(? AS INTEGER)` first.
  - Only if no row matches `track_id`, fallback to matching `WHERE server_track_id = str(?) AND srv.enabled = 1`.
  - Always include `srv.enabled = 1` when resolving `server_track_id`.
- **Option 2: Prefix RatingKeys in API Payloads (e.g., `plex:25873` vs `25873`)**:
  - Distinguish internal SQLite IDs from Plex ratingKeys by prefixing Plex keys (`plex:25873`).
- **Option 3: Eliminate `OR server_track_id = ?` and Require `track_id` Everywhere**:
  - Refactor all backend endpoints and frontend components to strictly consume SQLite `track_id`.

#### Recommendation
Implement **Option 1** combined with elements of **Option 3**.

#### Acceptance Criteria
1. Clicking "Add to Queue" or playing *Ants in My Room* (`track_id = 25873`) queues *Ants in My Room* by Carter Vail, never *Mrs. Brown...* (`server_track_id = 25873`).
2. Toggling servers ON and OFF in Settings does not cause track ID cross-contamination or wrong song playback.
3. All unit tests in `backend/tests/` pass cleanly without regressions.
