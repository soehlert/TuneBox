# Project Operating Directives

- **Branch Isolation**: NEVER work directly on the `main` branch. Always create a new feature/fix/hotfix branch before making any code or configuration changes.
- **Branch Merging (CRITICAL)**: NEVER merge any branch into `main` without explicit user approval. You must ALWAYS stop and ask the user for approval before merging.
- **Testing**: Always use `uv run pytest` to execute backend tests.

