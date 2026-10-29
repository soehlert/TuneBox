# 👑 Admin Features & Capabilities

TuneBox provides administrative controls for host users to manage playback, queue order, connected clients, and system settings.

## 🔐 Admin Authentication
Admin privileges are granted via an `X-Admin-Token` session token established during initial setup or configuration. Admin actions are validated on both the backend REST API endpoints and real-time WebSocket events.

---

## ⚡ Admin Capabilities Summary

| Capability | Description | Location |
| :--- | :--- | :--- |
| **Drag & Drop Queue Reorder** | Reorder any queued tracks in real-time via drag handle icon (desktop & mobile). | Queue Sidebar / Modal |
| **Move to Next** | Instantly push any song in the queue to be played next. | Track Menu (⋮) in Queue |
| **Force Skip** | Override guest skip vote counts and immediately skip to the next track. | Player Bar (`Force Skip` button) |
| **Stop Queue & Playback** | Stop active speaker playback, clear now-playing state, and drain all items from the queue. | Queue Header & Host Settings |
| **Queue Item Deletion** | Remove specific songs or clear upcoming items from the queue. | Track Menu (⋮) & Host Settings |
| **Multi-Server Library Management** | Enable or disable multi-server catalog discovery across primary and shared Plex servers. | Host Settings Modal (`⚙️`) |
| **Smart Autoplay Control** | Enable or disable dynamic background track auto-seeding. | Host Settings Modal -> Queue |
| **Display / Kiosk Delegation** | Set connected client sessions as shared kiosk screens or guest controllers. | Host Settings Modal -> Connected Users |

---

## 🔀 Queue Management

### 1. Drag-and-Drop Reordering
Admins can reorder items in the active queue:
- **Desktop**: Click and drag the drag handle icon (`drag_indicator`) next to any queued song. Drop indicator lines show exact placement insertion.
- **Mobile**: Touch and drag the drag handle icon to move tracks up or down in the queue.

### 2. Move to Next
To move a song to the top of the upcoming queue:
1. Open the track action menu (`⋮`) on any item in the queue.
2. Select **Move to Next**.
3. The track will leapfrog to the top of the queue right after the currently playing song.

### 3. Force Skip
When guests are voting to skip a song, the host can bypass vote thresholds:
- Click the blue **Force Skip** button on the playback bar.
- TuneBox immediately skips the currently playing track and advances the queue.

### 4. Stop Queue & Playback
- Click **⏹️ Stop** in the queue header or **⏹️ Stop Queue & Playback** in Host Settings.
- TuneBox sends a stop command to the active Plex player, resets local playback tracking, wipes the now-playing track, and drains all items from the queue.

### 5. Remove & Clear
- **Individual Delete**: Select **Remove from Queue** in the track menu (`⋮`).
- **Clear Queue**: Click **Clear Queue** in Host Settings to purge upcoming guest-queued songs (preserving current track if active).

---

## ⚙️ Host Settings & Display Control

### 1. Auto-Collapsing Accordions & Clean UX
- The Settings Modal features auto-collapsing accordions: expanding one section automatically collapses all others to keep the interface uncluttered.
- Designed with scrollbar-free styling (`hide-scrollbar`) while maintaining smooth touch and mouse scrolling.

### 2. Multi-Server Library Selection & Settings Protection
- Hosts can check or uncheck accessible Plex Media Servers under **Plex Media Servers (Unified Catalog)**. Selected servers default strictly to your primary server until remote servers are explicitly enabled.
- The **Save Settings** button persists settings with a green status message without auto-closing the modal.
- Closing the modal with unsaved changes prompts a confirmation dialog (`TuneBoxDialog`) offering **Save Settings**, **Discard**, or **Keep Editing**.

### 3. Display / Kiosk Mode & Admin Delegation
Admins can view all connected user sessions under **Active Party Guests** and **Connected Devices & Kiosks** in Settings to:
- Designate specific devices as dedicated display kiosks (**Make Kiosk** / **Remove Kiosk**).
- Promote or demote connected guest devices (such as a host's phone) to Admin (**Make Admin** / **Remove Admin**), pushing the `ADMIN_TOKEN` live over WebSocket.
- Rename connected guests (enforcing unique nicknames across all active sessions).
