#!/usr/bin/env python3
"""Merge personal DNS blocklists into dns/filter.txt."""

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

OUTPUT = ROOT / "dns" / "filter.txt"
BLOCKER_CACHE = ROOT / "sources" / "280blocker_dns.cache.txt"

DNS_SOURCES: list[tuple[str, str]] = [
    (
        "AdGuard DNS filter (#15)",
        "https://filters.adtidy.org/extension/chromium/filters/15.txt",
    ),
    (
        "HaGeZi Multi PRO",
        "https://raw.githubusercontent.com/hagezi/dns-blocklists/main/adblock/pro.txt",
    ),
]


def merge() -> tuple[list[str], list[str]]:
    merger = Merger()

    for name, url in DNS_SOURCES:
        merger.add(name, parse_rules(fetch(url)))

    label, text = fetch_with_cache(
        "280blocker domain_ag",
        month_urls_utc("https://280blocker.net/files/280blocker_domain_ag"),
        BLOCKER_CACHE,
    )
    merger.add(label, parse_rules(text))

    return merger.finish(), merger.log


def main() -> int:
    try:
        rules, log = merge()
        write_filter(
            OUTPUT,
            "Personal merged DNS filter",
            "AdGuard #15 + HaGeZi Multi PRO + 280blocker domain_ag (deduplicated)",
            rules,
            log,
        )
        return 0
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
