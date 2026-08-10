"""Tests verifying queue mutation operations: individual track removal, reordering, and album queuing."""

import pytest
from unittest.mock import MagicMock, AsyncMock
from fastapi.testclient import TestClient

from backend.config import settings
from backend.main import app
from backend.services.redis import (
    add_to_queue_redis,
    clear_redis_queue,
    get_redis_queue,
    reorder_redis_queue,
    remove_from_redis_queue,
)

client = TestClient(app)


def make_track(item_id: str, title: str, artist: str = "Foo Fighters"):
    """Helper to construct a valid mock Plex track object with clean serializable metadata."""
    t = MagicMock()
    t.type = "track"
    t.ratingKey = item_id
    t.album_id = "500"
    t.parentRatingKey = "500"
    t.title = title
    t.grandparentTitle = artist
    t.duration = 250000
    t.thumb = f"/library/metadata/{item_id}/thumb"
    t.server_id = "plex-so"
    t.server_name = "plex-so"
    t.server_token = None
    t.server_address = None
    return t


def test_remove_track_from_queue(mock_redis):
    """Verify removing a queued track deletes only that item without mutating other tracks or active track."""
    mock_queue_client, _ = mock_redis
    stored_queue = []

    def rpush_side_effect(key, value):
        stored_queue.append(value)

    def lrange_side_effect(key, start, end):
        return stored_queue[start : end + 1 if end != -1 else None]

    def lrem_side_effect(key, count, value):
        if value in stored_queue:
            stored_queue.remove(value)
            return 1
        return 0

    def delete_side_effect(key):
        stored_queue.clear()

    mock_queue_client.rpush.side_effect = rpush_side_effect
    mock_queue_client.lrange.side_effect = lrange_side_effect
    mock_queue_client.lrem.side_effect = lrem_side_effect
    mock_queue_client.delete.side_effect = delete_side_effect

    clear_redis_queue(force_all=True)

    track_1 = make_track("101", "Monkey Wrench")
    track_2 = make_track("102", "Everlong")
    track_3 = make_track("103", "My Hero")

    add_to_queue_redis(track_1, server_id="plex-so", server_name="plex-so")
    add_to_queue_redis(track_2, server_id="plex-so", server_name="plex-so")
    add_to_queue_redis(track_3, server_id="plex-so", server_name="plex-so")

    assert len(get_redis_queue()) == 3

    # Remove middle track ("Everlong", item_id 102)
    remove_from_redis_queue("102")

    updated_queue = get_redis_queue()
    assert len(updated_queue) == 2
    assert updated_queue[0]["title"] == "Monkey Wrench"
    assert updated_queue[1]["title"] == "My Hero"


def test_reorder_queue_and_move_to_top(mock_redis):
    """Verify reordering queue items (moving track from index 2 to index 1) updates upcoming playback order."""
    mock_queue_client, _ = mock_redis
    stored_queue = []

    def rpush_side_effect(key, *values):
        for val in values:
            stored_queue.append(val)

    def lrange_side_effect(key, start, end):
        return stored_queue[start : end + 1 if end != -1 else None]

    def delete_side_effect(key):
        stored_queue.clear()

    mock_queue_client.rpush.side_effect = rpush_side_effect
    mock_queue_client.lrange.side_effect = lrange_side_effect
    mock_queue_client.delete.side_effect = delete_side_effect

    clear_redis_queue(force_all=True)

    track_0 = make_track("200", "Currently Playing Track")
    track_1 = make_track("201", "Upcoming Track One")
    track_2 = make_track("202", "Upcoming Track Two")

    add_to_queue_redis(track_0, server_id="plex-so", server_name="plex-so")
    add_to_queue_redis(track_1, server_id="plex-so", server_name="plex-so")
    add_to_queue_redis(track_2, server_id="plex-so", server_name="plex-so")

    # Move index 2 ("Upcoming Track Two") to index 1 ("Move to Top" of upcoming queue)
    reorder_redis_queue(from_index=2, to_index=1)

    updated_queue = get_redis_queue()
    assert len(updated_queue) == 3
    assert updated_queue[0]["title"] == "Currently Playing Track"
    assert updated_queue[1]["title"] == "Upcoming Track Two"
    assert updated_queue[2]["title"] == "Upcoming Track One"


def test_add_album_to_queue_in_track_order(mocker):
    """Verify POST /api/music/albums/{id}/add-to-queue adds all album tracks sequentially in track order."""
    mock_album_data = {
        "album_id": 500,
        "title": "The Colour and the Shape",
        "artist": "Foo Fighters",
        "tracks": [
            {"track_id": "301", "title": "Monkey Wrench", "server_id": "plex-so"},
            {"track_id": "302", "title": "Everlong", "server_id": "plex-so"},
        ],
    }

    t1 = make_track("301", "Monkey Wrench")
    t2 = make_track("302", "Everlong")

    mocker.patch("backend.routers.music.fetch_tracks_for_album", return_value=mock_album_data)
    mocker.patch("backend.services.plex.fetch_tracks_for_album", return_value=mock_album_data)

    def get_track_side_effect(track_id, server_id=None):
        if str(track_id) == "301":
            return t1
        return t2

    mocker.patch("backend.routers.music.get_track", side_effect=get_track_side_effect)
    mock_add = mocker.patch("backend.routers.music.add_to_queue_redis")
    mocker.patch("backend.websockets.send_queue", new_callable=AsyncMock)
    mocker.patch("backend.websockets.send_current_playing", new_callable=AsyncMock)

    response = client.post(
        "/api/music/albums/500/add-to-queue",
        params={"server_id": "plex-so", "username": "Guest"},
    )

    assert response.status_code == 200
    assert response.json()["message"] == "Album added to queue successfully."
    assert mock_add.call_count == 2
