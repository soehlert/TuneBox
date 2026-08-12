"""Tests for queue limiters, FCFS placement, duplicate cooldown, session bump, and ETA calculation."""

import json
from unittest.mock import ANY, MagicMock, patch

import pytest
from fastapi import HTTPException

from backend.services.redis import (
    add_to_queue_redis,
    bump_existing_queue_item,
    calculate_queue_eta,
    has_user_bumped,
    is_song_on_cooldown,
    set_song_cooldown,
)


@pytest.fixture
def make_mock_track():
    """Factory fixture for creating mock track objects with standard attributes."""
    def _create(track_id="101", title="Test Track", artist="Test Artist", duration=200000):
        track = MagicMock()
        track.TYPE = "track"
        track.ratingKey = str(track_id)
        track.sqlite_track_id = str(track_id)
        track.parentRatingKey = "901"
        track.title = title
        track.grandparentTitle = artist
        track.artist = artist
        track.duration = duration
        track.thumb = "/thumb.jpg"
        track.moods = []
        return track
    return _create


def test_duplicate_cooldown_set_and_check(mock_redis):
    """Verify duplicate cooldown can be set and checked in Redis."""
    mock_queue_client, _ = mock_redis
    mock_queue_client.get.return_value = "1"
    mock_queue_client.ttl.return_value = 450

    set_song_cooldown("101", ttl_seconds=600)
    mock_queue_client.set.assert_called_with("song_cooldown:101", "1", ex=600)

    on_cooldown, rem_mins = is_song_on_cooldown("101")
    assert on_cooldown is True
    assert rem_mins == 8


def test_duplicate_cooldown_blocks_queue_add(mock_redis, make_mock_track, mocker):
    """Verify adding a track on duplicate cooldown raises HTTP 400."""
    mock_queue_client, _ = mock_redis
    mocker.patch("backend.services.redis.is_song_in_queue", return_value=False)
    mock_queue_client.get.side_effect = lambda key: "1" if key == "song_cooldown:101" else None
    mock_queue_client.ttl.return_value = 300

    track = make_mock_track(track_id="101", title="Cooldown Track")

    with patch("backend.services.redis.get_redis_queue_client", return_value=mock_queue_client):
        with pytest.raises(HTTPException) as exc_info:
            add_to_queue_redis(track)

    assert exc_info.value.status_code == 400
    assert "Duplicate cooldown active" in exc_info.value.detail


def test_single_use_session_bump(mock_redis, make_mock_track, mocker):
    """Verify 1-time session bump token allows 1 bump and blocks subsequent attempts."""
    mock_queue_client, _ = mock_redis
    mocker.patch("backend.services.redis.is_song_in_queue", return_value=False)
    mocker.patch("backend.services.redis.is_song_on_cooldown", return_value=(False, 0))

    user_bumps = {}
    def mock_get(key):
        return user_bumps.get(key)
    def mock_set(key, val, ex=None):
        user_bumps[key] = val

    mock_queue_client.get.side_effect = mock_get
    mock_queue_client.set.side_effect = mock_set

    # Pre-populate queue with index 0 (now playing) and index 1 (fallback)
    item_0 = json.dumps({"item_id": "1", "title": "Playing", "is_fallback": False}).encode("utf-8")
    item_1 = json.dumps({"item_id": "2", "title": "Fallback", "is_fallback": True}).encode("utf-8")
    mock_queue_client.lrange.return_value = [item_0, item_1]

    track1 = make_mock_track(track_id="201", title="Bumped Track 1")

    with patch("backend.services.redis.get_redis_queue_client", return_value=mock_queue_client):
        # 1st bump for PartyUser
        add_to_queue_redis(track1, added_by="PartyUser", bump=True)
        assert has_user_bumped("PartyUser") is True

        # 2nd bump for PartyUser should fail
        track2 = make_mock_track(track_id="202", title="Bumped Track 2")
        with pytest.raises(HTTPException) as exc_info:
            add_to_queue_redis(track2, added_by="PartyUser", bump=True)

        assert exc_info.value.status_code == 400
        assert "You have used your one bump" in exc_info.value.detail


def test_human_leapfrog_over_fallback_tracks(mock_redis, make_mock_track, mocker):
    """Verify human requests insert before non-playing fallback tracks."""
    mock_queue_client, _ = mock_redis
    mocker.patch("backend.services.redis.is_song_in_queue", return_value=False)
    mocker.patch("backend.services.redis.is_song_on_cooldown", return_value=(False, 0))

    item_0 = json.dumps({"item_id": "1", "title": "Playing Track", "is_fallback": False}).encode("utf-8")
    item_1 = json.dumps({"item_id": "2", "title": "Autoplay Track", "is_fallback": True}).encode("utf-8")
    mock_queue_client.lrange.return_value = [item_0, item_1]

    track = make_mock_track(track_id="301", title="Guest Requested Track")

    with patch("backend.services.redis.get_redis_queue_client", return_value=mock_queue_client):
        add_to_queue_redis(track, added_by="GuestA", bump=False)

    # Verify linsert was called to insert before item_1 (the fallback track)
    mock_queue_client.linsert.assert_called_once_with("playback_queue", "BEFORE", item_1, ANY)


def test_calculate_queue_eta(mock_redis):
    """Verify ETA calculation sums track durations ahead in queue."""
    mock_queue_client, _ = mock_redis
    item_0 = json.dumps({"item_id": "1", "duration": 180000})  # 3 min
    item_1 = json.dumps({"item_id": "2", "duration": 240000})  # 4 min
    item_2 = json.dumps({"item_id": "3", "duration": 300000})  # Target item
    mock_queue_client.lrange.return_value = [item_0, item_1, item_2]

    with patch("backend.services.redis.get_redis_queue_client", return_value=mock_queue_client):
        tot_sec, est_mins = calculate_queue_eta(target_item_id="3")

    # Sum of item 0 (180s) + item 1 (240s) = 420s (7 mins)
    assert tot_sec == 420
    assert est_mins == 7
