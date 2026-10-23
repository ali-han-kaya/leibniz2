#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""preview_server kalıcılık katmanının atomiklik sözleşmesi (sync_one deseni):
tmp dosya hedef dizininde BENZERSİZ adla üretilir (mkstemp), yazım başarısız
olursa tmp temizlenir ve hedef ESKİ içeriğiyle kalır. Sabit `.tmp` adı iki
yazıcı çakışırsa yarı-yazılmış dosyayı hedefe taşır; temizliksiz tmp ise
kalıntı bırakır.
"""

import contextlib
import hashlib
import io
import json
import os
import pathlib
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import preview_server as ps
import verify_delivery as vd


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


class SigtermMidWriteRegressionTests(unittest.TestCase):
    """SIGTERM iki-yazım penceresine düşerse K15 hash uyuşmazlığı doğar.

    `persist_history` history.jsonl'i ve .sha256 sidecar'ını İKİ ayrı atomik
    yazımla üretir. Sinyal tam aralarına gelirse diskte yeni-history +
    eski-sidecar kalır; verify_delivery --check-history (K15) bunu P1 görür.
    Kapanış drain'i (`drain_writer_lock`) uçuştaki yazımı bitirip öyle
    çıkar. Bu sınıf üç yönü pinler:

      1. pencere GERÇEKTEN tutarsız (drain'in neden yük taşıdığı),
      2. drain uçuştaki yazımı BEKLER (beklemezse test kırmızı),
      3. drain main()'in kapanış yoluna BAĞLI (tanımlı ama çağrısız olamaz).

    Zamanlama piyangosuna bırakılmaz: `_write_atomic` kapılı bir sarmalayıcıyla
    değiştirilir, yazıcı thread tam pencerede durdurulur.
    """

    def setUp(self):
        self._old_history = ps.HISTORY_PATH
        self._td = tempfile.TemporaryDirectory()
        self.addCleanup(self._td.cleanup)
        ps.HISTORY_PATH = os.path.join(self._td.name, "history.jsonl")
        self.addCleanup(setattr, ps, "HISTORY_PATH", self._old_history)

    def _sidecar_digest(self):
        history = pathlib.Path(ps.HISTORY_PATH).read_text(encoding="utf-8")
        sidecar = pathlib.Path(ps.HISTORY_PATH + ".sha256").read_text(
            encoding="utf-8")
        return (history, sidecar,
                "%s  history.jsonl\n" % hashlib.sha256(
                    history.encode("utf-8")).hexdigest())

    def _assert_pair_consistent(self):
        _history, sidecar, expected = self._sidecar_digest()
        self.assertEqual(sidecar, expected,
                         "history.jsonl ile .sha256 sidecar uyuşmuyor (K15 P1)")

    def test_window_between_the_two_writes_is_really_inconsistent(self):
        """Kanıt: pencere gerçek — yalnız history yazılıp çıkılırsa çift bozuk."""
        ps.persist_history(_rec("2026-01-01T00:00:00Z"))
        self._assert_pair_consistent()
        # Yazımın İLK yarısı tamamlandı, sidecar henüz yazılmadı (SIGTERM).
        history = pathlib.Path(ps.HISTORY_PATH).read_text(encoding="utf-8")
        ps._write_atomic(ps.HISTORY_PATH,
                         history + json.dumps(
                             _rec("2026-01-01T00:00:01Z")) + "\n")
        _h, sidecar, expected = self._sidecar_digest()
        self.assertNotEqual(sidecar, expected,
                            "pencere tutarsız değilse bu test vakum olurdu")

    def test_drain_blocks_until_inflight_persist_finishes(self):
        ps.persist_history(_rec("2026-01-01T00:00:00Z"))
        self._assert_pair_consistent()

        history_written = threading.Event()
        release = threading.Event()
        real_write = ps._write_atomic

        def gated(path, data, keep_tmp=False):
            result = real_write(path, data, keep_tmp=keep_tmp)
            if (os.path.abspath(path) == os.path.abspath(ps.HISTORY_PATH)
                    and not history_written.is_set()):
                history_written.set()
                release.wait(timeout=20)  # SIGTERM burada: sidecar henüz yok
            return result

        errors = []

        def writer():
            try:
                with ps.LOCK:
                    ps.persist_history(_rec("2026-01-01T00:00:01Z"))
            except BaseException as exc:  # noqa: BLE001 - thread'e taşınır
                errors.append(exc)

        drain_done = threading.Event()
        outcome = {}

        def drain():
            outcome["drained"] = ps.drain_writer_lock(timeout=20)
            drain_done.set()

        with mock.patch.object(ps, "_write_atomic", side_effect=gated):
            w = threading.Thread(target=writer, daemon=True)
            w.start()
            self.assertTrue(history_written.wait(timeout=10),
                            "yazıcı ölçüm penceresine girmedi")
            d = threading.Thread(target=drain, daemon=True)
            d.start()
            try:
                self.assertFalse(
                    drain_done.wait(0.3),
                    "drain, uçuştaki yazımı beklemeden döndü — K15 yarışı "
                    "açık (sidecar eski kalır)")
            finally:
                release.set()
                w.join(timeout=20)
                d.join(timeout=20)

        self.assertEqual(errors, [], "yazıcı thread hata verdi: %r" % errors)
        self.assertFalse(w.is_alive(), "yazıcı thread asılı kaldı")
        self.assertTrue(drain_done.is_set(), "drain asılı kaldı")
        self.assertTrue(outcome.get("drained"), "drain kilidi alamadı")
        self._assert_pair_consistent()

    def test_drain_times_out_instead_of_hanging_shutdown(self):
        """Kilit hiç bırakılmazsa drain döner: kapanış ASILI KALMAZ."""
        self.assertTrue(ps.LOCK.acquire(timeout=5))
        try:
            self.assertFalse(ps.drain_writer_lock(timeout=0.2),
                             "kilit tutulurken drain timeout dönmeli")
        finally:
            ps.LOCK.release()

    def test_main_calls_the_drain_before_exit(self):
        src = pathlib.Path(ps.__file__).resolve().read_text(encoding="utf-8")
        self.assertIn("drain_writer_lock()", src,
                      "main() kapanışta drain çağırmıyor — regresyon")
        self.assertGreaterEqual(src.count("drain_writer_lock("), 2,
                                "drain yalnız tanımlı, çağrısı yok")


class _HistoryPairFixture(unittest.TestCase):
    """history↔sidecar çifti üzerinde çalışan testlerin ortak kurulumu."""

    def setUp(self):
        self._old_history = ps.HISTORY_PATH
        self._td = tempfile.TemporaryDirectory()
        self.addCleanup(self._td.cleanup)
        ps.HISTORY_PATH = os.path.join(self._td.name, "history.jsonl")
        self.addCleanup(setattr, ps, "HISTORY_PATH", self._old_history)

    def _journal(self):
        return ps.HISTORY_PATH + ps.HISTORY_JOURNAL_SUFFIX

    def _digest(self, path=None):
        path = path or ps.HISTORY_PATH
        return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()

    def _sidecar_digest(self):
        raw = pathlib.Path(ps.HISTORY_PATH + ".sha256").read_text(
            encoding="utf-8").strip()
        return raw.split()[0] if raw else ""

    def _assert_consistent(self):
        self.assertEqual(self._sidecar_digest(), self._digest(),
                         "history.jsonl ile sidecar uyuşmuyor (K15 P1)")

    def _k15(self):
        findings = []
        ok, detail = vd.check_history_sidecar(
            ps.HISTORY_PATH, lambda *a: findings.append(a))
        return ok, detail, findings

    def _tamper_append(self, rec):
        with open(ps.HISTORY_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    def _kill_before_sidecar(self, rec):
        """Gerçek pencere: history yayınlanır, sidecar yazımı hiç olmaz."""
        real = ps._write_atomic

        def gated(path, data, keep_tmp=False):
            if os.path.abspath(path) == os.path.abspath(
                    ps.HISTORY_PATH + ".sha256"):
                raise _HardKill("SIGKILL: sidecar yazımından önce")
            return real(path, data, keep_tmp=keep_tmp)

        with mock.patch.object(ps, "_write_atomic", side_effect=gated):
            with self.assertRaises(_HardKill):
                ps.persist_history(rec)

    def _write_journal(self, intended, prev):
        pathlib.Path(self._journal()).write_text(json.dumps({
            "version": 1,
            "history": os.path.basename(ps.HISTORY_PATH),
            "prev": prev,
            "intended": intended,
            "pid": os.getpid(),
        }), encoding="utf-8")


class HardKillMidWindowTests(_HistoryPairFixture):
    """SIGKILL iki yazımın arasına düşse bile çift KANITLA onarılır.

    İki dosyalı yayında penceresi kapatılamaz (tek rename iki dosyayı
    birlikte değiştiremez). `persist_history` bu yüzden geçişi journal'lar:
    journal history'den ÖNCE kalıcı yazılır, sidecar'dan SONRA silinir.
    Bu sınıf dört yönü pinler:

      1. gerçek pencere: yalnız history yazılıp ölünürse diskte yırtık çift
         + journal kalır (K15 fail-closed),
      2. onarım: `reconcile_history_pair` sidecar'ı history'den türetir,
         journal'ı siler, K15 yeşile döner,
      3. fail-closed sınır: journal YOKSA ya da digest'ler tutmuyorsa
         dosyalara dokunulmaz (tamper / yabancı yazıcı onarılmaz),
      4. bağlama: startup ve `persist_history` onarımı çağırır; journal
         history'den önce yazılır.
    """

    # ── 1. pencere gerçek ve journal kanıtlı ──────────────────────────
    def test_hard_kill_leaves_journal_proving_the_inflight_commit(self):
        ps.persist_history(_rec("2026-01-01T00:00:00Z"))
        self._assert_consistent()
        before = self._digest()

        self._kill_before_sidecar(_rec("2026-01-01T00:00:01Z"))

        self.assertTrue(os.path.isfile(self._journal()),
                        "hard-kill penceresi journal bırakmadı")
        state = json.loads(pathlib.Path(self._journal()).read_text(
            encoding="utf-8"))
        self.assertEqual(state["intended"], self._digest(),
                         "journal, yayınlanan history'yi tarif etmiyor")
        self.assertEqual(state["prev"], before,
                         "journal önceki digest'i kaydetmemiş")
        self.assertEqual(self._sidecar_digest(), before,
                         "sidecar eski içerikte kalmamış — pencere testi vakum")

        ok, detail, findings = self._k15()
        self.assertFalse(ok, "K15 yırtık çifti PASS saydı: %s" % detail)
        self.assertIn("uyuşmuyor", detail)
        self.assertTrue(findings)

    # ── 2. onarım + K15 yeşil ────────────────────────────────────────
    def test_reconcile_repairs_pair_and_clears_journal(self):
        ps.persist_history(_rec("2026-01-01T00:00:00Z"))
        self._kill_before_sidecar(_rec("2026-01-01T00:00:01Z"))
        self.assertFalse(self._k15()[0])

        self.assertEqual(ps.reconcile_history_pair(), "repaired")
        self._assert_consistent()
        self.assertFalse(os.path.exists(self._journal()),
                         "onarım sonrası journal kaldı")
        self.assertTrue(self._k15()[0], "onarım sonrası K15 hâlâ kırmızı")
        self.assertEqual(ps.reconcile_history_pair(), "absent",
                         "ikinci çağrı idempotent değil")

    def test_reconcile_is_quiet_when_commit_already_finished(self):
        """Sidecar yazıldı ama journal silinemedi (kill penceresi: son adım)."""
        ps.persist_history(_rec("2026-01-01T00:00:00Z"))
        self._write_journal(self._digest(), None)
        self.assertEqual(ps.reconcile_history_pair(), "clean")
        self._assert_consistent()
        self.assertFalse(os.path.exists(self._journal()))

    # ── 3. fail-closed sınır ─────────────────────────────────────────
    def test_tampered_history_without_journal_is_not_repaired(self):
        ps.persist_history(_rec("2026-01-01T00:00:00Z"))
        with open(ps.HISTORY_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(_rec("2026-01-01T00:00:09Z")) + "\n")

        self.assertEqual(ps.reconcile_history_pair(), "absent")
        self.assertFalse(self._k15()[0], "journal'sız tamper onarıldı — "
                                        "denetim zayıfladı")

    def test_foreign_journal_never_touches_the_files(self):
        """Araya başka yazıcı (backfill / fetch) girdiyse kanıt yoktur."""
        ps.persist_history(_rec("2026-01-01T00:00:00Z"))
        self._write_journal("a" * 64, self._digest())
        with open(ps.HISTORY_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(_rec("2026-01-01T00:00:09Z")) + "\n")
        before = pathlib.Path(ps.HISTORY_PATH).read_bytes()
        sidecar_before = self._sidecar_digest()

        self.assertEqual(ps.reconcile_history_pair(), "foreign")
        self.assertEqual(pathlib.Path(ps.HISTORY_PATH).read_bytes(), before,
                         "foreign journal history'yi değiştirdi")
        self.assertEqual(self._sidecar_digest(), sidecar_before,
                         "foreign journal sidecar'ı değiştirdi")
        self.assertFalse(os.path.exists(self._journal()))

    def test_aborted_commit_is_harmless(self):
        """Journal yazıldı, history hiç yayınlanmadı (kill penceresi: ilk adım)."""
        ps.persist_history(_rec("2026-01-01T00:00:00Z"))
        before = self._digest()
        self._write_journal("b" * 64, before)

        self.assertEqual(ps.reconcile_history_pair(), "aborted")
        self.assertEqual(self._digest(), before, "aborted history'yi değiştirdi")
        self._assert_consistent()
        self.assertFalse(os.path.exists(self._journal()))

    # ── 4. bağlama: persist önce onarır, sonra yazar ─────────────────
    def test_persist_history_heals_before_appending(self):
        ps.persist_history(_rec("2026-01-01T00:00:00Z"))
        self._kill_before_sidecar(_rec("2026-01-01T00:00:01Z"))
        self.assertTrue(os.path.exists(self._journal()))

        # Çağrının KENDİSİ sözleşme: yazımdan önce onarım denenmeli.
        with mock.patch.object(ps, "reconcile_history_pair",
                               wraps=ps.reconcile_history_pair) as spy:
            ps.persist_history(_rec("2026-01-01T00:00:02Z"))
        self.assertTrue(spy.called, "persist_history yazımdan önce reconcile "
                                    "çağırmıyor")
        self._assert_consistent()
        self.assertFalse(os.path.exists(self._journal()))
        rows = [json.loads(ln) for ln in
                pathlib.Path(ps.HISTORY_PATH).read_text(
                    encoding="utf-8").splitlines()]
        self.assertEqual([r["ts"] for r in rows],
                         ["2026-01-01T00:00:00Z", "2026-01-01T00:00:01Z",
                          "2026-01-01T00:00:02Z"],
                         "onarım sırasında satır kayboldu/çogaldı")
        self.assertTrue(self._k15()[0])

    def test_journal_is_written_durably_before_history(self):
        """Journal history'den ÖNCE (ve fsync'li yoldan) yazılmalı."""
        order = []
        real_atomic = ps._write_atomic
        real_durable = ps._write_atomic_durable

        def atomic(path, data, keep_tmp=False):
            order.append(os.path.basename(path))
            return real_atomic(path, data, keep_tmp=keep_tmp)

        def durable(path, data):
            order.append("DURABLE:" + os.path.basename(path))
            return real_durable(path, data)

        with mock.patch.object(ps, "_write_atomic", side_effect=atomic), \
                mock.patch.object(ps, "_write_atomic_durable",
                                  side_effect=durable):
            ps.persist_history(_rec("2026-01-01T00:00:00Z"))

        self.assertEqual(
            order[:3],
            ["DURABLE:history.jsonl.pending", "history.jsonl",
             "history.jsonl.sha256"],
            "journal history'den önce yazılmıyor: %r" % (order,))
        self.assertFalse(os.path.exists(self._journal()))

    def test_real_sigkill_between_writes_is_repaired(self):
        """Exception değil GERÇEK SIGKILL: süreç history'den sonra ölür.

        Feragat: gated `_write_atomic` history'yi yazar ve süreci kendisi
        SIGKILL'ler — sidecar yazımı hiç çağrılmaz. Bu, sinyal yakalama
        yollarını (except/finally) atladığı için gerçek hard-kill'dir.
        """
        ps.persist_history(_rec("2026-01-01T00:00:00Z"))
        self._assert_consistent()
        before = self._digest()

        child = pathlib.Path(self._td.name, "kill_child.py")
        child.write_text(
            "import os, signal, sys\n"
            "sys.path.insert(0, %r)\n"
            "import preview_server as ps\n"
            "ps.HISTORY_PATH = sys.argv[1]\n"
            "real = ps._write_atomic\n"
            "def gated(path, data, keep_tmp=False):\n"
            "    result = real(path, data, keep_tmp=keep_tmp)\n"
            "    if os.path.abspath(path) == os.path.abspath(ps.HISTORY_PATH):\n"
            "        os.kill(os.getpid(), signal.SIGKILL)\n"
            "    return result\n"
            "ps._write_atomic = gated\n"
            "ps.persist_history({'ts': '2026-01-01T00:00:01Z',\n"
            "                   'verdict': 'PASS', 'p0': 0, 'p1': 0})\n"
            % str(pathlib.Path(ps.__file__).resolve().parent),
            encoding="utf-8")
        proc = subprocess.run([sys.executable, str(child), ps.HISTORY_PATH],
                              capture_output=True, text=True, timeout=60)

        self.assertEqual(proc.returncode, -signal.SIGKILL,
                         "çocuk süreç SIGKILL ile ölmedi: rc=%s\n%s"
                         % (proc.returncode, proc.stderr))
        self.assertTrue(os.path.isfile(self._journal()),
                        "gerçek SIGKILL journal bırakmadı")
        self.assertEqual(self._sidecar_digest(), before,
                         "sidecar yeni içerikle yazılmış — pencere testi vakum")
        self.assertFalse(self._k15()[0],
                         "K15 SIGKILL sonrası yırtık çifti PASS saydı")

        self.assertEqual(ps.reconcile_history_pair(), "repaired")
        self._assert_consistent()
        self.assertTrue(self._k15()[0])

    def test_startup_and_write_paths_call_reconcile(self):
        src = pathlib.Path(ps.__file__).resolve().read_text(encoding="utf-8")
        self.assertGreaterEqual(src.count("reconcile_history_pair("), 3,
                                "reconcile yalnız tanımlı; startup/persist "
                                "çağrıları eksik")
        self.assertLess(src.index(
                            "rec_status = reconcile_history_pair(HISTORY_PATH)"),
                        src.index("if load_cached_latest():"),
                        "main() startup'ta reconcile, önbellek yüklemesinden "
                        "sonra — yırtık çift cache'e girebilir")


class BootSidecarRepairTests(_HistoryPairFixture):
    """Boot onarımı: kanıtsız kalmış uyuşmazlıkta sidecar history'den üretilir.

    `reconcile_history_pair` journal KANITI ister. Boot'ta ayrıca son bir
    kapanış yolu vardır: history (atomik replace edilen tek yazıcı dosyası)
    yetkili kaynaktır, sidecar türevdir — sunucu açılışında uyuşmazlık
    sidecar'ı yeniden üretmekle kapanır ve eski digest stderr'e yazılır.

    Sınır: onarım YALNIZ boot'ta (`main`) koşar; `persist_history` ve K15
    çağırmaz — böylece her yazımda denetim gevşemez.
    """

    def test_regenerates_mismatched_sidecar_without_a_journal(self):
        ps.persist_history(_rec("2026-01-01T00:00:00Z"))
        self._assert_consistent()
        old = self._sidecar_digest()
        self._tamper_append(_rec("2026-01-01T00:00:09Z"))
        self.assertFalse(self._k15()[0], "tamper K15'te görünmüyor — test vakum")
        self.assertFalse(os.path.exists(self._journal()))

        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            status = ps.repair_history_sidecar()

        self.assertEqual(status, "repaired")
        self._assert_consistent()
        self.assertTrue(self._k15()[0], "boot onarımı sonrası K15 hâlâ kırmızı")
        log = err.getvalue()
        self.assertIn("BOOT onarımı", log, "onarım sessiz kaldı")
        self.assertIn(old[:12], log, "eski digest loglanmadı (denetim izi yok)")
        self.assertIn(self._digest()[:12], log)

    def test_recreates_missing_sidecar(self):
        ps.persist_history(_rec("2026-01-01T00:00:00Z"))
        os.unlink(ps.HISTORY_PATH + ".sha256")
        self.assertFalse(self._k15()[0])

        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(ps.repair_history_sidecar(), "repaired")
        self._assert_consistent()
        self.assertTrue(self._k15()[0])

    def test_is_a_noop_when_the_pair_already_matches(self):
        ps.persist_history(_rec("2026-01-01T00:00:00Z"))
        with mock.patch.object(ps, "_write_atomic") as writer:
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(ps.repair_history_sidecar(), "consistent")
        self.assertFalse(writer.called,
                         "tutarlı çiftte sidecar yeniden yazıldı (gürültü)")

    def test_history_absent_is_not_an_error(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertEqual(ps.repair_history_sidecar(), "no-history")
        self.assertFalse(os.path.exists(ps.HISTORY_PATH))
        self.assertFalse(os.path.exists(ps.HISTORY_PATH + ".sha256"))
        self.assertEqual(err.getvalue(), "")

    def test_persist_history_does_not_use_the_boot_repair(self):
        """Boot onarımı her yazıma sızmamalı (denetim zayıflamasın)."""
        ps.persist_history(_rec("2026-01-01T00:00:00Z"))
        self._tamper_append(_rec("2026-01-01T00:00:09Z"))
        with mock.patch.object(ps, "repair_history_sidecar") as boot:
            ps.persist_history(_rec("2026-01-01T00:00:10Z"))
        self.assertFalse(boot.called,
                         "persist_history boot onarımını çağırıyor")

    def test_boot_sequence_heals_a_foreign_journal_state(self):
        """Journal kanıtı tutmasa bile boot sırası çifti tutarlı bırakır.

        Sıra: (1) `reconcile_history_pair` journal'ı kapatır (kanıt yok →
        dosyalara dokunmaz), (2) `repair_history_sidecar` sidecar'ı history'den
        yeniden üretir. Araya giren bir yazıcının (backfill / fetch) yarım
        bıraktığı çift böylece boot'ta kapanır.
        """
        ps.persist_history(_rec("2026-01-01T00:00:00Z"))
        self._write_journal("a" * 64, self._digest())
        self._tamper_append(_rec("2026-01-01T00:00:09Z"))
        self.assertFalse(self._k15()[0])

        self.assertEqual(ps.reconcile_history_pair(), "foreign")
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(ps.repair_history_sidecar(), "repaired")
        self._assert_consistent()
        self.assertTrue(self._k15()[0])

    def test_real_main_boot_repairs_the_pair(self):
        """GERÇEK süreç: `main()` açılışta yırtık çifti onarır.

        Sunucu gerçekten başlatılır (port 0, verify dizini stub) — bağlama
        testi kaynağa değil, gözlemlenebilir davranışa bakar: history'ye
        dokunulmuş, sidecar bayat; süreç açıldıktan sonra çift tutarlı
        olmalı ve stderr boot onarımını yazmalı.
        """
        ps.persist_history(_rec("2026-01-01T00:00:00Z"))
        self._tamper_append(_rec("2026-01-01T00:00:09Z"))
        self.assertFalse(self._k15()[0])

        vdir = os.path.join(self._td.name, "verify_dir")
        os.makedirs(vdir)
        with open(os.path.join(vdir, "verify_delivery.py"), "w",
                  encoding="utf-8") as f:
            f.write("import json\n"
                    "print(json.dumps({'verdict': 'PASS',\n"
                    "                  'counts': {'P0': 0, 'P1': 0},\n"
                    "                  'layers': {}}))\n")

        proc = subprocess.Popen(
            [sys.executable, "-u", str(pathlib.Path(ps.__file__).resolve()),
             "--dir", vdir, "--preview-dir", self._td.name,
             "--port", "0", "--interval", "3600"],
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
        try:
            deadline = time.time() + 20
            while time.time() < deadline:
                if os.path.isfile(ps.HISTORY_PATH + ".sha256"):
                    if self._sidecar_digest() == self._digest():
                        break
                if proc.poll() is not None:
                    break
                time.sleep(0.05)
            self._assert_consistent()
        finally:
            proc.terminate()
            try:
                _out, err = proc.communicate(timeout=20)
            except subprocess.TimeoutExpired:
                proc.kill()
                _out, err = proc.communicate(timeout=20)

        self.assertIn("BOOT onarımı", err,
                      "gerçek boot onarım logu yok; stderr:\n%s" % err[-2000:])
        self.assertTrue(self._k15()[0])

    def test_startup_runs_boot_repair_after_journal_reconcile(self):
        src = pathlib.Path(ps.__file__).resolve().read_text(encoding="utf-8")
        self.assertIn("repair_history_sidecar(HISTORY_PATH)", src,
                      "main() boot onarımını çağırmıyor — regresyon")
        rec = src.index("rec_status = reconcile_history_pair(HISTORY_PATH)")
        boot = src.index("repair_history_sidecar(HISTORY_PATH)")
        cache = src.index("if load_cached_latest():")
        self.assertLess(rec, boot,
                        "boot onarımı journal uzlaştırmasından ÖNCE koşuyor")
        self.assertLess(boot, cache,
                        "boot onarımı cache yüklemesinden SONRA — yırtık çift "
                        "LATEST'e girebilir")


class _HardKill(BaseException):
    """SIGKILL benzetimi: Exception değil BaseException (yutulmasın)."""


if __name__ == "__main__":
    unittest.main()
