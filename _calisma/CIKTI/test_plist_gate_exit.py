#!/usr/bin/env python3
"""Plist kapısının exit 0/1/2 davranışını kapsayan birim testler.

İki kapı birlikte test edilir (her ikisi de macOS LaunchAgent plist şablonunu
denetler; her ikisi de fake HOME altında koşar — gerçek LaunchAgents/Caches'a
DOKUNMAZ, bu yüzden Linux CI'da da çalışır):

  1) update_preview.sh --plist-check (K12 kapısının sözleşmesi):
       0 = GÜNCEL  (kurulu plist şablondan üretilen içerikle birebir)
       1 = BAYAT   (kurulu plist şablondan farklı)
       2 = şablon yok (template dosyası mevcut değil)

  2) check_plist_drift.py main() (golden drift kapısı):
       0 = PASS   (render golden ile birebir + geçerli)
       1 = drift  (render golden'dan farklı)
       2 = hata   (script/golden yok, render başarısız)
"""
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
UPDATE_PREVIEW = os.path.join(HERE, "update_preview.sh")
CHECK_DRIFT = os.path.join(HERE, "check_plist_drift.py")
GOLDEN_DIR = os.path.join(HERE, "plist-golden")


def run(home, *args):
    """HOME'u fake dizine sabitleyip komutu koş; CompletedProcess döner."""
    env = dict(os.environ)
    env["HOME"] = home
    return subprocess.run(list(args), env=env, capture_output=True,
                          text=True, timeout=120)


class TestPlistCheckExitCodes(unittest.TestCase):
    """update_preview.sh --plist-check → 0=GÜNCEL / 1=BAYAT / 2=şablon yok."""

    def test_exit_0_guncel(self):
        with tempfile.TemporaryDirectory(prefix="plist-gate-") as home:
            # Üret → şablon + kurulu plist aynı içerikten gelir.
            gen = run(home, "bash", UPDATE_PREVIEW, "--plist-force", home)
            self.assertEqual(gen.returncode, 0, gen.stderr)
            chk = run(home, "bash", UPDATE_PREVIEW, "--plist-check", home)
            self.assertEqual(chk.returncode, 0, chk.stderr)
            self.assertIn("GÜNCEL", chk.stdout)

    def test_exit_1_bayat(self):
        with tempfile.TemporaryDirectory(prefix="plist-gate-") as home:
            gen = run(home, "bash", UPDATE_PREVIEW, "--plist-force", home)
            self.assertEqual(gen.returncode, 0, gen.stderr)
            # Kurulu plist'i boz (içerik şablondan farklı olsun).
            installed = os.path.join(
                home, "Library", "LaunchAgents",
                "com.freebuff.preview-leibniz2.plist")
            with open(installed, "a", encoding="utf-8") as f:
                f.write("\n<!-- drift -->\n")
            chk = run(home, "bash", UPDATE_PREVIEW, "--plist-check", home)
            self.assertEqual(chk.returncode, 1, chk.stdout + chk.stderr)
            self.assertIn("BAYAT", chk.stdout)

    def test_exit_2_sablon_yok(self):
        with tempfile.TemporaryDirectory(prefix="plist-gate-") as home:
            # Hiç üretmeden kontrol et → şablon dosyası yok.
            chk = run(home, "bash", UPDATE_PREVIEW, "--plist-check", home)
            self.assertEqual(chk.returncode, 2, chk.stdout + chk.stderr)
            self.assertIn("şablon yok", chk.stderr)


class TestCheckPlistDriftExitCodes(unittest.TestCase):
    """check_plist_drift.py main() → 0=PASS / 1=drift / 2=hata."""

    def test_exit_0_pass(self):
        with tempfile.TemporaryDirectory(prefix="plist-gate-") as home:
            r = run(home, sys.executable, CHECK_DRIFT, "--golden-dir", GOLDEN_DIR)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("TÜMÜ PASS", r.stdout)

    def test_exit_1_drift(self):
        with tempfile.TemporaryDirectory(prefix="plist-gate-") as home:
            wrong = os.path.join(home, "wrong-golden")
            os.makedirs(wrong)
            with open(os.path.join(wrong, "com.freebuff.preview-leibniz2.plist"),
                      "w", encoding="utf-8") as f:
                f.write("<dict><key>Label</key><string>WRONG</string></dict>")
            r = run(home, sys.executable, CHECK_DRIFT, "--golden-dir", wrong)
            self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
            self.assertIn("DRIFT", r.stdout)

    def test_exit_2_hata_golden_yok(self):
        with tempfile.TemporaryDirectory(prefix="plist-gate-") as home:
            r = run(home, sys.executable, CHECK_DRIFT,
                    "--golden-dir", os.path.join(home, "nope"))
            self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
            self.assertIn("golden dizini yok", r.stdout)

    def test_exit_2_hata_script_yok(self):
        with tempfile.TemporaryDirectory(prefix="plist-gate-") as home:
            r = run(home, sys.executable, CHECK_DRIFT,
                    "--script", os.path.join(home, "yok.sh"),
                    "--golden-dir", GOLDEN_DIR)
            self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
            self.assertIn("update_preview.sh yok", r.stdout)


if __name__ == "__main__":
    unittest.main()
