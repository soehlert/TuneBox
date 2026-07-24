"""Unit and integration tests for TuneBox multi-server library deduplication."""

from unittest.mock import MagicMock, patch
import pytest

from backend.config import settings
from backend.services.plex import (
    fetch_all_artists,
    fetch_albums_for_artist,
    search_music,
)


@pytest.fixture(autouse=True)
def setup_test_environment():
    """Ensure testing flag is False so fetch_all_artists executes real multi-server logic."""
    orig_testing = settings.testing
    settings.testing = False
    yield
    settings.testing = orig_testing


def build_mock_artist(rating_key, title, guid, thumb=None):
    """Helper to create a mock Plex artist object."""
    artist = MagicMock()
    artist.ratingKey = rating_key
    artist.title = title
    artist.guid = guid
    artist.thumb = thumb
    return artist


def build_mock_album(rating_key, title, thumb=None):
    """Helper to create a mock Plex album object."""
    album = MagicMock()
    album.ratingKey = rating_key
    album.title = title
    album.thumb = thumb
    return album


@pytest.fixture
def mock_multi_servers():
    """Set up 3 mock Plex servers with overlapping artist libraries and edge cases."""
    srv_a_id = "srv-1111-alpha"
    srv_b_id = "srv-2222-beta"
    srv_c_id = "srv-3333-gamma"

    accessible_servers = [
        {"server_id": srv_a_id, "name": "Alpha Server", "is_primary": True},
        {"server_id": srv_b_id, "name": "Beta Server", "is_primary": False},
        {"server_id": srv_c_id, "name": "Gamma Server", "is_primary": False},
    ]

    # Server Alpha Artists
    alpha_artists = [
        build_mock_artist("101", "Pink Floyd", "plex://artist/pf-100"),
        build_mock_artist("102", "Radiohead", "plex://artist/rh-200"),
        build_mock_artist("103", "Daft Punk", "plex://artist/dp-300"),
        build_mock_artist("104", "AC/DC", "plex://artist/acdc-400"),
        build_mock_artist("105", "Björk", "plex://artist/bjork-500"),
        build_mock_artist("106", "The Beatles", "plex://artist/beatles-600"),
    ]

    # Server Beta Artists (Overlapping + Variations)
    beta_artists = [
        build_mock_artist("201", "Pink Floyd", "plex://artist/pf-100"),  # Exact GUID & title match
        build_mock_artist("202", "Radiohead", "plex://artist/rh-200"),   # Exact match
        build_mock_artist("203", "ACDC", "plex://artist/acdc-400"),      # Punctuation variation + same GUID
        build_mock_artist("204", "Bjork", "plex://artist/bjork-500"),    # Accent variation + same GUID
        build_mock_artist("205", "Nirvana", "plex://artist/nirv-700"),   # Unique to Beta
    ]

    # Server Gamma Artists (Overlapping + Large dataset simulation)
    gamma_artists = [
        build_mock_artist("301", "Pink Floyd", "plex://artist/pf-100"),   # Present on all 3 servers
        build_mock_artist("302", "Daft Punk", "plex://artist/dp-300"),    # Present on Alpha & Gamma
        build_mock_artist("303", "Nirvana", "plex://artist/nirv-700"),    # Present on Beta & Gamma
        build_mock_artist("304", "Coldplay", "plex://artist/cp-800"),     # Unique to Gamma
    ]

    # Add synthetic unique artists across servers to test large dataset performance
    for i in range(1, 26):
        alpha_artists.append(build_mock_artist(f"150{i}", f"Alpha Artist {i}", f"plex://artist/alpha-{i}"))
        beta_artists.append(build_mock_artist(f"250{i}", f"Beta Artist {i}", f"plex://artist/beta-{i}"))
        gamma_artists.append(build_mock_artist(f"350{i}", f"Alpha Artist {i}", f"plex://artist/alpha-{i}"))  # Duplicates Alpha

    mock_plex_a = MagicMock()
    lib_a = MagicMock()
    lib_a.all.return_value = alpha_artists
    mock_plex_a.library.sections.return_value = [lib_a]

    mock_plex_b = MagicMock()
    lib_b = MagicMock()
    lib_b.all.return_value = beta_artists
    mock_plex_b.library.sections.return_value = [lib_b]

    mock_plex_c = MagicMock()
    lib_c = MagicMock()
    lib_c.all.return_value = gamma_artists
    mock_plex_c.library.sections.return_value = [lib_c]

    def get_target_conn_mock(server_id=None):
        if server_id == srv_a_id:
            return mock_plex_a
        elif server_id == srv_b_id:
            return mock_plex_b
        elif server_id == srv_c_id:
            return mock_plex_c
        return mock_plex_a

    return {
        "accessible_servers": accessible_servers,
        "enabled_ids": [srv_a_id, srv_b_id, srv_c_id],
        "get_target_conn": get_target_conn_mock,
        "mock_plex_a": mock_plex_a,
        "mock_plex_b": mock_plex_b,
        "mock_plex_c": mock_plex_c,
    }


@patch("backend.services.plex.get_cached_data", return_value=None)
@patch("backend.services.plex.cache_data")
def test_fetch_all_artists_multi_server_deduplication(mock_cache, mock_get_cached, mock_multi_servers):
    """Verify artists spanning multiple servers are merged correctly with source details."""
    with patch("backend.services.plex.get_enabled_server_ids", return_value=mock_multi_servers["enabled_ids"]), \
         patch("backend.services.plex.fetch_accessible_plex_servers", return_value=mock_multi_servers["accessible_servers"]), \
         patch("backend.services.plex.get_target_plex_connection", side_effect=mock_multi_servers["get_target_conn"]), \
         patch("backend.services.plex.is_music_library_section", return_value=True):

        merged_artists = fetch_all_artists()

        # Pink Floyd should exist on all 3 servers -> 1 merged item with 3 sources
        pf = next((a for a in merged_artists if a["name"] == "Pink Floyd"), None)
        assert pf is not None
        assert pf["source_count"] == 3
        assert len(pf["sources"]) == 3
        server_names = {s["server_name"] for s in pf["sources"]}
        assert server_names == {"Alpha Server", "Beta Server", "Gamma Server"}

        # Radiohead on Alpha & Beta -> 2 sources
        rh = next((a for a in merged_artists if a["name"] == "Radiohead"), None)
        assert rh is not None
        assert rh["source_count"] == 2

        # Coldplay only on Gamma -> 1 source
        cp = next((a for a in merged_artists if a["name"] == "Coldplay"), None)
        assert cp is not None
        assert cp["source_count"] == 1


@patch("backend.services.plex.get_cached_data", return_value=None)
@patch("backend.services.plex.cache_data")
def test_artist_guid_and_normalization_deduplication(mock_cache, mock_get_cached, mock_multi_servers):
    """Verify GUID priority and title normalization (e.g. AC/DC vs ACDC) merge to a single entry."""
    with patch("backend.services.plex.get_enabled_server_ids", return_value=mock_multi_servers["enabled_ids"]), \
         patch("backend.services.plex.fetch_accessible_plex_servers", return_value=mock_multi_servers["accessible_servers"]), \
         patch("backend.services.plex.get_target_plex_connection", side_effect=mock_multi_servers["get_target_conn"]), \
         patch("backend.services.plex.is_music_library_section", return_value=True):

        merged_artists = fetch_all_artists()

        # AC/DC and ACDC share GUID plex://artist/acdc-400 -> Should merge!
        acdc_matches = [a for a in merged_artists if "ac" in a["name"].lower()]
        assert len(acdc_matches) == 1
        assert acdc_matches[0]["source_count"] == 2

        # Björk and Bjork share GUID -> Should merge!
        bjork_matches = [a for a in merged_artists if "bj" in a["name"].lower()]
        assert len(bjork_matches) == 1
        assert bjork_matches[0]["source_count"] == 2


@patch("backend.services.plex.get_cached_data")
@patch("backend.services.plex.cache_data")
def test_fetch_albums_for_artist_deduplication(mock_cache, mock_get_cached, mock_multi_servers):
    """Verify album deduplication across multiple server sources for a given artist."""
    mock_get_cached.return_value = None  # Cache miss

    # Setup multi-server artist sources for Pink Floyd (Artist ID 101)
    pf_sources = [
        {"server_id": "srv-1111-alpha", "server_name": "Alpha Server", "artist_id": 101},
        {"server_id": "srv-2222-beta", "server_name": "Beta Server", "artist_id": 201},
    ]

    cached_all_artists = [
        {"artist_id": 101, "name": "Pink Floyd", "sources": pf_sources}
    ]

    def mock_cache_side_effect(key):
        if key == "all_artists":
            return cached_all_artists
        return None

    mock_get_cached.side_effect = mock_cache_side_effect

    # Mock album items on Alpha and Beta
    alpha_pf_artist = MagicMock()
    alpha_pf_artist.title = "Pink Floyd"
    alpha_pf_artist.albums.return_value = [
        build_mock_album("501", "Dark Side of the Moon"),
        build_mock_album("502", "Wish You Were Here"),
    ]

    beta_pf_artist = MagicMock()
    beta_pf_artist.title = "Pink Floyd"
    beta_pf_artist.albums.return_value = [
        build_mock_album("601", "Dark Side of the Moon"),  # Exact title match across servers
        build_mock_album("602", "The Wall"),                # Unique to Beta
    ]

    mock_plex_a = MagicMock()
    mock_plex_a.fetchItem.return_value = alpha_pf_artist

    mock_plex_b = MagicMock()
    mock_plex_b.fetchItem.return_value = beta_pf_artist

    def get_target_conn_albums(server_id):
        if server_id == "srv-1111-alpha":
            return mock_plex_a
        return mock_plex_b

    with patch("backend.services.plex.get_enabled_server_ids", return_value=["srv-1111-alpha", "srv-2222-beta"]), \
         patch("backend.services.plex.fetch_accessible_plex_servers", return_value=mock_multi_servers["accessible_servers"]), \
         patch("backend.services.plex.get_target_plex_connection", side_effect=get_target_conn_albums):

        albums = fetch_albums_for_artist(101)

        # "Dark Side of the Moon" present on both servers -> 1 album with 2 sources
        dsotm = next((alb for alb in albums if "dark side" in alb["title"].lower()), None)
        assert dsotm is not None
        assert dsotm["source_count"] == 2
        assert len(dsotm["sources"]) == 2

        # "The Wall" only on Beta -> 1 album with 1 source
        wall = next((alb for alb in albums if alb["title"] == "The Wall"), None)
        assert wall is not None
        assert wall["source_count"] == 1


@patch("backend.services.plex.get_cached_data", return_value=None)
@patch("backend.services.plex.cache_data")
def test_deduplication_resilience_on_server_failure(mock_cache, mock_get_cached, mock_multi_servers):
    """Verify deduplication gracefully handles timeout/failure from one of the connected servers."""
    def get_target_conn_with_failure(server_id=None):
        if server_id == "srv-2222-beta":
            raise Exception("Connection timed out to Beta Server")
        return mock_multi_servers["get_target_conn"](server_id)

    with patch("backend.services.plex.get_enabled_server_ids", return_value=mock_multi_servers["enabled_ids"]), \
         patch("backend.services.plex.fetch_accessible_plex_servers", return_value=mock_multi_servers["accessible_servers"]), \
         patch("backend.services.plex.get_target_plex_connection", side_effect=get_target_conn_with_failure), \
         patch("backend.services.plex.is_music_library_section", return_value=True):

        # Should complete cleanly without raising exception
        merged_artists = fetch_all_artists()

        assert len(merged_artists) > 0
        # Pink Floyd should still be present from Alpha and Gamma (2 sources instead of 3)
        pf = next((a for a in merged_artists if a["name"] == "Pink Floyd"), None)
        assert pf is not None
        assert pf["source_count"] == 2
        server_names = {s["server_name"] for s in pf["sources"]}
        assert server_names == {"Alpha Server", "Gamma Server"}


def test_audit_deduplication_script(mock_multi_servers):
    """Verify that audit_deduplication script runs independent GUID and fuzzy checks and produces valid reports."""
    from backend.scripts.audit_deduplication import audit_deduplication, generate_report

    raw_catalogs = {
        "Alpha Server": [
            {"rating_key": "101", "title": "Pink Floyd", "guid": "plex://artist/pf-100", "server_id": "srv-1111-alpha"},
            {"rating_key": "102", "title": "Radiohead", "guid": "plex://artist/rh-200", "server_id": "srv-1111-alpha"},
            {"rating_key": "103", "title": "Guns N' Roses", "guid": "plex://artist/gnr-300", "server_id": "srv-1111-alpha"},
        ],
        "Beta Server": [
            {"rating_key": "201", "title": "Pink Floyd", "guid": "plex://artist/pf-100", "server_id": "srv-2222-beta"},
            {"rating_key": "202", "title": "Radiohead", "guid": "plex://artist/rh-200", "server_id": "srv-2222-beta"},
            {"rating_key": "203", "title": "Guns N Roses", "guid": "plex://artist/gnr-900", "server_id": "srv-2222-beta"}, # Different GUID, similar name
        ],
    }

    merged_artists = [
        {
            "artist_id": "101",
            "name": "Pink Floyd",
            "sources": [
                {"server_id": "srv-1111-alpha", "server_name": "Alpha Server", "artist_id": "101"},
                {"server_id": "srv-2222-beta", "server_name": "Beta Server", "artist_id": "201"},
            ],
            "source_count": 2,
        },
        {
            "artist_id": "102",
            "name": "Radiohead",
            "sources": [
                {"server_id": "srv-1111-alpha", "server_name": "Alpha Server", "artist_id": "102"},
                {"server_id": "srv-2222-beta", "server_name": "Beta Server", "artist_id": "202"},
            ],
            "source_count": 2,
        },
        {
            "artist_id": "103",
            "name": "Guns N' Roses",
            "sources": [{"server_id": "srv-1111-alpha", "server_name": "Alpha Server", "artist_id": "103"}],
            "source_count": 1,
        },
        {
            "artist_id": "203",
            "name": "Guns N Roses",
            "sources": [{"server_id": "srv-2222-beta", "server_name": "Beta Server", "artist_id": "203"}],
            "source_count": 1,
        },
    ]

    summary = audit_deduplication(raw_catalogs, merged_artists)

    assert summary["total_raw_items"] == 6
    assert summary["merged_items_count"] == 4
    assert summary["verified_guid_merges"] == 2  # Pink Floyd & Radiohead matched by GUID
    assert summary["potential_missed_duplicates_count"] == 1  # Guns N' Roses vs Guns N Roses detected as candidate missed duplicate!

    report = generate_report(summary)
    assert "TUNEBOX MULTI-SERVER DEDUPLICATION AUDIT REPORT" in report
    assert "Guns N' Roses" in report

