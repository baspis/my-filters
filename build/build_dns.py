#!/usr/bin/env python3
"""Merge personal DNS blocklists into dns/filter.txt."""

from __future__ import annotations

import sys

from common import (
    ROOT,
    FilterMeta,
    Merger,
    MergeStats,
    SourceSpec,
    apply_dns_output_exclusions,
    fetch_first_validated,
    fetch_validated_source,
    fetch_with_cache,
    log_source_summary,
    month_urls_utc,
    print_build_summary,
    write_filter_atomic,
    MIN_OUTPUT_RULES_DNS,
)

OUTPUT = ROOT / "dns" / "filter.txt"
BLOCKER_CACHE = ROOT / "sources" / "280blocker_dns.cache.txt"

ADGUARD_DNS_CANDIDATES: list[SourceSpec] = [
    SourceSpec(
        "AdGuard DNS filter (#15)",
        "https://filters.adtidy.org/extension/chromium/filters/15.txt",
        min_parsed_rules=10_000,
    ),
    SourceSpec(
        "AdGuard DNS filter (#15, AdGuardSDNSFilter mirror)",
        "https://adguardteam.github.io/AdGuardSDNSFilter/Filters/filter.txt",
        min_parsed_rules=10_000,
    ),
    SourceSpec(
        "AdGuard DNS filter (#15, FiltersRegistry mirror)",
        "https://raw.githubusercontent.com/AdguardTeam/FiltersRegistry/master/filters/filter_15_DnsFilter/filter.txt",
        min_parsed_rules=10_000,
    ),
]

HAGEZI_SOURCE = SourceSpec(
    "HaGeZi Multi PRO",
    "https://raw.githubusercontent.com/hagezi/dns-blocklists/main/adblock/pro.txt",
    min_parsed_rules=10_000,
)

BLOCKER_MIN_RULES = 500


def merge() -> tuple[list[str], list[str], MergeStats, int]:
    merger = Merger()
    sources = []

    adguard = fetch_first_validated(ADGUARD_DNS_CANDIDATES, keep_exceptions=False)
    log_source_summary(adguard)
    sources.append(adguard)
    merger.add_source(adguard)

    hagezi = fetch_validated_source(HAGEZI_SOURCE, keep_exceptions=False)
    log_source_summary(hagezi)
    sources.append(hagezi)
    merger.add_source(hagezi)

    blocker = fetch_with_cache(
        "280blocker domain_ag",
        month_urls_utc("https://280blocker.net/files/280blocker_domain_ag"),
        BLOCKER_CACHE,
        min_parsed_rules=BLOCKER_MIN_RULES,
        keep_exceptions=False,
    )
    log_source_summary(blocker)
    sources.append(blocker)
    merger.add_source(blocker)

    rules, excluded = apply_dns_output_exclusions(merger.rules)
    merger.log.append(f"DNS output exclusions: {excluded}")
    return rules, merger.log, MergeStats(sources=sources), merger.duplicates_removed


def main() -> int:
    try:
        rules, log, stats, dupes = merge()
        log.append(f"Duplicates removed (exact match): {dupes}")
        log.append(f"Total rules: {len(rules)}")
        result = write_filter_atomic(
            OUTPUT,
            FilterMeta(
                "Personal merged DNS filter",
                "AdGuard #15 + HaGeZi Multi PRO + 280blocker domain_ag "
                "(exact-match dedupe; @@ exceptions excluded)",
            ),
            rules,
            stats.sources,
            log,
            min_output_rules=MIN_OUTPUT_RULES_DNS,
        )
        result.duplicates_removed = dupes
        print_build_summary(result, duplicates_removed=dupes)
        return 0
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
