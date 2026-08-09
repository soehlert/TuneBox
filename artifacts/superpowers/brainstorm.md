## Goal
Evaluate Plex PIN authentication vs current admin name resolution, and resolve the issue where `instance_name` (or fallback `"Admin"`) overrides the admin's logged-in username in stats/queues.

## Constraints
- **Framework & Stack**: React (Frontend), FastAPI (Backend), Plex API via `MyPlexAccount` / `MyPlexPinLogin`.
- **Existing Behaviors**: Guest sessions store custom guest names; Admin sessions store `tunebox_admin_token` and `tunebox_admin_name`.

## Known Context
- **Plex PIN Authentication**:
  - When an admin logs into TuneBox using Plex PIN linking (`/api/auth/pin`), Plex authenticates the user against `plex.tv`.
  - Upon successful PIN claim, `MyPlexAccount(token=token)` fetches the real authenticated Plex `username` (e.g. `"sadie"` or `"soehlert"`).
  - The backend returns `"username"` from `GET /api/auth/settings` and during PIN verification.
- **Root Cause of Username Being Overridden**:
  - `getLocalUsername()` in `frontend/src/utils.ts` currently falls back to `localStorage.getItem("tunebox_instance_name") || "Admin"` when `tunebox_admin_name` is missing or when fallback logic fires.
  - In `frontend/src/App.tsx`, admin registration and header badges fell back to `` `Admin (${instanceName})` `` instead of using the fetched Plex username.

## Risks
- If an admin token is present in localStorage but `tunebox_admin_name` hasn't been cached locally yet, queuing a song sends `username: "Admin"` or `username: instanceName` to stats instead of the real username.

## Options (2–4)

### Option 1: Store & Synchronize Plex Username on Admin Auth / Settings Fetch (Recommended)
- **Summary**:
  - Store the authenticated Plex `username` in `localStorage.setItem("tunebox_admin_name", username)` whenever `/api/auth/settings` or PIN check succeeds.
  - In `getLocalUsername()` (`utils.ts`), prioritize `tunebox_admin_name` > `guest.name` > `"Admin"`. Remove `instance_name` fallback from username resolution so stats never attribute actions to instance names.
- **Pros**: Ensures `getLocalUsername()` always returns the authenticated Plex username (e.g. `"sadie"`), ensuring stats properly attribute queue additions to the logged-in user.
- **Cons**: None.

### Option 2: Tie Admin Actions Strictly to Backend Auth Session
- **Summary**: Have the backend inject `added_by` from the active Plex token username automatically on the server side instead of trusting frontend `username` query parameters.
- **Pros**: Completely immune to frontend storage mismatches.
- **Cons**: Requires refactoring multiple backend queue endpoints to inspect request authorization headers.

## Recommendation
**Option 1** is recommended. We will update `utils.ts` and `App.tsx` so the authenticated Plex username returned by `/api/auth/settings` is stored as `tunebox_admin_name` and used consistently everywhere.

## Acceptance Criteria
- [ ] Admin username (e.g. `"sadie"`) is stored in `tunebox_admin_name` upon loading settings or logging in.
- [ ] `getLocalUsername()` strictly returns `tunebox_admin_name` for admin sessions and never returns `instance_name`.
- [ ] Admin header badge and WebSocket presence display the Plex username instead of `Admin (InstanceName)`.
- [ ] Queue additions by admin log under the Plex username in stats.
