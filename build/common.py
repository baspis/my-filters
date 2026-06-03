"""Shared fetch, parse, and dedupe helpers for filter builds."""

from __future__ import annotations

import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
SOURCES_DIR = ROOT / "sources"

FETCH_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; baspis-my-filters/1.0; "
        "+https://github.com/baspis/my-filters)"
    ),
    "Accept": "text/plain,*/*",
    "Accept-Language": "ja,en;q=0.9",
}

DOMAIN_RULE = re.compile(
    r"^\|\|([a-z0-9][a-z0-9._-]*\.)*[a-z0-9][a-z0-9._-]*\^",
    re.IGNORECASE,
)


def fetch(url: str, timeout: int = 120) -> str:
    req = urllib.request.Request(url, headers=FETCH_HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def month_ym_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m")


def month_urls_utc(base: str) -> list[str]:
    """base like https://280blocker.net/files/280blocker_domain_ag"""
    ym = month_ym_utc()
    year, month = int(ym[:4]), int(ym[4:6])
    urls = [f"{base}_{ym}.txt"]
    month -= 1
    if month < 1:
        month = 12
        year -= 1
    prev = f"{year}{month:02d}"
    urls.append(f"{base}_{prev}.txt")
    return urls


def fetch_with_cache(
    label: str,
    urls: list[str],
    cache_path: Path,
) -> tuple[str, str]:
    last_error: Exception | None = None
    for url in urls:
        try:
            text = fetch(url)
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(text, encoding="utf-8")
            return f"{label} ({url.rsplit('/', 1)[-1]})", text
        except urllib.error.HTTPError as exc:
            last_error = exc
            if exc.code in (403, 404):
                print(f"WARN: {url} -> HTTP {exc.code}", file=sys.stderr)
                continue
            raise
        except urllib.error.URLError as exc:
            last_error = exc
            print(f"WARN: {url} -> {exc}", file=sys.stderr)
            continue

    if cache_path.is_file():
        print(f"WARN: {label} using cache {cache_path}", file=sys.stderr)
        return f"{label} (cached)", cache_path.read_text(encoding="utf-8")

    raise RuntimeError(f"{label}: all URLs failed and no cache") from last_error


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


class Merger:
    def __init__(self) -> None:
        self._merged: list[str] = []
        self._seen: set[str] = set()
        self.log: list[str] = []

    def add(self, name: str, rules: list[str]) -> None:
        added = 0
        for rule in rules:
            key = dedupe_key(rule)
            if key in self._seen:
                continue
            self._seen.add(key)
            self._merged.append(rule)
            added += 1
        self.log.append(f"{name}: +{added} unique ({len(rules)} parsed)")

    @property
    def rules(self) -> list[str]:
        return self._merged

    def finish(self) -> list[str]:
        self.log.append(f"Total unique rules: {len(self._merged)}")
        return self._merged


def write_filter(
    output: Path,
    title: str,
    description: str,
    rules: list[str],
    log: list[str],
) -> None:
    now = datetime.now(ZoneInfo("Asia/Tokyo")).strftime("%Y-%m-%d %H:%M %Z")
    header = [
        f"! Title: {title}",
        f"! Description: {description}",
        "! Homepage: https://github.com/baspis/my-filters",
        "! License: See README (sources retain their own licenses)",
        f"! Last modified: {now}",
        "!",
    ]
    output.parent.mkdir(parents=True, exist_ok=True)
    body = "\n".join(header + rules) + "\n"
    output.write_text(body, encoding="utf-8")
    for line in log:
        print(line)
    print(f"Wrote {output} ({len(body):,} bytes)")
