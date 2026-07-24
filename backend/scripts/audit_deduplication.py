"""Live Multi-Server Deduplication Audit Tool for TuneBox.

Evaluates TuneBox's merged library catalog against raw connected Plex server data
using independent matching strategies (canonical GUID cross-referencing and fuzzy
string similarity) to detect missed duplicates (false negatives) and bad merges
(false positives).
"""

import logging
import re
from difflib import SequenceMatcher
from typing import Any

from backend.config import settings
from backend.services.plex import (
    fetch_accessible_plex_servers,
    fetch_all_artists,
    get_enabled_server_ids,
    get_target_plex_connection,
    is_music_library_section,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
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
) -> dict[str, list[dict[str, Any]]]:
    """Fetch raw artist lists from target Plex servers without TuneBox merging."""
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

    raw_catalogs: dict[str, list[dict[str, Any]]] = {}

    for s_info in target_servers:
        s_id = s_info.get("server_id")
        s_name = s_info.get("name", s_id or "unknown")
        raw_items = []
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

            for music_lib in music_libs:
                try:
                    artists = music_lib.all(libtype="artist")
                    for artist in artists:
                        guid_val = getattr(artist, "guid", None) or getattr(artist, "ratingKey", "")
                        raw_items.append({
                            "rating_key": artist.ratingKey,
                            "title": artist.title,
                            "guid": str(guid_val),
                            "server_id": s_id,
                            "server_name": s_name,
                        })
                except Exception as ex:
                    logger.warning("Failed fetching artists from %s: %s", s_name, ex)
            raw_catalogs[s_name] = raw_items
            logger.info("Retrieved %d raw artists from server '%s'", len(raw_items), s_name)
        except Exception as ex:
            logger.error("Failed to connect to server '%s': %s", s_name, ex)

    return raw_catalogs


def audit_deduplication(raw_catalogs: dict[str, list[dict[str, Any]]] | None = None, merged_artists: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Perform independent audit of TuneBox deduplication results."""

    if raw_catalogs is None:
        raw_catalogs = fetch_raw_server_catalogs()

    if merged_artists is None:
        merged_artists = fetch_all_artists()

    all_raw_items = []
    for s_name, items in raw_catalogs.items():
        all_raw_items.extend(items)

    total_raw_count = len(all_raw_items)
    merged_count = len(merged_artists)

    # 1. GUID Canonical Check
    # Group raw items by canonical GUID (e.g. plex://artist/...)
    guid_groups: dict[str, list[dict[str, Any]]] = {}
    for item in all_raw_items:
        guid = item.get("guid", "")
        if guid and "plex://" in guid:
            guid_groups.setdefault(guid, []).append(item)

    multi_server_guids = {guid: items for guid, items in guid_groups.items() if len({i["server_id"] for i in items}) > 1}

    verified_guid_merges = 0
    missed_guid_merges = []

    for guid, items in multi_server_guids.items():
        # Find if TuneBox merged these items into a single entry
        expected_servers = {i["server_id"] for i in items}

        matching_merged = [
            ma for ma in merged_artists
            if any(src.get("server_id") in expected_servers for src in ma.get("sources", []))
        ]

        # Check if all items ended up under 1 merged entity containing all expected servers
        fully_merged = any(
            expected_servers.issubset({s["server_id"] for s in ma.get("sources", [])})
            for ma in matching_merged
        )

        if fully_merged:
            verified_guid_merges += 1
        else:
            missed_guid_merges.append({
                "guid": guid,
                "titles": list({i["title"] for i in items}),
                "servers": list(expected_servers),
            })

    # 2. Missed Duplicates (False Negative Audit using Fuzzy Similarity)
    potential_missed_duplicates = []
    num_merged = len(merged_artists)

    for i in range(min(num_merged, 200)):
        a1 = merged_artists[i]
        for j in range(i + 1, min(num_merged, 200)):
            a2 = merged_artists[j]
            t1 = a1.get("name", "")
            t2 = a2.get("name", "")

            # Ignore exact same name (already normalized or distinct)
            if t1.lower() == t2.lower():
                continue

            sim = compute_similarity(t1, t2)
            if sim >= 0.85:
                potential_missed_duplicates.append({
                    "artist_1": t1,
                    "artist_2": t2,
                    "similarity": round(sim, 3),
                    "sources_1": [s.get("server_name") for s in a1.get("sources", [])],
                    "sources_2": [s.get("server_name") for s in a2.get("sources", [])],
                })

    # 3. Over-Aggregation (False Positive Audit)
    potential_false_merges = []
    for ma in merged_artists:
        sources = ma.get("sources", [])
        if len(sources) > 1:
            # Check if source artist names differ significantly
            names = [s.get("name") or ma.get("name", "") for s in sources]
            distinct_names = set(names)
            if len(distinct_names) > 1:
                # Compare max pairwise difference
                for n1 in distinct_names:
                    for n2 in distinct_names:
                        if n1 != n2 and compute_similarity(n1, n2) < 0.70:
                            potential_false_merges.append({
                                "merged_title": ma.get("name"),
                                "differing_sources": sources,
                                "similarity": round(compute_similarity(n1, n2), 3),
                            })
                            break

    audit_summary = {
        "total_raw_items": total_raw_count,
        "merged_items_count": merged_count,
        "compression_ratio": round((1 - (merged_count / total_raw_count)) * 100, 1) if total_raw_count > 0 else 0.0,
        "multi_server_guid_groups": len(multi_server_guids),
        "verified_guid_merges": verified_guid_merges,
        "missed_guid_merges": missed_guid_merges,
        "potential_missed_duplicates_count": len(potential_missed_duplicates),
        "potential_missed_duplicates": potential_missed_duplicates[:10],
        "potential_false_merges_count": len(potential_false_merges),
        "potential_false_merges": potential_false_merges[:10],
    }

    return audit_summary


def generate_report(summary: dict[str, Any]) -> str:
    """Format audit results as a human-readable text report."""
    report_lines = [
        "=" * 60,
        "       TUNEBOX MULTI-SERVER DEDUPLICATION AUDIT REPORT",
        "=" * 60,
        f"Total Raw Items across Servers:      {summary['total_raw_items']}",
        f"Merged Items in TuneBox Catalog:     {summary['merged_items_count']}",
        f"Deduplication Reduction:             {summary['compression_ratio']}%",
        "-" * 60,
        "CANONICAL GUID INTEGRITY",
        f"Multi-Server GUID Groups Identified: {summary['multi_server_guid_groups']}",
        f"Successfully Unified GUID Groups:    {summary['verified_guid_merges']}",
        f"Missed GUID Merges (Unmerged):       {len(summary['missed_guid_merges'])}",
        "-" * 60,
        "FUZZY ANOMALY DETECTION",
        f"Potential Missed Duplicates (False -): {summary['potential_missed_duplicates_count']}",
        f"Potential False Merges (False +):      {summary['potential_false_merges_count']}",
        "=" * 60,
    ]

    if summary["potential_missed_duplicates"]:
        report_lines.append("\n[TOP CANDIDATE MISSED DUPLICATES]")
        for item in summary["potential_missed_duplicates"]:
            report_lines.append(f"  • '{item['artist_1']}' ({item['sources_1']}) <--> '{item['artist_2']}' ({item['sources_2']}) [Similarity: {item['similarity'] * 100:.1f}%]")

    if summary["potential_false_merges"]:
        report_lines.append("\n[POTENTIAL SUSPECT MERGES]")
        for item in summary["potential_false_merges"]:
            report_lines.append(f"  • Merged: '{item['merged_title']}' with conflicting sources (Similarity: {item['similarity'] * 100:.1f}%)")

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

