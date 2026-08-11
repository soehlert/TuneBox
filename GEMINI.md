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
- **Browser Cache / Hard Reload**: `Cmd + Shift + R` does not reliably bypass cached JS/CSS bundles. Open DevTools with "Disable Cache" enabled or use private/incognito window when verifying frontend asset changes.
- **Testing Scope**: Do NOT run backend tests (`uv run pytest`) when ONLY updating frontend JavaScript, TypeScript, or CSS files.





