# Project Operating Directives

- **Branch Isolation**: NEVER work directly on the `main` branch. Always create a new feature/fix/hotfix branch before making any code or configuration changes.
- **Branch Merging (CRITICAL)**: NEVER merge any branch into `main` without explicit user approval. You must ALWAYS stop and ask the user for approval before merging.
- **Testing**: Always use `uv run pytest` to execute backend tests.
- **Manual Verification Instructions**: Always tell the user step-by-step how to manually verify code fixes and features.
- **Restart Stack**: Always restart the Docker compose stack (`docker compose up -d --build` or `docker compose restart`) after making code changes so updates are immediately live in place.
- **No Trailing Ellipsis**: NEVER use trailing ellipsis (`...`) in code comments, docstrings, log messages, or UI notifications/messages (such as status updates during indexing or loading).
- **No Mock Data Outside Tests**: NEVER return or display mock data, sample fallback datasets, or mock artists/albums/tracks outside of automated test execution (`settings.testing`). Always return real empty states (`[]` / `None`) when no data exists.
- **Docker Log Verification**: Always check Docker logs (`docker compose logs backend --tail 50` or `docker compose logs -f backend`) when investigating errors, diagnosing behavior, or forming an execution plan.
- **Global Imports Only**: NEVER import anything inside of a function or method. All imports MUST be placed globally at the top of the file. If circular import issues arise, alert the user immediately so we refactor module dependencies cleanly rather than adding local inline imports.
- **No Backward Compatibility / Legacy Debt**: NEVER keep fallback code or legacy adapters to deal with old ways of doing things. This is an active local development project — make clean, direct, breaking/destructive schema & code updates as needed, and notify the user whenever destructive updates are performed.
- **Strict Track ID Standardization**: Never accept or compare both external ratingKeys and internal track_ids simultaneously. Always use translation functions (`rating_key_to_track_id`) upfront to convert external ratingKeys to internal SQLite track_ids before performing operations or duplicate checks.
- **Browser Cache / Hard Reload**: `Cmd + Shift + R` does not reliably bypass cached JS/CSS bundles. Open DevTools with "Disable Cache" enabled or use private/incognito window when verifying frontend asset changes.
- **Testing Principles**:
  - Do NOT test vendor or third-party code — test only our own application code.
  - Do NOT test trivial or obvious code (e.g. `2+2=4`).
  - Test both the happy path and the broken/error path.
  - Do NOT make network calls in tests; use a mock DB and Redis cache with `fakeredis` to get the truest representation of the real application.
  - Write meaningful tests — if bad code could easily pass the test, design a more rigorous assertion.
  - Ignore guarding against external infrastructure failures (hardware failure, network latency, etc.); focus strictly on our own application logic.
- **Frontend Toast Readability**: When catching API errors in frontend components (`TrackList.tsx`, `ArtistList.tsx`), always extract `err?.response?.data?.detail` before falling back to default strings, and set `autoHideDuration` to at least `4000ms` (4 seconds) so toasts stay visible long enough to read. Avoid 1.5s durations for error/warning alerts.
- **Standalone Track Object Attributes**: When creating standalone or mock track objects in backend services (e.g. `trigger_closing_time_mode`), always include standard `track_obj.TYPE = "track"` to satisfy `is_track_object()` validation.






