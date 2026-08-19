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


if __name__ == "__main__":
    unittest.main()
