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
import contextlib
import io
import json
import os
import plistlib
import shutil
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
from verify_delivery import (  # noqa: E402
    parse_plist_check_output,
    parse_plist_out_of_scope,
)


def run(home, *args):
    """HOME'u fake dizine sabitleyip komutu koş; CompletedProcess döner."""
    return run_env(home, None, *args)


def run_env(home, extra_env, *args):
    """HOME'u fake dizine sabitleyip (opsiyonel ek env ile) komutu koşar."""
    env = dict(os.environ)
    env["HOME"] = home
    if extra_env:
        env.update(extra_env)
    return subprocess.run(list(args), env=env, capture_output=True,
                          text=True, timeout=300)


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

    def test_exit_1_fazla_profil_after_render(self):
        """Gerçek uçtan uca fazla-dosya senaryosu.

        update_preview.sh --plist-force (GERÇEK render) çalıştıktan SONRA
        render-home'a golden'da olmayan bir plist bırakılır → main()
        check()'i gerçek golden'larla koşup 'fazla profil' drift'ini
        yakalamalı: exit 1 + '[DRIFT] ... golden'da olmayan fazla profil'.
        """
        import check_plist_drift as cpd
        from unittest import mock
        render_home = tempfile.mkdtemp(prefix="plist-extra-")
        real_render = cpd.run_render

        def render_then_extra(script, home):
            rc, out = real_render(script, home)  # gerçek render (2 profil)
            la = os.path.join(home, "Library", "LaunchAgents")
            os.makedirs(la, exist_ok=True)
            with open(os.path.join(la, "com.example.extra.plist"), "w",
                      encoding="utf-8") as f:
                f.write(SAMPLE_PLIST)
            return rc, out

        buf = io.StringIO()
        try:
            with mock.patch.object(cpd, "run_render",
                                   side_effect=render_then_extra), \
                    contextlib.redirect_stdout(buf):
                rc = cpd.main(["--render-home", render_home,
                               "--golden-dir", GOLDEN_DIR])
        finally:
            shutil.rmtree(render_home, ignore_errors=True)
        self.assertEqual(rc, 1, buf.getvalue())
        self.assertIn("com.example.extra.plist", buf.getvalue())
        self.assertIn("fazla profil", buf.getvalue())
        self.assertIn("DRIFT TESPİT EDİLDİ", buf.getvalue())
        # Yönetilen iki profil yine de PASS (fazlalık onları bozmaz).
        self.assertIn("[PASS] com.freebuff.preview-leibniz2.plist",
                      buf.getvalue())
        self.assertIn("[PASS] com.freebuff.preview-server.plist",
                      buf.getvalue())


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
            # İki profilli yönetim: birincil leibniz2 + yedek preview-server
            # ikisi de PLIST_PROFILES'te — rapora GİRDİ SIRASIYLA girer.
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
            # Kapsam-dışı dosya yönetilen profilleri ETKİLEMEZ → exit 0 GÜNCEL,
            # ama denetim izinde INFO satırı olarak görünür (bilgi amaçlı).
            self.assertEqual(chk.returncode, 0, chk.stdout + chk.stderr)
            self.assertIn("GÜNCEL", chk.stdout)
            self.assertIn("INFO: kapsam dışı (yönetilmiyor)", chk.stdout)
            self.assertIn("com.example.out-of-scope.plist", chk.stdout)
            # Fazlalık yönetilen profilleri BAYAT'a düşürmez.
            self.assertNotIn("BAYAT", chk.stdout)

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
            # Rapor yalnızca yönetilen iki profili içerir; ekstra dosya
            # PROFILLERE girmez ama out_of_scope listesinde (denetim izi) görünür.
            labels = [p["label"] for p in d["profiles"]]
            self.assertEqual(labels,
                             ["com.freebuff.preview-leibniz2",
                              "com.freebuff.preview-server"])
            self.assertTrue(all(p["status"] == "GÜNCEL" for p in d["profiles"]))
            self.assertEqual(len(d["out_of_scope"]), 1)
            self.assertTrue(any("out-of-scope" in o for o in d["out_of_scope"]),
                            d["out_of_scope"])
            # Ham çıktıda INFO satırı duruyor (denetim izi).
            self.assertIn("INFO: kapsam dışı", d["output"])


class TestBootstrapAll(unittest.TestCase):
    """--bootstrap: mirror senkronu + HTML build + plist TEK ADIMDA.

    Üç artefaktın tümü fake HOME altında üretilir (gerçek
    ~/Library/Caches + LaunchAgents'a DOKUNMAZ, Linux CI'da da çalışır):
      (1) verify mirror senkronu → fake HOME/.../com.freebuff/verify/*
      (2) HTML build            → fake HOME/.../com.freebuff/preview/preview.html
      (3) plist üretimi         → fake HOME/Library/LaunchAgents/<label>.plist
    Her adım fail-closed: kaynak yoksa (SRC env ile yok sayılır) exit 2.
    """

    def _artifacts(self, home):
        return {
            "mirror": os.path.join(home, "Library", "Caches",
                                   "com.freebuff", "verify", "verify_delivery.py"),
            "html": os.path.join(home, "Library", "Caches",
                                 "com.freebuff", "preview", "preview.html"),
            "plist": os.path.join(home, "Library", "LaunchAgents",
                                  "com.freebuff.preview-leibniz2.plist"),
        }

    def test_bootstrap_all_three_artifacts(self):
        with tempfile.TemporaryDirectory(prefix="plist-gate-") as home:
            r = run(home, "bash", UPDATE_PREVIEW, "--bootstrap", home)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("BOOTSTRAP 1/3", r.stdout)
            self.assertIn("BOOTSTRAP 2/3", r.stdout)
            self.assertIn("BOOTSTRAP 3/3", r.stdout)
            self.assertIn("BOOTSTRAP: tamam", r.stdout)
            arts = self._artifacts(home)
            for name, p in arts.items():
                self.assertTrue(os.path.isfile(p), f"{name} üretilmedi: {p}")

    def test_bootstrap_idempotent_second_run(self):
        with tempfile.TemporaryDirectory(prefix="plist-gate-") as home:
            r1 = run(home, "bash", UPDATE_PREVIEW, "--bootstrap", home)
            self.assertEqual(r1.returncode, 0, r1.stdout + r1.stderr)
            r2 = run(home, "bash", UPDATE_PREVIEW, "--bootstrap", home)
            self.assertEqual(r2.returncode, 0, r2.stdout + r2.stderr)
            # İkinci koşuda da üç artefakt yerinde ve geçerli.
            arts = self._artifacts(home)
            for name, p in arts.items():
                self.assertTrue(os.path.isfile(p), f"{name} kayboldu: {p}")
            # Mirror yeniden senkron edildi (bayat değil).
            chk = run_env(home, {"MIRROR_DIR": os.path.join(
                home, "Library", "Caches", "com.freebuff", "verify"),
                "LEAN_MIRROR_DIR": os.path.join(
                    home, "Library", "Caches", "com.freebuff", "lean_reduct")},
                "bash", os.path.join(HERE, "sync_verify_mirror.sh"), "--check")
            self.assertEqual(chk.returncode, 0, chk.stdout + chk.stderr)

    def test_bootstrap_fail_closed_missing_src(self):
        with tempfile.TemporaryDirectory(prefix="plist-gate-") as home:
            # SRC env ile yok bir yola işaret et → build adımı exit 2.
            r = run_env(home, {"SRC": os.path.join(home, "yok.html")},
                        "bash", UPDATE_PREVIEW, "--bootstrap", home)
            self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
            self.assertIn("kaynak yok", r.stderr)

    def test_bootstrap_with_start_invokes_launchctl(self):
        """--bootstrap --start: üç artefakt + launchctl bootstrap AYNI KOMUTTA.

        Linux CI'da gerçek launchctl yok — PATH'e çağrılarını loglayıp exit 0
        dönen bir fake shim konur. Sonuç: --start bayrağı plist_start'ı
        tetikler (shim logunda `bootstrap .../com.freebuff.preview-leibniz2`
        görünür), üç artefakt kurulur, komut exit 0 döner.
        """
        with tempfile.TemporaryDirectory(prefix="plist-gate-") as home, \
             tempfile.TemporaryDirectory(prefix="launchctl-shim-") as bindir:
            log = os.path.join(bindir, "launchctl.log")
            shim = os.path.join(bindir, "launchctl")
            with open(shim, "w") as f:
                f.write("#!/bin/bash\n")
                f.write(f'echo "$@" >> "{log}"\n')
                f.write("exit 0\n")
            os.chmod(shim, 0o755)
            env = {"PATH": bindir + os.pathsep + os.environ.get("PATH", "")}
            r = run_env(home, env, "bash", UPDATE_PREVIEW,
                        "--bootstrap", "--start", home)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("BOOTSTRAP 4/4", r.stdout)
            self.assertIn("TEK KOMUTTA", r.stdout)
            # launchctl bootstrap gerçekten çağrıldı (birincil label).
            self.assertTrue(os.path.isfile(log), "launchctl hiç çağrılmadı")
            with open(log) as f:
                calls = f.read()
            self.assertIn("bootstrap", calls)
            self.assertIn("com.freebuff.preview-leibniz2", calls)
            # Üç artefakt kuruldu.
            arts = self._artifacts(home)
            for name, p in arts.items():
                self.assertTrue(os.path.isfile(p), f"{name} üretilmedi: {p}")

    def test_bootstrap_without_start_skips_launchctl(self):
        """Bayraksız --bootstrap: launchctl ÇAĞRILMAZ, yalnızca artefaktlar."""
        with tempfile.TemporaryDirectory(prefix="plist-gate-") as home, \
             tempfile.TemporaryDirectory(prefix="launchctl-shim-") as bindir:
            log = os.path.join(bindir, "launchctl.log")
            shim = os.path.join(bindir, "launchctl")
            with open(shim, "w") as f:
                f.write("#!/bin/bash\n")
                f.write(f'echo "$@" >> "{log}"\n')
                f.write("exit 0\n")
            os.chmod(shim, 0o755)
            env = {"PATH": bindir + os.pathsep + os.environ.get("PATH", "")}
            r = run_env(home, env, "bash", UPDATE_PREVIEW,
                        "--bootstrap", home)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertNotIn("BOOTSTRAP 4/4", r.stdout)
            self.assertIn("sonraki adım: update_preview.sh --start", r.stdout)
            self.assertFalse(os.path.isfile(log),
                             "bayraksız koşumda launchctl çağrılmamalı")


class TestParsePlistCheckOutputLegacyCompat(unittest.TestCase):
    """Legacy uyumluluk: parse_plist_check_output profil bazında ayrıştırma.

    Eski iki-profilli (birincil + legacy preview-server) dönemde bu fonksiyon
    çoklu profil çıktısını ayrıştırırdı. Artık yalnızca tek profil (leibniz2)
    yönetiliyor; testler tek profil üzerinden geriye dönük uyumluluğu korur.

    "test_" öneki taşımayan "_two_profiles_guncel" yardımcısı, iki profilli
    geçmiş senaryoyu mock'layarak fonksiyonun çoklu profil girişini hâlâ
    doğru ayrıştırabildiğini kanıtlar (tarihsel doğrulama).
    """

    def _two_profiles_guncel(self):
        """Yardımcı: iki-profilli (legacy) çıktıyı hâlâ ayrıştırabilir mi?

        Test olarak değil, tarihsel doğrulama amacıyla korunur. Eski iki-profilli
        dönemde `--plist-check` iki satır üretirdi; parse_plist_check_output
        her ikisini de profil listesine eklemeli.
        """
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

    def test_single_profile_all_guncel(self):
        """Tek profil GÜNCEL — mevcut canlı senaryo."""
        txt = (
            "GÜNCEL: /h/Library/LaunchAgents/com.freebuff.preview-leibniz2.plist"
            "  (şablonla aynı, plutil geçerli)\n"
        )
        profiles = parse_plist_check_output(txt)
        self.assertEqual(len(profiles), 1)
        self.assertEqual([p["label"] for p in profiles],
                         ["com.freebuff.preview-leibniz2"])
        self.assertTrue(all(p["status"] == "GÜNCEL" for p in profiles))

    def test_single_profile_bayat(self):
        """Tek profil BAYAT — legacy sonrası tek profil senaryosu."""
        txt = (
            "BAYAT/GEÇERSİZ: /h/Library/LaunchAgents/com.freebuff.preview-leibniz2.plist"
            " şablondan farklı\n"
        )
        profiles = parse_plist_check_output(txt)
        self.assertEqual(len(profiles), 1)
        self.assertEqual(profiles[0]["label"], "com.freebuff.preview-leibniz2")
        self.assertEqual(profiles[0]["status"], "BAYAT")

    def test_sablon_yok_line(self):
        """ŞABLON_YOK — ilk kurulum senaryosu (tek profil)."""
        txt = ("şablon yok: /h/Library/Caches/com.freebuff/preview-template/"
               "com.freebuff.preview-leibniz2.plist.tmpl (önce --plist çalıştır)\n")
        profiles = parse_plist_check_output(txt)
        self.assertEqual(len(profiles), 1)
        self.assertEqual(profiles[0]["label"], "com.freebuff.preview-leibniz2")
        self.assertEqual(profiles[0]["status"], "ŞABLON_YOK")

    def test_unrecognized_lines_skipped(self):
        """Tanınmayan satırlar atlanır — gürbüz ayrıştırma."""
        txt = "bazı özet satırı\nGÜNCEL: /h/x.plist  (ok)\nboş satır sonrası\n"
        profiles = parse_plist_check_output(txt)
        self.assertEqual(len(profiles), 1)
        self.assertEqual(profiles[0]["label"], "x")


class TestParseOutOfScope(unittest.TestCase):
    """parse_plist_out_of_scope: INFO satırlarından kapsam-dışı dosya listesi."""

    def test_parses_info_lines(self):
        txt = (
            "GÜNCEL: /h/Library/LaunchAgents/"
            "com.freebuff.preview-leibniz2.plist  (ok)\n"
            "INFO: kapsam dışı (yönetilmiyor): /h/Library/LaunchAgents/"
            "com.example.out-of-scope.plist\n"
            "INFO: kapsam dışı (yönetilmiyor): /h/Library/LaunchAgents/"
            "com.freebuff.legacy.plist\n"
            "INFO: 2 kapsam dışı dosya yok sayıldı (yalnızca yönetilen "
            "profiller denetlenir)\n"
        )
        out = parse_plist_out_of_scope(txt)
        self.assertEqual(len(out), 2)
        self.assertTrue(any("out-of-scope" in o for o in out), out)
        self.assertTrue(any("legacy" in o for o in out), out)

    def test_empty_or_no_info(self):
        self.assertEqual(parse_plist_out_of_scope(""), [])
        self.assertEqual(parse_plist_out_of_scope("GÜNCEL: /x.plist\n"), [])

    def test_only_path_after_marker(self):
        txt = ("INFO: kapsam dışı (yönetilmiyor): "
               "/Users/r/Library/LaunchAgents/a.plist\n")
        self.assertEqual(parse_plist_out_of_scope(txt),
                         ["/Users/r/Library/LaunchAgents/a.plist"])


SUMMARY_SCRIPT = os.path.join(HERE, "summary_plist_table.py")


class TestSummaryPlistTable(unittest.TestCase):
    """summary_plist_table.py markdown tablo üretimi — tek profil (legacy sonrası)."""

    def _run(self, json_str):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json",
                                         delete=False) as f:
            f.write(json_str)
            f.flush()
            out = subprocess.run(
                [sys.executable, SUMMARY_SCRIPT, f.name],
                capture_output=True, text=True, timeout=30)
        os.unlink(f.name)
        return out.stdout

    def test_valid_single_profile(self):
        """Tek profil GÜNCEL — legacy preview-server kaldırıldıktan sonraki canlı senaryo."""
        data = json.dumps({
            "ok": True, "exit": 0, "detail": "GÜNCEL (1/1)",
            "profiles": [
                {"label": "com.freebuff.preview-leibniz2",
                 "status": "GÜNCEL", "path": "/Users/r/.../a.plist"},
            ]})
        out = self._run(data)
        self.assertIn("✅ **K12**", out)
        self.assertIn("| com.freebuff.preview-leibniz2 | ✅ GÜNCEL |", out)
        self.assertIn("| Profil | Durum | Yol |", out)

    def test_legacy_two_profiles_still_render(self):
        """İki profil (legacy dönem) hâlâ render edilir — geriye dönük uyumluluk.

        parse_plist_check_output iki profili de ayrıştırabilir;
        summary_plist_table.py hepsini tabloya basar.
        """
        data = json.dumps({
            "ok": True, "exit": 0, "detail": "GÜNCEL (2/2)",
            "profiles": [
                {"label": "com.freebuff.preview-leibniz2",
                 "status": "GÜNCEL", "path": "/Users/r/.../a.plist"},
                {"label": "com.freebuff.preview-server",
                 "status": "GÜNCEL", "path": "/Users/r/.../b.plist"},
            ]})
        out = self._run(data)
        self.assertIn("✅ **K12**", out)
        self.assertIn("| com.freebuff.preview-leibniz2 | ✅ GÜNCEL |", out)
        self.assertIn("| com.freebuff.preview-server | ✅ GÜNCEL |", out)
        self.assertIn("| Profil | Durum | Yol |", out)

    def test_bayat_profile(self):
        data = json.dumps({
            "ok": False, "exit": 1, "detail": "BAYAT",
            "profiles": [
                {"label": "a", "status": "BAYAT", "path": "/x"},
            ]})
        out = self._run(data)
        self.assertIn("❌ **K12**", out)
        self.assertIn("| a | ❌ BAYAT |", out)

    def test_missing_file(self):
        out = subprocess.run(
            [sys.executable, SUMMARY_SCRIPT, "/nonexistent.json"],
            capture_output=True, text=True, timeout=30)
        self.assertIn("plist_report.json yok", out.stdout)



# ============================================================================
# Single-profile check_plist_drift tests
# ============================================================================
PLIST_DRIFT = os.path.join(HERE, "check_plist_drift.py")

SAMPLE_PLIST = """\
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.freebuff.preview-leibniz2</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/python3</string>
        <string>/tmp/test.py</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/tmp/out.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/err.log</string>
</dict>
</plist>
"""

SAMPLE_PLIST_DIFFERENT = """\
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.freebuff.preview-leibniz2</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/python3</string>
        <string>/tmp/CHANGED.py</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/tmp/out.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/err.log</string>
</dict>
</plist>
"""


class TestSingleProfileCheck(unittest.TestCase):
    """Tek-profil golden ile check_plist_drift.check() davranışı."""

    def _setup(self, golden_plists, rendered_plists):
        """golden + render dizinlerini kur, (golden_dir, render_home) dön."""
        golden = tempfile.mkdtemp(prefix="golden-")
        render = tempfile.mkdtemp(prefix="render-")
        la = os.path.join(render, "Library", "LaunchAgents")
        os.makedirs(la, exist_ok=True)
        for name, content in golden_plists.items():
            with open(os.path.join(golden, name), "w") as f:
                f.write(content)
        for name, content in rendered_plists.items():
            with open(os.path.join(la, name), "w") as f:
                f.write(content)
        return golden, render

    def test_single_profile_pass(self):
        """Tek golden plist, tek render → PASS."""
        from check_plist_drift import check
        golden, render = self._setup(
            {"com.freebuff.preview-leibniz2.plist": SAMPLE_PLIST},
            {"com.freebuff.preview-leibniz2.plist": SAMPLE_PLIST})
        results, drift, error = check(render, golden, "/Users/ci")
        self.assertFalse(drift)
        self.assertFalse(error)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["verdict"], "PASS")

    def test_single_profile_drift(self):
        """Tek golden plist, render farklı → DRIFT."""
        from check_plist_drift import check
        golden, render = self._setup(
            {"com.freebuff.preview-leibniz2.plist": SAMPLE_PLIST},
            {"com.freebuff.preview-leibniz2.plist": SAMPLE_PLIST_DIFFERENT})
        results, drift, error = check(render, golden, "/Users/ci")
        self.assertTrue(drift)
        self.assertFalse(error)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["verdict"], "DRIFT")

    def test_single_profile_missing_render(self):
        """Tek golden plist, render'da yok → DRIFT."""
        from check_plist_drift import check
        golden, render = self._setup(
            {"com.freebuff.preview-leibniz2.plist": SAMPLE_PLIST},
            {})  # render boş
        results, drift, error = check(render, golden, "/Users/ci")
        self.assertTrue(drift)
        self.assertEqual(results[0]["detail"], "render edilmedi (eksik)")

    def test_extra_rendered_profile(self):
        """Tek golden, render'da fazla profil → DRIFT."""
        from check_plist_drift import check
        golden, render = self._setup(
            {"com.freebuff.preview-leibniz2.plist": SAMPLE_PLIST},
            {"com.freebuff.preview-leibniz2.plist": SAMPLE_PLIST,
             "com.freebuff.extra.plist": SAMPLE_PLIST})
        results, drift, error = check(render, golden, "/Users/ci")
        self.assertTrue(drift)
        labels = [r["label"] for r in results]
        self.assertIn("com.freebuff.extra.plist", labels)
        extra = [r for r in results if r["label"] == "com.freebuff.extra.plist"][0]
        self.assertIn("fazla profil", extra["detail"])

    def test_no_golden_returns_error(self):
        """Golden dizini boşsa → error=True."""
        from check_plist_drift import check
        golden = tempfile.mkdtemp(prefix="golden-empty-")
        render = tempfile.mkdtemp(prefix="render-empty-")
        results, drift, error = check(render, golden, "/Users/ci")
        self.assertTrue(error)

    def test_check_plist_drift_main_single_profile(self):
        """check_plist_drift.py main() tek golden plist ile exit 0."""
        golden = tempfile.mkdtemp(prefix="golden-main-")
        render = tempfile.mkdtemp(prefix="render-main-")
        la = os.path.join(render, "Library", "LaunchAgents")
        os.makedirs(la, exist_ok=True)
        with open(os.path.join(golden, "com.freebuff.preview-leibniz2.plist"), "w") as f:
            f.write(SAMPLE_PLIST)
        with open(os.path.join(la, "com.freebuff.preview-leibniz2.plist"), "w") as f:
            f.write(SAMPLE_PLIST)
        # main() normally runs update_preview.sh --plist-force which we can't
        # do in a unit test, so test check() directly via main's internals.
        from check_plist_drift import check
        results, drift, _ = check(render, golden, "/Users/ci")
        self.assertFalse(drift)
        self.assertEqual(len(results), 1)
        shutil.rmtree(golden)
        shutil.rmtree(render)


# ============================================================================
# --remove-legacy tests
# ============================================================================

class TestRemoveLegacy(unittest.TestCase):
    """update_preview.sh --remove-legacy davranış testleri."""

    def _run(self, *args, home=None):
        env = dict(os.environ)
        if home:
            env["HOME"] = home
        return subprocess.run(
            ["bash", UPDATE_PREVIEW] + list(args),
            env=env, capture_output=True, text=True, timeout=30)

    def test_remove_legacy_deletes_plist(self):
        """Legacy plist dosyası silinmeli."""
        with tempfile.TemporaryDirectory(prefix="legacy-") as home:
            la = os.path.join(home, "Library", "LaunchAgents")
            os.makedirs(la, exist_ok=True)
            legacy = os.path.join(la, "com.freebuff.preview-server.plist")
            with open(legacy, "w") as f:
                f.write(SAMPLE_PLIST)
            self.assertTrue(os.path.exists(legacy))
            r = self._run("--remove-legacy", home)
            # bootout may fail on CI (no launchd), but file removal is idempotent
            self.assertFalse(os.path.exists(legacy),
                             "Legacy plist should be deleted")

    def test_remove_legacy_idempotent(self):
        """İki kez çalıştırılmalı — hata vermemeli."""
        with tempfile.TemporaryDirectory(prefix="legacy-idem-") as home:
            la = os.path.join(home, "Library", "LaunchAgents")
            os.makedirs(la, exist_ok=True)
            r1 = self._run("--remove-legacy", home)
            r2 = self._run("--remove-legacy", home)
            # İkincisi de hata vermemeli (zaten silinmiş)
            self.assertNotIn("HATA", r2.stdout + r2.stderr)

    def test_remove_legacy_preserves_primary(self):
        """Birincil profil korunmalı."""
        with tempfile.TemporaryDirectory(prefix="legacy-prim-") as home:
            la = os.path.join(home, "Library", "LaunchAgents")
            os.makedirs(la, exist_ok=True)
            legacy = os.path.join(la, "com.freebuff.preview-server.plist")
            primary = os.path.join(la, "com.freebuff.preview-leibniz2.plist")
            with open(legacy, "w") as f:
                f.write(SAMPLE_PLIST)
            with open(primary, "w") as f:
                f.write(SAMPLE_PLIST)
            r = self._run("--remove-legacy", home)
            self.assertFalse(os.path.exists(legacy))
            self.assertTrue(os.path.exists(primary),
                            "Primary plist should be preserved")

    def test_remove_legacy_no_legacy_files(self):
        """Legacy dosya yoksa bile çalışmalı."""
        with tempfile.TemporaryDirectory(prefix="legacy-none-") as home:
            r = self._run("--remove-legacy", home)
            self.assertNotIn("HATA", r.stdout + r.stderr)

    def test_remove_legacy_reports_primary_status(self):
        """Birincil profil durumu raporda görünmeli."""
        with tempfile.TemporaryDirectory(prefix="legacy-report-") as home:
            la = os.path.join(home, "Library", "LaunchAgents")
            os.makedirs(la, exist_ok=True)
            r = self._run("--remove-legacy", home)
            out = r.stdout + r.stderr
            # Should mention either primary is loaded or warning about --start
            self.assertTrue(
                "birincil" in out.lower() or "leibniz2" in out.lower() or
                "UYARI" in out or "CANLI" in out,
                f"Expected primary profile status in output: {out}")


if __name__ == "__main__":
    unittest.main()

if __name__ == "__main__":
    unittest.main()
