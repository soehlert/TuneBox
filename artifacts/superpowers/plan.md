# Implementation Plan: Connected Libraries Pill Enhancements & Text Cleanup

## Goal
Remove redundant `"Queue songs to TuneBox"` text on album track views, restyle Connected Libraries pill in subtle pink (`#ff4d94`, `rgba(191, 9, 94, 0.15)`), and position on a separate line below the album title.

## Assumptions
- Changes are isolated to `frontend/src/components/TrackList.tsx`.

## Plan
1. **Frontend Track Header Clean Up & Pink Pill Styling**
   - Files: `frontend/src/components/TrackList.tsx`
   - Change: Remove "Queue songs to TuneBox" element, restyle connected libraries badge to magenta/pink theme, and wrap in a dedicated row div.
   - Verify: `cd frontend && npm run build`

2. **Live Docker Stack Restart & Verification**
   - Files: Docker Compose environment
   - Change: Restart Docker stack and visually inspect album track header.
   - Verify: Visual inspection on `http://localhost:3000`.

## Risks & mitigations
- **Risk**: None (UI styling and layout adjustment).
- **Mitigation**: Verified via TypeScript build and visual rendering.

## Rollback plan
- Revert via `git checkout main`.
