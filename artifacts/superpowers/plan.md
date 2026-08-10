# Implementation Plan: Accurate Percentage-Based Progress Bar for Library Indexing

## Goal
Add a percentage progress bar and real-time detailed updates (`Indexing tracks on plex-so • 45% (11,700 / 26,000)`) to the WebSocket notification banner during library indexing.

## Assumptions
- Target Plex servers expose total item count during library section retrieval.
- WebSocket clients receive real-time progress broadcast payloads.
- Strictly **no trailing ellipsis (`...`)** in any log, comment, or notification text.

## Plan
1. **Backend Progress Tracking & Calculation**
   - Files: `backend/services/indexer.py`, `backend/websockets.py`
   - Change: Track total section items and current batch position; broadcast `index_progress` payload with percentage and formatted message.
   - Verify: `uv run python -m pytest backend/tests/test_indexer.py`

2. **Frontend Progress Bar UI & WebSocket Integration**
   - Files: `frontend/src/App.tsx`
   - Change: Store `indexingProgress` state, render percentage progress bar (`width: ${percentage}%`) with gradient styling, and format status text.
   - Verify: `npm run build` in `frontend/`

3. **Live Verification & Container Restart**
   - Files: Docker Compose environment
   - Change: Restart containers (`docker compose up -d --build` & `docker compose restart`) and trigger manual re-index to verify progress bar in browser.
   - Verify: Manual re-index test on `http://localhost:3000`.

## Risks & Mitigations
- **Risk**: Rapid WebSocket progress events overwhelming the browser.
- **Mitigation**: Progress events are emitted per batch (every 500 items), limiting updates to ~1-2 events per second.

## Rollback Plan
- Revert changes via `git checkout main`.
