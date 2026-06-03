#!/usr/bin/env python3
"""Merge lightweight Safari/iOS ad lists: 280blocker + Japanese filter Plus."""

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

OUTPUT = ROOT / "ad" / "filter-ios.txt"
BLOCKER_CACHE = ROOT / "sources" / "280blocker_ad.cache.txt"

JPF_PLUS_URLS = [
    (
        "AdGuard Japanese filter Plus",
        "https://yuki2718.github.io/adblock2/japanese/jpf-plus.txt",
    ),
    (
        "AdGuard Japanese filter Plus (GitHub raw)",
        "https://raw.githubusercontent.com/Yuki2718/adblock2/main/japanese/jpf-plus.txt",
    ),
]


def fetch_first(urls: list[tuple[str, str]]) -> tuple[str, str]:
    last_error: Exception | None = None
    for name, url in urls:
        try:
            return name, fetch(url)
        except Exception as exc:
            print(f"WARN: {name} failed ({url}): {exc}", file=sys.stderr)
            last_error = exc
    raise RuntimeError("All URLs failed") from last_error


def merge() -> tuple[list[str], list[str]]:
    merger = Merger()

    label, text = fetch_with_cache(
        "280blocker adblock",
        month_urls_utc("https://280blocker.net/files/280blocker_adblock"),
        BLOCKER_CACHE,
    )
    merger.add(label, parse_rules(text))

    name, text = fetch_first(JPF_PLUS_URLS)
    merger.add(name, parse_rules(text))

    return merger.finish(), merger.log


def main() -> int:
    try:
        rules, log = merge()
        write_filter(
            OUTPUT,
            "Personal merged ad filter (iOS/Safari)",
            "280blocker adblock + AdGuard Japanese filter Plus (deduplicated). "
            "Use with built-in AdGuard filters #2,3,7,11,14,17 — not ad/filter.txt.",
            rules,
            log,
        )
        return 0
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
