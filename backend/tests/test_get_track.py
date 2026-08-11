"""Tests for get_track strict ID resolution behavior."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from backend.config import settings
from backend.services.plex import get_track


@pytest.fixture(autouse=True)
def non_testing_mode():
    """Run get_track tests with settings.testing=False to exercise the real resolution path."""
    original = settings.testing
    settings.testing = False
    yield
    settings.testing = original


@patch("backend.services.plex.get_target_plex_connection")
@patch("backend.services.plex.track_id_to_rating_key")
def test_get_track_resolves_via_rating_key_and_calls_fetch_item(mock_resolve, mock_conn):
    """Valid internal track_id must resolve to its Plex ratingKey and call fetchItem with that int.

    This guards against the previous fallback behavior where get_track would try
    validate_track_id OR rating_key_to_track_id in one expression, allowing a raw
    Plex ratingKey to bypass SQLite lookup and cause wrong-track collisions.
    """
    mock_track = MagicMock()
    mock_track.title = "Test Song"
    mock_plex = MagicMock()
    mock_plex.fetchItem.return_value = mock_track
    mock_conn.return_value = mock_plex

    # ratingKey "87654" on server "server-abc" is what SQLite says this track maps to
    mock_resolve.return_value = ("87654", "server-abc")

    result = get_track(42)

    # Must resolve using the internal track_id
    mock_resolve.assert_called_once_with(42)
    # Must call fetchItem with the integer ratingKey — never the internal track_id
    mock_plex.fetchItem.assert_called_once_with(87654)
    # sqlite_track_id must be stamped onto the returned object so the queue can use it
    assert getattr(result, "sqlite_track_id", None) == 42


@patch("backend.services.plex.get_target_plex_connection")
@patch("backend.services.plex.track_id_to_rating_key")
def test_get_track_raises_404_when_track_not_in_library(mock_resolve, mock_conn):
    """track_id with no library entry must raise HTTP 404 without touching Plex.

    This confirms the fail-fast behavior: a track TuneBox has no record of
    should never reach fetchItem, since we have no ratingKey to give it.
    """
    mock_resolve.return_value = None
    mock_plex = MagicMock()
    mock_conn.return_value = mock_plex

    with pytest.raises(HTTPException) as exc_info:
        get_track(99999)

    assert exc_info.value.status_code == 404
    # Plex must never be contacted — we have no ratingKey to look up
    mock_plex.fetchItem.assert_not_called()
