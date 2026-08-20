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
import json
import os
import plistlib
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
UPDATE_PREVIEW = os.path.join(HERE, "update_preview.sh")
CHECK_DRIFT = os.path.join(HERE, "check_plist_drift.py")
VERIFY_DELIVERY = os.path.join(HERE, "verify_delivery.py")
GOLDEN_DIR = os.path.join(HERE, "plist-golden")

sys.path.insert(0, HERE)
from verify_delivery import parse_plist_check_output  # noqa: E402


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


class TestPlistOutSidecar(unittest.TestCase):
    """--plist-out: --plist-check ham çıktısı + K12 raporu tek sidecar JSON'da."""

    def test_sidecar_written_with_output_and_report(self):
        with tempfile.TemporaryDirectory(prefix="plist-gate-") as home:
            # Şablon + kurulu plist üret → GÜNCEL (exit 0) olsun.
            gen = run(home, "bash", UPDATE_PREVIEW, "--plist-force", home)
            self.assertEqual(gen.returncode, 0, gen.stderr)

            out = os.path.join(home, "plist_report.json")
            r = run(home, sys.executable, VERIFY_DELIVERY,
                    "--check-plist", "--plist-out", out)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

            self.assertTrue(os.path.isfile(out), "sidecar JSON yazılmadı")
            with open(out, encoding="utf-8") as f:
                d = json.load(f)
            # K12 raporu (layer + ok + exit + detail) VE ham --plist-check
            # çıktısı (output) aynı sidecar'da birlikte olmalı.
            self.assertEqual(d["layer"], "K12")
            self.assertTrue(d["ok"])
            self.assertEqual(d["exit"], 0)
            self.assertIn("GÜNCEL", d["detail"])
            self.assertIn("GÜNCEL", d["output"])
            # Çok-profilli yönetim: birincil leibniz2 + preview-server ikisi
            # de rapora girmeli (K11 --plist iki profili tek komutta denetler).
            labels = [p["label"] for p in d["profiles"]]
            self.assertEqual(labels,
                             ["com.freebuff.preview-leibniz2",
                              "com.freebuff.preview-server"])
            for p in d["profiles"]:
                self.assertEqual(p["status"], "GÜNCEL")
                self.assertTrue(p["path"].endswith(p["label"] + ".plist"))

    def test_sidecar_fail_detail_on_no_template(self):
        with tempfile.TemporaryDirectory(prefix="plist-gate-") as home:
            # Hiç üretmeden → --plist-check exit 2 (şablon yok); sidecar yine
            # yazılmalı ve ok=False + exit=2 + detail şablon yok olmalı.
            out = os.path.join(home, "plist_report.json")
            r = run(home, sys.executable, VERIFY_DELIVERY,
                    "--check-plist", "--plist-out", out)
            # --check-plist P1 üretir → genel exit 1 (P0=0 ama P1>0).
            self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
            with open(out, encoding="utf-8") as f:
                d = json.load(f)
            self.assertEqual(d["layer"], "K12")
            self.assertFalse(d["ok"])
            self.assertEqual(d["exit"], 2)
            self.assertIn("şablon yok", d["detail"])
            self.assertIn("şablon yok", d["output"])


class TestOutOfScopeExtraFile(unittest.TestCase):
    """Kapsam-dışı fazla dosya senaryosu (ekstra mock) — GERÇEK uçtan uca.

    K12'nin kapsamı yalnızca PLIST_PROFILES'teki yönetilen profillerdir:
    LaunchAgents'e düşen, şablonda/profillerde OLMAYAN bir plist (ör. başka
    bir uygulamanın agent'ı) kapsam-dışıdır ve --plist-check'i bozmamalı:
    yanlış BAYAT/exit 1 üretmemeli, K12 raporuna da girmemeli. Her iki kapı
    da GERÇEK script yoluyla koşulur (update_preview.sh --plist-force +
    --plist-check; verify_delivery.py --check-plist --plist-out) — mock
    içerik değil, gerçek üretim hattı.
    """

    EXTRA = ("<plist version=\"1.0\"><dict><key>Label</key>"
             "<string>com.example.out-of-scope</string></dict></plist>")

    def _setup_with_extra(self, home):
        gen = run(home, "bash", UPDATE_PREVIEW, "--plist-force", home)
        self.assertEqual(gen.returncode, 0, gen.stderr)
        extra = os.path.join(home, "Library", "LaunchAgents",
                             "com.example.out-of-scope.plist")
        with open(extra, "w", encoding="utf-8") as f:
            f.write(self.EXTRA)

    def test_plist_check_ignores_out_of_scope_extra_file(self):
        with tempfile.TemporaryDirectory(prefix="plist-gate-") as home:
            self._setup_with_extra(home)
            chk = run(home, "bash", UPDATE_PREVIEW, "--plist-check", home)
            # Kapsam-dışı dosya yönetilen profilleri etkilemez → exit 0 GÜNCEL.
            self.assertEqual(chk.returncode, 0, chk.stdout + chk.stderr)
            self.assertIn("GÜNCEL", chk.stdout)
            self.assertNotIn("out-of-scope", chk.stdout)

    def test_k12_layer_passes_with_out_of_scope_extra_file(self):
        with tempfile.TemporaryDirectory(prefix="plist-gate-") as home:
            self._setup_with_extra(home)
            out = os.path.join(home, "plist_report.json")
            r = run(home, sys.executable, VERIFY_DELIVERY,
                    "--check-plist", "--plist-out", out)
            # K12 gerçek hattı: ekstra dosya varken de exit 0 (PASS).
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            with open(out, encoding="utf-8") as f:
                d = json.load(f)
            self.assertTrue(d["ok"])
            self.assertEqual(d["exit"], 0)
            # Rapor yalnızca yönetilen profilleri içerir — ekstra dosya girmez.
            labels = [p["label"] for p in d["profiles"]]
            self.assertEqual(labels, ["com.freebuff.preview-leibniz2",
                                      "com.freebuff.preview-server"])
            self.assertTrue(all(p["status"] == "GÜNCEL" for p in d["profiles"]))
            self.assertNotIn("out-of-scope", json.dumps(d))


class TestParsePlistCheckOutput(unittest.TestCase):
    """parse_plist_check_output: çok-profilli çıktıyı profil bazında ayrıştırır."""

    def test_two_profiles_all_guncel(self):
        txt = (
            "GÜNCEL: /h/Library/LaunchAgents/com.freebuff.preview-leibniz2.plist"
            "  (şablonla aynı, plutil geçerli)\n"
            "GÜNCEL: /h/Library/LaunchAgents/com.freebuff.preview-server.plist"
            "  (şablonla aynı, plutil geçerli)\n"
        )
        profiles = parse_plist_check_output(txt)
        self.assertEqual(len(profiles), 2)
        self.assertEqual([p["label"] for p in profiles],
                         ["com.freebuff.preview-leibniz2",
                          "com.freebuff.preview-server"])
        self.assertTrue(all(p["status"] == "GÜNCEL" for p in profiles))

    def test_mixed_status(self):
        txt = (
            "BAYAT/GEÇERSİZ: /h/Library/LaunchAgents/com.freebuff.preview-leibniz2.plist"
            " şablondan farklı\n"
            "GÜNCEL: /h/Library/LaunchAgents/com.freebuff.preview-server.plist"
            "  (şablonla aynı, plutil geçerli)\n"
        )
        profiles = parse_plist_check_output(txt)
        self.assertEqual(len(profiles), 2)
        by_label = {p["label"]: p["status"] for p in profiles}
        self.assertEqual(by_label["com.freebuff.preview-leibniz2"], "BAYAT")
        self.assertEqual(by_label["com.freebuff.preview-server"], "GÜNCEL")

    def test_sablon_yok_line(self):
        txt = ("şablon yok: /h/Library/Caches/com.freebuff/preview-template/"
               "com.freebuff.preview-leibniz2.plist.tmpl (önce --plist çalıştır)\n")
        profiles = parse_plist_check_output(txt)
        self.assertEqual(len(profiles), 1)
        self.assertEqual(profiles[0]["label"], "com.freebuff.preview-leibniz2")
        self.assertEqual(profiles[0]["status"], "ŞABLON_YOK")

    def test_unrecognized_lines_skipped(self):
        txt = "bazı özet satırı\nGÜNCEL: /h/x.plist  (ok)\nboş satır sonrası\n"
        profiles = parse_plist_check_output(txt)
        self.assertEqual(len(profiles), 1)
        self.assertEqual(profiles[0]["label"], "x")


if __name__ == "__main__":
    unittest.main()
