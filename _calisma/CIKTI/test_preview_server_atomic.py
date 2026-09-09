#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""preview_server kalıcılık katmanının atomiklik sözleşmesi (sync_one deseni):
tmp dosya hedef dizininde BENZERSİZ adla üretilir (mkstemp), yazım başarısız
olursa tmp temizlenir ve hedef ESKİ içeriğiyle kalır. Sabit `.tmp` adı iki
yazıcı çakışırsa yarı-yazılmış dosyayı hedefe taşır; temizliksiz tmp ise
kalıntı bırakır.
"""

import json
import os
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import preview_server as ps


def _rec(ts):
    return {"ts": ts, "verdict": "PASS", "p0": 0, "p1": 0}


class AtomicWriteHelperTests(unittest.TestCase):
    """_write_atomic: sync_one deseninin Python ikizi."""

    def test_replaces_destination_atomically(self):
        with tempfile.TemporaryDirectory() as td:
            dst = os.path.join(td, "x.json")
            ps._write_atomic(dst, '{"v": 1}')
            ps._write_atomic(dst, '{"v": 2}')
            self.assertEqual(pathlib.Path(dst).read_text(), '{"v": 2}')
            leftovers = [n for n in os.listdir(td) if n != "x.json"]
            self.assertEqual(leftovers, [], f"tmp kalıntısı: {leftovers}")

    def test_tmp_name_is_unique_per_call(self):
        """İki eşzamanlı yazıcı aynı hedefe yazsa bile tmp adları çakışmaz
        (sabit .tmp adı yarı-yazılmış içeriği hedefe taşıyabilir)."""
        with tempfile.TemporaryDirectory() as td:
            dst = os.path.join(td, "x.json")
            seen = set()
            for i in range(20):
                name = ps._write_atomic(dst, f'{{"i": {i}}}', keep_tmp=True)
                self.assertNotIn(name, seen, "tmp adı tekrarlandı")
                seen.add(name)
                pathlib.Path(dst).write_text('{"base": true}')

    def test_write_failure_leaves_destination_and_no_tmp(self):
        """Yazım başarısız olursa hedef eski içerikte kalır ve tmp kalmaz."""
        with tempfile.TemporaryDirectory() as td:
            dst = os.path.join(td, "x.json")
            pathlib.Path(dst).write_text('{"old": true}')

            class Bad:
                def __str__(self):
                    raise RuntimeError("serialize boom")

            with self.assertRaises(TypeError):
                ps._write_atomic(dst, Bad())
            self.assertEqual(pathlib.Path(dst).read_text(), '{"old": true}')
            leftovers = [n for n in os.listdir(td) if n != "x.json"]
            self.assertEqual(leftovers, [], f"tmp kalıntısı: {leftovers}")


class PersistAtomicityTests(unittest.TestCase):
    """persist_history / persist_run_log: yazım yolu _write_atomic'e çıkmalı
    (unique tmp, temizlik, rename); sabit .tmp adı kalmasın."""

    def setUp(self):
        self._old_history = ps.HISTORY_PATH
        self._old_runs = ps.RUNS_DIR

    def tearDown(self):
        ps.HISTORY_PATH = self._old_history
        ps.RUNS_DIR = self._old_runs

    def test_persist_run_log_writes_via_helper(self):
        with tempfile.TemporaryDirectory() as td:
            ps.RUNS_DIR = os.path.join(td, "runs")
            rec = _rec("2026-01-01T00:00:00Z")
            ps.persist_run_log(rec)
            files = os.listdir(ps.RUNS_DIR)
            self.assertEqual(len(files), 1)
            self.assertTrue(files[0].startswith("run-"))
            data = json.loads(pathlib.Path(ps.RUNS_DIR, files[0]).read_text())
            self.assertEqual(data["ts"], rec["ts"])

    def test_persist_history_sidecar_uses_atomic_helper(self):
        """history.jsonl + .sha256 sidecar'ı aynı atomik yoldan yazılmalı
        (sidecar sabit .tmp adıyla yazılıyorsa aynı yarış orada yaşar)."""
        src = pathlib.Path(ps.__file__).resolve().read_text(encoding="utf-8")
        for banned in ('HISTORY_PATH + ".tmp"', 'sidecar + ".tmp"',
                       'path + ".tmp"'):
            self.assertNotIn(banned, src,
                             f"sabit .tmp yolu persist yolunda kaldı: {banned}")
        self.assertGreaterEqual(src.count("_write_atomic("), 3)

        with tempfile.TemporaryDirectory() as td:
            ps.HISTORY_PATH = os.path.join(td, "history.jsonl")
            ps.persist_history(_rec("2026-01-01T00:00:00Z"))
            digest = pathlib.Path(ps.HISTORY_PATH + ".sha256").read_text()
            self.assertRegex(digest, r"^[0-9a-f]{64}  history\.jsonl\n$")
            data = pathlib.Path(ps.HISTORY_PATH).read_text()
            self.assertIn("2026-01-01T00:00:00Z", data)


if __name__ == "__main__":
    unittest.main()
