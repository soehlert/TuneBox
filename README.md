# 🎵 TuneBox

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

**TuneBox** is a modern, collaborative party jukebox that turns your personal music library into a shared, interactive listening experience. Designed for parties, gatherings, and shared spaces, TuneBox allows guests to queue up songs from any device without an app or account.

---

## ✨ Features

- 🎧 **Multi-Server Unified Music Library**: Streams, indexes, and merges music across your primary home Plex server and shared remote servers simultaneously
- 🏆 **Smart Quality-Based Track Prioritization**: When identical albums or tracks are found on multiple servers, TuneBox automatically selects and streams the highest audio quality (Lossless FLAC/ALAC > High Bitrate MP3)
- 🌐 **Multi-Library Badges & Modals**: Visual badges (`🌐 X libraries`) indicate items hosted across multiple servers. Tapping a badge opens a custom glassmorphism modal detailing all hosting libraries
- 📱 **Guest Access via QR Code**: Guests scan a QR code at your party to browse music and queue tracks instantly—no app installation or accounts required
- ⚡ **Real-Time Queue Synchronization**: Everyone's device stays in sync. Queue changes, track progress, and playback state update instantly across all connected clients
- 🗳️ **Collaborative Skip Voting**: Party guests vote in real-time to skip songs. When the threshold is reached, TuneBox skips to the next track
- ⏹️ **Admin Stop & Queue Drain Control**: Admin capability to stop active speaker playback, clear now-playing state, and wipe the entire queue immediately
- 📋 **Playlist Pre-Seeding**: Host can seed TuneBox from Plex playlists. Guest selections automatically leapfrog ahead of pre-seeded tracks
- 📻 **Smart Autoplay Mode**: Keeps music playing when the guest queue runs low by dynamically seeding related tracks. Guest selections automatically leapfrog fallback tracks
- 🏆 **Party Stats & Leaderboards**: Track party stats (top queue contributors, skip voters, most skipped tracks) to see who is driving the vibe
- ⚙️ **Refined Settings Modal**: Clean, auto-collapsing accordions with scrollbar-free design, non-closing save confirmations, and primary server defaults

---

## 📷 Screenshots

### 🔐 Setup Wizard - Initial Configuration
![Setup Wizard](./docs/images/setup_wizard.png)
*Welcome screen to configure your Plex username and TuneBox instance name.*

### 🔑 Setup Wizard - Plex PIN Authorization
![Plex PIN Authorization](./docs/images/plex_pin_auth.png)
*Secure authorization via Plex account PIN link.*

### 🎛️ Setup Wizard - Server & Player Selection
![Select Plex Server](./docs/images/select_plex_server.png)
*Select your target Plex Media Server and active playback device.*

### 📱 Artist List & Guest QR Access
![Artist List & Guest QR Code](./docs/images/guest_qr_access.png)
*Browse music artists and scan the QR code on the central display screen to join the session instantly.*

### 💿 Artist Albums
![Led Zeppelin Albums](./docs/images/led_zeppelin_albums.png)
*Explore complete artist discographies with high-resolution album artwork.*

### 🎶 Album Track List & Player Queue
![Led Zeppelin Tracks & Player](./docs/images/led_zeppelin_tracks.png)
*View album track listings, queue songs to TuneBox, and monitor active playback.*

### ⚙️ Host Settings Modal
![Host Settings Modal](./docs/images/settings_modal.png)
*Configure play source, destination, queue management, and users.*

### 🏆 TuneBox Party Leaderboards & Stats
![TuneBox Leaderboards](./docs/images/leaderboard.png)
*View party stats to see who requested the most tracks, who cast the most skip votes, and whose music is getting skipped.*

---

## 🚀 Quickstart

Get TuneBox up and running on your local network using Docker Compose:

### Prerequisites
- [Docker](https://docs.docker.com/get-docker/) & Docker Compose
- A running [Plex Media Server](https://www.plex.tv/) with a Music library

### Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/soehlert/TuneBox.git
   cd TuneBox
   ```

2. **Start the containers:**
   ```bash
   docker compose up -d
   ```

3. **Open TuneBox:**
   Navigate to `http://localhost` (or your server's IP address) in any web browser. You will be greeted by the **Setup Wizard** to link your Plex Media Server and select your active playback player.

---

## 📖 Documentation

For in-depth details on system architecture, custom deployment setups, development guidelines, and API specifications, explore the documentation suite:

- 👑 **[Admin Features & Capabilities Guide](docs/admin.md)**: Overview of queue reordering, force skipping, host settings, and display kiosk controls.
- 🏛️ **[System Architecture](docs/architecture.md)**: Deep dive into the tech stack (FastAPI, React, Vite, Redis, Plex API) and component flow diagrams.
- 🛠️ **[Developer Guide](docs/development.md)**: Environment setup, coding standards, local mock library testing, Makefile commands, and step-by-step developer walkthroughs.
- 🌐 **[Deployment & Hosting Guide](docs/deployment.md)**: Production reverse-proxy configuration (Nginx, SSL/HTTPS) and direct LAN deployment instructions.
- 🔌 **[API & WebSocket Reference](docs/api.md)**: Complete specification of REST endpoints and real-time WebSocket protocol events.

---

## 🤖 Attribution & Credits

> **Note**: The architecture, user experience, and design of this project were directed and architected by the project maintainer, with implementation assistance from an AI/LLM coding assistant.

---

## 📄 License

TuneBox is open-source software licensed under the [MIT License](LICENSE).
