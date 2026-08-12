"""mDNS Zeroconf Local Discovery Service (tunebox.local)."""

import logging
import socket
from zeroconf import ServiceInfo, Zeroconf

logger = logging.getLogger(__name__)

_zeroconf_instance: Zeroconf | None = None
_service_info: ServiceInfo | None = None


def get_lan_ip() -> str:
    """Get the local LAN IP address of this machine."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


def register_mdns_service(hostname: str = "tunebox.local", port: int = 8000) -> bool:
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
