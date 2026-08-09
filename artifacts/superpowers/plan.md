## Goal
Enable clicking a queue track (or its artwork/title) in the Queue panel to navigate directly to that track's Album view (`/albums/:albumId/tracks`) in the main viewing area.

## Assumptions
1. Since this is local dev, all tracks stored in the Redis queue will strictly include `album_id` in their queue payload. No fallback or legacy data handling code is needed.
2. Clicking a queue track's title/artwork will navigate to `/albums/${track.album_id}/tracks` using React Router's `useNavigate()` hook.
3. Queue action buttons (delete, drag handle, move to top) stop click propagation so clicking action buttons does not trigger album navigation.

## Plan
1. **Include `album_id` in Redis Queue Payload**
   - Files: `backend/services/redis.py`
   - Change: Always set `"album_id": getattr(song, "album_id", getattr(song, "parentRatingKey", None))` in the `song_data` dict inside `add_to_queue_redis`.
   - Verify: `uv run pytest backend/tests/test_redis.py`

2. **Add Album Navigation to Queue Component**
   - Files: `frontend/src/components/Queue.tsx`, `frontend/src/components/Queue.css`
   - Change: Import `useNavigate` in `Queue.tsx`. Add `onClick` on track title/artwork to execute `navigate(`/albums/${track.album_id}/tracks${sParam}`)`. Add cursor pointer styling and hover styling in `Queue.css`.
   - Verify: `uv run python -m pytest backend/tests/` and verify UI build via `npm run build` in `frontend/`.

3. **Add Unit Test for `album_id` Serialization**
   - Files: `backend/tests/test_redis.py`
   - Change: Verify `album_id` is present in Redis queue track serialization output.
   - Verify: `uv run pytest backend/tests/test_redis.py`

## Risks & mitigations
- **Risk**: Clicking drag handle or action buttons could trigger navigation if event propagation isn't stopped.
- **Mitigation**: Add `e.stopPropagation()` on all action button and drag handle click/touch handlers.

## Rollback plan
- Revert changes via `git checkout main` or `git revert` on `feature/queue-item-album-navigation`.
