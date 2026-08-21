#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_refs_trend.py — refs_trend.py regresyon kapısı.

Özellikle _NoAuthRedirect'i kapılar: GitHub /zip endpoint'i imzalı Azure blob
URL'ine 302 döner; urllib Authorization'ı redirect'e taşırsa blob 401
(InvalidAuthenticationInfo) verir. Handler'ın auth başlığını düşürdüğü ve
diğer başlıkları (User-Agent) koruduğu doğrulanır. Ayrıca parse_report +
short_date saf fonksiyonları test edilir. stdlib unittest — ek bağımlılık yok.
"""
import datetime
import io
import json
import pathlib
import sys
import unittest
import urllib.request
import zipfile

CIKTI = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(CIKTI))

import refs_trend as rt  # noqa: E402


class TestNoAuthRedirect(unittest.TestCase):
    def _redirect(self, headers=None):
        req = urllib.request.Request("https://api.github.com/x")
        for k, v in (headers or {}).items():
            req.add_header(k, v)
        h = rt._NoAuthRedirect()
        return h.redirect_request(req, None, 302, "Found", {},
                                  "https://blob.core.windows.net/y")

    def test_strips_authorization(self):
        new = self._redirect({"Authorization": "Bearer abc"})
        self.assertIsNotNone(new)
        self.assertFalse("Authorization" in new.headers)

    def test_keeps_other_headers(self):
        new = self._redirect({"User-Agent": "refs-trend",
                              "Authorization": "Bearer abc"})
        self.assertEqual(new.headers.get("User-agent"), "refs-trend")
        self.assertFalse("Authorization" in new.headers)


class TestParseReport(unittest.TestCase):
    def _zip(self, payload):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("references_online.json",
                       json.dumps(payload, ensure_ascii=False))
        return buf.getvalue()

    def test_parses_references_online_json(self):
        payload = {"verified": 49, "total_online": 54, "by_source": {"a": 1}}
        rep = rt.parse_report(self._zip(payload))
        self.assertEqual(rep["verified"], 49)
        self.assertEqual(rep["total_online"], 54)

    def test_missing_json_raises(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("other.txt", "x")
        with self.assertRaises(ValueError):
            rt.parse_report(buf.getvalue())


class TestChangelog(unittest.TestCase):
    def test_changelog_has_hicks_hume(self):
        lines = rt.changelog_lines()
        self.assertTrue(lines)
        joined = "\n".join(lines)
        self.assertIn("## Changelog", joined)
        self.assertIn("Hicks 1925", joined)
        self.assertIn("Hume 1975", joined)
        self.assertIn("31/31", joined)

    def test_changelog_has_v5n_norton_popkin(self):
        """V5n: Norton/Popkin CrossRef girişi changelog'da olmalı (54→56)."""
        lines = rt.changelog_lines()
        self.assertTrue(lines)
        joined = "\n".join(lines)
        self.assertIn("V5n", joined)
        self.assertIn("Norton 1981", joined)
        self.assertIn("Popkin 1951", joined)
        self.assertIn("54→56", joined)
        # En yeni üstte: V5n (2026-08-19), Hicks/Hume (2026-08-18)'den önce.
        self.assertLess(joined.index("V5n"), joined.index("Hicks 1925"))

    def test_changelog_has_v5o(self):
        """V5o: 11 UNVERIFIED → 56/56 tam kapsam changelog'da olmalı."""
        lines = rt.changelog_lines()
        self.assertTrue(lines)
        joined = "\n".join(lines)
        self.assertIn("V5o", joined)
        self.assertIn("56/56", joined)
        self.assertIn("REFERENCE_POOL_SIZE", joined)
        # En yeni üstte: V5o (2026-08-19), V5n (2026-08-19)'den önce (aynı gün,
        # V5n'den sonraki değişiklik).
        self.assertLess(joined.index("V5o"), joined.index("V5n"))

    def test_changelog_has_v5t_handle(self):
        """V5t: Della Rocca 2010 Handle System doğrulaması changelog'da olmalı."""
        lines = rt.changelog_lines()
        self.assertTrue(lines)
        joined = "\n".join(lines)
        self.assertIn("V5t", joined)
        self.assertIn("Della Rocca 2010", joined)
        self.assertIn("Handle", joined)
        # En yeni üstte: V5t (2026-08-21), V5n (2026-08-19)'den önce.
        self.assertLess(joined.index("V5t"), joined.index("V5n"))

    def test_changelog_has_v5w_loc(self):
        """V5w: LoC katalog kanıtı changelog'da olmalı (en yeni üstte)."""
        lines = rt.changelog_lines()
        self.assertTrue(lines)
        joined = "\n".join(lines)
        self.assertIn("V5w", joined)
        self.assertIn("Library of Congress", joined)
        self.assertIn("loc", joined)
        # En yeni üstte: V5w (2026-08-21), V5v'den önce.
        self.assertLess(joined.index("V5w"), joined.index("V5v"))

    def test_changelog_has_v5p_oclc_lccn(self):
        """V5p: OL'den OCLC/LCCN çekimi + Xunzi HT kaydı changelog'da olmalı."""
        lines = rt.changelog_lines()
        self.assertTrue(lines)
        joined = "\n".join(lines)
        self.assertIn("V5p", joined)
        self.assertIn("OCLC/LCCN", joined)
        self.assertIn("HathiTrust", joined)
        self.assertIn("Xunzi", joined)
        # Sıralama: V5p (08-19, V5o'dan sonra) → V5o → V5n (aynı gün).
        self.assertLess(joined.index("V5p"), joined.index("V5o"))
        self.assertLess(joined.index("V5o"), joined.index("V5n"))

    def test_changelog_empty_when_no_entries(self):
        saved = rt.CHANGELOG
        try:
            rt.CHANGELOG = []
            self.assertEqual(rt.changelog_lines(), [])
        finally:
            rt.CHANGELOG = saved


class TestShortDate(unittest.TestCase):
    def test_iso_z(self):
        self.assertEqual(rt.short_date("2026-08-19T12:08:38Z"),
                         "2026-08-19 12:08")

    def test_empty(self):
        self.assertEqual(rt.short_date(""), "")


class TestParseHistoryRecord(unittest.TestCase):
    def _zip_jsonl(self, records):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr(
                "history.jsonl",
                "\n".join(json.dumps(r, ensure_ascii=False)
                           for r in records) + "\n",
            )
        return buf.getvalue()

    def test_parses_last_record(self):
        rec = rt.parse_history_record(self._zip_jsonl([
            {"ts": "a", "duration_s": 1.0, "budget_usd": 0.5},
            {"ts": "b", "duration_s": 2.0, "budget_usd": 1.08},
        ]))
        self.assertEqual(rec["ts"], "b")
        self.assertEqual(rec["duration_s"], 2.0)
        self.assertEqual(rec["budget_usd"], 1.08)

    def test_skips_blank_lines(self):
        rec = rt.parse_history_record(self._zip_jsonl([
            {"ts": "a", "duration_s": 3.0},
        ]))
        self.assertEqual(rec["duration_s"], 3.0)

    def test_missing_jsonl_raises(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("other.txt", "x")
        with self.assertRaises(ValueError):
            rt.parse_history_record(buf.getvalue())

    def test_empty_jsonl_raises(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("history.jsonl", "\n")
        with self.assertRaises(ValueError):
            rt.parse_history_record(buf.getvalue())


class TestStats(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(rt.stats([1, 2, 3]),
                         {"count": 3, "min": 1, "max": 3, "avg": 2})

    def test_ignores_non_numbers(self):
        s = rt.stats([None, "x", 5, 15])
        self.assertEqual(s["count"], 2)
        self.assertEqual(s["min"], 5)
        self.assertEqual(s["max"], 15)
        self.assertEqual(s["avg"], 10)

    def test_empty(self):
        self.assertEqual(rt.stats([]),
                         {"count": 0, "min": None, "max": None, "avg": None})


class TestFetchArtifactsByName(unittest.TestCase):
    def test_filters_sorts_by_date(self):
        artifacts = [
            {"name": "refs-online", "id": 1,
             "created_at": "2026-08-18T00:00:00Z"},
            {"name": "other", "id": 2,
             "created_at": "2026-08-19T00:00:00Z"},
            {"name": "refs-online", "id": 3,
             "created_at": "2026-08-17T00:00:00Z"},
        ]
        orig = rt.api_get

        def fake_api(path, token, binary=False):
            return {"artifacts": artifacts}

        rt.api_get = fake_api
        try:
            out = rt.fetch_artifacts_by_name("o/r", "", "refs-online", 100)
        finally:
            rt.api_get = orig
        self.assertEqual([a["id"] for a in out], [3, 1])


WORKFLOW = CIKTI.parent.parent / ".github" / "workflows" / "verify.yml"


class TestWorkflowCliConsistency(unittest.TestCase):
    """verify.yml'in refs-trend job'ı refs_trend.py CLI'sıyla senkron olmalı.

    refs_trend.py --out-dir refs-trend altına refs-trend.md + refs-trend.json
    üretir; gen_repro_manifest.py'nin REFS TREND bölümü refs-trend/ önekini ve
    reproducibility job'ı `name: refs-trend` artifact'ını ayrıca indirir.
    CLI/artifact drift bu zinciri sessizce koparır — fail-closed.
    """
    def _workflow(self):
        return WORKFLOW.read_text(encoding="utf-8")

    def test_job_uses_refs_trend_out_dir(self):
        text = self._workflow()
        self.assertIn("_calisma/CIKTI/refs_trend.py", text)
        self.assertIn("--out-dir refs-trend", text)
        self.assertIn("--max-artifacts 100", text)

    def test_artifact_name_matches_output_prefix(self):
        # refs_trend.py çıktısı refs-trend/ altına yazılır; reproducibility
        # job'ı aynı adla indirir → manifest REFS TREND bölümüne girer.
        text = self._workflow()
        self.assertIn("name: refs-trend", text)
        self.assertIn("path: all_artifacts/refs-trend/", text)


if __name__ == "__main__":
    unittest.main()
