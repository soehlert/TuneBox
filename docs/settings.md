# ⚙️ TuneBox Frontend Settings & Host Controls

This document details the configuration options and host control features in the TuneBox Frontend Settings interface, as well as **Admin Authentication**.

---

## 🔒 Admin Access & Security

TuneBox separates capabilities into host/admin actions and guest actions:
- **Party Guests**: Can browse artists, albums, and tracks, add items to the queue, and cast votes to skip the current track.
- **Host / Admin**: Has access to the **Settings Gear Button** (located on the right side of the **bottom playback controls bar**) and administrative backend actions.

### How Admin Authentication Works
1. **Admin Token**: During the initial Setup Wizard, an `ADMIN_TOKEN` is saved to `.env` and stored in the host browser's `localStorage`.
2. **Header Authorization**: Administrative actions (such as clearing the queue, setting display devices, or changing server settings) automatically include the `x-admin-token` HTTP header:
   ```http
   POST /api/music/clear-queue
   x-admin-token: <your_admin_token>
   ```
3. **Backend Middleware**: The FastAPI backend verifies the `x-admin-token` header against `ADMIN_TOKEN`. Unauthenticated requests to admin endpoints return `HTTP 401 Unauthorized`.
4. **Guest View**: Guests accessing TuneBox do not have the `ADMIN_TOKEN` and will not see the Settings gear button on their bottom bar.

---

## 🎛️ Settings Reference

Clicking the **Settings Gear Button** (⚙) on the right side of the **bottom player bar** opens the Settings Modal:

![Host Settings Modal](images/settings_modal.png)

### 1. Plex Username
- **Description**: Displays and configures the username associated with your Plex account.

### 2. TuneBox Instance Name
- **Description**: Custom display name for this jukebox instance (e.g., *"Living Room Party Box"*).
- **Effect**: Displayed in the bottom player bar and header across connected devices.

### 3. Plex Player (Playback Device)
- **Description**: Dropdown selecting the target Plex playback device:
  - **Selected Player**: Sends queued tracks to play on that specific Plex client or speaker.
  - **`None (Released / Disconnected)`**: Releases TuneBox's hold on the player, leaving the player free for direct manual use.
- **Refresh Button**: Scans your local network and Plex account to discover newly turned-on Plex players without restarting TuneBox.

### 4. Plex Media Server
- **Description**: Dropdown selecting which linked Plex Media Server TuneBox queries for music tracks, albums, artists, and artwork.

### 5. Connected Guest Devices Manager
- **Description**: Live list of all devices (phones, tablets, displays) currently connected to the jukebox via WebSockets.
- **Features**:
  - **Rename Device**: Assign friendly names to connected devices (e.g., rename *"Device-82f"* to *"Alex's Phone"*).
  - **Set / Unset Display Device**: Designates a device as a **Display Device**, displaying the QR code prominently while remaining a fully functional TuneBox interface for browsing and queueing.
  - **Disconnect Device**: Forcefully disconnects a guest session.

### 6. Clear Playback Queue
- **Description**: An administrative action button to wipe all upcoming queued tracks.
- **Note**: The queue (`Queue.tsx`) is an **"Up Next" read-only list**. There is no drag-and-drop reordering or individual track deletion in the queue UI; admins use **Clear Queue** to flush the queue when needed.
