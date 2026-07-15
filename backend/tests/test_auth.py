"""Unit tests for the Plex OAuth PIN authentication endpoints."""

from unittest.mock import patch

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
    settings.plex_token = ""
    settings.plex_username = ""
    yield
    settings.plex_token = original_token
    settings.plex_username = original_username


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
        response = client.post("/api/auth/pin?simulate=true")
        assert response.status_code == 200
        data = response.json()
        assert data["pin_id"] == MOCK_PIN_ID
        assert data["code"] == "MOCK"
        assert "mock-claim" in data["url"]

        # 2. Check login status before claiming PIN (should be False)
        check_response = client.get(f"/api/auth/check?pin_id={MOCK_PIN_ID}")
        assert check_response.status_code == 200
        assert check_response.json()["authenticated"] is False

        # 3. Claim/authorize the PIN
        claim_response = client.post("/api/auth/mock-claim")
        assert claim_response.status_code == 200
        assert claim_response.json()["message"] == "Simulated PIN authorized successfully!"

        # 4. Check login status after claiming (should be True and load token)
        check_response = client.get(f"/api/auth/check?pin_id={MOCK_PIN_ID}")
        assert check_response.status_code == 200
        check_data = check_response.json()
        assert check_data["authenticated"] is True
        assert check_data["token"] == MOCK_TOKEN

        # 5. Check global settings state is updated
        assert settings.plex_token == MOCK_TOKEN
        assert settings.plex_username == "MockUser"

