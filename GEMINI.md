# Project Operating Directives

- **Branch Isolation**: NEVER work directly on the `main` branch. Always create a new feature/fix/hotfix branch before making any code or configuration changes.
- **Branch Merging**: NEVER merge any branch into `main` without explicit user approval.
- **Testing**: Always use `uv run pytest` to execute backend tests.
