## Goal
1. Design a sane, local mechanism for hosts/admins to manually override TuneBox deduplication results (force-merge separate entries, split false-positive merges, and lock match states).
2. Fix missing artist artwork for items residing on secondary/remote Plex servers without requiring write access to remote Plex servers.

## Constraints
- **Read-Only Remote Access**: TuneBox must never attempt to write metadata or lock fields back to remote Plex Media Server databases.
- **Local Persistence**: All manual merge overrides, unmerges, and match locks must be stored in TuneBox's local persistent store (Redis/SQLite).
- **Multi-Server Key Disparity**: An artist or album has different local `ratingKey` IDs on each Plex server (e.g. AC/DC is ID `101` on Server A and ID `504` on Server B). Overrides must identify items using composite keys `(server_id, ratingKey)` or canonical Plex GUIDs.

## Known Context
- **Deduplication Engine**: `backend/services/plex.py` currently merges artists and albums across servers using canonical Plex GUIDs (`plex://artist/...`) and title normalization (`re.sub(r"[^a-z0-9]", "", title)`).
- **Image Proxying (`fetch_art`)**: TuneBox proxies images from Plex using `/api/music/artist-image/{artist_id}?server_id={server_id}`.
- **Why Remote Artist Pictures Fail**:
  1. Secondary server artist images fail if `server_id` is omitted in frontend image URLs, causing TuneBox to search the primary server (`plex-so`) where the secondary `artist_id` doesn't exist.
  2. Plex Media Server does not automatically download artist bio photos unless agents match the artist.
  3. When an artist is merged across multiple servers, if Server A lacks an artist photo, TuneBox currently does not attempt to fetch art from candidate Servers B or C that *do* have photos.

## Risks
- **ID Instability**: Raw integer `ratingKey`s on Plex can change if a server library is recreated. Storing overrides solely by integer ID could orphan locks. *(Mitigation: Use canonical GUIDs when available, falling back to composite `server_id:ratingKey` pairs)*.
- **UI Clutter**: Adding matching controls to everyday guest views will degrade the simple jukebox experience. *(Mitigation: Keep match/unmerge/lock controls strictly within Host Settings / Admin views)*.

## Options

### Option 1: Local Override & Lock Registry with Multi-Server Image Fallback (Recommended)
- **Local Override Registry**:
  - Maintain a local Redis hash `manual_dedupe_overrides` with three rule types:
    1. **Force Merge**: Explicitly group `[serverA:id1, serverB:id2]` into a single entity regardless of title/GUID differences.
    2. **Unmerge / Split**: Explicitly separate `serverA:id1` from `serverB:id2` regardless of matching titles/GUIDs.
    3. **Match Lock**: Flag an artist/album entity as `"locked": true`, instructing deduplication routines to bypass auto-merging or auto-splitting for that entity.
- **Multi-Server Artwork Fallback**:
  - Update `fetch_art` for merged entities: if Server A returns 404 or has no `thumb`, automatically check connected candidate Servers B and C for that merged artist before giving up.
  - Ensure frontend image URLs pass `server_id` or query the unified entity.
- **Admin UI**:
  - Add an "Edit Match & Artwork" modal accessible in Host Settings -> Catalog Audit or from the Artist detail view.

### Option 2: CLI / Audit Script Interactive Overrides
- Extend `audit_deduplication.py` with an interactive CLI mode (`--fix`) that prompts the user to approve/reject missed or suspect merges and saves choices to a JSON config file.
- *Pros*: Quick to script; minimal frontend UI needed.
- *Cons*: Host must run CLI commands in terminal to fix catalog mistakes.

### Option 3: External Artwork Provider Fallback (Fanart.tv / MusicBrainz)
- When no connected Plex server has an artist photo, query Fanart.tv or Last.fm APIs directly using artist name/MBID to fetch high-res artist posters.
- *Pros*: Fills in missing artist pictures even if all Plex servers lack photos.
- *Cons*: Requires external API keys and network calls to third-party services.

## Recommendation
Implement **Option 1**:
1. Store local deduplication overrides and lock states in Redis (`manual_dedupe_overrides`).
2. Add a clean "Edit Match" modal in Host Settings for force-merging, unmerging, and locking items.
3. Enhance `fetch_art` image proxying to try all candidate servers of a merged entity, and ensure `server_id` is properly passed from the frontend.

## Acceptance Criteria
1. Admin can force-merge two separate artists/albums into one unified entry.
2. Admin can unmerge incorrectly matched artists/albums into separate entries.
3. Admin can toggle a "Lock" state on any artist/album that prevents background deduplication scans from changing its match state.
4. Remote server artist pictures render correctly in TuneBox by passing `server_id` and falling back across candidate servers for merged entities.
5. All override rules are stored locally in TuneBox without writing to remote Plex servers.
