# 🧠 Brainstorm: Separating Connected Users & Devices for Kiosks and Leaderboards

## Goal
Decouple the concepts of **Connected Users** (human participants for party stats and leaderboards) and **Connected Devices** (physical browser instances that can be designated as central display Kiosks), while keeping the guest connection flow fast and zero-friction without forcing users to type a device name manually.

## Constraints
- **Zero Friction for Guests**: Guests joining via QR code must NOT be forced to type both a username AND a device name.
- **Leaderboard Accuracy**: Leaderboard stats (songs queued, skips voted) must accurately attribute actions to a human user identity across session reconnects.
- **Kiosk Control**: Hosts must be able to designate specific browser sessions/devices as the central TV/kiosk display screen.
- **No Heavy Authentication**: No account registration or complex login for party guests.

## Known Context
- Currently, TuneBox tracks sessions in Redis under `connected_clients` as `{ client_id, name, role, is_display }`.
- `name` is currently serving as both the user's handle and the device identifier.
- The Admin settings panel currently groups these under "👥 Connected Users" with a "Make Display" action button.

## Risks
- **Identity Confusion**: If a user re-joins from a different tab or browser, they might create duplicate "users" on the leaderboard.
- **Generic Device Labels**: User-Agent strings alone (e.g., "Chrome on macOS") can be identical for multiple guests on similar devices.
- **State Desynchronization**: If device state and user session state are separate, disconnecting a device might leave phantom user leaderboard stats.

---

## Options

### Option 1: Automatic User-Agent Detection + Persistent Device ID (Recommended)
- **Mechanism**:
  - Automatically parse `navigator.userAgent` on client connect (e.g., `"Safari on iPhone"`, `"Chrome on Mac"`).
  - Store a unique `device_id` in `localStorage` alongside the user's `username`.
  - When connecting, client sends `{ client_id, user_name, device_label: "Safari on iPhone" }`.
- **User Experience**:
  - Guests only enter a username (or keep default guest handle).
  - Device label is auto-detected silently.
  - Host sees: `"Alex (Safari on iPhone)"` in Connected Devices list.

### Option 2: Default "User's Device" Labeling with Optional Rename
- **Mechanism**:
  - Set default device label automatically to `"{user_name}'s Device"` (e.g., `"Sam's Device"`).
  - Provide a subtle inline edit pencil icon in the Connected Devices list so hosts can rename a device if needed (e.g., rename `"Living Room iPad"`).
- **User Experience**:
  - Zero extra steps for guests.
  - Full customization control for host.

### Option 3: Mandatory Dual Input (Username + Device Name)
- **Mechanism**:
  - Prompt guest for both "Your Name" and "Device Name" on first join.
- **User Experience**:
  - High friction and annoying for party guests scanning a QR code.

---

## Recommendation
**Combine Option 1 & Option 2**:
1. Automatically detect device details via `User-Agent` parsing (e.g., `"iPhone"`, `"iPad"`, `"Mac Chrome"`).
2. Store a persistent `device_id` in `localStorage`.
3. In the backend and WebSocket registry, track both `user_name` (for leaderboards) and `device_info` (for kiosk assignment).
4. In Settings, split the panel cleanly into:
   - **👥 Active Party Guests** (for leaderboards and guest management).
   - **🖥️ Connected Display Kiosks & Screens** (showing auto-detected device labels like `"Sam's iPhone"`, with "Make Kiosk" actions).

---

## Acceptance Criteria
1. Guests joining via QR code only enter a username (or use default handle); device name is auto-detected without manual input.
2. Device model and browser (e.g., `"iPhone / Safari"`) are parsed automatically and attached to session telemetry.
3. Kiosk screens can be managed independently of guest user leaderboard stats.
