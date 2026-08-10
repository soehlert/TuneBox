# Project Operating Directives

- **Branch Isolation**: NEVER work directly on the `main` branch. Always create a new feature/fix/hotfix branch before making any code or configuration changes.
- **Branch Merging (CRITICAL)**: NEVER merge any branch into `main` without explicit user approval. You must ALWAYS stop and ask the user for approval before merging.
- **Testing**: Always use `uv run pytest` to execute backend tests.
- **Manual Verification Instructions**: Always tell the user step-by-step how to manually verify code fixes and features.
- **Restart Stack**: Always restart the Docker compose stack (`docker compose up -d --build` or `docker compose restart`) after making code changes so updates are immediately live in place.
- **No Trailing Ellipsis**: NEVER use trailing ellipsis (`...`) in code comments, docstrings, log messages, or UI notifications/messages (such as status updates during indexing or loading).
- **No Mock Data Outside Tests**: NEVER return or display mock data, sample fallback datasets, or mock artists/albums/tracks outside of automated test execution (`settings.testing`). Always return real empty states (`[]` / `None`) when no data exists.
- **No Manual Seeking**: Do NOT code, assume, or suggest manual seeking in TuneBox / Plexamp playback controls.


