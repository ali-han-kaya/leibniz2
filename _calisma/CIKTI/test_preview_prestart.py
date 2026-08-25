#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""preview_prestart.py — launchd PreStart kontrolünün birim testleri.

Kapsanan davranış (fail-closed):
  - PASS: tüm zorunlu runtime dosyaları + geçerli python + drift yok → exit 0
  - EKSİK: preview/verify dosyası yok → exit 1
  - BOZUK: preview_server.py py_compile hatası (yarım sync) → exit 1
  - DRIFT: kurulu plist şablondan farklı → exit 1
  - exec: PASS'te sunucu komutu exec edilir (PID korunur); --check-only exec etmez
  - golden plist'ler PreStart wrapper'ını içerir ve plutil ile geçerlidir

Tüm testler fake HOME altında koşar (gerçek ~/Library'a DOKUNMAZ).
"""
import json
import os
import plistlib
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
PRESTART = os.path.join(HERE, "preview_prestart.py")
GOLDEN_DIR = os.path.join(HERE, "plist-golden")

sys.path.insert(0, HERE)
import preview_prestart as pp  # noqa: E402

PREVIEW_NAMES = ("preview_server.py", "_daemonize.py", "preview.html")
VERIFY_NAMES = ("verify_delivery.py", "verify_delivery.config.json",
                "daemon_http_test.py")

VALID_PY = "x = 1\n"
VALID_HTML = "<html><body>preview</body></html>\n"


def build_env(preview_dir, verify_dir):
    """Zorunlu runtime dosyalarını doldur (hepsi geçerli)."""
    for name in PREVIEW_NAMES:
        content = VALID_PY if name.endswith(".py") else VALID_HTML
        with open(os.path.join(preview_dir, name), "w", encoding="utf-8") as f:
            f.write(content)
    for name in VERIFY_NAMES:
        with open(os.path.join(verify_dir, name), "w", encoding="utf-8") as f:
            f.write(VALID_PY)


def make_installed_plist(home, label, preview_dir, port=8000, interval=30):
    """Fake HOME altına kurulu plist yaz; tam yolu döner."""
    la = os.path.join(home, "Library", "LaunchAgents")
    os.makedirs(la, exist_ok=True)
    path = os.path.join(la, "%s.plist" % label)
    with open(path, "wb") as f:
        plistlib.dump({
            "Label": label,
            "ProgramArguments": [
                "/usr/bin/python3",
                os.path.join(preview_dir, "preview_server.py"),
                "--dir", os.path.join(home, "verify"),
                "--preview-dir", preview_dir,
                "--port", str(port),
                "--interval", str(interval),
            ],
            "RunAtLoad": True,
            "KeepAlive": {"SuccessfulExit": False},
            "StandardOutPath": os.path.join(
                home, "Library", "Logs", "com.freebuff", "%s.log" % label),
            "StandardErrorPath": os.path.join(
                home, "Library", "Logs", "com.freebuff", "%s.log" % label),
        }, f)
    return path


def run_cli(preview_dir, verify_dir, label, tmpl_dir, home, *extra):
    """preview_prestart.py --check-only alt süreç; CompletedProcess döner."""
    env = dict(os.environ)
    env["HOME"] = home
    cmd = [sys.executable, PRESTART, "--preview-dir", preview_dir,
           "--verify-dir", verify_dir, "--label", label,
           "--tmpl-dir", tmpl_dir, "--check-only"] + list(extra)
    return subprocess.run(cmd, env=env, capture_output=True, text=True,
                          timeout=120)


class TestPrestartProbe(unittest.TestCase):
    """--check-only davranışı (exit 0/1) — fake HOME altında."""

    def _dirs(self, home):
        preview = os.path.join(home, "preview")
        verify = os.path.join(home, "verify")
        tmpl = os.path.join(home, "tmpl")
        os.makedirs(preview, exist_ok=True)
        os.makedirs(verify, exist_ok=True)
        os.makedirs(tmpl, exist_ok=True)
        return preview, verify, tmpl

    def test_pass_all_files_present(self):
        with tempfile.TemporaryDirectory(prefix="prestart-") as home:
            preview, verify, tmpl = self._dirs(home)
            build_env(preview, verify)
            r = run_cli(preview, verify, "fake", tmpl, home)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("PASS", r.stdout)

    def test_missing_preview_server_fail_closed(self):
        with tempfile.TemporaryDirectory(prefix="prestart-") as home:
            preview, verify, tmpl = self._dirs(home)
            build_env(preview, verify)
            os.remove(os.path.join(preview, "preview_server.py"))
            r = run_cli(preview, verify, "fake", tmpl, home)
            self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
            self.assertIn("EKSİK", r.stderr)
            self.assertIn("preview_server.py", r.stderr)

    def test_missing_verify_file_fail_closed(self):
        with tempfile.TemporaryDirectory(prefix="prestart-") as home:
            preview, verify, tmpl = self._dirs(home)
            build_env(preview, verify)
            os.remove(os.path.join(verify, "daemon_http_test.py"))
            r = run_cli(preview, verify, "fake", tmpl, home)
            self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
            self.assertIn("EKSİK", r.stderr)
            self.assertIn("daemon_http_test.py", r.stderr)

    def test_corrupt_python_fail_closed(self):
        with tempfile.TemporaryDirectory(prefix="prestart-") as home:
            preview, verify, tmpl = self._dirs(home)
            build_env(preview, verify)
            with open(os.path.join(preview, "preview_server.py"), "w",
                      encoding="utf-8") as f:
                f.write("def broken(:\n")  # sentaks hatası
            r = run_cli(preview, verify, "fake", tmpl, home)
            self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
            self.assertIn("BOZUK", r.stderr)

    def test_plist_drift_fail_closed(self):
        # Şablon var ama kurulu plist'ten farklı (port) → DRIFT.
        with tempfile.TemporaryDirectory(prefix="prestart-") as home:
            preview, verify, tmpl = self._dirs(home)
            build_env(preview, verify)
            installed = make_installed_plist(home, "fake", preview, port=8000)
            with open(installed, "r", encoding="utf-8") as f:
                cur = f.read()
            # Şablon = kurulu plist içeriğinden farklı (port 9999 olsun).
            tmpl_path = os.path.join(tmpl, "fake.plist.tmpl")
            with open(tmpl_path, "w", encoding="utf-8") as f:
                f.write(cur.replace("8000", "9999"))
            r = run_cli(preview, verify, "fake", tmpl, home)
            self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
            self.assertIn("DRIFT", r.stderr)

    def test_no_drift_when_template_matches(self):
        # Şablon kurulu plist ile birebir aynı içerikten → drift yok.
        with tempfile.TemporaryDirectory(prefix="prestart-") as home:
            preview, verify, tmpl = self._dirs(home)
            build_env(preview, verify)
            installed = make_installed_plist(home, "fake", preview, port=8000)
            with open(installed, "r", encoding="utf-8") as f:
                cur = f.read()
            with open(os.path.join(tmpl, "fake.plist.tmpl"), "w",
                      encoding="utf-8") as f:
                f.write(cur)
            r = run_cli(preview, verify, "fake", tmpl, home)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("PASS", r.stdout)


class TestPrestartExec(unittest.TestCase):
    """PASS'te sunucu komutu exec edilir; --check-only exec etmez."""

    def test_exec_called_with_server_args(self):
        with tempfile.TemporaryDirectory(prefix="prestart-") as home:
            preview = os.path.join(home, "preview")
            verify = os.path.join(home, "verify")
            tmpl = os.path.join(home, "tmpl")
            os.makedirs(preview)
            os.makedirs(verify)
            os.makedirs(tmpl)
            build_env(preview, verify)
            server = os.path.join(preview, "preview_server.py")
            env = dict(os.environ)
            env["HOME"] = home
            with mock.patch.dict(os.environ, {"HOME": home}), \
                 mock.patch.object(pp.os, "execv") as m_execv:
                rc = pp.main([
                    "--preview-dir", preview,
                    "--verify-dir", verify,
                    "--label", "fake",
                    "--tmpl-dir", tmpl,
                    "--", server, "--port", "8000",
                ])
            # execv mock'lu olduğundan "döner" → post-execv hata yolu (2).
            # Gerçekte execv asla dönmez; bu değer yalnızca mock kanıtıdır.
            self.assertEqual(rc, pp.EXIT_ERROR)
            m_execv.assert_called_once()
            args, kwargs = m_execv.call_args
            self.assertEqual(args[0], sys.executable)
            self.assertEqual(args[1],
                             [sys.executable, server, "--port", "8000"])

    def test_check_only_never_execs(self):
        with tempfile.TemporaryDirectory(prefix="prestart-") as home:
            preview = os.path.join(home, "preview")
            verify = os.path.join(home, "verify")
            tmpl = os.path.join(home, "tmpl")
            os.makedirs(preview)
            os.makedirs(verify)
            os.makedirs(tmpl)
            build_env(preview, verify)
            with mock.patch.dict(os.environ, {"HOME": home}), \
                 mock.patch.object(pp.os, "execv") as m_execv:
                rc = pp.main([
                    "--preview-dir", preview,
                    "--verify-dir", verify,
                    "--label", "fake",
                    "--tmpl-dir", tmpl,
                    "--check-only",
                    "--", os.path.join(preview, "preview_server.py"),
                ])
            self.assertEqual(rc, 0)
            m_execv.assert_not_called()

    def test_missing_server_cmd_exit_2(self):
        with tempfile.TemporaryDirectory(prefix="prestart-") as home:
            preview = os.path.join(home, "preview")
            verify = os.path.join(home, "verify")
            tmpl = os.path.join(home, "tmpl")
            os.makedirs(preview)
            os.makedirs(verify)
            os.makedirs(tmpl)
            build_env(preview, verify)
            with mock.patch.dict(os.environ, {"HOME": home}):
                rc = pp.main([
                    "--preview-dir", preview,
                    "--verify-dir", verify,
                    "--label", "fake",
                    "--tmpl-dir", tmpl,
                ])
            self.assertEqual(rc, 2)


class TestPrestartGoldens(unittest.TestCase):
    """Golden plist'ler PreStart wrapper'ını içerir + plutil ile geçerli."""

    def test_golden_contains_wrapper(self):
        for name in ("com.freebuff.preview-leibniz2.plist",
                     "com.freebuff.preview-server.plist"):
            p = os.path.join(GOLDEN_DIR, name)
            self.assertTrue(os.path.isfile(p), "%s golden'ı yok" % name)
            with open(p, "r", encoding="utf-8") as f:
                content = f.read()
            self.assertIn("preview_prestart.py", content,
                          "%s PreStart wrapper'ını içermeli" % name)
            self.assertIn("<string>--</string>", content,
                          "%s ayraç içermeli" % name)

    def test_golden_plutil_valid(self):
        if not shutil_which("plutil"):
            self.skipTest("plutil yok (Linux) — plistlib ile doğrula")
        for name in ("com.freebuff.preview-leibniz2.plist",
                     "com.freebuff.preview-server.plist"):
            p = os.path.join(GOLDEN_DIR, name)
            r = subprocess.run(["plutil", "-lint", p], capture_output=True,
                               text=True, timeout=30)
            self.assertEqual(r.returncode, 0, "%s geçersiz: %s" % (name, r.stderr))

    def test_golden_plistlib_loadable(self):
        # plutil olmayan ortamda (Linux CI) da geçerli olmalı.
        for name in ("com.freebuff.preview-leibniz2.plist",
                     "com.freebuff.preview-server.plist"):
            p = os.path.join(GOLDEN_DIR, name)
            with open(p, "rb") as f:
                d = plistlib.load(f)
            args = d["ProgramArguments"]
            self.assertIn("preview_prestart.py", args[1])
            self.assertEqual(args[args.index("--") + 1].endswith(
                "preview_server.py"), True)


def shutil_which(name):
    import shutil
    return shutil.which(name)


if __name__ == "__main__":
    unittest.main()
