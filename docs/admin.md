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
| **Queue Item Deletion** | Remove specific songs or clear the entire queue. | Track Menu (⋮) & Queue Header |
| **Plex Account & Server Settings** | Change linked Plex credentials, target server, and active playback client. | Host Settings Modal (`⚙️`) |
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

### 4. Remove & Clear
- **Individual Delete**: Select **Remove from Queue** in the track menu (`⋮`).
- **Clear Queue**: Click **Clear Queue** in the queue header to purge all guest-queued songs.

---

## ⚙️ Host Settings & Display Control

### 1. Settings Form Protection
- The **Save Settings** button sits at the bottom footer of the Settings Modal.
- If you edit settings without saving, closing the modal prompts an unsaved changes warning dialog (`TuneBoxDialog`) giving options to **Save Settings**, **Discard**, or **Keep Editing**.

### 2. Display / Kiosk Mode
Admins can view all connected user sessions under **Connected Users** in Settings and designate specific devices as dedicated display kiosks.
