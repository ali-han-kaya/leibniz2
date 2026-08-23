#!/usr/bin/env python3
"""daemon_http_test.py — daemon-modu HTTP 200 testinin birim testleri.

Daemon dalı (PREVIEW_DAEMON=1 → setsid + stdio'yu /dev/null'a dup2
yönlendirme, EBADF'sız) gerçek süreçte doğrulanır — bu yüzden test, gerçek
preview_server.py'yi daemon modda geçici portta başlatır ve üç endpoint'in
de HTTP 200 döndüğünü + sürecin canlı kaldığını poll eder. Stub verify dizini
CIKTI'dan kopyalanır (offline; network/venv gerekmez, Linux CI'da da çalışır).

Sözleşme: exit 0 = PASS (üç 200 + daemon canlı); exit 1 = FAIL; exit 2 =
kullanım hatası. --out raporu ok/endpoints/daemon_alive/error içerir.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
DAEMON_TEST = os.path.join(HERE, "daemon_http_test.py")


def run(*args):
    return subprocess.run([sys.executable, DAEMON_TEST, *args],
                          capture_output=True, text=True, timeout=240)


class TestDaemonHttpEndToEnd(unittest.TestCase):
    """Daemon modda gerçek sunucu: üç endpoint de 200 + canlı süreç."""

    def test_pass_all_200_and_daemon_alive(self):
        with tempfile.TemporaryDirectory(prefix="daemon-http-") as tmp:
            out = os.path.join(tmp, "report.json")
            r = run("--out", out)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("PASS", r.stdout)
            with open(out, encoding="utf-8") as f:
                d = json.load(f)
            self.assertTrue(d["ok"])
            self.assertTrue(d["daemon_alive"])
            self.assertEqual(d["endpoints"]["/preview.html"], 200)
            self.assertEqual(d["endpoints"]["/api/latest"], 200)
            self.assertEqual(d["endpoints"]["/api/history"], 200)
            self.assertIsNone(d["error"])

    def test_sse_endpoints_200_and_event_seen(self):
        # Canlı akış endpoint'leri (/api/run + /api/run-stream): HTTP 200 +
        # ilk event üretmeli (akış canlı — bağlantı test tarafından kapatılır).
        with tempfile.TemporaryDirectory(prefix="daemon-http-") as tmp:
            out = os.path.join(tmp, "report.json")
            r = run("--out", out)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            with open(out, encoding="utf-8") as f:
                d = json.load(f)
            self.assertIn("/api/run", d["sse_endpoints"])
            self.assertIn("/api/run-stream", d["sse_endpoints"])
            for ep in ("/api/run", "/api/run-stream"):
                self.assertEqual(d["sse_endpoints"][ep]["status"], 200,
                                 ep)
                self.assertTrue(d["sse_endpoints"][ep]["event_seen"], ep)

    def test_run_now_accepted(self):
        # /api/run-now: 200+started veya busy-guard 409+already_running —
        # ikisi de geçerli (endpoint canlı ve doğru yanıt veriyor).
        with tempfile.TemporaryDirectory(prefix="daemon-http-") as tmp:
            out = os.path.join(tmp, "report.json")
            r = run("--out", out)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            with open(out, encoding="utf-8") as f:
                d = json.load(f)
            rn = d["run_now"]
            self.assertIn(rn["status"], (200, 409))
            if rn["status"] == 200:
                self.assertEqual(rn["body"].get("status"), "started")
            elif rn["status"] == 409:
                self.assertEqual(rn["body"].get("status"), "already_running")

    def test_report_has_server_and_port(self):
        with tempfile.TemporaryDirectory(prefix="daemon-http-") as tmp:
            out = os.path.join(tmp, "report.json")
            r = run("--out", out)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            with open(out, encoding="utf-8") as f:
                d = json.load(f)
            self.assertTrue(d["port"] > 0)
            self.assertTrue(d["server"].endswith("preview_server.py"))


class TestDaemonHttpFailClosed(unittest.TestCase):
    """Eksik ön-koşul / hatalı kullanım → exit 1/2 (fail-closed)."""

    def test_missing_server_exit_2(self):
        with tempfile.TemporaryDirectory(prefix="daemon-http-") as tmp:
            r = run("--server", os.path.join(tmp, "yok.py"))
            self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
            self.assertIn("server yok", r.stderr)

    def test_missing_preview_source_exit_2(self):
        with tempfile.TemporaryDirectory(prefix="daemon-http-") as tmp:
            r = run("--preview-src", os.path.join(tmp, "yok.html"))
            self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
            self.assertIn("preview kaynağı yok", r.stderr)

    def test_unreachable_port_exit_1(self):
        # 127.0.0.1:1 (privileged, kapalı) — sunucu dinleyemez, poll zaman
        # aşar → exit 1 + rapor ok=False. Hızlı olsun diye --interval küçük.
        with tempfile.TemporaryDirectory(prefix="daemon-http-") as tmp:
            out = os.path.join(tmp, "report.json")
            # --start-timeout 5: poll kısa sürsün (port 1 dinleyemez → FAIL).
            r = run("--port", "1", "--start-timeout", "5", "--out", out)
            self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
            self.assertIn("FAIL", r.stderr)
            with open(out, encoding="utf-8") as f:
                d = json.load(f)
            self.assertFalse(d["ok"])
            self.assertIsNotNone(d["error"])


if __name__ == "__main__":
    unittest.main()
