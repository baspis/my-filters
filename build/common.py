"""Shared fetch, parse, merge, validate, and write helpers for filter builds."""

from __future__ import annotations

import errno
import os
import re
import sys
import tempfile
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable
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

DEFAULT_TIMEOUT = 120
MAX_FETCH_ATTEMPTS = 4
INITIAL_BACKOFF_SEC = 2.0

# Reject merged outputs far below the last good publish (upstream may shrink legitimately;
# set BUILD_ALLOW_RULE_DROP=1 after manual review to accept a large decrease).
MIN_OUTPUT_RULES_DNS = 50_000
MIN_OUTPUT_RULES_AD = 2_000
OUTPUT_DROP_RATIO = 0.70

HTML_MARKERS = re.compile(
    r"^\s*(?:<!doctype\s+html|<html\b|<head\b|<body\b)",
    re.IGNORECASE,
)
PREPROCESSOR_DIRECTIVE = re.compile(r"^!#(?:include|if|endif)\b")

REQUIRED_HEADER_KEYS = ("Title:", "Description:", "Homepage:", "License:", "Last modified:")

DNS_RULE_HOST = re.compile(r"^\|\|([^\^$/]+)")

# Broad DNS blocks that break legitimate services when this list is used as
# recursive DNS (e.g. AdGuard Home + AdGuard app filter updates via filters.adtidy.org).
DNS_OUTPUT_EXCLUDED_RULES: frozenset[str] = frozenset(
    {
        "||rsc.cdn77.org^",
    }
)

# Browser geolocation backends. Upstream tracker lists often block these; keep them
# reachable when this file is recursive DNS (Zen/Firefox, Chrome, Safari).
BROWSER_GEOLOCATION_HOSTS: frozenset[str] = frozenset(
    {
        "location.services.mozilla.com",
        "geo.mozilla.org",
        "www.googleapis.com",
        "maps.googleapis.com",
        "gsp-ssl.ls.apple.com",
        "ls.apple.com",
    }
)


@dataclass(frozen=True)
class SourceSpec:
    name: str
    url: str
    min_parsed_rules: int


@dataclass
class ParsedSource:
    name: str
    adopted_label: str
    adopted_url: str
    from_cache: bool
    raw_bytes: int
    parsed_rules: int
    exceptions_kept: int = 0
    exceptions_dropped: int = 0
    rules: list[str] = field(default_factory=list)


@dataclass
class MergeStats:
    sources: list[ParsedSource] = field(default_factory=list)
    duplicates_removed: int = 0
    final_rules: int = 0
    output_changed: bool = False
    output_path: Path | None = None


@dataclass
class FilterMeta:
    title: str
    description: str
    license_line: str = "! License: See README (sources retain their own licenses)"


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


def normalize_line(line: str) -> str:
    return line.strip()


def looks_like_html(text: str) -> bool:
    sample = text.lstrip()[:4096]
    return bool(HTML_MARKERS.search(sample))


def decode_utf8_strict(data: bytes) -> str:
    if b"\x00" in data:
        raise ValueError("response contains NUL bytes")
    return data.decode("utf-8")


def validate_fetched_text(
    text: str,
    *,
    source_name: str,
    min_parsed_rules: int,
    keep_exceptions: bool,
    reject_preprocessor: bool = False,
) -> int:
    if not text.strip():
        raise ValueError(f"{source_name}: empty response")
    if looks_like_html(text):
        raise ValueError(f"{source_name}: response looks like HTML")
    rules, kept, dropped = parse_rules(
        text,
        keep_exceptions=keep_exceptions,
        reject_preprocessor=reject_preprocessor,
        source_name=source_name,
    )
    count = len(rules)
    if count < min_parsed_rules:
        raise ValueError(
            f"{source_name}: only {count} rules parsed "
            f"(minimum {min_parsed_rules})"
        )
    return count


def parse_rules(
    text: str,
    *,
    keep_exceptions: bool,
    reject_preprocessor: bool = False,
    source_name: str = "source",
) -> tuple[list[str], int, int]:
    """Return (rules, exceptions_kept, exceptions_dropped)."""
    rules: list[str] = []
    kept = 0
    dropped = 0
    for raw in text.splitlines():
        line = normalize_line(raw).removeprefix("\ufeff")
        if not line:
            continue
        if reject_preprocessor and PREPROCESSOR_DIRECTIVE.match(line):
            raise ValueError(
                f"{source_name}: unsupported preprocessor directive: {line}"
            )
        if line.startswith("!") or line.startswith("#"):
            continue
        if line.startswith("["):
            continue
        if line.startswith("@@"):
            if keep_exceptions:
                rules.append(line)
                kept += 1
            else:
                dropped += 1
            continue
        rules.append(line)
    return rules, kept, dropped


def apply_dns_output_exclusions(rules: list[str]) -> tuple[list[str], int]:
    """Drop known-problematic rules from DNS output; returns (rules, excluded_count)."""
    excluded = 0
    kept: list[str] = []
    for rule in rules:
        if rule in DNS_OUTPUT_EXCLUDED_RULES:
            excluded += 1
            continue
        host_match = DNS_RULE_HOST.match(rule)
        if host_match and host_match.group(1) in BROWSER_GEOLOCATION_HOSTS:
            excluded += 1
            continue
        kept.append(rule)
    return kept, excluded


def dedupe_exact(rules: list[str]) -> tuple[list[str], int]:
    seen: set[str] = set()
    merged: list[str] = []
    removed = 0
    for rule in rules:
        if rule in seen:
            removed += 1
            continue
        seen.add(rule)
        merged.append(rule)
    return merged, removed


class Merger:
    def __init__(self) -> None:
        self._merged: list[str] = []
        self._seen: set[str] = set()
        self.duplicates_removed = 0
        self.log: list[str] = []

    def add_source(self, source: ParsedSource) -> None:
        added = 0
        for rule in source.rules:
            if rule in self._seen:
                self.duplicates_removed += 1
                continue
            self._seen.add(rule)
            self._merged.append(rule)
            added += 1
        self.log.append(
            f"{source.adopted_label}: +{added} unique "
            f"({source.parsed_rules} parsed, cache={source.from_cache})"
        )

    @property
    def rules(self) -> list[str]:
        return self._merged


def _retryable_http(code: int) -> bool:
    return code == 429 or code >= 500


def _is_retryable_error(exc: Exception) -> bool:
    if isinstance(exc, TimeoutError):
        return True
    if isinstance(exc, urllib.error.HTTPError):
        return _retryable_http(exc.code)
    if isinstance(exc, ConnectionRefusedError):
        return False
    if isinstance(exc, OSError):
        if exc.errno in (
            errno.ETIMEDOUT,
            errno.EHOSTUNREACH,
            errno.ENETUNREACH,
            errno.ECONNRESET,
            errno.ECONNABORTED,
        ):
            return True
        if exc.errno in (errno.ECONNREFUSED, errno.EPIPE):
            return False
    if isinstance(exc, urllib.error.URLError):
        reason = exc.reason
        if reason is None:
            return False
        return _is_retryable_error(reason)
    return False


def fetch_bytes(
    url: str,
    *,
    timeout: int = DEFAULT_TIMEOUT,
    opener: Callable[..., object] | None = None,
) -> bytes:
    last_error: Exception | None = None
    open_fn = opener or urllib.request.urlopen
    for attempt in range(1, MAX_FETCH_ATTEMPTS + 1):
        try:
            req = urllib.request.Request(url, headers=FETCH_HEADERS)
            with open_fn(req, timeout=timeout) as resp:
                return resp.read()
        except urllib.error.HTTPError as exc:
            last_error = exc
            if exc.code in (403, 404):
                raise
            if _is_retryable_error(exc) and attempt < MAX_FETCH_ATTEMPTS:
                _sleep_backoff(attempt)
                continue
            raise
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last_error = exc
            if _is_retryable_error(exc) and attempt < MAX_FETCH_ATTEMPTS:
                _sleep_backoff(attempt)
                continue
            raise
    raise RuntimeError(f"fetch failed for {url}") from last_error


def _sleep_backoff(attempt: int) -> None:
    delay = INITIAL_BACKOFF_SEC * (2 ** (attempt - 1))
    print(f"WARN: retry in {delay:.0f}s (attempt {attempt})", file=sys.stderr)
    time.sleep(delay)


def fetch_text(url: str, **kwargs: object) -> str:
    return decode_utf8_strict(fetch_bytes(url, **kwargs))


def fetch_validated_source(
    spec: SourceSpec,
    *,
    keep_exceptions: bool,
    reject_preprocessor: bool = False,
    opener: Callable[..., object] | None = None,
) -> ParsedSource:
    data = fetch_bytes(spec.url, opener=opener)
    text = decode_utf8_strict(data)
    rules, kept, dropped = parse_rules(
        text,
        keep_exceptions=keep_exceptions,
        reject_preprocessor=reject_preprocessor,
        source_name=spec.name,
    )
    validate_fetched_text(
        text,
        source_name=spec.name,
        min_parsed_rules=spec.min_parsed_rules,
        keep_exceptions=keep_exceptions,
        reject_preprocessor=reject_preprocessor,
    )
    return ParsedSource(
        name=spec.name,
        adopted_label=spec.name,
        adopted_url=spec.url,
        from_cache=False,
        raw_bytes=len(data),
        parsed_rules=len(rules),
        exceptions_kept=kept,
        exceptions_dropped=dropped,
        rules=rules,
    )


def fetch_with_cache(
    label: str,
    urls: list[str],
    cache_path: Path,
    *,
    min_parsed_rules: int,
    keep_exceptions: bool,
    reject_preprocessor: bool = False,
    opener: Callable[..., object] | None = None,
) -> ParsedSource:
    last_error: Exception | None = None
    for url in urls:
        try:
            data = fetch_bytes(url, opener=opener)
            text = decode_utf8_strict(data)
            validate_fetched_text(
                text,
                source_name=label,
                min_parsed_rules=min_parsed_rules,
                keep_exceptions=keep_exceptions,
                reject_preprocessor=reject_preprocessor,
            )
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_bytes(data)
            rules, kept, dropped = parse_rules(
                text,
                keep_exceptions=keep_exceptions,
                reject_preprocessor=reject_preprocessor,
                source_name=label,
            )
            adopted = f"{label} ({url.rsplit('/', 1)[-1]})"
            print(
                f"OK: {label} url={url} bytes={len(data)} "
                f"parsed={len(rules)} cache_written=yes",
                file=sys.stderr,
            )
            return ParsedSource(
                name=label,
                adopted_label=adopted,
                adopted_url=url,
                from_cache=False,
                raw_bytes=len(data),
                parsed_rules=len(rules),
                exceptions_kept=kept,
                exceptions_dropped=dropped,
                rules=rules,
            )
        except urllib.error.HTTPError as exc:
            last_error = exc
            if exc.code in (403, 404):
                print(f"WARN: {url} -> HTTP {exc.code}", file=sys.stderr)
                continue
            raise
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            last_error = exc
            print(f"WARN: {url} -> {exc}", file=sys.stderr)
            continue

    if cache_path.is_file():
        data = cache_path.read_bytes()
        try:
            text = decode_utf8_strict(data)
            validate_fetched_text(
                text,
                source_name=f"{label} (cache)",
                min_parsed_rules=min_parsed_rules,
                keep_exceptions=keep_exceptions,
                reject_preprocessor=reject_preprocessor,
            )
        except ValueError as exc:
            raise RuntimeError(f"{label}: cache invalid ({exc})") from exc
        rules, kept, dropped = parse_rules(
            text,
            keep_exceptions=keep_exceptions,
            reject_preprocessor=reject_preprocessor,
            source_name=f"{label} (cache)",
        )
        adopted = f"{label} (cached {cache_path.name})"
        print(
            f"OK: {label} url=cache:{cache_path.name} bytes={len(data)} "
            f"parsed={len(rules)} cache_written=no",
            file=sys.stderr,
        )
        return ParsedSource(
            name=label,
            adopted_label=adopted,
            adopted_url=str(cache_path),
            from_cache=True,
            raw_bytes=len(data),
            parsed_rules=len(rules),
            exceptions_kept=kept,
            exceptions_dropped=dropped,
            rules=rules,
        )

    raise RuntimeError(f"{label}: all URLs failed and no valid cache") from last_error


def fetch_first_validated(
    candidates: list[SourceSpec],
    *,
    keep_exceptions: bool,
    reject_preprocessor: bool = False,
    opener: Callable[..., object] | None = None,
) -> ParsedSource:
    last_error: Exception | None = None
    for spec in candidates:
        try:
            return fetch_validated_source(
                spec,
                keep_exceptions=keep_exceptions,
                reject_preprocessor=reject_preprocessor,
                opener=opener,
            )
        except Exception as exc:
            print(f"WARN: {spec.name} failed ({spec.url}): {exc}", file=sys.stderr)
            last_error = exc
    raise RuntimeError("All candidate URLs failed") from last_error


def extract_rules_from_filter_text(text: str) -> list[str]:
    rules: list[str] = []
    for raw in text.splitlines():
        line = normalize_line(raw)
        if not line or line.startswith("!"):
            continue
        rules.append(line)
    return rules


def read_existing_rules(path: Path) -> list[str] | None:
    if not path.is_file():
        return None
    return extract_rules_from_filter_text(path.read_text(encoding="utf-8"))


def build_header_lines(
    meta: FilterMeta,
    sources: list[ParsedSource],
    *,
    last_modified: str | None = None,
) -> list[str]:
    if last_modified is None:
        last_modified = datetime.now(ZoneInfo("Asia/Tokyo")).strftime(
            "%Y-%m-%d %H:%M %Z"
        )
    lines = [
        f"! Title: {meta.title}",
        f"! Description: {meta.description}",
        "! Homepage: https://github.com/baspis/my-filters",
        meta.license_line,
        f"! Last modified: {last_modified}",
        "!",
    ]
    for src in sources:
        lines.append(f"! Source: {src.adopted_label} - {src.adopted_url}")
    lines.append("!")
    return lines


def build_filter_body(
    meta: FilterMeta,
    rules: list[str],
    sources: list[ParsedSource],
    *,
    last_modified: str | None = None,
) -> str:
    header = build_header_lines(meta, sources, last_modified=last_modified)
    return "\n".join(header + rules) + "\n"


def validate_output_body(
    body: str,
    *,
    min_rules: int,
    existing_rules: list[str] | None,
) -> None:
    if looks_like_html(body) or "\x00" in body:
        raise ValueError("output looks like HTML or binary")
    rules = extract_rules_from_filter_text(body)
    if not rules:
        raise ValueError("output has no rules")
    if len(rules) < min_rules:
        raise ValueError(
            f"output has only {len(rules)} rules (minimum {min_rules})"
        )
    for key in REQUIRED_HEADER_KEYS:
        if f"! {key}" not in body:
            raise ValueError(f"output missing header: {key}")
    if existing_rules and os.environ.get("BUILD_ALLOW_RULE_DROP") != "1":
        if len(rules) < len(existing_rules) * OUTPUT_DROP_RATIO:
            raise ValueError(
                f"output rules dropped from {len(existing_rules)} to {len(rules)} "
                f"(below {OUTPUT_DROP_RATIO:.0%} threshold; set BUILD_ALLOW_RULE_DROP=1 "
                "after manual review to allow)"
            )


def preserve_last_modified(existing_path: Path, rules_changed: bool) -> str | None:
    if rules_changed or not existing_path.is_file():
        return None
    for line in existing_path.read_text(encoding="utf-8").splitlines():
        if line.startswith("! Last modified:"):
            return line.removeprefix("! Last modified:").strip()
    return None


def write_filter_atomic(
    output: Path,
    meta: FilterMeta,
    rules: list[str],
    sources: list[ParsedSource],
    log: list[str],
    *,
    min_output_rules: int,
) -> MergeStats:
    existing_rules = read_existing_rules(output)
    rules_changed = existing_rules != rules

    last_mod = preserve_last_modified(output, rules_changed)
    body = build_filter_body(meta, rules, sources, last_modified=last_mod)

    validate_output_body(
        body, min_rules=min_output_rules, existing_rules=existing_rules
    )

    if not rules_changed and output.is_file():
        for line in log:
            print(line)
        print(f"Unchanged {output} ({len(rules):,} rules)")
        return MergeStats(
            sources=sources,
            final_rules=len(rules),
            output_changed=False,
        )

    output.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(
        dir=output.parent, prefix=f".{output.name}.", suffix=".tmp"
    )
    os.close(fd)
    tmp_path = Path(tmp)
    try:
        tmp_path.write_text(body, encoding="utf-8")
        validate_output_body(
            tmp_path.read_text(encoding="utf-8"),
            min_rules=min_output_rules,
            existing_rules=existing_rules,
        )
        os.replace(tmp_path, output)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise

    for line in log:
        print(line)
    print(f"Wrote {output} ({len(body):,} bytes, {len(rules):,} rules)")
    return MergeStats(
        sources=sources,
        final_rules=len(rules),
        output_changed=True,
    )


def log_source_summary(source: ParsedSource) -> None:
    print(
        f"  source={source.adopted_label} url={source.adopted_url} "
        f"cache={source.from_cache} bytes={source.raw_bytes} "
        f"parsed={source.parsed_rules} "
        f"exceptions_kept={source.exceptions_kept} "
        f"exceptions_dropped={source.exceptions_dropped}",
        file=sys.stderr,
    )


def print_build_summary(stats: MergeStats, *, duplicates_removed: int) -> None:
    total_kept = sum(s.exceptions_kept for s in stats.sources)
    total_dropped = sum(s.exceptions_dropped for s in stats.sources)
    print(
        f"SUMMARY: final_rules={stats.final_rules} "
        f"duplicates_removed={duplicates_removed} "
        f"exceptions_kept={total_kept} exceptions_dropped={total_dropped} "
        f"output_changed={stats.output_changed}",
        file=sys.stderr,
    )
