## Goal
Clarify the purpose, behavior, copy, visual styling, and placement of queue management admin controls (`Clear Queue` vs `Stop Queue & Playback`).

## Constraints
- **Framework & Stack**: React / Vite / Material UI / Python FastAPI / Redis.
- **Role Scoping**: Admin controls require admin credentials (`X-Admin-Token` header).
- **Core Requirement**: Must avoid accidental queue/playback destruction while keeping common party/host actions easy to understand and execute.

## Known context
- Currently in `frontend/src/App.tsx` (under Admin Controls drawer/panel):
  - **`Clear Queue`** calls `POST /api/music/clear-queue`.
    - *Behavior*: Clears upcoming queue tracks (indexes 1..N), but **keeps the currently playing track (index 0)** playing.
  - **`Stop Queue & Playback`** calls `POST /api/music/stop-queue`.
    - *Behavior*: Stops PlexAmp player playback, halts the time tracker, clears `now_playing`, and **wipes the entire queue including the current track (index 0)**.
- **UI Problem**:
  - The current buttons are generic side-by-side solid color rectangular blocks (`#e67e22` orange vs `#ff4d4d` red).
  - "Clear Queue" sounds like it wipes everything (including current track), which causes confusion since it actually preserves the active song.
  - The icons and labels don't visually reflect the non-destructive (soft clear) vs destructive (hard stop & reset) difference.

## Risks
- **Accidental Disruption**: An admin wanting to just clear upcoming queued guest requests accidentally hits "Stop Queue & Playback", cutting off party music instantly.
- **UI Clutter**: Adding overly verbose explanations directly on the main admin panel.

## Options (2–4)

### Option 1: Keep Both Buttons, Re-label, Re-style, and Add Distinct Micro-copy & Icons (Recommended)
- **Concept**:
  - Keep both functions, as "clear upcoming requests" vs "emergency stop everything" serve two distinct real-world needs (e.g., party host clearing bad guest requests vs shutting down the jukebox).
  - **Button 1 (Upcoming queue)**:
    - *Label*: **"Clear Upcoming Queue"** (or **"Clear Up Next"**)
    - *Icon*: `playlist_remove` or `cleaning_services`
    - *Sub-text / Tooltip*: *"Clears upcoming songs, keeps current song playing"*
    - *Styling*: Outline or subtle warning style (e.g. Amber/Orange outline `#f5a623`).
  - **Button 2 (Stop & Drain Everything)**:
    - *Label*: **"Stop Music & Reset Queue"** (or **"Stop Playback & Clear All"**)
    - *Icon*: `stop_circle`
    - *Sub-text / Tooltip*: *"Stops player immediately and wipes all songs"*
    - *Styling*: Solid red destructive action style (`#e74c3c` or `#d32f2f`) with prompt confirmation modal.

### Option 2: Single Primary Action with a Secondary Action Dropdown / Toggle
- **Concept**:
  - Provide a single primary action button **"Clear Queue"** with a dropdown/split-button or radio toggle selecting scope:
    - `(•) Clear Up Next (keep current track)`
    - `( ) Stop & Clear Everything`
- **Pros**: Reduces button count on screen.
- **Cons**: Requires an extra click/toggle to switch modes, hiding common admin actions.

### Option 3: Move "Clear Upcoming Queue" into Queue Drawer Header, Keep "Stop Playback" in Admin Modal
- **Concept**:
  - Place a small "Clear Upcoming" icon/button inside the Queue panel header (`Queue.tsx`), accessible directly next to the Queue tab.
  - Keep the full emergency "Stop Playback & Reset" button inside Admin Settings.
- **Pros**: Contextually places queue clearing directly where the queue is viewed.
- **Cons**: Puts destructive/admin actions in public queue view unless hidden behind admin auth tokens.

## Recommendation
**Option 1** is recommended:
1. **Keep both buttons** because preserving current music while wiping guest requests vs shutting down playback are fundamentally different actions.
2. **Rename for absolute clarity**:
   - **"Clear Upcoming Queue"** (preserves current song)
   - **"Stop Playback & Clear All"** (stops player + wipes current song)
3. **Sensible Hierarchical Styling**:
   - **"Clear Upcoming Queue"**: Soft warning style (Amber border/ghost button or muted orange button with `playlist_remove` icon).
   - **"Stop Playback & Clear All"**: Distinct danger/destructive style (Red background with `stop_circle` icon) requiring confirmation modal.
   - Include a concise 1-line helper text underneath each button explaining exact behavior.

## Acceptance Criteria
- [ ] Admin panel clearly distinguishes between clearing upcoming tracks vs stopping current playback and clearing all tracks.
- [ ] Button labels explicitly state "Clear Upcoming Queue" and "Stop Playback & Clear All".
- [ ] Visual hierarchy reflects non-destructive (upcoming queue clear) vs destructive (full stop & wipe).
- [ ] Clicking "Clear Upcoming Queue" prompts confirmation and leaves active track playing.
- [ ] Clicking "Stop Playback & Clear All" prompts confirmation, halts player, and empties entire queue.
