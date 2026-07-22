# 🌐 TuneBox Deployment & Hosting Guide

This guide covers deployment strategies for **TuneBox**, including recommended secure setups with reverse proxies and SSL, as well as direct local network (LAN) deployment options.

---

## 🧙 Automatic Setup Wizard & `.env` File

TuneBox includes an **interactive Setup Wizard** on first launch.

When you start TuneBox for the first time and open the web UI, the Setup Wizard automatically walks you through:
1. Connecting to your Plex account via OAuth PIN login.
2. Selecting your Plex Media Server and active playback player.
3. Setting an Admin Security Token.

> [!NOTE]
> **Automatic `.env` Generation**: You do **not** need to manually create or edit the `.env` file before launching TuneBox. The backend automatically creates and writes `.env` settings when you complete the Setup Wizard!

---

## 🔑 Environment Variables Reference

Below is a reference of settings saved in `.env` by the Setup Wizard or configured manually:

| Variable Name | Default / Example | Description |
| :--- | :--- | :--- |
| `PLEX_TOKEN` | `c8x912...` | Authentication token retrieved automatically via Plex OAuth PIN login. |
| `PLEX_SERVER_NAME` | `MyPlexServer` | The exact name of your Plex Media Server. |
| `CLIENT_NAME` | `TuneBox-Host` | Identifier string for TuneBox when connecting to Plex. |
| `PLEX_USERNAME` | `user@example.com` | Username of the connected Plex account. |
| `ADMIN_TOKEN` | `random_secure_token` | Secret admin token required for host playback controls and settings access. |
| `REDIS_URL` | `redis://redis:6379` | Connection URI for the Redis service container. |
| `TESTING` | `false` | Set to `false` for live Plex server connectivity; `true` for mock testing library. |

---

## 🔒 Recommended Secure Deployment (Reverse Proxy + HTTPS)

For public hosting or network security, host TuneBox behind a reverse proxy (Nginx, Traefik, Caddy) configured with SSL/TLS encryption.

### Architecture Overview
```
Client (HTTPS:443) ──> Nginx / Traefik (SSL Termination) ──> TuneBox Frontend (Port 80)
                                                          ──> TuneBox Backend (Port 8000)
```

### Sample Nginx Reverse Proxy Configuration

```nginx
server {
    listen 80;
    server_name tunebox.yourdomain.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name tunebox.yourdomain.com;

    ssl_certificate /etc/letsencrypt/live/tunebox.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/tunebox.yourdomain.com/privkey.pem;

    # Frontend Static Assets & Web App
    location / {
        proxy_pass http://127.0.0.1:80;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Backend REST API
    location /api/ {
        proxy_pass http://127.0.0.1:8000/api/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    # Real-time WebSockets
    location /ws {
        proxy_pass http://127.0.0.1:8000/ws;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "Upgrade";
        proxy_set_header Host $host;
    }
}
```

---

## ⚠️ Direct Unsafe LAN Deployment (No HTTPS, No Reverse Proxy)

If you are hosting TuneBox strictly inside a private, trusted home network (LAN) for a party and do not want to set up domain names or SSL certificates, you can deploy directly via Docker Compose.

> [!CAUTION]
> **SECURITY WARNING**: Direct LAN deployment runs over unencrypted HTTP (`http://`). 
> - **Unencrypted Credentials**: Session tokens and admin tokens are transmitted in cleartext across the local network.
> - **Trusted Networks Only**: Deploy this way **ONLY** on fully trusted, password-protected home Wi-Fi networks.
> - **NEVER Expose to Public Internet**: Do **NOT** port-forward port 80 or 8000 on your router directly to the internet without a reverse proxy and HTTPS!

### Direct Deployment Instructions

1. **Start Docker Containers**:
   ```bash
   docker compose up -d
   ```

2. **Open Web UI & Complete Setup Wizard**:
   Navigate to `http://localhost` (or host LAN IP) in your browser. The Setup Wizard will guide you through Plex authentication and automatically generate your `.env` settings.

3. **Determine Host LAN IP Address**:
   Find your host computer's local IP address (e.g., `192.168.1.150`):
   - **macOS**: `ipconfig getifaddr en0`
   - **Linux**: `hostname -I`

4. **Accessing the App on LAN**:
   - Host display: Open `http://localhost` or `http://192.168.1.150`
   - Guest phones: Connect to home Wi-Fi and open `http://192.168.1.150` in phone browser (or scan the QR code on the host screen).
