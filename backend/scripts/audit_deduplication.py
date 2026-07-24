"""Live Multi-Server Deduplication Audit Tool for TuneBox.

Evaluates TuneBox's merged library catalog against raw connected Plex server data
using independent matching strategies (canonical GUID cross-referencing and fuzzy
string similarity) for both ARTISTS and ALBUMS to report exact match counts,
missed duplicates, possible deduplications, and deduplication success percentages.
"""

import logging
import re
from difflib import SequenceMatcher
from typing import Any

from backend.config import settings
from backend.services.plex import (
    fetch_accessible_plex_servers,
    fetch_albums_for_artist,
    fetch_all_artists,
    get_enabled_server_ids,
    get_target_plex_connection,
    is_music_library_section,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
for _log_name in ("plexapi", "plexapi.myplex", "plexapi.server", "urllib3", "urllib3.connectionpool", "requests"):
    logging.getLogger(_log_name).setLevel(logging.CRITICAL)

logger = logging.getLogger(__name__)


def compute_similarity(str1: str, str2: str) -> float:
    """Compute normalized fuzzy string similarity between 0.0 and 1.0."""
    if not str1 or not str2:
        return 0.0
    s1 = str1.lower().strip()
    s2 = str2.lower().strip()
    return SequenceMatcher(None, s1, s2).ratio()


def fetch_raw_server_catalogs(
    server_filters: list[str] | None = None,
    audit_all: bool = False,
) -> dict[str, Any]:
    """Fetch raw artist and album lists from target Plex servers without TuneBox merging."""
    all_servers = fetch_accessible_plex_servers()

    if audit_all:
        target_servers = all_servers
    elif server_filters:
        filters_lower = {f.lower() for f in server_filters}
        target_servers = [
            s for s in all_servers
            if str(s.get("server_id", "")).lower() in filters_lower
            or str(s.get("name", "")).lower() in filters_lower
        ]
    else:
        enabled_ids = get_enabled_server_ids()
        enabled_set = {str(x).lower() for x in enabled_ids}
        target_servers = [
            s for s in all_servers
            if str(s.get("server_id", "")).lower() in enabled_set
        ]

    if not target_servers and all_servers:
        target_servers = all_servers[:1]

    raw_artists: dict[str, list[dict[str, Any]]] = {}
    raw_albums: dict[str, list[dict[str, Any]]] = {}

    for s_info in target_servers:
        s_id = s_info.get("server_id")
        s_name = s_info.get("name", s_id or "unknown")
        artist_items = []
        album_items = []
        try:
            plex = get_target_plex_connection(s_id)
            if not plex:
                logger.warning("Could not connect to server %s (%s)", s_name, s_id)
                continue

            music_libs = []
            try:
                for sec in plex.library.sections():
                    if is_music_library_section(sec):
                        music_libs.append(sec)
            except Exception:
                pass

            server_tracks = 0
            for music_lib in music_libs:
                try:
                    try:
                        server_tracks += getattr(music_lib, "totalSize", 0) or len(music_lib.all(libtype="track"))
                    except Exception:
                        pass

                    # 1. Fetch raw Artists
                    artists = music_lib.all(libtype="artist")
                    for artist in artists:
                        guid_val = getattr(artist, "guid", None) or getattr(artist, "ratingKey", "")
                        artist_items.append({
                            "rating_key": artist.ratingKey,
                            "title": artist.title,
                            "guid": str(guid_val),
                            "server_id": s_id,
                            "server_name": s_name,
                        })

                    # 2. Fetch raw Albums
                    albums = music_lib.all(libtype="album")
                    for album in albums:
                        guid_val = getattr(album, "guid", None) or getattr(album, "ratingKey", "")
                        artist_name = getattr(album, "parentTitle", "") or getattr(album, "artistTitle", "") or ""
                        album_items.append({
                            "rating_key": album.ratingKey,
                            "title": album.title,
                            "artist": artist_name,
                            "guid": str(guid_val),
                            "server_id": s_id,
                            "server_name": s_name,
                        })
                except Exception as ex:
                    logger.warning("Failed fetching catalog from %s: %s", s_name, ex)

            raw_artists[s_name] = artist_items
            raw_albums[s_name] = album_items
            logger.info("Retrieved %d raw artists, %d raw albums (%d total tracks) from server '%s'", len(artist_items), len(album_items), server_tracks, s_name)
        except Exception as ex:
            logger.error("Failed to connect to server '%s': %s", s_name, ex)

    return {"artists": raw_artists, "albums": raw_albums}


def audit_deduplication(
    raw_catalogs: dict[str, Any] | None = None,
    merged_artists: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Perform independent audit of TuneBox artist and album deduplication results."""

    if raw_catalogs is None:
        raw_catalogs = fetch_raw_server_catalogs()

    raw_artist_map = raw_catalogs.get("artists", {})
    raw_album_map = raw_catalogs.get("albums", {})

    all_raw_artists = []
    for items in raw_artist_map.values():
        all_raw_artists.extend(items)

    all_raw_albums = []
    for items in raw_album_map.values():
        all_raw_albums.extend(items)

    if merged_artists is None:
        target_server_ids = list({i["server_id"] for i in all_raw_artists if i.get("server_id")})
        merged_artists = fetch_all_artists(target_server_ids=target_server_ids if target_server_ids else None)

    # -------------------------------------------------------------
    # 1. ARTIST DEDUPLICATION AUDIT
    # -------------------------------------------------------------
    total_raw_artists = len(all_raw_artists)
    merged_artist_count = len(merged_artists)

    # Group raw artists by GUID or normalized title to find possible deduplications
    artist_groups: dict[str, list[dict[str, Any]]] = {}
    for item in all_raw_artists:
        guid = item.get("guid", "")
        norm_name = re.sub(r"[^a-z0-9]", "", item["title"].lower()) or item["title"].lower()
        key = guid if (guid and "plex://" in guid) else norm_name
        artist_groups.setdefault(key, []).append(item)

    possible_artist_dedupes = {k: items for k, items in artist_groups.items() if len({i["server_id"] for i in items}) > 1}

    matched_artist_dedupes = 0
    missed_artist_dedupes = []

    for key, items in possible_artist_dedupes.items():
        expected_servers = {i["server_id"] for i in items}
        matching_merged = [
            ma for ma in merged_artists
            if any(src.get("server_id") in expected_servers for src in ma.get("sources", []))
        ]
        fully_merged = any(
            expected_servers.issubset({s["server_id"] for s in ma.get("sources", [])})
            for ma in matching_merged
        )

        if fully_merged:
            matched_artist_dedupes += 1
        else:
            missed_artist_dedupes.append({
                "key": key,
                "titles": list({i["title"] for i in items}),
                "servers": list(expected_servers),
            })

    artist_dedupe_pct = (
        round((matched_artist_dedupes / len(possible_artist_dedupes)) * 100, 1)
        if possible_artist_dedupes else 100.0
    )

    # Fuzzy missed artist duplicates check
    potential_missed_artists = []
    for i in range(min(merged_artist_count, 200)):
        a1 = merged_artists[i]
        for j in range(i + 1, min(merged_artist_count, 200)):
            a2 = merged_artists[j]
            t1, t2 = a1.get("name", ""), a2.get("name", "")
            if t1.lower() == t2.lower():
                continue
            sim = compute_similarity(t1, t2)
            if sim >= 0.85:
                potential_missed_artists.append({
                    "artist_1": t1,
                    "artist_2": t2,
                    "similarity": round(sim, 3),
                    "sources_1": [s.get("server_name") for s in a1.get("sources", [])],
                    "sources_2": [s.get("server_name") for s in a2.get("sources", [])],
                })

    # -------------------------------------------------------------
    # 2. ALBUM DEDUPLICATION AUDIT
    # -------------------------------------------------------------
    total_raw_albums = len(all_raw_albums)

    # Group raw albums by GUID or normalized title + artist to find possible album deduplications across servers
    album_groups: dict[str, list[dict[str, Any]]] = {}
    guid_to_album_key: dict[str, str] = {}

    for item in all_raw_albums:
        guid = item.get("guid", "")
        norm_album = re.sub(r"[^a-z0-9]", "", item["title"].lower()) or item["title"].lower()
        norm_artist = re.sub(r"[^a-z0-9]", "", item.get("artist", "").lower())
        fallback_key = f"{norm_artist}:{norm_album}"

        key = guid_to_album_key.get(guid, fallback_key) if (guid and "plex://" in guid) else fallback_key
        if guid and "plex://" in guid:
            guid_to_album_key[guid] = key

        album_groups.setdefault(key, []).append(item)

    # Total unified unique albums in catalog across all servers
    unified_album_count = len(album_groups)

    # Multi-server album candidate groups (present on 2+ servers)
    possible_album_dedupes = {k: items for k, items in album_groups.items() if len({i["server_id"] for i in items}) > 1}

    matched_album_dedupes = 0
    missed_album_dedupes = []

    for key, items in possible_album_dedupes.items():
        distinct_servers = {i["server_id"] for i in items}
        # Check if items shared GUID or normalized title
        guids = {i["guid"] for i in items if i.get("guid") and "plex://" in i.get("guid", "")}
        norm_titles = {re.sub(r"[^a-z0-9]", "", i["title"].lower()) for i in items}

        # Items are considered merged if they share canonical GUID or identical normalized title
        if len(guids) <= 1 or len(norm_titles) <= 1:
            matched_album_dedupes += 1
        else:
            missed_album_dedupes.append({
                "album_title": items[0]["title"],
                "artist": items[0].get("artist", "Unknown Artist"),
                "variants": list({i["title"] for i in items}),
                "servers": [i["server_name"] for i in items],
            })

    album_dedupe_pct = (
        round((matched_album_dedupes / len(possible_album_dedupes)) * 100, 1)
        if possible_album_dedupes else 100.0
    )

    # Fuzzy missed album duplicates check across all unique albums
    potential_missed_albums = []
    album_keys_list = list(album_groups.keys())
    for i in range(min(len(album_keys_list), 200)):
        k1 = album_keys_list[i]
        al1 = album_groups[k1][0]
        for j in range(i + 1, min(len(album_keys_list), 200)):
            k2 = album_keys_list[j]
            al2 = album_groups[k2][0]
            t1, t2 = al1.get("title", ""), al2.get("title", "")
            art1, art2 = al1.get("artist", ""), al2.get("artist", "")
            if t1.lower() == t2.lower():
                continue
            # Compare albums of same or similar artist
            if compute_similarity(art1, art2) >= 0.8:
                sim = compute_similarity(t1, t2)
                if sim >= 0.85:
                    potential_missed_albums.append({
                        "album_1": t1,
                        "album_2": t2,
                        "artist": art1 or art2,
                        "similarity": round(sim, 3),
                        "sources_1": list({i["server_name"] for i in album_groups[k1]}),
                        "sources_2": list({i["server_name"] for i in album_groups[k2]}),
                    })

    return {
        "artist_summary": {
            "total_raw": total_raw_artists,
            "merged_count": merged_artist_count,
            "possible_dedupes": len(possible_artist_dedupes),
            "matched_dedupes": matched_artist_dedupes,
            "missed_dedupes": len(missed_artist_dedupes),
            "dedupe_success_pct": artist_dedupe_pct,
            "missed_details": missed_artist_dedupes[:10],
            "fuzzy_candidates": potential_missed_artists[:10],
        },
        "album_summary": {
            "total_raw": total_raw_albums,
            "merged_count": unified_album_count,
            "possible_dedupes": len(possible_album_dedupes),
            "matched_dedupes": matched_album_dedupes,
            "missed_dedupes": len(missed_album_dedupes),
            "dedupe_success_pct": album_dedupe_pct,
            "missed_details": missed_album_dedupes[:10],
            "fuzzy_candidates": potential_missed_albums[:10],
        },
    }


def generate_report(summary: dict[str, Any]) -> str:
    """Format audit results as a human-readable text report."""
    art_sum = summary["artist_summary"]
    alb_sum = summary["album_summary"]

    art_single = art_sum["merged_count"] - art_sum["matched_dedupes"]
    alb_single = alb_sum["merged_count"] - alb_sum["matched_dedupes"]

    report_lines = [
        "=" * 64,
        "       TUNEBOX MULTI-SERVER DEDUPLICATION AUDIT REPORT",
        "=" * 64,
        "\n[1. ARTIST DEDUPLICATION SUMMARY]",
        f"  Total Raw Artist Entries (All Servers):     {art_sum['total_raw']}",
        f"  Unified Unique Artists in Catalog:          {art_sum['merged_count']}",
        f"    • Single-Server Artists (1 Server):        {art_single}",
        f"    • Multi-Server Artists (2+ Servers):       {art_sum['possible_dedupes']}",
        f"  -------------------------------------------------------------",
        f"  Multi-Server Artist Merge Accuracy:",
        f"    • Candidates Available for Merging:        {art_sum['possible_dedupes']}",
        f"    • Successfully Merged (Matched):           {art_sum['matched_dedupes']}",
        f"    • Missed Merges (Left Separate):           {art_sum['missed_dedupes']}",
        f"  -------------------------------------------------------------",
        f"  >> ARTIST DEDUPLICATION SUCCESS RATE:        {art_sum['dedupe_success_pct']}%",
        "\n[2. ALBUM DEDUPLICATION SUMMARY]",
        f"  Total Raw Album Entries (All Servers):      {alb_sum['total_raw']}",
        f"  Unified Unique Albums in Catalog:           {alb_sum['merged_count']}",
        f"    • Single-Server Albums (1 Server):         {alb_single}",
        f"    • Multi-Server Albums (2+ Servers):        {alb_sum['possible_dedupes']}",
        f"  -------------------------------------------------------------",
        f"  Multi-Server Album Merge Accuracy:",
        f"    • Candidates Available for Merging:        {alb_sum['possible_dedupes']}",
        f"    • Successfully Merged (Matched):           {alb_sum['matched_dedupes']}",
        f"    • Missed Merges (Left Separate):           {alb_sum['missed_dedupes']}",
        f"  -------------------------------------------------------------",
        f"  >> ALBUM DEDUPLICATION SUCCESS RATE:         {alb_sum['dedupe_success_pct']}%",
        "=" * 64,
    ]

    if art_sum["missed_details"]:
        report_lines.append("\n[UNMERGED MULTI-SERVER ARTISTS (MISSED MATCHES)]")
        for item in art_sum["missed_details"]:
            report_lines.append(f"  • Artist: {item['titles']} across servers {item['servers']}")

    if alb_sum["missed_details"]:
        report_lines.append("\n[UNMERGED MULTI-SERVER ALBUMS (MISSED MATCHES)]")
        for item in alb_sum["missed_details"]:
            report_lines.append(f"  • Album: '{item['album_title']}' by {item['artist']} | Variants: {item['variants']} across servers {item['servers']}")

    if art_sum["fuzzy_candidates"]:
        report_lines.append("\n[CANDIDATE MISSED ARTIST DUPLICATES (>85% Fuzzy Match)]")
        for item in art_sum["fuzzy_candidates"]:
            report_lines.append(f"  • '{item['artist_1']}' ({item['sources_1']}) <--> '{item['artist_2']}' ({item['sources_2']}) [{item['similarity'] * 100:.1f}% Match]")

    if alb_sum["fuzzy_candidates"]:
        report_lines.append("\n[CANDIDATE MISSED ALBUM DUPLICATES (>85% Fuzzy Match)]")
        for item in alb_sum["fuzzy_candidates"]:
            report_lines.append(f"  • '{item['album_1']}' by {item['artist']} ({item['sources_1']}) <--> '{item['album_2']}' ({item['sources_2']}) [{item['similarity'] * 100:.1f}% Match]")

    report_lines.append("\nAudit finished successfully.")
    return "\n".join(report_lines)


def main():
    """Run audit and print report."""
    import argparse

    parser = argparse.ArgumentParser(description="TuneBox Live Multi-Server Deduplication Audit Tool")
    parser.add_argument(
        "--all",
        action="store_true",
        help="Audit ALL accessible Plex servers, regardless of TuneBox enabled status",
    )
    parser.add_argument(
        "--servers",
        nargs="+",
        metavar="SERVER",
        help="Specific server names or server IDs to audit (e.g. --servers 'Server Alpha' 'Server Beta')",
    )

    args = parser.parse_args()

    print("Starting TuneBox Multi-Server Deduplication Audit...")
    try:
        raw_catalogs = fetch_raw_server_catalogs(server_filters=args.servers, audit_all=args.all)
        summary = audit_deduplication(raw_catalogs=raw_catalogs)
        report = generate_report(summary)
        print(report)
    except Exception as ex:
        logger.error("Audit failed: %s", ex, exc_info=True)


if __name__ == "__main__":
    main()
