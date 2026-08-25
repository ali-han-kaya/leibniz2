#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_run_summary_changelog.py — run_summary_changelog.py birim testleri.

Kapsam:
  - status(): SENKRON (rc 0) / DRIFT (rc 1) / HATA (rc 2, bozuk rc) / MISSING
  - render(): GITHUB_STEP_SUMMARY dosyasına bölüm yazar; env yoksa stdout
  - Bölüm başlığı ve durum satırları (SENKRON/DRIFT/HATA/MISSING)
  - DRIFT'te ham bulgular code block içinde korunur
"""
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent))
import run_summary_changelog as rsc


class TestStatus(unittest.TestCase):
    """status(): txt+rc dosyalarından tek satır durum."""

    def _write(self, td, txt, rc):
        td = Path(td)
        (td / "changelog_drift.txt").write_text(txt)
        (td / "changelog_drift.rc").write_text(rc)
        return str(td / "changelog_drift.txt"), str(td / "changelog_drift.rc")

    def test_sync_rc0(self):
        with tempfile.TemporaryDirectory() as td:
            t, r = self._write(td, "TÜMÜ PASS", "0")
            self.assertEqual(rsc.status(t, r), "SENKRON")

    def test_drift_rc1(self):
        with tempfile.TemporaryDirectory() as td:
            t, r = self._write(td, "DRIFT tespit edildi", "1")
            self.assertEqual(rsc.status(t, r), "DRIFT")

    def test_error_rc2(self):
        with tempfile.TemporaryDirectory() as td:
            t, r = self._write(td, "HATA: git log boş", "2")
            self.assertEqual(rsc.status(t, r), "HATA")

    def test_empty_rc_is_zero(self):
        with tempfile.TemporaryDirectory() as td:
            t, r = self._write(td, "TÜMÜ PASS", "")
            self.assertEqual(rsc.status(t, r), "SENKRON")

    def test_garbage_rc_is_hata(self):
        with tempfile.TemporaryDirectory() as td:
            t, r = self._write(td, "x", "abc")
            self.assertEqual(rsc.status(t, r), "HATA")

    def test_missing_files(self):
        with tempfile.TemporaryDirectory() as td:
            t = str(Path(td, "yok.txt"))
            r = str(Path(td, "yok.rc"))
            self.assertEqual(rsc.status(t, r), "MISSING")


class TestRender(unittest.TestCase):
    """render(): bölüm içeriği."""

    def _write(self, td, txt, rc):
        td = Path(td)
        (td / "changelog_drift.txt").write_text(txt)
        (td / "changelog_drift.rc").write_text(rc)
        return str(td / "changelog_drift.txt"), str(td / "changelog_drift.rc")

    def test_missing_section(self):
        buf = io.StringIO()
        rsc.render(buf, "yok.txt", "yok.rc")
        self.assertIn("## 🔄 Changelog drift", buf.getvalue())
        self.assertIn("çalışmadı", buf.getvalue())

    def test_sync_section(self):
        with tempfile.TemporaryDirectory() as td:
            t, r = self._write(td, "TÜMÜ PASS: changelog tabloları git log ile senkron", "0")
            buf = io.StringIO()
            rsc.render(buf, t, r)
            out = buf.getvalue()
        self.assertIn("## 🔄 Changelog drift", out)
        self.assertIn("✅ SENKRON", out)

    def test_drift_section_keeps_findings(self):
        findings = "README.md: 2 commit tabloda yok:\n  + aaa1111\nDRIFT tespit edildi.\n"
        with tempfile.TemporaryDirectory() as td:
            t, r = self._write(td, findings, "1")
            buf = io.StringIO()
            rsc.render(buf, t, r)
            out = buf.getvalue()
        self.assertIn("⚠️ DRIFT", out)
        self.assertIn("aaa1111", out)
        self.assertIn("```text", out)

    def test_drift_section_adds_trailing_newline(self):
        with tempfile.TemporaryDirectory() as td:
            t, r = self._write(td, "satır yeni satırsız", "1")
            buf = io.StringIO()
            rsc.render(buf, t, r)
            out = buf.getvalue()
        self.assertIn("satır yeni satırsız\n```", out)

    def test_hata_section(self):
        with tempfile.TemporaryDirectory() as td:
            t, r = self._write(td, "HATA: git log boş", "2")
            buf = io.StringIO()
            rsc.render(buf, t, r)
            out = buf.getvalue()
        self.assertIn("⚠️ HATA", out)
        self.assertIn("git log boş", out)

    def test_writes_to_github_step_summary_file(self):
        """GITHUB_STEP_SUMMARY setliyse main() bölümü o dosyaya ekler."""
        with tempfile.TemporaryDirectory() as td:
            summary_path = Path(td, "summary.md")
            t, r = self._write(td, "TÜMÜ PASS", "0")
            with patch.dict(os.environ,
                            {"GITHUB_STEP_SUMMARY": str(summary_path)}):
                rc = rsc.main([t, r])
            self.assertEqual(rc, 0)
            content = summary_path.read_text()
        self.assertIn("Changelog drift", content)
        self.assertIn("✅ SENKRON", content)

    def test_fallback_stdout_when_env_unset(self):
        """GITHUB_STEP_SUMMARY yoksa çıktı stdout'a yazılır (main dönüşü 0)."""
        with tempfile.TemporaryDirectory() as td:
            t, r = self._write(td, "TÜMÜ PASS", "0")
            with patch.dict(os.environ, {}, clear=True), \
                 patch.object(sys, "stdout", new=io.StringIO()) as out:
                rc = rsc.main([t, r])
        self.assertEqual(rc, 0)
        self.assertIn("Changelog drift", out.getvalue())


if __name__ == "__main__":
    unittest.main(verbosity=2)
