# Superpowers Execution Summary: Ignore "The " when Sorting Artists & Albums

## Verification Results
1. **Backend Unit Test Suite**: `env GIT_CONFIG_GLOBAL=/dev/null uv run python -m pytest backend/tests/test_the_sorting.py` -> **2/2 PASSED**
2. **Full Backend Test Suite**: `env GIT_CONFIG_GLOBAL=/dev/null uv run python -m pytest` -> **132/132 PASSED** in 17.90s
3. **Frontend TypeScript Compilation**: `npx tsc --noEmit` -> **0 errors**
4. **Docker Stack Deployment**: Rebuilt & restarted (`docker compose up -d --build`) -> **Containers updated & running live**

---

## Summary of Changes
- **Backend Database Query Engine**:
  - [`backend/services/library.py`](file:///Users/soehlert/projects/testing/TuneBox/backend/services/library.py): Updated SQL `ORDER BY` clauses for `get_indexed_artists`, `get_indexed_albums`, and `get_albums_by_genre_db` to evaluate `CASE WHEN LOWER(title) LIKE 'the %' THEN SUBSTR(title, 5) ELSE title END`.
  - [`backend/tests/test_the_sorting.py`](file:///Users/soehlert/projects/testing/TuneBox/backend/tests/test_the_sorting.py): Created new unit test suite testing artist and album order without leading "The ".
- **Frontend UI & Fast-Scroll Rail**:
  - [`frontend/src/utils.ts`](file:///Users/soehlert/projects/testing/TuneBox/frontend/src/utils.ts): Added helper function `getSortKey(text)` to strip leading `"The "` (case-insensitive).
  - [`frontend/src/components/ArtistList.tsx`](file:///Users/soehlert/projects/testing/TuneBox/frontend/src/components/ArtistList.tsx): Updated `useMemo` sorting, alphabet rail index matching, and manual scroll observer to use `getSortKey()`.
  - [`frontend/src/components/BrowseViews.tsx`](file:///Users/soehlert/projects/testing/TuneBox/frontend/src/components/BrowseViews.tsx): Updated `useMemo` sorting, alphabet rail index matching, and manual scroll observer to use `getSortKey()`.

---

## Review Pass
- **Blocker**: None
- **Major**: None
- **Minor**: None
- **Nit**: None

---

## Manual Verification Steps
1. Open TuneBox in your browser.
2. Navigate to **Artists** view:
   - Verify `"The Beatles"`, `"The Beach Boys"`, and `"The Clash"` display under **B** and **C** instead of **T**.
3. Click **B** on the alphabet rail:
   - Verify the view smooth-scrolls directly to `"The Beach Boys"` / `"The Beatles"`.
