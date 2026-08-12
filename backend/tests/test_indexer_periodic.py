import asyncio
import pytest
from unittest.mock import patch, MagicMock
from backend.config import settings
from backend.services.indexer import periodic_library_indexer


@pytest.mark.asyncio
async def test_periodic_library_indexer_disabled(mocker):
    """Test that periodic_library_indexer returns immediately when disabled (index_interval_hours <= 0)."""
    mocker.patch.object(settings, "index_interval_hours", 0)
    mock_sync = mocker.patch("backend.services.indexer.sync_all_servers")

    # Should exit immediately without sleeping or syncing
    await periodic_library_indexer()
    mock_sync.assert_not_called()


@pytest.mark.asyncio
async def test_periodic_library_indexer_triggers_sync(mocker):
    """Test that periodic_library_indexer invokes sync_all_servers after sleep interval."""
    mocker.patch.object(settings, "index_interval_hours", 1)
    mock_sync = mocker.patch("backend.services.indexer.sync_all_servers")

    # Mock asyncio.sleep to cancel the loop on the second iteration
    sleep_count = 0

    async def mock_sleep(seconds):
        nonlocal sleep_count
        sleep_count += 1
        assert seconds == 3600
        if sleep_count >= 2:
            raise asyncio.CancelledError()

    mocker.patch("asyncio.sleep", side_effect=mock_sleep)

    await periodic_library_indexer()
    assert mock_sync.call_count == 1
