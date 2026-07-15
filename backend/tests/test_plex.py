"""Unit tests for the Plex service connection and player resolution."""

from unittest.mock import MagicMock, patch

import pytest
from plexapi.exceptions import PlexApiException

from backend.config import settings
from backend.services.plex import (
    get_active_player,
    get_myplex_account,
    get_plex_connection,
)


@pytest.fixture(autouse=True)
def reset_testing_and_tokens():
    """Reset configuration settings before and after each test."""
    original_testing = settings.testing
    original_plex_token = settings.plex_token
    original_plex_username = settings.plex_username
    original_plex_password = settings.plex_password
    original_client_name = settings.client_name

    settings.testing = False
    settings.plex_token = "mock-token-123"
    settings.plex_username = "mock-user"
    settings.plex_password = "mock-password"
    settings.client_name = "Target Player"

    # Clear lru_cache for plex connection helpers
    get_myplex_account.cache_clear()
    get_plex_connection.cache_clear()

    yield

    settings.testing = original_testing
    settings.plex_token = original_plex_token
    settings.plex_username = original_plex_username
    settings.plex_password = original_plex_password
    settings.client_name = original_client_name

    get_myplex_account.cache_clear()
    get_plex_connection.cache_clear()


@patch("backend.services.plex.MyPlexAccount")
def test_get_myplex_account_uses_token(mock_myplex_account):
    """Verify get_myplex_account uses token when provided."""
    settings.plex_token = "token-abc"
    get_myplex_account()
    mock_myplex_account.assert_called_once_with(token="token-abc")


@patch("backend.services.plex.MyPlexAccount")
def test_get_myplex_account_uses_username_password(mock_myplex_account):
    """Verify get_myplex_account uses credentials when token is missing."""
    settings.plex_token = ""
    settings.plex_username = "user-abc"
    settings.plex_password = "pass-123"
    get_myplex_account()
    mock_myplex_account.assert_called_once_with(
        username="user-abc", password="pass-123"
    )


@patch("backend.services.plex.get_plex_connection")
def test_get_active_player_local_success(mock_get_conn):
    """Verify local PMS client lookup success."""
    mock_player = MagicMock()
    mock_player.title = "Target Player"

    mock_server = MagicMock()
    mock_server.clients.return_value = [mock_player]
    mock_get_conn.return_value = mock_server

    player = get_active_player("Target Player")
    assert player == mock_player
    mock_server.clients.assert_called_once()


@patch("backend.services.plex.get_myplex_account")
@patch("backend.services.plex.get_plex_connection")
def test_get_active_player_myplex_fallback(mock_get_conn, mock_get_account):
    """Verify fallback to MyPlex resource resolution when player is not found locally."""
    # Local lookup returns a different player
    other_player = MagicMock()
    other_player.title = "Other Player"

    mock_server = MagicMock()
    mock_server.clients.return_value = [other_player]
    mock_get_conn.return_value = mock_server

    # MyPlex lookup setup
    mock_player_resource = MagicMock()
    mock_target_player = MagicMock()
    mock_player_resource.connect.return_value = mock_target_player

    mock_account = MagicMock()
    mock_account.resource.return_value = mock_player_resource
    mock_get_account.return_value = mock_account

    player = get_active_player("Target Player")

    assert player == mock_target_player
    mock_account.resource.assert_called_once_with("Target Player")
    mock_player_resource.connect.assert_called_once()


@patch("backend.services.plex.get_myplex_account")
@patch("backend.services.plex.get_plex_connection")
def test_get_active_player_fallback_to_first_local(
    mock_get_conn, mock_get_account
):
    """Verify fallback to first local player when specific lookup completely fails."""
    local_player = MagicMock()
    local_player.title = "First Local"

    mock_server = MagicMock()
    mock_server.clients.return_value = [local_player]
    mock_get_conn.return_value = mock_server

    # MyPlex fails
    mock_account = MagicMock()
    mock_account.resource.side_effect = Exception("MyPlex client offline")
    mock_get_account.return_value = mock_account

    player = get_active_player("Target Player")

    assert player == local_player


@patch("backend.services.plex.get_myplex_account")
@patch("backend.services.plex.get_plex_connection")
def test_get_active_player_fails_all_paths(mock_get_conn, mock_get_account):
    """Verify PlexApiException raised when local players are empty and MyPlex lookup fails."""
    mock_server = MagicMock()
    mock_server.clients.return_value = []
    mock_get_conn.return_value = mock_server

    mock_account = MagicMock()
    mock_account.resource.side_effect = Exception("MyPlex client offline")
    mock_get_account.return_value = mock_account

    with pytest.raises(PlexApiException):
        get_active_player("Target Player")
