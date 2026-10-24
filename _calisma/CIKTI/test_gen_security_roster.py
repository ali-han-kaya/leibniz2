#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_gen_security_roster.py — roster üretiminin sözleşmesi.

  1. Commit'li iki `.list` dosyası üretici çıktısıyla BİREBİR (drift →
     kırmızı; remedy `--write`). Elle .list bakımı bu testle biter.
  2. Üretim kuralları sentetik dizinde kanıtlanır: işaretsiz dosya düşer,
     çift/bozuk işaret ve kapısız `browser` hata verir.
  3. Mutant: işaret silinince dosya roster'dan düşer (üretim işarete bağlı,
     dosya adına değil).

stdlib-only, OFFLINE.
"""
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import gen_security_roster as gen  # noqa: E402


class TestRosterMatchesGenerator(unittest.TestCase):
    def test_committed_lists_are_generator_output(self):
        written = gen.generate()
        bad = []
        for path, content in written.items():
            with open(path, encoding="utf-8") as f:
                actual = f.read()
            if actual != content:
                bad.append(os.path.basename(path))
        self.assertEqual(bad, [],
                         "roster drift: %s — remedy: gen_security_roster.py "
                         "--write" % bad)

    def test_expected_membership(self):
        """Üretim bugünkü üyeliği korur (kapsam daralması sessizce olmaz)."""
        found = gen.collect_markers()
        self.assertEqual(found["browser"], [
            "test_dashboard_budget_rh_filters.py",
            "test_dashboard_keyboard_nav.py",
            "test_design_preview_hover_csp.py",
            "test_preview_escaping.py",
            "test_preview_hover_tooltip.py",
            "test_preview_uncovered_surface.py",
        ])
        self.assertEqual(found["static"], [
            "test_csp_directives.py",
            "test_dashboard_csp_nonce.py",
            "test_local_security_surface.py",
            "test_preview_inline_handler_gate.py",
            "test_preview_video_player.py",
            "test_security_header_matrix.py",
            "test_security_headers.py",
            "test_static_isolation.py",
        ])


def _sandbox(files):
    td = tempfile.TemporaryDirectory(prefix="roster_")
    for name, content in files.items():
        with open(os.path.join(td.name, name), "w",
                  encoding="utf-8") as f:
            f.write(content)
    return td


class TestGeneratorRules(unittest.TestCase):
    def test_unmarked_file_is_dropped(self):
        """Mutant: işaret silinince dosya roster'dan DÜŞER (ada değil
        işarete bağlı)."""
        td = _sandbox({
            "test_a.py": "# SECURITY-TIER: browser\n"
                         "try:\n"
                         "    from playwright.sync_api import sync_playwright\n"
                         "except ImportError:\n"
                         "    sync_playwright = None\n",
            "test_b.py": "import unittest\n",
        })
        self.addCleanup(td.cleanup)
        found = gen.collect_markers(td.name)
        self.assertEqual(found["browser"], ["test_a.py"])
        self.assertEqual(found["static"], [])

    def test_duplicate_marker_is_an_error(self):
        td = _sandbox({
            "test_a.py": "# SECURITY-TIER: static\n# SECURITY-TIER: browser\n",
        })
        self.addCleanup(td.cleanup)
        with self.assertRaises(ValueError):
            gen.collect_markers(td.name)

    def test_malformed_marker_is_an_error(self):
        td = _sandbox({
            "test_a.py": "# SECURITY-TIER: banana\n",
        })
        self.addCleanup(td.cleanup)
        with self.assertRaises(ValueError):
            gen.collect_markers(td.name)

    def test_browser_marker_without_gate_is_an_error(self):
        td = _sandbox({
            "test_a.py": "# SECURITY-TIER: browser\nimport unittest\n",
        })
        self.addCleanup(td.cleanup)
        with self.assertRaises(ValueError):
            gen.collect_markers(td.name)

    def test_non_test_files_are_ignored(self):
        td = _sandbox({
            "helper.py": "# SECURITY-TIER: browser\n",
        })
        self.addCleanup(td.cleanup)
        found = gen.collect_markers(td.name)
        self.assertEqual(found, {"static": [], "browser": []})


if __name__ == "__main__":
    unittest.main()
