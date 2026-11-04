#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""GERÇEK süreçte kapanış DRAIN'i uçuştaki verify yazımını bekliyor mu?

`preview_server.main()` kapanışta `drain_writer_lock()` çağırır (bkz.
`SigtermMidWriteRegressionTests` — aynı süreçte thread'lerle kanıtlar).
Buradaki test o kanıtı SÜREÇ SINIRININ ötesine taşır: sunucu gerçekten
`preview_server.py` olarak başlatılır, `/api/run-now` ile gerçek bir verify
thread'i tetiklenir, SIGTERM o thread `persist_history` içindeyken gönderilir
ve süreç gözlemlenir.

Neden ayrı bir subprocess testi?

  • Aynı-süreç testi `drain_writer_lock`'u doğrudan çağırır; `main()`'in
    `finally` bloğunun GERÇEKTEN o çağrıya ulaştığını, sinyal yolunun
    (`signal.signal` → `sys.exit(143)` → `finally`) atlanmadığını göstermez.
  • Kaynak-grep testi (`assertIn("drain_writer_lock()", src)`) yalnızca metni
    arar; çağrının sırasını, `stop_event`/`join` sonrası konumunu ya da
    drain'in gerçekten BEKLEDİĞİNİ kanıtlamaz.
  • Kapanış yolu üç ayrı bekleme katmanı içerir (`t.join` → `srv.shutdown`
    → `drain`). Run-now thread'i `t.join`'in kapsamı DIŞINDADIR (daemon):
    onu yalnızca drain durdurabilir. Test tam bu thread'i kullanır.

Zamanlama piyangosuna bırakılmaz. Çocuk süreç `_write_atomic`'i kapılı bir
sarmalayıcıyla değiştirir (yalnız test harness'ında): history yazıldıktan
SONRA durur, sidecar henüz yazılmamıştır — K15 çiftinin yırtık kaldığı tam
pencere. Parent release dosyasını bırakana kadar yazıcı thread'i kilit
tutmaya devam eder.

Pinlenen yönler:

  1. POZİTİF: SIGTERM sonrası drain girdisi görülür, süreç hâlâ ayaktadır,
     sidecar yazılmamıştır (pencere açık) → drain bekliyor.
  2. SÜREKLİLİK: release sonrası süreç 143 ile çıkar, history+sidecar
     tutarlıdır, olay sırası history-written < drain-enter < sidecar-written.
  3. NEGATİF KONTROL (vakum değil): drain devre dışıyken aynı senaryoda
     süreç release'i beklemeden çıkar ve çift YIRTIK kalır — yani 1. maddedeki
     iddia drain'in kendisine duyarlıdır, tesadüfe değil.
"""

import hashlib
import json
import os
import pathlib
import signal
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request

HERE = pathlib.Path(__file__).resolve().parent
SERVER_PATH = HERE / "preview_server.py"

# verify_delivery.py yerine geçen stub: komut satırını yok sayar, tek JSON
# basar. Gerçek verify koşmaz — testin konusu verify'ın kendisi değil,
# verify BİTTİKTEN sonraki yazımın kapanışta beklenip beklenmediği.
_VERIFY_STUB = """import json

print(json.dumps({
    "verdict": "PASS",
    "counts": {"P0": 0, "P1": 0},
    "layers": {},
}))
"""

# Çocuk süreç harness'ı. Gerçek `preview_server` modülü olduğu gibi yüklenir;
# yalnız iki dikiş sarmalanır:
#   • `_write_atomic`  → yazım penceresini gözlemlenebilir/kapılı yapar,
#   • `drain_writer_lock` → drain'in ÇAĞRILDIĞINI olay olarak kaydeder
#     (PS_DRAIN_DISABLED=1 iken no-op: "drain yok" senaryosu).
# Sunucu kendi gerçek `main()`'i, sinyal yakalayıcısı ve serve_forever
# döngüsüyle koşar.
_CHILD_SCRIPT = r'''
import os
import sys
import time

SERVER_DIR, PREVIEW_DIR, VERIFY_DIR = sys.argv[1], sys.argv[2], sys.argv[3]
sys.path.insert(0, SERVER_DIR)
import preview_server as ps  # noqa: E402

HISTORY = os.path.join(PREVIEW_DIR, "history.jsonl")
FLAGS = os.path.join(PREVIEW_DIR, "flags")
EVENTS = os.path.join(PREVIEW_DIR, "events.log")
os.makedirs(FLAGS, exist_ok=True)


def _evt(name):
    fd = os.open(EVENTS, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    try:
        os.write(fd, (name + "\n").encode("utf-8"))
    finally:
        os.close(fd)


def _armed():
    return os.path.exists(os.path.join(FLAGS, "arm"))


_real_write = ps._write_atomic


def _gated(path, data, keep_tmp=False):
    result = _real_write(path, data, keep_tmp=keep_tmp)
    if not _armed():
        return result
    target = os.path.abspath(path)
    if target == os.path.abspath(HISTORY):
        # history yayınlandı, sidecar HENÜZ yok: SIGTERM buraya düşerse
        # diskte yırtık çift kalır — drain'in beklemesi gereken pencere.
        _evt("history-written")
        release = os.path.join(FLAGS, "release")
        deadline = time.time() + 30.0
        while not os.path.exists(release) and time.time() < deadline:
            time.sleep(0.01)
        _evt("history-released")
    elif target == os.path.abspath(HISTORY + ".sha256"):
        _evt("sidecar-written")
    return result


ps._write_atomic = _gated

_real_drain = ps.drain_writer_lock


def _drain(timeout=None):
    _evt("drain-enter")
    return _real_drain(timeout=timeout)


ps.drain_writer_lock = _drain

if os.environ.get("PS_DRAIN_DISABLED") == "1":
    # NEGATİF KONTROL: kapanış drain'i yokmuş gibi davran.
    ps.drain_writer_lock = lambda timeout=None: True


class _ReportingServer(ps.ThreadingHTTPServer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        with open(os.path.join(PREVIEW_DIR, "server.port"), "w",
                  encoding="utf-8") as fh:
            fh.write(str(self.server_address[1]))


ps.ThreadingHTTPServer = _ReportingServer

sys.argv = ["preview_server.py", "--dir", VERIFY_DIR,
            "--preview-dir", PREVIEW_DIR, "--port", "0",
            "--interval", "3600"]
ps.main()
'''


def _sha256_text(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sidecar_digest(history_path):
    raw = pathlib.Path(history_path + ".sha256").read_text(
        encoding="utf-8").strip()
    return raw.split()[0] if raw else ""


class DrainWaitsForInflightVerifyWriteTests(unittest.TestCase):
    """SIGTERM, run-now verify thread'i `persist_history` içindeyken gelir."""

    def setUp(self):
        self._td = tempfile.TemporaryDirectory(prefix="ps-drain-")
        self.addCleanup(self._td.cleanup)
        self.root = pathlib.Path(self._td.name)
        self.preview = self.root / "preview"
        self.preview.mkdir()
        self.verify = self.root / "verify"
        self.verify.mkdir()
        (self.verify / "verify_delivery.py").write_text(_VERIFY_STUB,
                                                        encoding="utf-8")
        self.flags = self.preview / "flags"
        self.flags.mkdir()
        self.events_path = self.preview / "events.log"
        self.history = self.preview / "history.jsonl"
        self.child = self.root / "child_server.py"
        self.child.write_text(_CHILD_SCRIPT, encoding="utf-8")
        self._procs = []

    def tearDown(self):
        for proc, err_file in self._procs:
            if proc.poll() is None:
                proc.kill()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    pass
            try:
                err_file.close()
            except OSError:
                pass

    # ── yardımcılar ───────────────────────────────────────────────────
    def _spawn(self, drain_disabled=False):
        err_path = self.root / ("stderr-%d.log" % len(self._procs))
        err_file = open(err_path, "w", encoding="utf-8")
        env = dict(os.environ)
        env.pop("PS_DRAIN_DISABLED", None)
        if drain_disabled:
            env["PS_DRAIN_DISABLED"] = "1"
        proc = subprocess.Popen(
            [sys.executable, "-u", str(self.child), str(HERE),
             str(self.preview), str(self.verify)],
            stdout=subprocess.DEVNULL, stderr=err_file, text=True, env=env)
        self._procs.append((proc, err_file))
        return proc

    def _wait_for(self, predicate, timeout, message):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if predicate():
                return
            time.sleep(0.02)
        self.fail(message)

    def _events(self):
        if not self.events_path.is_file():
            return []
        return [ln.strip() for ln in
                self.events_path.read_text(encoding="utf-8").splitlines()
                if ln.strip()]

    def _wait_event(self, proc, name, timeout=15.0):
        self._wait_for(
            lambda: name in self._events(), timeout,
            "'%s' olayı %ss içinde gelmedi; olaylar=%r" %
            (name, timeout, self._events()))
        self.assertIsNone(proc.poll(),
                          "süreç '%s' beklenirken çıktı (rc=%s)" %
                          (name, proc.returncode))

    def _stderr(self, proc):
        for p, f in self._procs:
            if p is proc:
                f.flush()
                return pathlib.Path(f.name).read_text(
                    encoding="utf-8", errors="replace")
        return ""

    def _wait_ready(self):
        """Sunucu ayağa kalksın ve İLK verify run'ı history'ye yazılsın.

        `--interval 3600` olsa da verify_loop ilk turu hemen koşar; run-now
        POST'u ancak o tur bittikten sonra 200 döner (VERIFY_BUSY).
        """
        self._wait_for(lambda: (self.preview / "server.port").is_file(), 30,
                       "sunucu port dosyasını yazmadı")
        def _first_row_committed():
            if not self.history.is_file():
                return False
            data = self.history.read_text(encoding="utf-8").strip()
            if not data:
                return False
            sidecar = self.preview / (self.history.name + ".sha256")
            if not sidecar.is_file():
                return False
            return _sidecar_digest(str(self.history)) == _sha256_text(
                self.history.read_text(encoding="utf-8"))
        self._wait_for(_first_row_committed, 30,
                       "ilk verify run'ı history+sidecar çiftini yazmadı")

    def _port(self):
        return int((self.preview / "server.port").read_text(
            encoding="utf-8").strip())

    def _run_now(self):
        """`/api/run-now` — gerçek endpoint, gerçek run-now thread'i."""
        url = "http://127.0.0.1:%d/api/run-now" % self._port()
        deadline = time.time() + 15
        last = None
        while time.time() < deadline:
            request = urllib.request.Request(url, data=b"", method="POST")
            try:
                with urllib.request.urlopen(request, timeout=5) as response:
                    self.assertEqual(response.status, 200)
                    return
            except urllib.error.HTTPError as exc:
                last = "HTTP %s" % exc.code
                if exc.code != 409:  # 409 = verify zaten koşuyor, tekrar dene
                    self.fail("/api/run-now beklenmedik yanıt: %s" % last)
            except urllib.error.URLError as exc:
                last = str(exc)
            time.sleep(0.1)
        self.fail("/api/run-now 15s içinde başlatılamadı: %s" % last)

    def _row_count(self):
        return len([ln for ln in self.history.read_text(
            encoding="utf-8").splitlines() if ln.strip()])

    def _assert_pair_consistent(self, n_rows):
        history = self.history.read_text(encoding="utf-8")
        self.assertEqual(_sidecar_digest(str(self.history)),
                         _sha256_text(history),
                         "history.jsonl ile .sha256 sidecar uyuşmuyor (K15 P1)")
        rows = [json.loads(ln) for ln in history.splitlines() if ln.strip()]
        self.assertEqual(len(rows), n_rows,
                         "beklenen satır sayısı %d, diskte %d" %
                         (n_rows, len(rows)))

    def _send_sigterm(self, proc):
        proc.send_signal(signal.SIGTERM)

    # ── 1+2. POZİTİF + SÜREKLİLİK ────────────────────────────────────
    def test_drain_waits_for_inflight_verify_write_before_exit(self):
        proc = self._spawn()
        self._wait_ready()

        # Pencereyi aç: run-now verify'ı history'yi yazıp sidecar'dan ÖNCE durur.
        (self.flags / "arm").write_text("1", encoding="utf-8")
        self._run_now()
        self._wait_event(proc, "history-written")

        # Pencere gerçekten yırtık: 2 satır history, sidecar hâlâ 1. satırı
        # tarif ediyor (test vakum olmasın).
        self.assertEqual(self._row_count(), 2)
        self.assertNotEqual(_sidecar_digest(str(self.history)),
                            _sha256_text(self.history.read_text(
                                encoding="utf-8")),
                            "yazım penceresi tutarlı görünüyor — test vakum")

        self._send_sigterm(proc)

        # Kapanış drain'e ULAŞMALI (sinyal yolu finally'yi atlamıyor)…
        self._wait_for(lambda: "drain-enter" in self._events(), 15.0,
                       "'drain-enter' 15s içinde gelmedi; olaylar=%r"
                       % self._events())
        # …ve orada BEKLEMELİ: süreç hâlâ ayakta, sidecar yazılmamış.
        self.assertIsNone(
            proc.poll(),
            "drain, uçuştaki verify yazımı bitmeden çıktı — K15 yarışı açık "
            "(history yazıldı, sidecar bayat kalırdı)")
        self.assertNotIn("sidecar-written", self._events(),
                         "sidecar, release'den önce yazıldı — kapı çalışmıyor")

        # Yazımı serbest bırak: drain kilidi alıp döner, süreç çıkar.
        (self.flags / "release").write_text("1", encoding="utf-8")
        try:
            rc = proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            self.fail("release sonrası süreç 30s içinde çıkmadı; stderr:\n%s"
                      % self._stderr(proc)[-2000:])

        self.assertEqual(rc, 143, "SIGTERM çıkış kodu 143 değil: %s\n%s"
                         % (rc, self._stderr(proc)[-2000:]))
        self.assertIn("[main] SIGTERM/SIGINT received",
                      self._stderr(proc),
                      "sinyal yakalayıcı logu yok — kapanış yolu çalışmadı")

        # Sıra kanıtı: history → drain girdi → sidecar (sonra çıkış).
        events = self._events()
        self.assertLess(events.index("history-written"),
                        events.index("drain-enter"),
                        "drain, yazım başlamadan önce çağrılmış: %r" % events)
        self.assertLess(events.index("drain-enter"),
                        events.index("sidecar-written"),
                        "sidecar drain'den önce yazılmış: %r" % events)

        # Kapanış tamamlandı: çift tutarlı, iki run diske inmiş.
        self._assert_pair_consistent(2)
        self.assertFalse(self.history.with_name(
            self.history.name + ".pending").exists(),
            "commit journal'ı kalıntı bıraktı")

    # ── 3. NEGATİF KONTROL: iddia drain'e duyarlı ────────────────────
    def test_without_drain_the_same_scenario_leaves_a_torn_pair(self):
        proc = self._spawn(drain_disabled=True)
        self._wait_ready()

        (self.flags / "arm").write_text("1", encoding="utf-8")
        self._run_now()
        self._wait_event(proc, "history-written")

        self._send_sigterm(proc)
        try:
            rc = proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            self.fail("drain devre dışıyken süreç çıkmadı — kapanış asılı "
                      "kaldı (testin ölçtüğü şey bu değil)")

        self.assertEqual(rc, 143)
        events = self._events()
        self.assertNotIn("drain-enter", events,
                         "negatif kontrolde drain çağrıldı: %r" % events)
        self.assertNotIn("sidecar-written", events,
                         "negatif kontrolde sidecar yazıldı — pencere kapandı")
        # Kanıt: drain olmadan çift GERÇEKTEN yırtık kalır.
        self.assertEqual(self._row_count(), 2)
        self.assertNotEqual(_sidecar_digest(str(self.history)),
                            _sha256_text(self.history.read_text(
                                encoding="utf-8")),
                            "drain'siz senaryoda çift tutarlı çıktı — pozitif "
                            "testin iddiası drain'e duyarlı değil")


if __name__ == "__main__":
    unittest.main()
