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
Client (HTTPS:443) ──> Nginx / Traefik (SSL Termination) ──> TuneBox Frontend (Port 80) ──> TuneBox Backend (Internal Docker Network:8000)
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

    # Frontend Static Assets & REST API (proxied internally by the frontend Nginx container)
    location / {
        proxy_pass http://127.0.0.1:80;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Real-time WebSockets (proxied through the frontend Nginx container)
    location /ws {
        proxy_pass http://127.0.0.1:80/ws;
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

---

## 📡 Optional Reference: mDNS (`tunebox.local`) Zeroconf Discovery

Because Docker's default bridge network isolates link-local multicast traffic (`224.0.0.251:5353/udp`), container-based mDNS announcements do not cross a standard Docker bridge network (or across Guest/Main VLANs). For multi-VLAN or Portainer deployments, a local DNS A-record on your router/Pi-hole/UniFi (e.g., `tunebox.home` -> `<Host_IP>`) is recommended instead.

If you ever deploy TuneBox on a standalone Linux host using `network_mode: host` (or `macvlan`) and want Python-based Zeroconf registration (`tunebox.local`), you can add `zeroconf>=0.150.0` and `ifaddr>=0.2.0` and use the reference service below (`backend/services/mdns.py`):

```python
"""mDNS Zeroconf Local Discovery Service (tunebox.local)."""

import logging
import os
import socket
import ifaddr
from zeroconf import ServiceInfo, Zeroconf

logger = logging.getLogger(__name__)

_zeroconf_instance: Zeroconf | None = None
_service_info: ServiceInfo | None = None


def get_lan_ip() -> str:
    """Get the local LAN IP address of the host machine, VM, or LXC container."""
    env_ip = os.getenv("HOST_IP")
    if env_ip and not env_ip.startswith("127."):
        return env_ip

    try:
        adapters = ifaddr.get_adapters()
        for adapter in adapters:
            name = adapter.name.lower()
            if any(skip in name for skip in ["lo", "docker", "veth", "bridge", "utun", "tun", "tap", "virbr"]):
                continue
            for ip in adapter.ips:
                if isinstance(ip.ip, str) and not ip.ip.startswith("127.") and not ip.ip.startswith("172."):
                    return ip.ip
    except Exception as ex:
        logger.debug("ifaddr LAN IP lookup error: %s", ex)

    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        if not ip.startswith("172."):
            return ip
    except Exception:
        pass
    finally:
        s.close()

    return "127.0.0.1"


def register_mdns_service(hostname: str = "tunebox.local", port: int = 80) -> bool:
    """Register 'tunebox.local' and HTTP service on the local network via Zeroconf mDNS."""
    global _zeroconf_instance, _service_info

    unregister_mdns_service()

    lan_ip = get_lan_ip()
    if lan_ip == "127.0.0.1":
        logger.warning("mDNS: Could not detect active LAN IP address. Skipping zeroconf registration.")
        return False

    try:
        clean_hostname = hostname.rstrip(".").lower()
        if not clean_hostname.endswith(".local"):
            clean_hostname = f"{clean_hostname}.local"

        server_name = f"{clean_hostname}."
        addresses = [socket.inet_aton(lan_ip)]

        _service_info = ServiceInfo(
            type_="_http._tcp.local.",
            name="TuneBox Jukebox._http._tcp.local.",
            addresses=addresses,
            port=port,
            properties={
                "name": "TuneBox",
                "path": "/",
            },
            server=server_name,
        )

        _zeroconf_instance = Zeroconf()
        _zeroconf_instance.register_service(_service_info)
        logger.info("mDNS: Successfully registered 'http://%s' (%s:%d) via Zeroconf.", clean_hostname, lan_ip, port)
        return True
    except Exception as e:
        logger.warning("mDNS Zeroconf registration failed: %s", e)
        _zeroconf_instance = None
        _service_info = None
        return False


def unregister_mdns_service():
    """Unregister mDNS zeroconf service on shutdown."""
    global _zeroconf_instance, _service_info
    if _zeroconf_instance and _service_info:
        try:
            _zeroconf_instance.unregister_service(_service_info)
            _zeroconf_instance.close()
            logger.info("mDNS: Unregistered zeroconf service cleanly.")
        except Exception as e:
            logger.warning("Error unregistering mDNS service: %s", e)
        finally:
            _zeroconf_instance = None
            _service_info = None
```
