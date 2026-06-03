#!/usr/bin/env python3
"""Merge and deduplicate personal DNS blocklists."""

from __future__ import annotations

import re
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "dns" / "filter.txt"
BLOCKER_CACHE = ROOT / "sources" / "280blocker.cache.txt"

FETCH_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; baspis-my-filters/1.0; "
        "+https://github.com/baspis/my-filters)"
    ),
    "Accept": "text/plain,*/*",
    "Accept-Language": "ja,en;q=0.9",
}

ADGUARD_URLS = [
    (
        "AdGuard DNS filter",
        "https://adguardteam.github.io/AdGuardSDNSFilter/Filters/filter.txt",
    ),
    (
        "AdGuard DNS filter (GitHub mirror)",
        "https://raw.githubusercontent.com/AdguardTeam/FiltersRegistry/master/filters/filter_15_DnsFilter/filter.txt",
    ),
]

HAGEZI_URL = (
    "HaGeZi Multi PRO",
    "https://raw.githubusercontent.com/hagezi/dns-blocklists/main/adblock/pro.txt",
)

DOMAIN_RULE = re.compile(
    r"^\|\|([a-z0-9][a-z0-9._-]*\.)*[a-z0-9][a-z0-9._-]*\^",
    re.IGNORECASE,
)


def fetch(url: str, timeout: int = 120) -> str:
    req = urllib.request.Request(url, headers=FETCH_HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def fetch_first(urls: list[tuple[str, str]]) -> tuple[str, str]:
    last_error: Exception | None = None
    for name, url in urls:
        try:
            return name, fetch(url)
        except Exception as exc:
            print(f"WARN: {name} failed ({url}): {exc}", file=sys.stderr)
            last_error = exc
    raise RuntimeError("All URLs failed") from last_error


def blocker_urls() -> list[str]:
    now = datetime.now(ZoneInfo("Asia/Tokyo"))
    candidates = []
    for offset in (0, 1):
        month = now.month - offset
        year = now.year
        while month < 1:
            month += 12
            year -= 1
        ym = f"{year}{month:02d}"
        candidates.append(
            f"https://280blocker.net/files/280blocker_domain_ag_{ym}.txt"
        )
    return candidates


def fetch_280blocker() -> tuple[str, str, bool]:
    """Return (label, text, updated_cache)."""
    last_error: Exception | None = None
    for url in blocker_urls():
        try:
            text = fetch(url)
            BLOCKER_CACHE.parent.mkdir(parents=True, exist_ok=True)
            BLOCKER_CACHE.write_text(text, encoding="utf-8")
            return f"280blocker ({url.split('/')[-1]})", text, True
        except urllib.error.HTTPError as exc:
            last_error = exc
            if exc.code in (403, 404):
                continue
            raise
        except urllib.error.URLError as exc:
            last_error = exc
            continue

    if BLOCKER_CACHE.is_file():
        print(
            "WARN: 280blocker fetch failed; using cached sources/280blocker.cache.txt",
            file=sys.stderr,
        )
        return "280blocker (cached)", BLOCKER_CACHE.read_text(encoding="utf-8"), False

    raise RuntimeError("280blocker: fetch failed and no cache") from last_error


def normalize_line(line: str) -> str:
    return line.strip()


def domain_key(line: str) -> str | None:
    m = DOMAIN_RULE.match(line)
    if not m:
        return None
    body = line[2 : line.index("^", 2)]
    return body.lower()


def dedupe_key(line: str) -> str:
    domain = domain_key(line)
    if domain:
        return f"domain:{domain}"
    return f"line:{line.lower()}"


def parse_rules(text: str) -> list[str]:
    rules: list[str] = []
    for raw in text.splitlines():
        line = normalize_line(raw)
        if not line or line.startswith("!"):
            continue
        if line.startswith("["):
            continue
        if line.startswith("@@"):
            continue
        rules.append(line)
    return rules


def merge_sources() -> tuple[list[str], list[str]]:
    merged: list[str] = []
    seen: set[str] = set()
    log: list[str] = []

    def add_rules(name: str, rules: list[str]) -> None:
        added = 0
        for rule in rules:
            key = dedupe_key(rule)
            if key in seen:
                continue
            seen.add(key)
            merged.append(rule)
            added += 1
        log.append(f"{name}: +{added} unique ({len(rules)} parsed)")

    name, text = fetch_first(ADGUARD_URLS)
    add_rules(name, parse_rules(text))

    name, url = HAGEZI_URL
    add_rules(name, parse_rules(fetch(url)))

    label, text, _ = fetch_280blocker()
    add_rules(label, parse_rules(text))

    log.append(f"Total unique rules: {len(merged)}")
    return merged, log


def write_filter(rules: list[str], log: list[str]) -> None:
    now = datetime.now(ZoneInfo("Asia/Tokyo")).strftime("%Y-%m-%d %H:%M %Z")
    header = [
        "! Title: Personal merged DNS filter",
        "! Description: AdGuard DNS filter + HaGeZi Multi PRO + 280blocker (deduplicated)",
        "! Homepage: https://github.com/baspis/my-filters",
        "! License: See README (sources retain their own licenses)",
        f"! Last modified: {now}",
        "!",
    ]
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    body = "\n".join(header + rules) + "\n"
    OUTPUT.write_text(body, encoding="utf-8")
    for line in log:
        print(line)
    print(f"Wrote {OUTPUT} ({len(body):,} bytes)")


def main() -> int:
    try:
        rules, log = merge_sources()
        write_filter(rules, log)
        return 0
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
