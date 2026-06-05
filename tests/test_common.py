"""Offline unit tests for filter build helpers."""

from __future__ import annotations

import io
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build"))

from common import (  # noqa: E402
    FilterMeta,
    Merger,
    ParsedSource,
    apply_dns_output_exclusions,
    build_filter_body,
    dedupe_exact,
    extract_rules_from_filter_text,
    fetch_bytes,
    fetch_with_cache,
    month_urls_utc,
    month_ym_utc,
    parse_rules,
    read_existing_rules,
    validate_fetched_text,
    validate_output_body,
    write_filter_atomic,
)


class TestParseRules(unittest.TestCase):
    SAMPLE = """\
! comment
||Example.COM^
||example.com^
||example.com^$third-party
@@||allow.example^
[Adblock Plus 2.0]

||blocked.com^
"""

    def test_skips_comments_and_headers(self) -> None:
        rules, kept, dropped = parse_rules(self.SAMPLE, keep_exceptions=True)
        self.assertNotIn("! comment", rules)
        self.assertEqual(kept, 1)
        self.assertEqual(dropped, 0)

    def test_skips_hash_comments_and_bom_hash_comments(self) -> None:
        rules, _, _ = parse_rules(
            "\ufeff# title\n# comment\n||blocked.com^\n",
            keep_exceptions=False,
        )
        self.assertEqual(rules, ["||blocked.com^"])

    def test_keeps_case_and_modifier_variants(self) -> None:
        rules, _, _ = parse_rules(self.SAMPLE, keep_exceptions=True)
        self.assertIn("||Example.COM^", rules)
        self.assertIn("||example.com^", rules)
        self.assertIn("||example.com^$third-party", rules)

    def test_dns_drops_exceptions(self) -> None:
        rules, kept, dropped = parse_rules(self.SAMPLE, keep_exceptions=False)
        self.assertEqual(kept, 0)
        self.assertEqual(dropped, 1)
        self.assertTrue(all(not r.startswith("@@") for r in rules))

    def test_ad_keeps_exceptions(self) -> None:
        rules, kept, _ = parse_rules(self.SAMPLE, keep_exceptions=True)
        self.assertEqual(kept, 1)
        self.assertIn("@@||allow.example^", rules)

    def test_rejects_preprocessor_when_requested(self) -> None:
        with self.assertRaises(ValueError):
            parse_rules(
                "!#include module.txt\n||blocked.com^\n",
                keep_exceptions=True,
                reject_preprocessor=True,
                source_name="test",
            )


class TestDnsOutputExclusions(unittest.TestCase):
    def test_drops_rsc_cdn77_parent(self) -> None:
        rules = ["||rsc.cdn77.org^", "||1991482557.rsc.cdn77.org^", "||evil.com^"]
        out, n = apply_dns_output_exclusions(rules)
        self.assertEqual(n, 1)
        self.assertNotIn("||rsc.cdn77.org^", out)
        self.assertIn("||1991482557.rsc.cdn77.org^", out)

    def test_preserves_browser_geolocation_hosts(self) -> None:
        rules = [
            "||location.services.mozilla.com^",
            "||geo.mozilla.org^",
            "||www.googleapis.com^",
            "||maps.googleapis.com^",
            "||gsp-ssl.ls.apple.com^",
            "||telemetry.googleapis.com^",
            "||geolocation.forbes.com^",
        ]
        out, n = apply_dns_output_exclusions(rules)
        self.assertEqual(n, 5)
        self.assertNotIn("||location.services.mozilla.com^", out)
        self.assertNotIn("||geo.mozilla.org^", out)
        self.assertNotIn("||www.googleapis.com^", out)
        self.assertNotIn("||maps.googleapis.com^", out)
        self.assertNotIn("||gsp-ssl.ls.apple.com^", out)
        self.assertIn("||telemetry.googleapis.com^", out)
        self.assertIn("||geolocation.forbes.com^", out)


class TestDedupeExact(unittest.TestCase):
    def test_exact_only(self) -> None:
        rules = [
            "||a.com^",
            "||a.com^",
            "||a.com^$third-party",
            "||A.com^",
        ]
        out, removed = dedupe_exact(rules)
        self.assertEqual(removed, 1)
        self.assertEqual(
            out,
            ["||a.com^", "||a.com^$third-party", "||A.com^"],
        )

    def test_order_preserved(self) -> None:
        rules = ["b", "a", "b", "c"]
        out, _ = dedupe_exact(rules)
        self.assertEqual(out, ["b", "a", "c"])


class TestMerger(unittest.TestCase):
    def test_exact_dedupe_in_merger(self) -> None:
        merger = Merger()
        src = ParsedSource(
            name="t",
            adopted_label="t",
            adopted_url="http://x",
            from_cache=False,
            raw_bytes=1,
            parsed_rules=2,
            rules=["||x.com^", "||x.com^$image"],
        )
        merger.add_source(src)
        merger.add_source(
            ParsedSource(
                name="t2",
                adopted_label="t2",
                adopted_url="http://y",
                from_cache=False,
                raw_bytes=1,
                parsed_rules=1,
                rules=["||x.com^"],
            )
        )
        self.assertEqual(merger.rules, ["||x.com^", "||x.com^$image"])
        self.assertEqual(merger.duplicates_removed, 1)


class TestMonthUrls(unittest.TestCase):
    @mock.patch("common.month_ym_utc", return_value="202606")
    def test_current_and_previous_month(self, _mock: mock.MagicMock) -> None:
        urls = month_urls_utc("https://280blocker.net/files/280blocker_domain_ag")
        self.assertEqual(
            urls,
            [
                "https://280blocker.net/files/280blocker_domain_ag_202606.txt",
                "https://280blocker.net/files/280blocker_domain_ag_202605.txt",
            ],
        )

    @mock.patch("common.month_ym_utc", return_value="202601")
    def test_january_rolls_to_december(self, _mock: mock.MagicMock) -> None:
        urls = month_urls_utc("https://280blocker.net/files/280blocker_adblock")
        self.assertIn("202512", urls[1])


class TestResponseValidation(unittest.TestCase):
    def test_rejects_empty(self) -> None:
        with self.assertRaises(ValueError):
            validate_fetched_text(
                "",
                source_name="x",
                min_parsed_rules=1,
                keep_exceptions=False,
            )

    def test_rejects_html(self) -> None:
        with self.assertRaises(ValueError):
            validate_fetched_text(
                "<!DOCTYPE html><html><body>error</body></html>",
                source_name="x",
                min_parsed_rules=1,
                keep_exceptions=False,
            )

    def test_rejects_invalid_utf8_via_bytes(self) -> None:
        from common import decode_utf8_strict

        with self.assertRaises(ValueError):
            decode_utf8_strict(b"\xff\xfe")

    def test_rejects_nul_bytes(self) -> None:
        from common import decode_utf8_strict

        with self.assertRaises(ValueError):
            decode_utf8_strict(b"||a.com^\x00")

    def test_rejects_too_few_rules(self) -> None:
        with self.assertRaises(ValueError):
            validate_fetched_text(
                "||only.com^\n",
                source_name="x",
                min_parsed_rules=5,
                keep_exceptions=False,
            )

    def test_rejects_preprocessor_directive(self) -> None:
        with self.assertRaises(ValueError):
            validate_fetched_text(
                "!#if adguard\n||only.com^\n",
                source_name="x",
                min_parsed_rules=1,
                keep_exceptions=True,
                reject_preprocessor=True,
            )


class TestFetchRetry(unittest.TestCase):
    def test_no_retry_on_404(self) -> None:
        import urllib.error

        calls = {"n": 0}

        def fake_open(_req, timeout=0):
            calls["n"] += 1
            raise urllib.error.HTTPError(
                "http://x", 404, "nope", None, io.BytesIO(b"")
            )

        with mock.patch("common.urllib.request.urlopen", fake_open):
            with self.assertRaises(urllib.error.HTTPError):
                fetch_bytes("http://x")
        self.assertEqual(calls["n"], 1)

    def test_retries_on_503(self) -> None:
        import urllib.error

        calls = {"n": 0}

        class Resp:
            def read(self) -> bytes:
                return b"||a.com^\n||b.com^\n"

            def __enter__(self):
                return self

            def __exit__(self, *args: object) -> None:
                return None

        def fake_open(_req, timeout=0):
            calls["n"] += 1
            if calls["n"] < 2:
                raise urllib.error.HTTPError(
                    "http://x", 503, "busy", None, io.BytesIO(b"")
                )
            return Resp()

        with mock.patch("common.urllib.request.urlopen", fake_open):
            with mock.patch("common.time.sleep"):
                data = fetch_bytes("http://x")
        self.assertIn(b"||a.com^", data)
        self.assertEqual(calls["n"], 2)


class TestFetchWithCache(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(self._testMethodName)  # placeholder
        import tempfile

        self.dir = Path(tempfile.mkdtemp())
        self.cache = self.dir / "cache.txt"

    def tearDown(self) -> None:
        import shutil

        shutil.rmtree(self.dir, ignore_errors=True)

    def _good_body(self) -> bytes:
        lines = [f"||host{i}.com^" for i in range(10)]
        return ("\n".join(lines) + "\n").encode()

    def test_bad_response_does_not_overwrite_cache(self) -> None:
        self.cache.write_bytes(self._good_body())
        import urllib.error

        def fail_fetch(_url: str, **kwargs: object) -> bytes:
            raise urllib.error.HTTPError(
                "http://x", 404, "nope", None, io.BytesIO(b"")
            )

        with mock.patch("common.fetch_bytes", side_effect=fail_fetch):
            parsed = fetch_with_cache(
                "280blocker",
                ["http://current", "http://prev"],
                self.cache,
                min_parsed_rules=5,
                keep_exceptions=False,
            )
        self.assertTrue(parsed.from_cache)
        self.assertEqual(self.cache.read_bytes(), self._good_body())

    def test_empty_response_not_cached(self) -> None:
        with mock.patch("common.fetch_bytes", return_value=b""):
            with self.assertRaises(RuntimeError):
                fetch_with_cache(
                    "280blocker",
                    ["http://only"],
                    self.cache,
                    min_parsed_rules=1,
                    keep_exceptions=False,
                )
        self.assertFalse(self.cache.exists())

    def test_month_fallback(self) -> None:
        def fetch(url: str, **kwargs: object) -> bytes:
            if url == "http://current":
                return b""
            return self._good_body()

        with mock.patch("common.fetch_bytes", side_effect=fetch):
            parsed = fetch_with_cache(
                "280blocker",
                ["http://current", "http://prev"],
                self.cache,
                min_parsed_rules=5,
                keep_exceptions=False,
            )
        self.assertEqual(parsed.adopted_url, "http://prev")
        self.assertEqual(self.cache.read_bytes(), self._good_body())


class TestWriteFilter(unittest.TestCase):
    def setUp(self) -> None:
        import tempfile

        self.dir = Path(tempfile.mkdtemp())
        self.out = self.dir / "filter.txt"

    def tearDown(self) -> None:
        import shutil

        shutil.rmtree(self.dir, ignore_errors=True)

    def _meta(self) -> FilterMeta:
        return FilterMeta("T", "D")

    def _source(self) -> ParsedSource:
        return ParsedSource(
            name="s",
            adopted_label="s",
            adopted_url="http://example",
            from_cache=False,
            raw_bytes=10,
            parsed_rules=2,
            rules=["||a.com^", "||b.com^"],
        )

    def test_idempotent_second_write(self) -> None:
        rules = ["||a.com^", "||b.com^", "||c.com^"]
        meta = self._meta()
        sources = [self._source()]
        write_filter_atomic(
            self.out, meta, rules, sources, [], min_output_rules=3
        )
        first = self.out.read_text(encoding="utf-8")
        write_filter_atomic(
            self.out, meta, rules, sources, [], min_output_rules=3
        )
        second = self.out.read_text(encoding="utf-8")
        self.assertEqual(first, second)

    def test_validation_failure_leaves_existing(self) -> None:
        rules = ["||a.com^", "||b.com^", "||c.com^"]
        write_filter_atomic(
            self.out,
            self._meta(),
            rules,
            [self._source()],
            [],
            min_output_rules=3,
        )
        before = self.out.read_text(encoding="utf-8")
        with self.assertRaises(ValueError):
            write_filter_atomic(
                self.out,
                self._meta(),
                ["||only.com^"],
                [self._source()],
                [],
                min_output_rules=3,
            )
        self.assertEqual(self.out.read_text(encoding="utf-8"), before)

    def test_large_drop_rejected(self) -> None:
        rules = [f"||host{i}.com^" for i in range(100)]
        write_filter_atomic(
            self.out,
            self._meta(),
            rules,
            [self._source()],
            [],
            min_output_rules=10,
        )
        with self.assertRaises(ValueError):
            write_filter_atomic(
                self.out,
                self._meta(),
                rules[:5],
                [self._source()],
                [],
                min_output_rules=10,
            )


class TestExtractRules(unittest.TestCase):
    def test_header_excluded(self) -> None:
        body = build_filter_body(
            FilterMeta("T", "D"),
            ["||x.com^"],
            [
                ParsedSource(
                    "n",
                    "n",
                    "u",
                    False,
                    1,
                    1,
                    rules=[],
                )
            ],
        )
        self.assertEqual(extract_rules_from_filter_text(body), ["||x.com^"])


if __name__ == "__main__":
    unittest.main()
