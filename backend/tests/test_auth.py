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

    settings.plex_token = ""
    settings.plex_username = ""
    settings.plex_server_name = ""
    settings.client_name = ""
    settings.testing = True
    yield
    settings.plex_token = original_token
    settings.plex_username = original_username
    settings.plex_server_name = original_server
    settings.client_name = original_client
    settings.testing = original_testing


def test_auth_status_unauthenticated(client):
    """Test retrieving auth status when credentials are not configured."""
    response = client.get("/api/auth/status")
    assert response.status_code == 200
    data = response.json()
    assert data["authenticated"] is False
    assert data["username"] == ""


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

    with patch("backend.services.redis.get_redis_cache_client", return_value=mock_cache):
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
        assert claim_response.json()["message"] == "Simulated PIN authorized successfully!"

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



