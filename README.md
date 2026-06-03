# my-filters

Personal merged blocklists (DNS now; browser ad filter later).

## DNS filter (ready)

Merged, deduplicated list from:

- [AdGuard DNS filter](https://github.com/AdguardTeam/AdguardSDNSFilter)
- [HaGeZi Multi PRO](https://github.com/hagezi/dns-blocklists) (`adblock/pro.txt`)
- [280blocker](https://280blocker.net/) AdGuard domain list (current month, JST)

Unbreaker / exception lists are **not** included.

### Subscribe URL

```text
https://raw.githubusercontent.com/baspis/my-filters/main/dns/filter.txt
```

Use in **AdGuard Home** → DNS blocklists, or **AdGuard DNS** custom filters.

Rebuild locally:

```bash
python3 build/build_dns.py
```

GitHub Actions rebuilds daily (`build-dns.yml`).

## Ad filter (planned)

Browser filter will live at `ad/filter.txt` with URL:

```text
https://raw.githubusercontent.com/baspis/my-filters/main/ad/filter.txt
```

## Licenses

Source lists keep their own licenses. This repo only merges them for personal use.
