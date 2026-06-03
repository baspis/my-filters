#!/usr/bin/env python3
"""Merge personal browser ad blocklists into ad/filter.txt."""

from __future__ import annotations

import sys

from common import (
    ROOT,
    Merger,
    fetch,
    fetch_with_cache,
    month_urls_utc,
    parse_rules,
    write_filter,
)

OUTPUT = ROOT / "ad" / "filter.txt"
BLOCKER_CACHE = ROOT / "sources" / "280blocker_ad.cache.txt"

ADGUARD_FILTER_IDS = (2, 3, 17, 14, 7, 11)


def merge() -> tuple[list[str], list[str]]:
    merger = Merger()

    for fid in ADGUARD_FILTER_IDS:
        url = f"https://filters.adtidy.org/extension/chromium/filters/{fid}.txt"
        merger.add(f"AdGuard filter #{fid}", parse_rules(fetch(url)))

    label, text = fetch_with_cache(
        "280blocker adblock",
        month_urls_utc("https://280blocker.net/files/280blocker_adblock"),
        BLOCKER_CACHE,
    )
    merger.add(label, parse_rules(text))

    return merger.finish(), merger.log


def main() -> int:
    try:
        rules, log = merge()
        write_filter(
            OUTPUT,
            "Personal merged ad filter",
            "AdGuard #2,3,17,14,7,11 + 280blocker adblock (deduplicated)",
            rules,
            log,
        )
        return 0
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
