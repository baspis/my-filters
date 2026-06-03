# my-filters

Personal merged blocklists (DNS + browser ad), each as a single subscribe URL.

## DNS filter

Sources:

- AdGuard DNS filter — `filters.adtidy.org/.../15.txt`
- [HaGeZi Multi PRO](https://github.com/hagezi/dns-blocklists) — `adblock/pro.txt`
- [280blocker](https://280blocker.net/) — `280blocker_domain_ag_YYYYMM.txt` (UTC month)

**Subscribe URL**

```text
https://raw.githubusercontent.com/baspis/my-filters/main/dns/filter.txt
```

AdGuard Home → DNS blocklists, or AdGuard DNS custom filters.

## Ad filter (browser)

Sources:

- AdGuard — filters `#2` `#3` `#17` `#14` `#7` `#11` (adtidy chromium)
- 280blocker — `280blocker_adblock_YYYYMM.txt` (UTC month)

**Subscribe URL**

```text
https://raw.githubusercontent.com/baspis/my-filters/main/ad/filter.txt
```

uBlock Origin / AdGuard extension → custom filter lists.

## Rebuild locally

```bash
python3 build/build_dns.py
python3 build/build_ad.py
```

GitHub Actions rebuilds both daily (`build-filters.yml`).

## Licenses

Source lists keep their own licenses. Personal use only.
