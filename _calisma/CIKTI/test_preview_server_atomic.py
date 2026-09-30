#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""preview_server kalıcılık katmanının atomiklik sözleşmesi (sync_one deseni):
tmp dosya hedef dizininde BENZERSİZ adla üretilir (mkstemp), yazım başarısız
olursa tmp temizlenir ve hedef ESKİ içeriğiyle kalır. Sabit `.tmp` adı iki
yazıcı çakışırsa yarı-yazılmış dosyayı hedefe taşır; temizliksiz tmp ise
kalıntı bırakır.
"""

import hashlib
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


# ── SIGTERM yarışı: kill-ortasında history ↔ sidecar tutarlılığı ───────────
#
# `persist_history` iki AYRI atomik yazım yapar: history.jsonl, sonra
# .sha256 sidecar. SIGTERM tam araya gelirse diskte yeni-history +
# eski-sidecar kalır → K15 P1 hash uyuşmazlığı. Bu, CI'daki daemon-http
# kırmızısının kök-nedeniydi ve `3cabbff` onu kapattı — AMA o commit yalnız
# ürün kodunu değiştirdi (preview_server.py +10/−1), regresyon testi
# BIRAKMADI. Aşağıdaki sınıf o boşluğu kapatır: yarış bir daha sessizce
# geri gelemez, çünkü gerçek SIGTERM ile gerçek çıkış yolu ölçülür.
#
# Ölçüt elle yazılmış bir hash karşılaştırması DEĞİL: ürünün kendi K15
# doğrulayıcısı (`verify_delivery.check_history_sidecar`). Test kendi
# beklentisini yeniden uydurursa ürün sözleşmesinden sessizce ayrışabilir.

_TERM_CHILD = r'''#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import json, os, signal, sys, threading, time

sys.path.insert(0, os.environ["H_CIKTI"])
import preview_server as ps

HIST = os.path.join(os.environ["H_DIR"], "history.jsonl")
WINDOW = os.path.join(os.environ["H_DIR"], "midwindow")
WIDEN = float(os.environ["H_WIDEN"])

# Pencereyi deterministik olarak GENİŞLET: sidecar yazımından hemen önce
# bir marker bırak ve bekle. Böylece ebeveyn, kesinlikle pencere İÇİNDE
# olduğumuzu bilerek SIGTERM yollar (yarış artık şansa bağlı değil).
_real_atomic = ps._write_atomic

def _trace(msg):
    sys.stderr.write("[H] %s\n" % msg)
    sys.stderr.flush()


def slow_atomic(path, data, keep_tmp=False):
    if str(path).endswith(".sha256"):
        _trace("sidecar yazimi BASLADI (pencere aciliyor)")
        with open(WINDOW, "w", encoding="utf-8") as fh:
            fh.write("mid\n")
        _trace("MARKER yazildi")
        time.sleep(WIDEN)
        _trace("MARKER uykusu BİTTİ")
    out = _real_atomic(path, data, keep_tmp)
    if str(path).endswith(".sha256"):
        _trace("SIDECAR YAZILDI")
    return out

ps._write_atomic = slow_atomic

# run_verify yerine gerçek yazım yolu: kilit altında persist_history.
# (Verify'ı koşmak dakikalar sürer; burada ölçülen şey yazım/çıkış yarışı,
#  doğrulama mantığı değil — o ayrı katmanlarda test ediliyor.)
def fake_verify(verify_dir, *a, **kw):
    _trace("fake_verify: kilit ALINIYOR")
    with ps.LOCK:
        _trace("fake_verify: kilit ALINDI")
        ps.persist_history({"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                               time.gmtime()),
                            "verdict": "PASS", "p0": 0, "p1": 0})
        _trace("fake_verify: persist_history DONDU, kilit BIRAKILIYOR")

ps.run_verify = fake_verify
sys.argv = ["preview_server.py", "--preview-dir", os.environ["H_DIR"],
            "--port", "0", "--bind", "127.0.0.1", "--interval", "1"]
ps.main()
'''


class SigtermMidwriteConsistencyTests(unittest.TestCase):
    """SIGTERM iki-yazım penceresinin içine gelirse çıkış TUTARLI olmalı."""

    def setUp(self):
        self._old_history = ps.HISTORY_PATH
        self._old_latest = dict(ps.LATEST)

    def tearDown(self):
        ps.HISTORY_PATH = self._old_history
        ps.LATEST.clear()
        ps.LATEST.update(self._old_latest)

    @staticmethod
    def _k15(history_path):
        """Ürünün KENDİ K15 doğrulayıcısı → (ok, detail, bulgular)."""
        import verify_delivery as vd
        findings = []
        ok, detail = vd.check_history_sidecar(
            history_path, lambda *a, **kw: findings.append(a))
        return ok, detail, findings

    def test_drain_waits_for_an_inflight_two_write_sequence(self):
        """`drain_writer_lock` kilidi ALANA KADAR bekler — uçuştaki yazım sürerken.

        Bu testin daha önceki bir sürümü `finish.set()`'i drain'den ÖNCE
        çağırıyordu; o sırada yazıcı kilidi zaten bırakmış oluyordu, yani
        drain'in bekleyeceği hiçbir şey kalmıyordu ve drain'i tamamen boşa
        çıkarmak (mutasyon) testi KIRMIZIYA DÖNDÜRMÜYORDU — test yeşil
        görünüp hiçbir şey ölçmüyordu.

        Doğrusu: yazıcı pencere boyunca kilidi TUTAR; serbest bırakma AYRI
        bir thread'den, belli bir gecikmeyle gelir. Drain ancak yazım
        bittiğinde dönebilir, dolayısıyla ÖLÇÜLEN SÜRE gecikmeyi kapsamalı.
        """
        with tempfile.TemporaryDirectory() as td:
            ps.HISTORY_PATH = os.path.join(td, "history.jsonl")
            mid = threading.Event()
            finish = threading.Event()
            errors = []
            hold = 0.5          # yazıcı pencereyi bu kadar AÇIK tutar

            def writer():
                try:
                    with ps.LOCK:
                        content = (json.dumps(_rec("2026-01-01T00:00:00Z")) + "\n")
                        ps._write_atomic(ps.HISTORY_PATH, content)
                        mid.set()
                        finish.wait(timeout=10)
                        digest = hashlib.sha256(
                            content.encode("utf-8")).hexdigest()
                        ps._write_atomic(ps.HISTORY_PATH + ".sha256",
                                         "%s  history.jsonl\n" % digest)
                except BaseException as exc:      # noqa: BLE001
                    errors.append(exc)

            def releaser():
                """Pencereyi AÇIK tut, sonra kapat (yazıcı kilidi bırakır)."""
                time.sleep(hold)
                finish.set()

            th = threading.Thread(target=writer, daemon=True)
            th.start()
            self.assertTrue(mid.wait(timeout=10), "yazıcı pencereye girmedi")

            ok_open, detail_open, _ = self._k15(ps.HISTORY_PATH)
            self.assertFalse(
                ok_open,
                "pencere AÇIKKEN K15 temiz görünüyor — ölçüm yüzeyi kayboldu "
                "(sidecar yazımı history'den önce mi?): %s" % detail_open)

            rel = threading.Thread(target=releaser, daemon=True)
            rel.start()
            t0 = time.monotonic()
            drained = ps.drain_writer_lock(timeout=10)
            elapsed = time.monotonic() - t0
            rel.join(timeout=10)
            th.join(timeout=10)

            self.assertTrue(drained, "drain kilidi alamadı")
            self.assertGreaterEqual(
                elapsed, hold * 0.5,
                "drain uçuştaki yazımı BEKLEMEDİ (%.3fs < %.3fs) — kapanışta "
                "sidecar yazılmadan çıkılır" % (elapsed, hold * 0.5))
            self.assertFalse(th.is_alive(), "yazıcı thread takıldı")
            self.assertEqual(errors, [], "yazıcı hatası: %r" % (errors,))

            ok, detail, findings = self._k15(ps.HISTORY_PATH)
            self.assertTrue(ok, "drain sonrası K15 kirli: %s %r"
                            % (detail, findings))

    def test_verify_loop_starts_no_run_after_stop(self):
        """Kapanış işareti konmuşsa verify_loop YENİ run başlatmaz.

        `3cabbff` öncesi döngü `while True:` idi — stop_event yok sayılıyor,
        kapanış sırasında yeni bir run başlayıp persist_history'yi yeniden
        pencereye sokabiliyordu.
        """
        stop = threading.Event()
        stop.set()
        calls = []
        old = ps.run_verify
        ps.run_verify = lambda *a, **kw: calls.append(a)
        th = threading.Thread(
            target=lambda: ps.verify_loop("/nonexistent", 0.01, stop),
            daemon=True)
        try:
            th.start()
            th.join(timeout=10)
        finally:
            ps.run_verify = old
        self.assertFalse(th.is_alive(),
                         "stop_event set edildiği hâlde verify_loop dönmedi")
        self.assertEqual(calls, [],
                         "stop_event set edildiği hâlde yeni run başlatıldı")

    def test_sigterm_midwrite_leaves_history_and_sidecar_consistent(self):
        """GERÇEK SIGTERM, pencere AÇIKKEN: çıkışta disk tutarlı olmalı.

        Alt süreç gerçek `preview_server.main()`'i koşar — sinyal işleyicisi
        ve `finally` çıkış yolu ÜRÜN kodudur, testin kopyası değil. Pencere
        yalnızca `_write_atomic` sarmalanarak genişletilir; ebeveyn, pencere
        marker'ını görünce (yani kesinlikle pencere içindeyken) SIGTERM
        yollar. Ölçüt: çıkıştan sonra history ↔ sidecar tutarlı.
        """
        with tempfile.TemporaryDirectory() as td:
            child = os.path.join(td, "term_child.py")
            pathlib.Path(child).write_text(_TERM_CHILD, encoding="utf-8")
            env = dict(os.environ)
            env.update({"H_CIKTI": str(pathlib.Path(ps.__file__).resolve().parent),
                        "H_DIR": td, "H_WIDEN": "0.6"})
            env.pop("PREVIEW_DAEMON", None)
            # stderr DOSYAYA: alt sürecin neden/temiz mi çıktığı çıplak
            # gözlemmesin diye değil, "pencere ortasında çıkıldı" teşhisi
            # için gerekli (SIGTERM handler'ı izini buraya yazar).
            err_path = os.path.join(td, "child.err")
            err_fh = open(err_path, "wb")
            proc = subprocess.Popen([sys.executable, child], env=env,
                                    stdout=subprocess.DEVNULL,
                                    stderr=err_fh)
            try:
                window = os.path.join(td, "midwindow")
                deadline = time.monotonic() + 30
                while not os.path.exists(window):
                    if proc.poll() is not None:
                        self.fail("alt süreç penceriye girmeden öldü (rc=%s)"
                                  % proc.returncode)
                    if time.monotonic() > deadline:
                        self.fail("alt süreç 30 sn içinde pencereye girmedi")
                    time.sleep(0.02)
                # Pencere AÇIK (sidecar yazımından hemen önce).
                proc.send_signal(signal.SIGTERM)
                try:
                    rc = proc.wait(timeout=60)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    self.fail("SIGTERM sonrası çıkış 60 sn'de tamamlanmadı "
                              "(kapanış drain'de asılı kaldı?)")
            finally:
                if proc.poll() is None:
                    proc.kill()
                    proc.wait(timeout=10)

            err_fh.close()
            child_err = pathlib.Path(err_path).read_text(
                encoding="utf-8", errors="replace")

            self.assertEqual(rc, 143, "SIGTERM çıkış kodu 143 olmalı")
            hist = os.path.join(td, "history.jsonl")
            self.assertTrue(os.path.isfile(hist),
                            "history.jsonl yok — yazım turu hiç tamamlanmadı")
            self.assertTrue(
                os.path.isfile(hist + ".sha256"),
                "sidecar yok — pencere ORTASINDA çıkılmış (K15 P1)\n"
                "        alt süreç çıkış kodu: %s\n"
                "        alt süreç stderr:\n%s" % (rc, child_err.strip() or "(boş)"))
            ok, detail, findings = self._k15(hist)
            self.assertTrue(
                ok,
                "SIGTERM pencere ortasında çıktı, disk tutarsız kaldı "
                "(K15): %s %r" % (detail, findings))


if __name__ == "__main__":
    unittest.main()
