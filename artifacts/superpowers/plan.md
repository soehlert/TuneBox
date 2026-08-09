## Goal
Fix admin username resolution in `frontend/src/utils.ts` and `frontend/src/App.tsx` so the authenticated Plex username takes precedence over `instance_name` or default `"Admin"` strings when queuing tracks and displaying user stats.

## Assumptions
1. The backend already resolves and returns the real Plex `username` in `GET /api/auth/settings` (`plex_username`).
2. Storing `res.data.plex_username` in `localStorage.setItem("tunebox_admin_name", username)` upon fetching settings will make `getLocalUsername()` consistently return the user's real Plex username.
3. `instance_name` is an application/jukebox instance label (e.g. "Living Room Jukebox") and must NEVER be used as a personal user's display name or stats username.

## Plan
1. **Fix `getLocalUsername()` Resolution Logic in `utils.ts`**
   - Files: `frontend/src/utils.ts`
   - Change:
     - Check `localStorage.getItem("tunebox_admin_name")`.
     - Check `localStorage.getItem("tunebox_guest")`.
     - Remove `localStorage.getItem("tunebox_instance_name")` from user identity fallback; fallback to `"Admin"` only if no specific username exists.
   - Verify: `npm run build` in `frontend/`.

2. **Sync Authenticated Plex Username in `App.tsx`**
   - Files: `frontend/src/App.tsx`
   - Change:
     - In `GET /api/auth/settings` handler, set `localStorage.setItem("tunebox_admin_name", res.data.plex_username)` if `res.data.plex_username` is present.
     - Update admin header badge and WebSocket client registration to use `tunebox_admin_name` or `plexUsername` instead of `` `Admin (${instanceName})` ``.
   - Verify: `npm run build` in `frontend/` and `uv run python -m pytest backend/tests/`.

3. **Add Unit Tests for Admin Username Persistence in Frontend/Backend Context**
   - Files: `backend/tests/test_auth.py`
   - Change: Verify `GET /api/auth/settings` returns the authenticated Plex username properly.
   - Verify: `uv run python -m pytest backend/tests/test_auth.py`.

## Risks & mitigations
- **Risk**: Stale `tunebox_admin_name` remaining in localStorage after logging out.
- **Mitigation**: Ensure `localStorage.removeItem("tunebox_admin_name")` is executed on admin logout.

## Rollback plan
- Revert via `git checkout main` or `git restore frontend/src/App.tsx frontend/src/utils.ts`.
