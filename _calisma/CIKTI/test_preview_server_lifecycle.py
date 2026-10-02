#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_preview_server_lifecycle.py — preview_server kapanış/drain yaşam-döngüsü
subprocess regresyon kapısı.

test_sync_lifecycle.py desenini izler: gerçek preview_server.py GERÇEK main()
ile SUBPROCESS olarak başlatılır (in-process import değil); temp verify+preview
sandbox'ında uçtan-uca kapanış yolu sınanır. Sabitlenen sözleşme:

  1. START   — /api/health 200 (gerçek süreç ayakta, port dinliyor)
  2. SIGTERM — main() sinyal-dalı: stderr'de "SIGTERM/SIGINT received" +
     rc=143; `finally` DRAIN tamamlanır (stop_event.set → verify-loop join →
     srv.shutdown → server_close → K15 LOCK acquire/release): süreç asılı
     KALMAZ ve port SERBEST kalır (server_close kanıtı).
  3. /api/stop — POST 202; SERVER.shutdown thread'i serve_forever'ı bitirir;
     aynı DRAIN yolu koşar; süreç rc=0 ile çıkar.
  4. K15 drain — kapanış sonrası history.jsonl ile .sha256 sidecar'ı TUTARLI
     (yarım yazım kalmaz); atomik-yazım artığı (*.tmp) bırakılmaz.

Gerçek repo ağacına dokunmaz: her test kendi temp sandbox'ında koşar.
stdlib only — OFFLINE, ağ yok (yalnız loopback).
"""

import hashlib
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
SERVER = os.path.join(HERE, "preview_server.py")

STUB_VERIFY = 'print("{}")\n'      # main() varlık-kontrolü + hızlı koşum
READY_TIMEOUT = 15
DRAIN_TIMEOUT = 15


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _can_bind(port):
    """Portu yeniden bind edebiliyor muyuz? (drain sonrası server_close kanıtı)"""
    s = socket.socket()
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        s.bind(("127.0.0.1", port))
        return True
    except OSError:
        return False
    finally:
        s.close()


class ServerSandbox:
    """Gerçek preview_server.py alt-sürecini izole temp sandbox'ta koşturur."""

    def __init__(self, seed_history=True):
        self.td = tempfile.TemporaryDirectory(prefix="ps_life_")
        self.root = self.td.name
        self.verify = os.path.join(self.root, "verify")
        self.preview = os.path.join(self.root, "preview")
        os.makedirs(self.verify)
        os.makedirs(self.preview)
        with open(os.path.join(self.verify, "verify_delivery.py"),
                  "w", encoding="utf-8") as f:
            f.write(STUB_VERIFY)
        if seed_history:
            self._seed_history()
        self.port = _free_port()
        self.log = os.path.join(self.root, "server.log")
        self._logfh = open(self.log, "w", encoding="utf-8")
        self.proc = subprocess.Popen(
            [sys.executable, SERVER,
             "--dir", self.verify, "--preview-dir", self.preview,
             "--port", str(self.port), "--bind", "127.0.0.1",
             "--interval", "3600"],
            stdout=self._logfh, stderr=subprocess.STDOUT)

    @property
    def history_path(self):
        return os.path.join(self.preview, "history.jsonl")

    def _seed_history(self):
        """Taze ölçüm gibi geçerli history + .sha256 sidecar'ı (K15 tohumu)."""
        content = json.dumps({"ts": "2026-09-20T00:00:00Z",
                              "verdict": "PASS"}, ensure_ascii=False) + "\n"
        with open(self.history_path, "w", encoding="utf-8") as f:
            f.write(content)
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        with open(self.history_path + ".sha256", "w", encoding="utf-8") as f:
            f.write("%s  history.jsonl\n" % digest)

    def wait_health(self, seconds=READY_TIMEOUT):
        deadline = time.time() + seconds
        while time.time() < deadline:
            if self.proc.poll() is not None:
                raise AssertionError(
                    "preview_server erken öldü (rc=%s):\n%s"
                    % (self.proc.returncode, self.read_log()))
            try:
                with urllib.request.urlopen(
                        "http://127.0.0.1:%d/api/health" % self.port,
                        timeout=1) as r:
                    if r.status == 200:
                        return
            except OSError:
                time.sleep(0.15)
        raise AssertionError(
            "preview_server %ss içinde hazır olmadı\n%s"
            % (seconds, self.read_log()))

    def post_stop(self):
        req = urllib.request.Request(
            "http://127.0.0.1:%d/api/stop" % self.port, method="POST",
            data=b"")
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status

    def read_log(self):
        self._logfh.flush()
        with open(self.log, encoding="utf-8") as f:
            return f.read()

    def drain(self, timeout=DRAIN_TIMEOUT):
        """Çıkışı bekler; asılı kalırsa kill + FAIL (drain regresyonu)."""
        try:
            self.proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait(timeout=5)
            raise AssertionError(
                "preview_server %ss içinde kapanmadı — DRAIN asıldı:\n%s"
                % (timeout, self.read_log()))

    def cleanup(self):
        if self.proc.poll() is None:
            self.proc.kill()
            self.proc.wait(timeout=5)
        self._logfh.close()
        self.td.cleanup()


class TestShutdownDrainLifecycle(unittest.TestCase):
    """preview_server kapanış/drain döngüsünün kalıcı subprocess regresyonu."""

    def test_sigterm_drains_and_exits_143(self):
        sb = ServerSandbox()
        try:
            sb.wait_health()
            self.assertFalse(_can_bind(sb.port),
                             "sunucu ayaktayken port dinliyor olmalı")
            sb.proc.send_signal(signal.SIGTERM)
            sb.drain()
            self.assertEqual(sb.proc.returncode, 143, sb.read_log())
            self.assertIn("SIGTERM/SIGINT received", sb.read_log())
            # DRAIN sonucu: server_close → port serbest; süreç asılı kalmadı.
            self.assertTrue(_can_bind(sb.port),
                            "drain sonrası port serbest değil (server_close?)")
        finally:
            sb.cleanup()

    def test_stop_route_drains_and_exits_zero(self):
        sb = ServerSandbox()
        try:
            sb.wait_health()
            self.assertFalse(_can_bind(sb.port))
            self.assertEqual(sb.post_stop(), 202)
            sb.drain()
            self.assertEqual(sb.proc.returncode, 0, sb.read_log())
            self.assertTrue(_can_bind(sb.port),
                            "stop yolu sonrası port serbest değil")
        finally:
            sb.cleanup()

    def test_k15_drain_keeps_history_sidecar_consistent(self):
        """DRAIN, K15 yarışını kapatır: history ↔ .sha256 tutarlı kalır."""
        sb = ServerSandbox(seed_history=True)
        try:
            sb.wait_health()
            sb.proc.send_signal(signal.SIGTERM)
            sb.drain()
            self.assertEqual(sb.proc.returncode, 143, sb.read_log())
            self.assertTrue(os.path.isfile(sb.history_path),
                            "tohumlanan history.jsonl kaybolmamalı")
            with open(sb.history_path, "rb") as f:
                content = f.read()
            sidecar = sb.history_path + ".sha256"
            self.assertTrue(os.path.isfile(sidecar),
                            "history.jsonl.sha256 sidecar'ı yok (K15)")
            with open(sidecar, encoding="utf-8") as f:
                declared = f.read().split()[0]
            self.assertEqual(
                declared, hashlib.sha256(content).hexdigest(),
                "drain sonrası sidecar içerikle tutarsız (yarım yazım — K15)")
            leftovers = [n for n in os.listdir(sb.preview)
                         if n.endswith(".tmp")]
            self.assertEqual(leftovers, [],
                             "drain atomik-yazım artığı bıraktı: %s" % leftovers)
        finally:
            sb.cleanup()


if __name__ == "__main__":
    unittest.main()
