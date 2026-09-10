"""Unit tests for check_badge_endpoints.py — badge URL HTTP 200 doğrulama."""

import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))
from check_badge_endpoints import (
    extract_badges_from_readme,
    check_badge,
    _FALLBACK_BADGES,
)


class TestExtractBadges(unittest.TestCase):
    """README'den badge çıkarma."""

    def test_fallback_when_no_readme(self):
        badges = extract_badges_from_readme("/tmp/_nonexistent_readme_12345.md")
        self.assertEqual(len(badges), len(_FALLBACK_BADGES))

    def test_extracts_shields_io(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md",
                                          delete=False) as f:
            f.write("# Title\n\n"
                    "![pre-commit](https://img.shields.io/badge/test-green)\n"
                    "![CI](https://github.com/user/repo/actions/workflows/ci.yml/badge.svg)\n")
            f.flush()
            path = f.name
        try:
            badges = extract_badges_from_readme(path)
            self.assertEqual(len(badges), 2)
            labels = [b["label"] for b in badges]
            self.assertIn("pre-commit", labels)
            self.assertIn("CI", labels)
            sources = [b["source"] for b in badges]
            self.assertIn("shields.io", sources)
            self.assertIn("github-actions", sources)
        finally:
            os.unlink(path)

    def test_empty_readme_returns_fallback(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md",
                                          delete=False) as f:
            f.write("# Title\n\nNo badges here.\n")
            f.flush()
            path = f.name
        try:
            badges = extract_badges_from_readme(path)
            self.assertEqual(len(badges), len(_FALLBACK_BADGES))
        finally:
            os.unlink(path)


class TestCheckBadge(unittest.TestCase):
    """Badge HTTP kontrolü (mock)."""

    def test_ok_response(self):
        mock_resp = mock.MagicMock()
        mock_resp.getcode.return_value = 200
        mock_resp.__enter__ = mock.MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = mock.MagicMock(return_value=False)
        with mock.patch("check_badge_endpoints.urllib.request.urlopen",
                        return_value=mock_resp):
            r = check_badge("https://example.com/badge.svg")
            self.assertTrue(r["ok"])
            self.assertEqual(r["status"], 200)
            self.assertIsNone(r["error"])

    def test_404_response(self):
        mock_resp = mock.MagicMock()
        mock_resp.getcode.return_value = 404
        mock_resp.__enter__ = mock.MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = mock.MagicMock(return_value=False)
        with mock.patch("check_badge_endpoints.urllib.request.urlopen",
                        return_value=mock_resp):
            r = check_badge("https://example.com/badge.svg")
            self.assertFalse(r["ok"])
            self.assertEqual(r["status"], 404)

    def test_connection_error(self):
        with mock.patch("check_badge_endpoints.urllib.request.urlopen",
                        side_effect=OSError("connection refused")):
            r = check_badge("https://example.com/badge.svg")
            self.assertFalse(r["ok"])
            self.assertEqual(r["status"], 0)
            self.assertIn("connection refused", r["error"])

    def test_timeout(self):
        import urllib.error
        with mock.patch("check_badge_endpoints.urllib.request.urlopen",
                        side_effect=urllib.error.URLError("timed out")):
            r = check_badge("https://example.com/badge.svg", timeout=1)
            self.assertFalse(r["ok"])

    def test_302_redirect_ok(self):
        """302 redirect (shields.io Behaviour Rules) başarılı sayılmalı."""
        mock_resp = mock.MagicMock()
        mock_resp.getcode.return_value = 302
        mock_resp.__enter__ = mock.MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = mock.MagicMock(return_value=False)
        with mock.patch("check_badge_endpoints.urllib.request.urlopen",
                        return_value=mock_resp):
            r = check_badge("https://img.shields.io/badge/test-green")
            self.assertTrue(r["ok"])
            self.assertEqual(r["status"], 302)


class TestFallbackBadges(unittest.TestCase):
    """Fallback badge listesi."""

    def test_three_badges(self):
        self.assertEqual(len(_FALLBACK_BADGES), 3)

    def test_all_have_required_keys(self):
        for b in _FALLBACK_BADGES:
            self.assertIn("label", b)
            self.assertIn("url", b)
            self.assertIn("source", b)
            self.assertTrue(b["url"].startswith("http"))

    def test_sources_distributed(self):
        sources = {b["source"] for b in _FALLBACK_BADGES}
        self.assertIn("github-actions", sources)
        self.assertIn("shields.io", sources)


if __name__ == "__main__":
    unittest.main()
