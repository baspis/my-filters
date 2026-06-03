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

AdGuard Home → DNS blocklists, or AdGuard DNS custom filters (including AdGuard for iOS → DNS protection).

## Ad filter — PC / desktop browser

Full merge for uBlock Origin, AdGuard extension on PC, etc.

Sources: AdGuard `#2` `#3` `#17` `#14` `#7` `#11` + 280blocker adblock (UTC month).

```text
https://raw.githubusercontent.com/baspis/my-filters/main/ad/filter.txt
```

## Ad filter — iPhone / Safari (lightweight)

**Do not** use `ad/filter.txt` on iOS (exceeds Safari rule limits).

Instead:

1. Enable built-in AdGuard filters **#2, #3, #7, #11, #14, #17**
2. Add **one** custom filter:

```text
https://raw.githubusercontent.com/baspis/my-filters/main/ad/filter-ios.txt
```

Sources (deduplicated):

- [280blocker](https://280blocker.net/) — `280blocker_adblock_YYYYMM.txt`
- [AdGuard Japanese filter Plus](https://github.com/Yuki2718/adblock2) — `jpf-plus.txt` (Yuki2718)

## Rebuild locally

```bash
python3 build/build_dns.py
python3 build/build_ad.py
python3 build/build_ad_ios.py
```

GitHub Actions rebuilds all three daily (`build-filters.yml`).

## Licenses

Source lists keep their own licenses. Personal use only.
