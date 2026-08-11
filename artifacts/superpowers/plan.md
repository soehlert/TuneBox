# Implementation Plan: Ignore "The " when Sorting Artists and Albums

Ignore leading "The " (case-insensitive) when sorting artists and albums across TuneBox so bands like "The Beatles" appear under **B** instead of **T** in both the backend database queries and frontend UI views / alphabet fast-scroll rail.

## Proposed Changes

### Backend Database & Query Engine

#### [MODIFY] [`backend/services/library.py`](file:///Users/soehlert/projects/testing/TuneBox/backend/services/library.py)
- Update `get_indexed_artists` SQL query `ORDER BY` clause to ignore leading `"The "` when sorting alphabetically (`CASE WHEN LOWER(a.name) LIKE 'the %' THEN SUBSTR(a.name, 5) ELSE a.name END COLLATE NOCASE`).
- Update `get_indexed_albums` SQL query `ORDER BY` clause to ignore leading `"The "` when sorting alphabetically (`CASE WHEN LOWER(alb.title) LIKE 'the %' THEN SUBSTR(alb.title, 5) ELSE alb.title END COLLATE NOCASE`).
- Update `get_albums_by_genre_db` SQL query `ORDER BY` clause to ignore leading `"The "`.

#### [NEW] [`backend/tests/test_the_sorting.py`](file:///Users/soehlert/projects/testing/TuneBox/backend/tests/test_the_sorting.py)
- Add unit tests verifying `get_indexed_artists` places `"The Beatles"` in the **B** position (between `"Beach Boys"` and `"Blink-182"`).
- Add unit tests verifying `get_indexed_albums` places `"The Dark Side of the Moon"` in the **D** position.

---

### Frontend UI & Alphabet Fast-Scroll Rail

#### [MODIFY] [`frontend/src/utils.ts`](file:///Users/soehlert/projects/testing/TuneBox/frontend/src/utils.ts)
- Add helper function `getSortKey(text: string): string` that strips leading `"The "` / `"the "` (case-insensitive) from names and titles.

#### [MODIFY] [`frontend/src/components/ArtistList.tsx`](file:///Users/soehlert/projects/testing/TuneBox/frontend/src/components/ArtistList.tsx)
- Use `getSortKey(artist.name)` in `sortedArtists` `localeCompare` array sorting.
- Use `getSortKey(artist.name)` in alphabet rail fast-scroll `sortedArtists.findIndex` matching so clicking **B** jumps directly to `"The Beatles"`.

#### [MODIFY] [`frontend/src/components/BrowseViews.tsx`](file:///Users/soehlert/projects/testing/TuneBox/frontend/src/components/BrowseViews.tsx)
- Use `getSortKey(alb.title)` in `sortedAlbums` `localeCompare` array sorting.
- Use `getSortKey(alb.title)` in alphabet rail fast-scroll `sortedAlbums.findIndex` matching and manual scroll observer matching so clicking **D** jumps directly to `"The Dark Side of the Moon"`.

---

## Verification Plan

### Automated Tests
- Run `env GIT_CONFIG_GLOBAL=/dev/null uv run python -m pytest backend/tests/test_the_sorting.py`
- Run full backend test suite: `env GIT_CONFIG_GLOBAL=/dev/null uv run python -m pytest`
- Run frontend TypeScript compilation check: `npx tsc --noEmit`

### Manual Verification
- Rebuild & restart Docker stack (`docker compose up -d --build`).
- Open Artist view: Verify `"The Beatles"` appears under **B** instead of **T**.
- Click **B** on the alphabet rail: Verify the page smooth-scrolls directly to `"The Beatles"`.
