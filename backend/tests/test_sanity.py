"""Sanity checks for testing module imports."""

from backend.main import app
from backend.routers import music
from backend.services import plex, redis, redis_client


def test_imports():
    """Verify that all core modules can be imported without error."""
    assert app is not None
    assert plex is not None
    assert redis is not None
    assert redis_client is not None
    assert music is not None
