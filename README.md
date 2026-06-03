# my-filters

Personal merged blocklists (DNS + browser ad), each as a single subscribe URL.

## DNS filter

Sources:

- AdGuard DNS filter — `filters.adtidy.org/.../15.txt`
- [HaGeZi Multi PRO](https://github.com/hagezi/dns-blocklists) — `adblock/pro.txt`
- [280blocker](https://280blocker.net/) — `280blocker_domain_ag_YYYYMM.txt` (UTC month)

```text
https://raw.githubusercontent.com/baspis/my-filters/main/dns/filter.txt
```

## Ad filter (custom supplement)

**One URL** for lists that are not built into AdGuard as switches:

- [280blocker](https://280blocker.net/) — `280blocker_adblock_YYYYMM.txt` (UTC month)
- [AdGuard Japanese filter Plus](https://github.com/Yuki2718/adblock2) — `jpf-plus.txt`

```text
https://raw.githubusercontent.com/baspis/my-filters/main/ad/filter.txt
```

Also enable built-in AdGuard filters **#2, #3, #7, #11, #14, #17** (Base, Tracking, Japanese, Mobile ads, Annoyances, URL Tracking). Those are **not** in `filter.txt` — they load via app switches and use separate Safari content-blocker slots on iOS.

## Rebuild locally

```bash
python3 build/build_dns.py
python3 build/build_ad.py
```

GitHub Actions rebuilds daily (`build-filters.yml`).

## Licenses

Source lists keep their own licenses. Personal use only.
