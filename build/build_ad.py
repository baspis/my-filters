#!/usr/bin/env python3
"""Build ad/filter.txt from 280blocker adblock."""

from __future__ import annotations

import sys

from common import (
    ROOT,
    FilterMeta,
    Merger,
    MergeStats,
    fetch_with_cache,
    log_source_summary,
    month_urls_utc,
    print_build_summary,
    write_filter_atomic,
    MIN_OUTPUT_RULES_AD,
)

OUTPUT = ROOT / "ad" / "filter.txt"
BLOCKER_CACHE = ROOT / "sources" / "280blocker_ad.cache.txt"

BLOCKER_MIN_RULES = 100


def merge() -> tuple[list[str], list[str], MergeStats, int]:
    merger = Merger()
    sources = []

    blocker = fetch_with_cache(
        "280blocker adblock",
        month_urls_utc("https://280blocker.net/files/280blocker_adblock"),
        BLOCKER_CACHE,
        min_parsed_rules=BLOCKER_MIN_RULES,
        keep_exceptions=True,
        reject_preprocessor=True,
    )
    log_source_summary(blocker)
    sources.append(blocker)
    merger.add_source(blocker)

    rules = merger.rules
    return rules, merger.log, MergeStats(sources=sources), merger.duplicates_removed


def main() -> int:
    try:
        rules, log, stats, dupes = merge()
        log.append(f"Duplicates removed (exact match): {dupes}")
        log.append(f"Total rules: {len(rules)}")
        result = write_filter_atomic(
            OUTPUT,
            FilterMeta(
                "Personal ad supplement",
                "280blocker adblock supplement "
                "(exact-match dedupe; @@ exceptions kept if upstream provides them). "
                "Subscribe to AdGuard Japanese filter Plus directly. "
                "Pair with built-in AdGuard #2,3,7,11,14,17 on iOS/PC.",
            ),
            rules,
            stats.sources,
            log,
            min_output_rules=MIN_OUTPUT_RULES_AD,
        )
        result.duplicates_removed = dupes
        print_build_summary(result, duplicates_removed=dupes)
        return 0
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
