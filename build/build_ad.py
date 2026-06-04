#!/usr/bin/env python3
"""Merge ad/filter.txt: 280blocker adblock + AdGuard Japanese filter Plus."""

from __future__ import annotations

import sys

from common import (
    ROOT,
    FilterMeta,
    Merger,
    MergeStats,
    SourceSpec,
    fetch_first_validated,
    fetch_with_cache,
    log_source_summary,
    month_urls_utc,
    print_build_summary,
    write_filter_atomic,
    MIN_OUTPUT_RULES_AD,
)

OUTPUT = ROOT / "ad" / "filter.txt"
BLOCKER_CACHE = ROOT / "sources" / "280blocker_ad.cache.txt"

JPF_PLUS_CANDIDATES: list[SourceSpec] = [
    SourceSpec(
        "AdGuard Japanese filter Plus",
        "https://yuki2718.github.io/adblock2/japanese/jpf-plus.txt",
        min_parsed_rules=50,
    ),
    SourceSpec(
        "AdGuard Japanese filter Plus (GitHub raw)",
        "https://raw.githubusercontent.com/Yuki2718/adblock2/main/japanese/jpf-plus.txt",
        min_parsed_rules=50,
    ),
]

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
    )
    log_source_summary(blocker)
    sources.append(blocker)
    merger.add_source(blocker)

    jpf = fetch_first_validated(JPF_PLUS_CANDIDATES, keep_exceptions=True)
    log_source_summary(jpf)
    sources.append(jpf)
    merger.add_source(jpf)

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
                "Personal merged ad filter",
                "280blocker adblock + AdGuard Japanese filter Plus "
                "(exact-match dedupe; @@ exceptions kept). "
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
