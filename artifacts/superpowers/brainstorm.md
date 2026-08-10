# Superpowers Brainstorm: Missing Artwork Inspector & Plex Fixer Modal

## Goal
Provide an interactive inspector modal accessible by clicking the "Missing Artist Art" or "Missing Album Art" cards in Settings, displaying a filterable list of all items lacking artwork on the primary/admin server with 1-click tools to resolve missing artwork.

## Constraints
- **Primary Server Scope Only**: Only items sourced from the user's primary/admin Plex server (`srv.is_primary = 1`) are inspected, as the admin cannot edit metadata on remote friend servers.
- **Fast Pagination / Lazy Loading**: Must support large libraries (e.g. 50+ missing artwork items) without modal scrolling lag.
- **No Automatic Image Overwrites**: Must preserve Plex metadata hierarchy and allow forced artwork re-indexing per item.

## Known context
- SQLite database `library.db` contains `artists`, `albums`, `artist_sources`, and `album_sources`.
- Items with missing artwork are identified by `(thumb IS NULL OR thumb = '' OR thumb LIKE '/api/music/%')` joined with `srv.is_primary = 1`.
- TuneBox already has `fetch_and_cache_art` and Redis artwork caching services in `backend/services/plex.py`.

## Risks
- **Large Missing Item Lists**: If hundreds of items lack artwork, rendering all items at once in React could slow down the modal. (Mitigated by server-side pagination / search filtering).
- **Plex API Metadata Refresh Latency**: Re-fetching artwork from Plex API for a missing item requires network round-trip (~200ms).

## Options

### Option 1: Clickable Metric Cards Opening a Filterable `MissingArtworkModal` (Recommended)
- **UI Flow**:
  - Click the **Missing Artist Art** or **Missing Album Art** cards in Settings.
  - Opens a dedicated glassmorphism modal listing missing items for the primary server.
  - Search bar to quickly filter items by name.
- **Features Per Item**:
  - Item name + Album/Artist details.
  - **"Copy Name" button** for quick pasting into Plex Web search.
  - **"Re-Sync Artwork" button** that triggers a targeted single-item artwork fetch from the primary Plex server and clears Redis cache for that item.
- **Backend API**:
  - `GET /api/stats/missing-art?type=artist|album`
  - `POST /api/stats/refetch-art?type=artist|album&id=123`

### Option 2: Inline Expandable List inside Settings Modal
- Embed the list directly under the metric cards inside the Settings accordion.
- **Downside**: Makes the Settings Modal very long and crowded.

### Option 3: Direct Deep-Links to Plex Web App Edit View
- Include a button on each missing item row opening the item directly inside Plex Web (`http://<server_ip>:32400/web/index.html#!/server/...`).
- **Downside**: Requires knowing the external Web UI URL for every Plex server setup.

## Recommendation
Implement **Option 1**. It keeps the Settings Modal clean, provides an intuitive workflow to inspect missing items, and includes a 1-click single-item re-sync action after fixing artwork in Plex.

## Acceptance Criteria
1. Clicking **Missing Artist Art** or **Missing Album Art** in Settings opens the `MissingArtworkModal`.
2. Modal displays only items belonging to the user's primary/admin Plex server.
3. Users can search missing items by title and click "Re-Sync Artwork" to refresh thumbnail URLs live.
