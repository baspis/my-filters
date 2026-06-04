# my-filters

Personal merged blocklists for AdGuard: one DNS list and one browser ad supplement. Rules are rebuilt from upstream sources; semantics are preserved with exact-match deduplication only.

**Personal use only.** Source lists keep their own licenses and redistribution terms; see [Licenses and attribution](#licenses-and-attribution).

## DNS filter vs ad filter

| | DNS (`dns/filter.txt`) | Ad (`ad/filter.txt`) |
|---|---|---|
| Use in | AdGuard DNS / DNS filtering | AdGuard for iOS, Safari, browser extension |
| Role | Merged DNS block rules | **Supplement** only (does not replace built-in lists) |
| `@@` exceptions | **Excluded** (block-only collection) | **Kept** (full list semantics where upstream provides them) |
| Dedup | Exact line match after trim | Same |

Subscribe URLs (unchanged):

```text
https://raw.githubusercontent.com/baspis/my-filters/main/dns/filter.txt
https://raw.githubusercontent.com/baspis/my-filters/main/ad/filter.txt
```

### AdGuard built-in filters (enable separately)

`ad/filter.txt` does **not** include AdGuard built-in filters. Also enable **#2, #3, #7, #11, #14, #17** (Base, Tracking, Japanese, Mobile ads, Annoyances, URL Tracking) in the app.

## Upstream sources (full URLs)

### DNS (`build/build_dns.py`)

| Source | URL |
|---|---|
| AdGuard DNS filter (#15) | `https://filters.adtidy.org/extension/chromium/filters/15.txt` (fallback: [AdGuardSDNSFilter](https://adguardteam.github.io/AdGuardSDNSFilter/Filters/filter.txt), [FiltersRegistry](https://raw.githubusercontent.com/AdguardTeam/FiltersRegistry/master/filters/filter_15_DnsFilter/filter.txt)) |
| HaGeZi Multi PRO | `https://raw.githubusercontent.com/hagezi/dns-blocklists/main/adblock/pro.txt` |
| 280blocker domain_ag | `https://280blocker.net/files/280blocker_domain_ag_YYYYMM.txt` (UTC month) |

### Ad (`build/build_ad.py`)

| Source | URL |
|---|---|
| 280blocker adblock | `https://280blocker.net/files/280blocker_adblock_YYYYMM.txt` (UTC month) |
| AdGuard Japanese filter Plus | `https://yuki2718.github.io/adblock2/japanese/jpf-plus.txt` (fallback: `https://raw.githubusercontent.com/Yuki2718/adblock2/main/japanese/jpf-plus.txt`) |

Upstream lists are **not** pinned to git SHAs; this repo tracks current lists on a schedule. Reproducibility uses git history, build logs, cache files under `sources/`, and `! Source:` lines in each output file.

## 280blocker fetch order (UTC)

1. Current month file (`…_YYYYMM.txt`)
2. Previous month file
3. Validated cache under `sources/280blocker_*.cache.txt`

Invalid or empty responses are not written to cache. If all URLs fail and cache is missing or invalid, the build fails.

## Build behavior

- **Dedup:** Only identical lines (after stripping leading/trailing whitespace) are removed. Different modifiers, paths, or letter case are kept. First occurrence wins.
- **DNS `@@` rules:** Dropped by design; count is logged. They must not silently disappear without documentation—see table above.
- **Ad `@@` rules:** Kept. They may disable blocking from another merged source; use only if you accept that trade-off.
- **Fetch:** Timeouts, limited retries with backoff for timeouts, connection errors, HTTP 429, and 5xx. No retry on 403/404 for the same URL.
- **Validation:** Non-empty UTF-8 text, not HTML, no NUL/binary; per-source minimum rule counts; merged output minimums; optional drop guard vs previous publish (see `build/common.py`).
- **Failure:** Required sources must succeed; incomplete filters are not published; existing `dns/filter.txt` / `ad/filter.txt` are left unchanged on failure (atomic write to temp, then replace).
- **Idempotent output:** If rule bodies are unchanged, the output file is not rewritten and `! Last modified:` is preserved (no header-only commits).
- **DNS exclusions:** `||rsc.cdn77.org^` is omitted from `dns/filter.txt` because it blocks `filters.adtidy.org` (CNAME) and breaks AdGuard app filter updates when this list is your recursive DNS (e.g. AdGuard Home on a VPS). Specific `*.rsc.cdn77.org` entries are kept.

### Requirements

- Python **3.10+** (CI uses 3.12)
- **No** third-party Python packages (`requirements.txt` not used)

### Local build

```bash
cd /path/to/my-filters
python3 -m unittest discover -s tests -v
python3 build/build_dns.py
python3 build/build_ad.py
```

Run the same build again; `git diff` should be empty if upstream data unchanged.

### Override large rule-count drops

If upstream legitimately shrinks a lot, after manual review:

```bash
BUILD_ALLOW_RULE_DROP=1 python3 build/build_dns.py
```

## GitHub Actions

- `build-filters.yml` — daily schedule + `workflow_dispatch`; runs tests, then builds; commits only when outputs change.
- `test.yml` — tests on push/PR (read-only).

## Licenses and attribution

| Source | License / terms (check upstream for updates) |
|---|---|
| [AdGuard DNS filter](https://github.com/AdguardTeam/AdguardFilters) | GPL-3.0 (filter `#15` in [AdguardFilters](https://github.com/AdguardTeam/AdguardFilters)) |
| [HaGeZi DNS blocklists](https://github.com/hagezi/dns-blocklists) | See repository `LICENSE` / readme |
| [280blocker](https://280blocker.net/) | See site terms |
| [AdGuard Japanese filter Plus](https://github.com/Yuki2718/adblock2) | See repository license |

Generated files include `! Source:` lines with the URL or cache label actually used. This repo’s README does not replace upstream license notices.
