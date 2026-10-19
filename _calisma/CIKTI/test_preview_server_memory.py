#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_preview_server_memory.py — preview_server bellek profili regresyon kapısı.

Profil turlarında ölçülen üç davranışı kalıcı sözleşmeye çevirir; biri
bozulursa (önbellek ıskalanır, kanal kaydı sızar, kuyruk tavanı kalkar ya da
finalize bloklamaya döner) bu dosya KIRMIZI olur:

  1) `load_history` önbellek-plateau — mtime_ns+boyut anahtarı tutarken dosya
     YENİDEN OKUNMAZ (`open` çağrısı 0; pozitif kontrol: dosya değişince tam
     1) ve tekrarlanan okumalar kalıcı bellek büyütmez (tracemalloc deltası
     eşik altı). Dosya büyüse bile dönen satır sayısı `HISTORY_MAX`'ta
     sabitlenir → dosya boyutundan bağımsız bellek tavanı.
  2) SSE kanal temizliği — bağlan/kop döngüsü sonunda `SSE_CLIENTS` /
     `STREAM_CLIENTS` boşalır, kayıtlı kuyruk nesneleri garbage-collect
     EDİLİR (weakref), tavan reddi (503) kayıt sızdırmaz ve boşta tahliye
     kaydı düşürür.
  3) Kuyruk sınırı — kanal kuyrukları gerçekten tavanlıdır (`maxsize > 0`,
     sabit kopyalanmadan bağlanan istemcinin kuyruğundan OKUNUR), flood'da
     `qsize()` tavanı aşmaz, en yeni mesaj korunur (en eski düşer) ve snapshot
     yayını dolmuş kuyrukta bile çağıranı bloklamaz.

Koşum: python3 -m unittest test_preview_server_memory
stdlib only — sunucu/soket/ağ gerekmez.
"""
import gc
import io
import json
import os
import pathlib
import queue
import sys
import tempfile
import threading
import time
import tracemalloc
import unittest
import weakref
from unittest import mock

CIKTI = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(CIKTI))

import preview_server as ps  # noqa: E402


def _rec(i):
    """Gerçekçi history satırı (dashboard alanları + layers; ~1 KB)."""
    return {
        "ts": "2026-10-19T00:00:%02dZ" % (i % 60),
        "verdict": "PASS",
        "p0": 0, "p1": 0, "duration_s": 120.5 + i, "duration_pct_warn": False,
        "budget_usd": 1.08, "budget_limit": 5.0, "budget_method": "estimate",
        "pdf_pages": 42, "ref_count": 64, "raw_sha256": "a" * 64,
        "stripped_sha256": "b" * 64, "exit_code": 0,
        "refs_verified": 64, "refs_total": 64, "refs_mismatch": 0,
        "refs_by_source": {"crossref": 60, "openlibrary": 4},
        "hook_env": "local", "z3_passed": 12, "z3_failed": 0, "z3_total": 12,
        "lean_ok": True, "lean_detail": "1 dosya", "lean_override": None,
        "lean_source": None, "cli_override_count": 0,
        "layers": {"K%d" % k: {"status": "PASS"} for k in (1, 8, 9, 21)},
        "findings": [], "audit_refs_trend": "PASS",
    }


def _write_history(path, rows):
    with open(path, "w", encoding="utf-8") as f:
        for i in range(rows):
            f.write(json.dumps(_rec(i), ensure_ascii=False) + "\n")


def _append_history(path, rows, start):
    with open(path, "a", encoding="utf-8") as f:
        for i in range(start, start + rows):
            f.write(json.dumps(_rec(i), ensure_ascii=False) + "\n")


# ────────────────────────────────────────────────────────────────────────────
# 1) load_history önbellek-plateau
# ────────────────────────────────────────────────────────────────────────────

class LoadHistoryCachePlateauTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self._old_path = ps.HISTORY_PATH
        self._old_cache = ps._history_cache
        self.addCleanup(self._restore)
        ps.HISTORY_PATH = os.path.join(self._tmp.name, "history.jsonl")
        ps._history_cache = (None, ())

    def _restore(self):
        ps.HISTORY_PATH = self._old_path
        ps._history_cache = self._old_cache

    def test_cache_hit_reads_no_file_and_drops_reparse(self):
        """Iska yokken dosya HİÇ açılmaz; anahtar değişince tam olarak bir kez."""
        _write_history(ps.HISTORY_PATH, ps.HISTORY_MAX + 10)
        warm = ps.load_history()
        self.assertEqual(len(warm), ps.HISTORY_MAX)
        real_open = open
        with mock.patch("builtins.open", side_effect=real_open) as m:
            again = ps.load_history()
            self.assertEqual(m.call_count, 0,
                             "önbellek ıskalandı: aynı anahtarla dosya yeniden okundu")
        self.assertEqual(len(again), ps.HISTORY_MAX)
        # Dönen liste KOPYADIR: çağıranın mutasyonu önbelleği bozmamalı.
        again.append({"ts": "kirli"})
        self.assertEqual(len(ps.load_history()), ps.HISTORY_MAX)
        # Pozitif kontrol — prob gerçekten canlı: dosya değişince 1 okuma.
        _append_history(ps.HISTORY_PATH, 1, ps.HISTORY_MAX + 10)
        with mock.patch("builtins.open", side_effect=real_open) as m2:
            ps.load_history()
            self.assertEqual(m2.call_count, 1,
                             "bayatlama yakalanmadı: anahtar değişti ama okuma yok")

    def test_rows_bounded_while_file_grows(self):
        """Dosya büyürken önbellek satır sayısı HISTORY_MAX'ta sabit kalır."""
        _write_history(ps.HISTORY_PATH, ps.HISTORY_MAX)
        self.assertEqual(len(ps.load_history()), ps.HISTORY_MAX)
        cached_rows = ps._history_cache[1]
        # Dosyayı 3× büyüt: satır sayısı tavanı aşarsa bellek dosyayla
        # birlikte büyürdü (profilin kapattığı asıl açık).
        _append_history(ps.HISTORY_PATH, ps.HISTORY_MAX * 2,
                        ps.HISTORY_MAX)
        rows = ps.load_history()
        self.assertEqual(len(rows), ps.HISTORY_MAX)
        self.assertEqual(len(ps._history_cache[1]), ps.HISTORY_MAX)
        self.assertLessEqual(len(ps._history_cache[1]), len(cached_rows))
        # Önbellek tek girdidir (yeni dosya yeni satırlar, ikinci kopya yok).
        self.assertEqual(len(ps._history_cache), 2)

    def test_memory_plateau_under_repeated_reads(self):
        """2000 okuma sonrası kalıcı bellek artışı eşiğin altında kalır."""
        _write_history(ps.HISTORY_PATH, ps.HISTORY_MAX + 10)
        ps.load_history()                    # ısınma: ilk parse + modül cache'leri
        gc.collect()
        tracemalloc.start()
        try:
            base, _ = tracemalloc.get_traced_memory()
            for _ in range(2000):
                ps.load_history()
            gc.collect()
            cur, _peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        delta = cur - base
        # Eşik kasten gevşek: 2000 çağrıda tek satırlık (~1 KB) bir sızıntı
        # bile ~2 MB eder; bu yüzden 256 KB üstü = gerçek sızıntı.
        self.assertLess(delta, 256 * 1024,
                        "tekrarlanan load_history kalıcı bellek büyüttü: %d B" % delta)


# ────────────────────────────────────────────────────────────────────────────
# Ortak SSE koşum düzeneği (gerçek socket yok; sahte wfile + gerçek kuyruk)
# ────────────────────────────────────────────────────────────────────────────

class _SSECycle:
    """Bir SSE handler koşumu; yazımlar buffer'a gider, `broken` ile kopar."""

    def __init__(self, method):
        self.buf = io.BytesIO()
        self.lock = threading.Lock()
        self.broken = threading.Event()
        outer = self

        class _W:
            def write(self, b):
                with outer.lock:
                    if outer.broken.is_set():
                        raise BrokenPipeError("client gone")
                    outer.buf.write(b)

            def flush(self):
                pass

        class _H:
            def __init__(self):
                self.wfile = _W()
                self.headers = {}
                self.status = None
                self.headers_sent = []
                self.close_connection = False

            def send_response(self, code):
                self.status = code

            def send_header(self, k, v):
                self.headers_sent.append((k, v))

            def end_headers(self):
                pass

            def _replay_runs(self, records):
                ps.Handler._replay_runs(self, records)

        self.handler = _H()
        self.thread = threading.Thread(target=method, args=(self.handler,),
                                       daemon=True)
        self.thread.start()

    def raw(self):
        with self.lock:
            return self.buf.getvalue().decode("utf-8")

    def wait_for(self, needle, timeout=5.0):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if needle in self.raw():
                return True
            time.sleep(0.005)
        return False

    def stop(self):
        """Kopar ve thread'in bittiğini doğrular (temizlik buna bağlı)."""
        self.broken.set()
        self.thread.join(timeout=5)
        return not self.thread.is_alive()


class _RegistryTestCase(unittest.TestCase):
    """Modül globali kayıt listelerini izole eder ve birebir geri sarar."""

    def setUp(self):
        self._saved = {}
        with ps.LOCK:
            self._clients_before = list(ps.SSE_CLIENTS)
            ps.SSE_CLIENTS[:] = []
            self._stream_before = list(ps.STREAM_CLIENTS)
            ps.STREAM_CLIENTS[:] = []
        self.addCleanup(self._restore)
        self._patch("SSE_POLL_TIMEOUT", 0.02)

    def _restore(self):
        with ps.LOCK:
            ps.SSE_CLIENTS[:] = self._clients_before
            ps.STREAM_CLIENTS[:] = self._stream_before
        for name, val in self._saved.items():
            setattr(ps, name, val)

    def _patch(self, name, value):
        self._saved.setdefault(name, getattr(ps, name))
        setattr(ps, name, value)

    def _registry(self, registry):
        with ps.LOCK:
            return list(registry)

    def _wait_registry(self, registry, n, timeout=5.0):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if len(self._registry(registry)) >= n:
                return True
            time.sleep(0.005)
        return False

    def _registered_queue(self, method, registry):
        """Handler'ı koş, kayıtlı kuyruğu al, kopar; kuyruk TAVANI döndür."""
        cyc = _SSECycle(method)
        try:
            self.assertTrue(self._wait_registry(registry, 1))
            with ps.LOCK:
                maxsize = registry[0].maxsize
            self.assertTrue(cyc.stop())
            self.assertEqual(self._registry(registry), [])
        finally:
            cyc.broken.set()
            cyc.thread.join(timeout=5)
        return maxsize


# ────────────────────────────────────────────────────────────────────────────
# 2) SSE kanal temizliği
# ────────────────────────────────────────────────────────────────────────────

class SseChannelCleanupTests(_RegistryTestCase):
    def test_connect_disconnect_cycles_leave_no_registry_entries(self):
        """25 döngü sonunda kayıtlar boş; kuyruk nesneleri GC edilmiş olmalı."""
        refs = []
        for _ in range(25):
            cyc = _SSECycle(ps.Handler.serve_sse)
            self.assertTrue(self._wait_registry(ps.SSE_CLIENTS, 1))
            with ps.LOCK:
                q = ps.SSE_CLIENTS[0]
            ref = weakref.ref(q)
            refs.append(ref)
            self.assertIsNotNone(ref(), "kuyruk kayıttan önce çöp toplandı")
            # Güçlü yerel referansı BIRAK: aksi halde testin kendi frame'i
            # (son döngünün `q` yuvası) kuyruğu canlı tutar ve GC kontrolü
            # yanlış pozitif verir.
            q = None
            self.assertTrue(cyc.stop())
            self.assertEqual(self._registry(ps.SSE_CLIENTS), [],
                             "kopan istemci kayıttan düşmedi")
        gc.collect()
        alive = [r for r in refs if r() is not None]
        self.assertEqual(alive, [],
                         "%d kuyruk nesnesi sızdı (kayıt dışı referans var)"
                         % len(alive))

    def test_stream_cycles_leave_no_registry_entries(self):
        for _ in range(5):
            self._patch("RUNS_DIR", None)
            cyc = _SSECycle(ps.Handler.serve_run_stream)
            self.assertTrue(self._wait_registry(ps.STREAM_CLIENTS, 1))
            self.assertTrue(cyc.stop())
            self.assertEqual(self._registry(ps.STREAM_CLIENTS), [])

    def test_cap_rejection_does_not_leak_registry_entry(self):
        """503 reddi kanala KAYIT eklemez (kendi kuyruğu hemen ölür)."""
        self._patch("SSE_MAX_CLIENTS", 1)
        sentinel = queue.Queue(maxsize=1)
        with ps.LOCK:
            ps.SSE_CLIENTS.append(sentinel)
        cyc = _SSECycle(ps.Handler.serve_sse)
        cyc.thread.join(timeout=5)
        self.assertFalse(cyc.thread.is_alive(),
                         "503 reddi sonrası handler bitmedi")
        self.assertEqual(cyc.handler.status, 503)
        with ps.LOCK:
            self.assertEqual(ps.SSE_CLIENTS, [sentinel])
        self.assertIn(("Retry-After", "30"), cyc.handler.headers_sent)
        with ps.LOCK:
            ps.SSE_CLIENTS[:] = []

    def test_idle_eviction_drops_registry_entry(self):
        """Boşta tahliye sonrası kayıt düşer ve handler kendiliğinden biter."""
        self._patch("SSE_IDLE_TIMEOUT", 0.2)
        cyc = _SSECycle(ps.Handler.serve_sse)
        self.assertTrue(self._wait_registry(ps.SSE_CLIENTS, 1))
        self.assertTrue(cyc.wait_for("event: evicted", timeout=5.0))
        cyc.thread.join(timeout=5)
        self.assertFalse(cyc.thread.is_alive())
        self.assertEqual(self._registry(ps.SSE_CLIENTS), [])


# ────────────────────────────────────────────────────────────────────────────
# 3) Kuyruk sınırı
# ────────────────────────────────────────────────────────────────────────────

class QueueBoundTests(_RegistryTestCase):
    def test_channel_queues_are_bounded(self):
        """Kuyruk tavanları gerçek handler'dan okunur — 0 (sınırsız) olamaz."""
        sse_max = self._registered_queue(ps.Handler.serve_sse, ps.SSE_CLIENTS)
        stream_max = self._registered_queue(ps.Handler.serve_run_stream,
                                           ps.STREAM_CLIENTS)
        self.assertGreater(sse_max, 0, "SSE kuyruğu sınırsız (maxsize=0)")
        self.assertGreater(stream_max, 0, "satır akışı kuyruğu sınırsız")

    def test_stream_broadcast_keeps_newest_within_bound(self):
        """Flood'da kuyruk tavanı aşmaz, EN YENİ satır korunur (eski düşer)."""
        stream_max = self._registered_queue(ps.Handler.serve_run_stream,
                                           ps.STREAM_CLIENTS)
        q = queue.Queue(maxsize=stream_max)
        with ps.LOCK:
            ps.STREAM_CLIENTS.append(q)
        n = stream_max + 500
        done = threading.Event()

        def _flood():
            for i in range(n):
                ps._broadcast_stream("stdout", "satır %d" % i)
            done.set()

        # Bekçi thread: bloklayan bir yayın regresyonu testi ASMAMALI
        # (bataryada dosya-başına zaman aşımı yok) — kırmızı raporla, takılma.
        t = threading.Thread(target=_flood, daemon=True)
        t0 = time.monotonic()
        t.start()
        done.wait(timeout=3.0)
        elapsed = time.monotonic() - t0
        blocked = not done.is_set()
        if blocked:
            while True:                    # bloklanan put'u aç, thread sızmasın
                try:
                    q.get_nowait()
                except queue.Empty:
                    break
            t.join(timeout=5)
        with ps.LOCK:
            ps.STREAM_CLIENTS.remove(q)
        self.assertFalse(blocked,
                         "yayın bloklandı (dolu kuyruk): %.2fs" % elapsed)
        self.assertLess(elapsed, 1.0,
                        "yayın çok yavaş: %.3fs (%d satır)" % (elapsed, n))
        self.assertEqual(q.qsize(), stream_max,
                         "kuyruk tavanı aşıldı ya da boşta kaldı")
        msgs = [json.loads(m) for m in list(q.queue)]
        # Tam sözleşme: dolu kuyrukta kalan pencere = flood'un SON
        # `stream_max` satırı, sırası bozulmadan (en yeni kalır, en eski
        # düşer). Tek tek öğe kontrolü bunun zayıf hâliydi.
        expected = ["satır %d" % i for i in range(n - stream_max, n)]
        self.assertEqual([m["line"] for m in msgs], expected,
                         "dolu kuyrukta yanlış pencere kaldı (en yeni satır "
                         "ve sıra korunmalı)")

    def test_run_end_survives_full_line_queue(self):
        """`end` sinyali en yeni mesajdır → dolu kuyrukta bile düşmez.

        Düz `put_nowait` davranışında (tavan doluyken YENİ mesaj düşer) bir
        istemci run'ın bittiğini hiç görmezdi; `_offer_latest` en eskiyi
        atıp bunu garanti eder.
        """
        stream_max = self._registered_queue(ps.Handler.serve_run_stream,
                                           ps.STREAM_CLIENTS)
        q = queue.Queue(maxsize=stream_max)
        with ps.LOCK:
            ps.STREAM_CLIENTS.append(q)
        for i in range(stream_max + 10):
            ps._broadcast_stream("stdout", "satır %d" % i)
        ps._broadcast_run_end({"ts": "2026-10-19T00:00:00Z",
                               "verdict": "PASS"})
        with ps.LOCK:
            ps.STREAM_CLIENTS.remove(q)
        self.assertEqual(q.qsize(), stream_max, "kuyruk tavanı aşıldı")
        last = json.loads(list(q.queue)[-1])
        self.assertEqual(last.get("stream"), "end",
                         "run-end sinyali dolu kuyrukta düştü")
        self.assertEqual(last["snapshot"]["verdict"], "PASS")
        # End'den önceki pencere hâlâ sıralı ve kesintisiz olmalı.
        lines = [json.loads(m)["line"] for m in list(q.queue)[:-1]]
        self.assertEqual(lines, ["satır %d" % i
                                 for i in range(stream_max + 10 - stream_max + 1,
                                                stream_max + 10)])

    def test_finalize_snapshot_broadcast_never_blocks_on_full_queue(self):
        """Dolmuş SSE kuyruğu finalize'ı (LOCK altında) bloklamamalı."""
        sse_max = self._registered_queue(ps.Handler.serve_sse, ps.SSE_CLIENTS)
        q = queue.Queue(maxsize=sse_max)
        for i in range(sse_max):
            q.put_nowait(json.dumps({"eski": i}))
        with ps.LOCK:
            ps.SSE_CLIENTS.append(q)
        self._patch("HISTORY_PATH", None)   # disk yan etkisi yok
        self._patch("RUNS_DIR", None)
        stdout = json.dumps({"verdict": "PASS",
                             "counts": {"P0": 0, "P1": 0}})
        err = []

        def _run():
            try:
                ps._finalize_run(stdout, "", 0, 1.0, data=None, verify_dir=None)
            except BaseException as exc:      # pragma: no cover - tanı için
                err.append(repr(exc))

        # LATEST'i birebir geri sar: `_finalize_run` onu stdout JSON'undan
        # doldurur; sızarsa sonraki testlerin (ve shuffle-audit'in) gördüğü
        # durum bu testin koşumuna bağlı hâle gelirdi.
        with ps.LOCK:
            latest_before = dict(ps.LATEST)

        def _restore_latest():
            with ps.LOCK:
                ps.LATEST.clear()
                ps.LATEST.update(latest_before)

        self.addCleanup(_restore_latest)
        t = threading.Thread(target=_run, daemon=True)
        with ps.LOCK:
            ps.LATEST.update({"cli_overrides": None})
        t.start()
        t.join(timeout=3.0)
        blocked = t.is_alive()
        if blocked:
            # Bloklanan put'u aç ki thread sızmasın, sonra kırmızı raporla.
            while True:
                try:
                    q.get_nowait()
                except queue.Empty:
                    break
            t.join(timeout=5)
        with ps.LOCK:
            try:
                ps.SSE_CLIENTS.remove(q)
            except ValueError:
                pass
        self.assertEqual(err, [], "finalize hata verdi")
        self.assertFalse(blocked,
                         "finalize dolu kuyrukta bloklandı (LOCK altında put)")
        self.assertEqual(q.qsize(), sse_max,
                         "finalize sonrası kuyruk tavanı aştı")
        newest = json.loads(list(q.queue)[-1])
        self.assertEqual(newest.get("verdict"), "PASS",
                         "en yeni snapshot kuyruğa yazılmadı")
        self.assertNotIn("eski", newest)


if __name__ == "__main__":
    unittest.main()
