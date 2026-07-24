# Finish Summary - Blue Server Status, Configurable Preseed Count & Stop Button Cleanup

## Verification Summary
- **Backend Test Suite**: `uv run python -m pytest backend/tests` -> **84 passed in 9.23s**
- **Preseed API Unit Tests**: `uv run python -m pytest backend/tests/test_mock_music.py` -> **11 passed in 0.16s**

## Summary of Changes
1. **Server Choice Status Badge Color**: Updated `App.tsx` server status badge styling for `connecting` and `enabled` states to use blue (`#3498db`, `rgba(52, 152, 219, 0.15)`, `1px solid rgba(52, 152, 219, 0.4)` and `🔵 Connecting` / `🔵 Enabled`).
2. **Configurable Playlist Pre-seeding**:
   - Updated `POST /api/music/playlists/{playlist_id}/seed` and `seed_queue_from_playlist` to accept an optional `count` parameter (default 10).
   - Used `min(len(tracks), max(1, count))` to safely cap sample size so if count > playlist length, it seeds the entire playlist without throwing an error.
   - Added `preseedCount` state and number input in Host Settings Queue Management section.
   - Renamed button back to **"Preseed Queue"** (and **"Preseeding..."** when loading).
3. **Queue Header Stop Button Removal**: Removed the `⏹️ Stop` button from `Queue.tsx` header bar, leaving the Stop Queue action exclusively in Host Settings next to Clear Queue.

## Artifact Check
- `artifacts/superpowers/plan.md`
- `artifacts/superpowers/execution.md`
- `artifacts/superpowers/finish.md`
