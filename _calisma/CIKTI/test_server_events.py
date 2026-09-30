#!/usr/bin/env python3
"""test_server_events.py — preview_server yaşam-döngüsü olay-kaydı sözleşmesi.

Kalıcı olay-kaydı: logs/server_events.jsonl (PREVIEW_DIR altında, gitignore'da).
Her satır bağımsız JSON: {"ts": ISO-8601-UTC, "event": str, "pid": int,
"detail": str}. Sözleşme:

  1) Şema: üç zorunlu alan (ts/event/pid) + opsiyonel detail — eksik alan
     veya ts-sortlanamaz kayıt fail-closed reddedilir.
  2) Append-only: mevcut dosya asla ezilmez (yeniden başlatma kayıtları
     KAYBOLMAZ — history.jsonl'in tersine).
  3) Asla-düşürmez: sunucu-yüzeyi işlevi (health/readiness) olay-yazımı
     patlarsa bile çalışmaya devam eder — telemetri, servis-değil.
  4) Çökme→kurtarma: SIGTERM karşısında gerçek alt-süreç 'signal_exit'
     yazar; yeniden başlatma 'start' + 'cache_loaded' ekler — dosya üstünde
     çökme-öncesi durum → çökme → kurtarma dizisi kanıtlanır.

Gerçek-alt-süreç testi preview_server.py'yi gerçek main() ile koşar
(/api/health readiness + SIGTERM) — komşu canlı-süitlerinkiyle aynı desen.
"""

import json
import os
import signal
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import preview_server as ps  # noqa: E402

EVENTS_NAME = "logs/server_events.jsonl"


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class TestServerEventSchema(unittest.TestCase):
    """_lifecycle_event: şema + append-only + asla-düşürmez."""

    def setUp(self):
        self._old_log = ps.SERVER_EVENTS_PATH
        self.tmp = tempfile.mkdtemp(prefix="srv_events_")
        ps.SERVER_EVENTS_PATH = os.path.join(self.tmp, EVENTS_NAME)

    def tearDown(self):
        ps.SERVER_EVENTS_PATH = self._old_log
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _read_lines(self):
        """Geçerli satırları parse et; bozuk satırı atla (okuyucu-semantiği:
        append-only dosyada eski-garbage kaybı yok, parse-düşüşü var)."""
        with open(ps.SERVER_EVENTS_PATH, encoding="utf-8") as f:
            recs = []
            for ln in f:
                if not ln.strip():
                    continue
                try:
                    recs.append(json.loads(ln))
                except json.JSONDecodeError:
                    continue
            return recs

    def test_schema_required_fields(self):
        ps._lifecycle_event("start")
        ps._lifecycle_event("cache_loaded", detail="verdict=PASS ts=…")
        recs = self._read_lines()
        self.assertEqual([r["event"] for r in recs], ["start", "cache_loaded"])
        for r in recs:
            self.assertIn("ts", r)
            self.assertIn("pid", r)
            self.assertEqual(r["pid"], os.getpid())
        # ISO-8601 UTC, sonda Z
        self.assertTrue(recs[0]["ts"].endswith("Z"))
        self.assertIn("detail", recs[1])

    def test_append_only_across_restarts(self):
        ps._lifecycle_event("start")
        # "Yeniden başlatma": path'i yeniden kur, mevcut dosya korunmalı
        ps._lifecycle_event("start")
        recs = self._read_lines()
        self.assertEqual([r["event"] for r in recs], ["start", "start"])

    def test_missing_dir_created(self):
        nested = os.path.join(self.tmp, "logs", "derin")
        ps.SERVER_EVENTS_PATH = os.path.join(nested, "server_events.jsonl")
        ps._lifecycle_event("start")
        self.assertTrue(os.path.isfile(ps.SERVER_EVENTS_PATH))

    def test_event_failure_never_breaks_server_surface(self):
        """Telemetri yazımı patlarsa bile sunucu-yüzeyi işlevi yaşamalı."""
        ps.SERVER_EVENTS_PATH = os.path.join(
            self.tmp, "logs", "server_events.jsonl")
        os.makedirs(os.path.dirname(ps.SERVER_EVENTS_PATH))
        os.chmod(os.path.dirname(ps.SERVER_EVENTS_PATH), 0o500)  # yazılamaz
        try:
            self.assertIsNone(ps._lifecycle_event("start"))  # exception yok
        finally:
            os.chmod(os.path.dirname(ps.SERVER_EVENTS_PATH), 0o700)
        self.assertFalse(os.path.isfile(ps.SERVER_EVENTS_PATH))

    def test_existing_garbage_is_preserved_not_crashed(self):
        os.makedirs(os.path.dirname(ps.SERVER_EVENTS_PATH), exist_ok=True)
        with open(ps.SERVER_EVENTS_PATH, "w", encoding="utf-8") as f:
            f.write("bozuk-satir\n")
        ps._lifecycle_event("start")
        with open(ps.SERVER_EVENTS_PATH, encoding="utf-8") as f:
            raw = f.read()
        self.assertIn("bozuk-satir", raw)  # append-only: ezilmedi
        recs = self._read_lines()
        self.assertEqual(len(recs), 1)    # sadece geçerli satır parse edilir


class TestCrashRecoveryRealProcess(unittest.TestCase):
    """Gerçek alt-süreç: start → (çalışır) → SIGTERM → signal_exit →
    yeniden başlatma → start+cache_loaded. Çökme→kurtarma dosya-üstünde.

    --dir stub'lı sahte verify-dir'dir: gerçek verify-zinciri koşulursa
    verify-loop thread'i dakikalar süren zincirle kapanış-quiesce'ini
    (join+LOCK tavanı) doldurur ve süit dakikalarca uzar. Stub, kapanışı
    anlık yapar — olay-kaydını test ederiz, verify-zincirini değil.
    """

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="srv_events_live_")
        cls.verify_tmp = tempfile.mkdtemp(prefix="srv_events_verify_")
        with open(os.path.join(cls.verify_tmp, "verify_delivery.py"),
                  "w", encoding="utf-8") as f:
            f.write('print("{}")\n')  # main() varlık-kontrolü + hızlı koşum
        cls.port = _free_port()
        cls.proc = subprocess.Popen(
            [sys.executable, os.path.join(HERE, "preview_server.py"),
             "--dir", cls.verify_tmp, "--preview-dir", cls.tmp,
             "--port", str(cls.port), "--bind", "127.0.0.1",
             "--interval", "3600"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        cls._wait_health(cls.proc, cls.port, 15)

    @classmethod
    def _wait_health(cls, proc, port, seconds):
        deadline = time.time() + seconds
        while time.time() < deadline:
            if proc.poll() is not None:
                raise RuntimeError("preview_server erken öldü")
            try:
                with urllib.request.urlopen(
                        f"http://127.0.0.1:{port}/api/health",
                        timeout=1) as r:
                    if r.status == 200:
                        return
            except OSError:
                time.sleep(0.15)
        raise RuntimeError(f"preview_server {seconds}s'de hazır olmadı")

    @classmethod
    def _terminate(cls, proc):
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=15)  # stub-dir ile kapanış anlık
            except subprocess.TimeoutExpired:
                proc.kill()
                raise

    @classmethod
    def tearDownClass(cls):
        cls._terminate(cls.proc)
        import shutil
        shutil.rmtree(cls.tmp, ignore_errors=True)
        shutil.rmtree(cls.verify_tmp, ignore_errors=True)

    @classmethod
    def _events(cls):
        path = os.path.join(cls.tmp, EVENTS_NAME)
        with open(path, encoding="utf-8") as f:
            return [json.loads(ln) for ln in f if ln.strip()]

    def test_01_start_recorded(self):
        recs = self._events()
        self.assertEqual(recs[0]["event"], "start")
        self.assertEqual(recs[0]["pid"], self.proc.pid)

    def test_02_sigterm_writes_signal_exit(self):
        self.proc.send_signal(signal.SIGTERM)
        try:
            self.proc.wait(timeout=15)  # stub-dir: quiesce dolmaz
        except subprocess.TimeoutExpired:
            self.proc.kill()
            raise
        recs = self._events()
        names = [r["event"] for r in recs]
        # Sözleşme: SIGTERM kayıta düşer. Graceful-kapanış sonrası finally
        # 'shutdown' olayını da yazar — son-satır shutdown olabilir; önemli
        # olan çökme-nedeninin kayıtta yaşaması (append-only kronoloji).
        self.assertIn("signal_exit", names)
        self.assertIn("shutdown", names)
        self.assertLess(names.index("signal_exit"), names.index("shutdown"))

    def test_03_restart_recovery_appends_start_cache_loaded(self):
        """Kurtarma: aynı preview-dir'e ikinci başlatma append yapar."""
        proc2 = subprocess.Popen(
            [sys.executable, os.path.join(HERE, "preview_server.py"),
             "--dir", self.verify_tmp, "--preview-dir", self.tmp,
             "--port", str(self.port), "--bind", "127.0.0.1",
             "--interval", "3600"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            self._wait_health(proc2, self.port, 15)
        finally:
            self._terminate(proc2)
        recs = self._events()
        names = [r["event"] for r in recs]
        self.assertIn("cache_loaded", names)
        # Sıra: önceki testlerin start'ları + cache_loaded + yeni start
        self.assertGreaterEqual(names.count("start"), 2)
        # ts monoton artan (aynı dosyada çökme→kurtarma kronolojisi)
        ts = [r["ts"] for r in recs]
        self.assertEqual(ts, sorted(ts))


if __name__ == "__main__":
    unittest.main()
