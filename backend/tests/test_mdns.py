import pytest
from unittest.mock import patch, MagicMock
from backend.services.mdns import get_lan_ip, register_mdns_service, unregister_mdns_service


def test_get_lan_ip():
    """Test retrieving local LAN IP address."""
    ip = get_lan_ip()
    assert isinstance(ip, str)
    assert len(ip) > 0


def test_register_mdns_service(mocker):
    """Test registering mDNS service with Zeroconf."""
    mock_zeroconf = MagicMock()
    mocker.patch("backend.services.mdns.Zeroconf", return_value=mock_zeroconf)
    mocker.patch("backend.services.mdns.get_lan_ip", return_value="192.168.1.100")

    success = register_mdns_service(hostname="tunebox.local", port=8000)
    assert success is True
    mock_zeroconf.register_service.assert_called_once()

    unregister_mdns_service()
    mock_zeroconf.unregister_service.assert_called_once()
    mock_zeroconf.close.assert_called_once()


def test_register_mdns_service_fallback_localhost(mocker):
    """Test that localhost (127.0.0.1) skips zeroconf registration gracefully."""
    mocker.patch("backend.services.mdns.get_lan_ip", return_value="127.0.0.1")
    success = register_mdns_service(hostname="tunebox.local", port=8000)
    assert success is False
