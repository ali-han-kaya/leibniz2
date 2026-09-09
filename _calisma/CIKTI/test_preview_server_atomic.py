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
import threading
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


class ConcurrentWriteStressTests(unittest.TestCase):
    """8 yazıcı aynı hedefe eşzamanlı yazsa bile dosya hep geçerli JSON kalır.

    os.replace atomik olduğu için okuyucu asla yarı-yazılmış (torn) dosya
    görmez; sabit .tmp adı veya truncating write olsaydı JSONDecodeError
    üretirdi. Test hem yazıcı hem okuyucu thread'leriyle hammer eder."""

    def test_eight_writers_never_leave_torn_json(self):
        with tempfile.TemporaryDirectory() as td:
            dst = os.path.join(td, "hammer.json")
            # Başlangıçta geçerli bir dosya olsun ki ilk okuma da anlamlı olsun.
            pathlib.Path(dst).write_text('{"init": true}', encoding="utf-8")
            errors = []
            errors_lock = threading.Lock()
            barrier = threading.Barrier(8)
            stop_reader = threading.Event()
            n_iter = 80  # 8 * 80 = 640 atomik yazım

            def writer(tid):
                try:
                    barrier.wait(timeout=5)
                except threading.BrokenBarrierError:
                    return
                for i in range(n_iter):
                    payload = json.dumps(
                        {"t": tid, "i": i, "pad": "x" * 256},
                        ensure_ascii=False,
                    )
                    try:
                        ps._write_atomic(dst, payload)
                    except Exception as exc:
                        with errors_lock:
                            errors.append(exc)

            def reader():
                while not stop_reader.is_set():
                    try:
                        if os.path.isfile(dst):
                            text = pathlib.Path(dst).read_text(encoding="utf-8")
                            if text.strip():
                                obj = json.loads(text)
                                # Yazılan şemaya uygun olmalı (init veya t/i/pad)
                                self.assertIsInstance(obj, dict)
                                if "init" not in obj:
                                    self.assertIn("t", obj)
                                    self.assertIn("i", obj)
                    except Exception as exc:
                        with errors_lock:
                            errors.append(exc)
                    # Yoğun hammer: sleep yok, busy-read torn penceresini kaçırmasın.
                    # Arada nefes ver ki writer'lar da koşabilsin.
                    if stop_reader.is_set():
                        break

            writers = [threading.Thread(target=writer, args=(tid,)) for tid in range(8)]
            r = threading.Thread(target=reader)
            r.start()
            for th in writers:
                th.start()
            for th in writers:
                th.join(timeout=15)
            stop_reader.set()
            r.join(timeout=5)

            # Hiçbir thread hata üretmemeli (özellikle JSONDecodeError = torn).
            self.assertEqual(errors, [], f"eşzamanlı yazım/okuma hatası: {errors[:3]}")
            for th in writers:
                self.assertFalse(th.is_alive(), "writer thread takıldı")

            # Final dosya geçerli JSON ve son yazılanlardan biri olmalı.
            final_text = pathlib.Path(dst).read_text(encoding="utf-8")
            final_obj = json.loads(final_text)
            self.assertIn("t", final_obj)
            self.assertGreaterEqual(final_obj["t"], 0)
            self.assertLess(final_obj["t"], 8)

            # Hiçbir .tmp kalıntısı kalmamalı (her yazım unique tmp + replace).
            leftovers = [n for n in os.listdir(td) if n != "hammer.json"]
            self.assertEqual(leftovers, [], f"tmp kalıntısı: {leftovers}")


if __name__ == "__main__":
    unittest.main()
