"""Unit tests for the Plex OAuth PIN authentication endpoints."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from backend.config import settings
from backend.main import app
from backend.routers.auth import MOCK_PIN_ID, MOCK_TOKEN


@pytest.fixture
def client():
    """Create a test client for the FastAPI app."""
    return TestClient(app)


@pytest.fixture(autouse=True)
def reset_settings():
    """Reset configuration settings before and after each test."""
    original_token = settings.plex_token
    original_username = settings.plex_username
    original_server = settings.plex_server_name
    original_client = settings.client_name
    original_testing = settings.testing
    original_admin_token = settings.admin_token

    settings.plex_token = ""
    settings.plex_username = ""
    settings.plex_server_name = ""
    settings.client_name = ""
    settings.testing = True
    settings.admin_token = ""
    yield
    settings.plex_token = original_token
    settings.plex_username = original_username
    settings.plex_server_name = original_server
    settings.client_name = original_client
    settings.testing = original_testing
    settings.admin_token = original_admin_token


def test_auth_status_unauthenticated(client):
    """Test retrieving auth status when credentials are not configured (non-testing path)."""
    # Explicitly disable testing mode to exercise the real unauthenticated code path.
    settings.testing = False
    response = client.get("/api/auth/status")
    assert response.status_code == 200
    data = response.json()
    assert data["authenticated"] is False
    assert data["username"] == ""


def test_auth_status_testing_bypass(client):
    """Testing bypass fires when TESTING=True and admin_token is set (setup already done)."""
    settings.admin_token = "mock-admin-token"
    response = client.get("/api/auth/status")
    assert response.status_code == 200
    data = response.json()
    assert data["authenticated"] is True
    assert data["is_configured"] is True
    assert data["admin_token"] == "mock-admin-token"
    assert data["testing"] is True


def test_auth_status_testing_no_bypass(client):
    """No bypass when TESTING=True but admin_token is empty (fresh start shows wizard)."""
    # admin_token is already "" from the autouse fixture — bypass should NOT fire.
    assert settings.admin_token == ""
    response = client.get("/api/auth/status")
    assert response.status_code == 200
    data = response.json()
    assert data["authenticated"] is False


def test_auth_status_authenticated(client):
    """Test retrieving auth status when credentials are configured."""
    settings.plex_token = "some_token"
    settings.plex_username = "TestUser"
    response = client.get("/api/auth/status")
    assert response.status_code == 200
    data = response.json()
    assert data["authenticated"] is True
    assert data["username"] == "TestUser"


def test_simulation_auth_flow(client, mock_redis):
    """Test the complete offline simulation auth flow from PIN request to authorization."""
    _, mock_cache = mock_redis
    cache_store = {}

    def mock_setex(key, ttl, value):
        cache_store[key] = value

    def mock_get(key):
        return cache_store.get(key)

    mock_cache.setex.side_effect = mock_setex
    mock_cache.get.side_effect = mock_get

    with patch(
        "backend.services.redis.get_redis_cache_client", return_value=mock_cache
    ):
        # 1. Request simulated PIN
        response = client.post("/api/auth/pin")
        assert response.status_code == 200
        data = response.json()
        assert data["pin_id"] == MOCK_PIN_ID
        assert data["code"] == "MOCK"
        assert "mock-claim" in data["url"]

        # 2. Under settings.testing = True, check login status returns True immediately
        check_response = client.get(f"/api/auth/check?pin_id={MOCK_PIN_ID}")
        assert check_response.status_code == 200
        assert check_response.json()["authenticated"] is True

        # 3. Under settings.testing = False, check login status returns False initially
        settings.testing = False
        check_response = client.get(f"/api/auth/check?pin_id={MOCK_PIN_ID}")
        assert check_response.status_code == 200
        assert check_response.json()["authenticated"] is False

        # 4. Claim the mock PIN (needs testing flag)
        settings.testing = True
        claim_response = client.post("/api/auth/mock-claim")
        assert claim_response.status_code == 200
        assert (
            claim_response.json()["message"] == "Simulated PIN authorized successfully!"
        )

        # 5. Check login status after claiming (should be True under settings.testing = False)
        settings.testing = False
        check_response = client.get(f"/api/auth/check?pin_id={MOCK_PIN_ID}")
        assert check_response.status_code == 200
        check_data = check_response.json()
        assert check_data["authenticated"] is True
        assert check_data["token"] == MOCK_TOKEN

        # 6. Check global settings state is updated
        assert settings.plex_token == MOCK_TOKEN
        assert settings.plex_username == "MockUser"


def test_get_resources_simulation(client):
    """Test retrieving mock resources in simulation mode."""
    settings.plex_token = MOCK_TOKEN
    response = client.get("/api/auth/resources")
    assert response.status_code == 200
    data = response.json()
    assert "[Mock] Local Jukebox Server" in data["servers"]
    assert "[Mock] Living Room Plexamp" in data["players"]


def test_get_resources_production(client):
    """Test retrieving servers and players in production mode with mocked Plex API."""
    settings.plex_token = "some_valid_token"

    mock_resource_1 = MagicMock()
    mock_resource_1.name = "My Server"
    mock_resource_1.provides = "server"

    mock_resource_2 = MagicMock()
    mock_resource_2.name = "My Player"
    mock_resource_2.provides = "client,player"

    with patch("backend.routers.auth.MyPlexAccount") as mock_account_class:
        mock_account = MagicMock()
        mock_account.resources.return_value = [mock_resource_1, mock_resource_2]
        mock_account_class.return_value = mock_account

        response = client.get("/api/auth/resources")
        assert response.status_code == 200
        data = response.json()
        assert data["servers"] == ["My Server"]
        assert data["players"] == ["My Player"]


def test_configure_endpoint(client, tmp_path):
    """Test saving selected server and player names to env and settings."""
    settings.plex_token = "some_token"

    with (
        patch("backend.routers.auth.reinitialize_plex") as mock_reinit,
        patch("pathlib.Path.exists", return_value=True),
        patch("pathlib.Path.read_text", return_value=""),
        patch("pathlib.Path.write_text") as mock_write,
    ):
        payload = {
            "plex_username": "MyPlexUser",
            "plex_server_name": "SelectedServer",
            "client_name": "SelectedPlayer",
        }
        response = client.post("/api/auth/configure", json=payload)

        assert response.status_code == 200
        assert settings.plex_username == "MyPlexUser"
        assert settings.plex_server_name == "SelectedServer"
        assert settings.client_name == "SelectedPlayer"

        # Verify settings update and reinitialization trigger
        mock_reinit.assert_called_once()
        mock_write.assert_called_once()


def test_simulation_disabled_in_production(client):
    """Test that simulation endpoints are rejected when settings.testing is False."""
    settings.testing = False

    # POST /api/auth/pin?simulate=true should fail
    response = client.post("/api/auth/pin?simulate=true")
    assert response.status_code == 400
    assert "only allowed when testing is enabled" in response.json()["detail"]

    # POST /api/auth/mock-claim should fail
    response = client.post("/api/auth/mock-claim")
    assert response.status_code == 400
    assert "only allowed when testing is enabled" in response.json()["detail"]


def test_configure_generates_admin_token(client):
    """Test that configure endpoint generates an admin_token and returns it."""
    settings.plex_token = "some_token"

    with (
        patch("backend.routers.auth.reinitialize_plex"),
        patch("pathlib.Path.exists", return_value=True),
        patch("pathlib.Path.read_text", return_value=""),
        patch("pathlib.Path.write_text"),
    ):
        payload = {
            "plex_username": "AdminUser",
            "plex_server_name": "MyServer",
            "client_name": "MyJukebox",
        }
        response = client.post("/api/auth/configure", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert "admin_token" in data
        assert len(data["admin_token"]) == 32  # secrets.token_hex(16) = 32 hex chars
        # Token should also be persisted in settings
        assert settings.admin_token == data["admin_token"]


def test_settings_get_requires_admin_token(client):
    """Test that GET /settings is rejected without a valid admin token."""
    settings.admin_token = "valid_token_abc"

    # No header → 401
    response = client.get("/api/auth/settings")
    assert response.status_code == 401

    # Wrong token → 401
    response = client.get("/api/auth/settings", headers={"x-admin-token": "wrong"})
    assert response.status_code == 401


def test_settings_get_with_valid_token(client):
    """Test that GET /settings returns config data with a valid admin token."""
    settings.admin_token = "valid_token_abc"
    settings.plex_username = "OwnerUser"
    settings.client_name = "MyJukebox"
    settings.plex_server_name = "MyServer"

    response = client.get(
        "/api/auth/settings", headers={"x-admin-token": "valid_token_abc"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["plex_username"] == "OwnerUser"
    assert data["client_name"] == "MyJukebox"
    assert data["plex_server_name"] == "MyServer"


def test_settings_post_requires_admin_token(client):
    """Test that POST /settings is rejected without a valid admin token."""
    settings.admin_token = "valid_token_abc"
    payload = {"plex_username": "X", "client_name": "Y", "plex_server_name": "Z"}

    response = client.post("/api/auth/settings", json=payload)
    assert response.status_code == 401

    response = client.post(
        "/api/auth/settings", json=payload, headers={"x-admin-token": "bad"}
    )
    assert response.status_code == 401


def test_settings_post_updates_config(client):
    """Test that POST /settings with valid token persists updated config."""
    settings.admin_token = "valid_token_abc"
    settings.plex_token = "plex_tok"

    with (
        patch("backend.routers.auth.reinitialize_plex"),
        patch("pathlib.Path.exists", return_value=True),
        patch("pathlib.Path.read_text", return_value=""),
        patch("pathlib.Path.write_text"),
    ):
        payload = {
            "plex_username": "NewUser",
            "client_name": "NewJukebox",
            "plex_server_name": "NewServer",
        }
        response = client.post(
            "/api/auth/settings",
            json=payload,
            headers={"x-admin-token": "valid_token_abc"},
        )
        assert response.status_code == 200
        assert settings.plex_username == "NewUser"
        assert settings.plex_server_name == "NewServer"


def test_verify_username_unconfigured(client):
    """Test verify-username returns 503 when Jukebox is not yet configured."""
    settings.plex_token = ""
    response = client.get("/api/auth/verify-username?username=anyone")
    assert response.status_code == 503


def test_verify_username_guest_in_testing(client):
    """Test verify-username returns guest role for unknown names in testing mode."""
    settings.plex_token = "some_token"
    settings.testing = True

    response = client.get("/api/auth/verify-username?username=randomguy")
    assert response.status_code == 200
    data = response.json()
    assert data["role"] == "guest"
    assert data["is_member"] is False


def test_verify_username_member_in_testing(client):
    """Test verify-username returns member role for friend_ prefix names in testing mode."""
    settings.plex_token = "some_token"
    settings.testing = True

    response = client.get("/api/auth/verify-username?username=friend_alice")
    assert response.status_code == 200
    data = response.json()
    assert data["role"] == "member"
    assert data["is_member"] is True


def test_clients_endpoints_requires_admin_token(client):
    """Test that client endpoints require a valid admin token."""
    response = client.get("/api/auth/clients")
    assert response.status_code == 401

    response = client.get("/api/auth/clients", headers={"x-admin-token": "bad_token"})
    assert response.status_code == 401

    response = client.post("/api/auth/clients/some_id/set-display")
    assert response.status_code == 401

    response = client.post(
        "/api/auth/clients/some_id/set-display", headers={"x-admin-token": "bad_token"}
    )
    assert response.status_code == 401


def test_get_clients_and_set_display(client):
    """Test retrieving client list and designating one as display."""
    settings.admin_token = "valid_admin_token"

    from backend.websockets import client_registry

    client_registry.clear()
    client_registry["uuid_123"] = {
        "name": "Living Room TV",
        "role": "guest",
        "is_display": False,
        "connected_at": "2026-07-15T12:00:00Z",
    }

    response = client.get(
        "/api/auth/clients", headers={"x-admin-token": "valid_admin_token"}
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["client_id"] == "uuid_123"
    assert data[0]["name"] == "Living Room TV"
    assert data[0]["is_display"] is False

    with patch("backend.websockets.send_to_client_id") as mock_send:
        response = client.post(
            "/api/auth/clients/uuid_123/set-display",
            headers={"x-admin-token": "valid_admin_token"},
        )
        assert response.status_code == 200
        assert client_registry["uuid_123"]["is_display"] is True
        mock_send.assert_called_once_with("uuid_123", {"type": "set_display_mode"})


def test_production_pin_flow_mocked(client):
    """Test requesting a real PIN in production mode (mocked MyPlexPinLogin)."""
    settings.testing = False

    mock_pinlogin = MagicMock()
    mock_pinlogin._id = 12345
    mock_pinlogin.pin = "CODE"

    with patch(
        "backend.routers.auth.MyPlexPinLogin", return_value=mock_pinlogin
    ) as mock_class:
        response = client.post("/api/auth/pin")
        assert response.status_code == 200
        data = response.json()
        assert data["pin_id"] == 12345
        assert data["code"] == "CODE"
        assert data["url"] == "https://plex.tv/link"

        mock_class.assert_called_once_with(oauth=False)
        mock_pinlogin.run.assert_not_called()
