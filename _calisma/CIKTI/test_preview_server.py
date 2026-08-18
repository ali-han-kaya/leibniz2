#!/usr/bin/env python3
"""test_preview_server.py — preview_server.py birim testleri (CI fail-closed).

Kapsam:
  - persist_history : append + HISTORY_MAX trim + atomik replace (tmp kalıntısı yok)
  - load_history    : parse + bozuk satır atlama + eksik dosya → []
  - deadlock        : persist/load, LOCK tutulurken çağrıldığında asılmamalı
                      (fonksiyonlar içeride LOCK'u YENİDEN almaz; threading.Lock
                      re-entrant değildir — run_verify bunları `with LOCK:` içinde
                      çağırır, o yüzden bu bir regresyon kapısıdır)

stdlib `unittest` kullanır — ek bağımlılık yok. CI'da:
    python3 -m unittest discover -s _calisma/CIKTI -p "test_preview_server.py" -v
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import preview_server as ps


def _rec(ts, verdict="PASS", **kw):
    rec = {"ts": ts, "verdict": verdict, "p0": 0, "p1": 0}
    rec.update(kw)
    return rec


class PersistHistoryTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._path = os.path.join(self._tmp.name, "history.jsonl")
        self._old_path = ps.HISTORY_PATH
        self._old_max = ps.HISTORY_MAX
        ps.HISTORY_PATH = self._path
        ps.HISTORY_MAX = 3

    def tearDown(self):
        ps.HISTORY_PATH = self._old_path
        ps.HISTORY_MAX = self._old_max
        self._tmp.cleanup()

    def test_persist_appends_and_load_returns_in_order(self):
        ps.persist_history(_rec("2026-01-01T00:00:00Z"))
        ps.persist_history(_rec("2026-01-01T00:01:00Z"))
        rows = ps.load_history()
        self.assertEqual([r["ts"] for r in rows],
                         ["2026-01-01T00:00:00Z", "2026-01-01T00:01:00Z"])

    def test_persist_trims_to_history_max(self):
        for i in range(5):
            ps.persist_history(_rec(f"2026-01-01T00:0{i}:00Z"))
        rows = ps.load_history()
        self.assertEqual(len(rows), 3)
        # en eski 2 satır atıldı → ilk kalan 00:02
        self.assertEqual(rows[0]["ts"], "2026-01-01T00:02:00Z")
        self.assertEqual(rows[-1]["ts"], "2026-01-01T00:04:00Z")

    def test_persist_ignores_record_without_ts(self):
        ps.persist_history({"verdict": "PASS"})  # ts yok → yazılmaz
        self.assertEqual(ps.load_history(), [])

    def test_load_skips_corrupt_lines(self):
        with open(self._path, "w", encoding="utf-8") as f:
            f.write("{bozuk json\n")
            f.write(json.dumps(_rec("2026-01-01T00:00:00Z")) + "\n")
            f.write("\n")  # boş satır da atlanır
        rows = ps.load_history()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["ts"], "2026-01-01T00:00:00Z")

    def test_load_missing_file_returns_empty(self):
        self.assertEqual(ps.load_history(), [])

    def test_atomic_replace_leaves_no_tmp(self):
        ps.persist_history(_rec("2026-01-01T00:00:00Z"))
        self.assertTrue(os.path.isfile(self._path))
        self.assertFalse(os.path.exists(self._path + ".tmp"))


class DeadlockTests(unittest.TestCase):
    """persist/load, LOCK tutulurken çağrıldığında asılmamalı.

    Subprocess + timeout ile doğrulanır: içeride LOCK yeniden alınsaydı aynı
    thread kilitlenir, süreç timeout'a takılır ve test patlar.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._path = os.path.join(self._tmp.name, "history.jsonl")

    def tearDown(self):
        self._tmp.cleanup()

    def _run_under_lock(self):
        code = (
            "import sys\n"
            f"sys.path.insert(0, {HERE!r})\n"
            "import preview_server as ps\n"
            f"ps.HISTORY_PATH = {self._path!r}\n"
            "with ps.LOCK:\n"
            "    ps.persist_history({'ts': '2026-01-01T00:00:00Z',"
            " 'verdict': 'PASS'})\n"
            "    ps.load_history()\n"
            "print('OK')\n"
        )
        return subprocess.run([sys.executable, "-c", code],
                              capture_output=True, text=True, timeout=10)

    def test_persist_and_load_do_not_deadlock_under_lock(self):
        try:
            r = self._run_under_lock()
        except subprocess.TimeoutExpired as e:
            self.fail(f"deadlock: persist/load LOCK altında asılı kaldı: {e}")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("OK", r.stdout)


class ReplayEventsTests(unittest.TestCase):
    """build_replay_events — /api/run-stream geriye dönük akışı.

    Son tamamlanmış run'un satırları, canlı akıştan ÖNCE, replay-start/end
    sınırları arasında ve `replay: true` işaretiyle üretilmelidir.
    """

    def test_no_ts_returns_empty(self):
        self.assertEqual(ps.build_replay_events(None, "PASS", "x", "y"), [])
        self.assertEqual(ps.build_replay_events("", "PASS", "x", "y"), [])

    def test_orders_stderr_then_stdout(self):
        ev = ps.build_replay_events("t", "PASS", "out1\nout2", "err1")
        names = [n for n, _ in ev]
        self.assertEqual(names, ["replay-start", "stderr", "stdout", "stdout",
                                 "replay-end"])
        payloads = [json.loads(d) for _, d in ev]
        # sıra: stderr satırı önce, sonra stdout satırları (zamansal sıra)
        self.assertEqual(payloads[1], {"stream": "stderr", "line": "err1",
                                       "replay": True})
        self.assertEqual(payloads[2]["line"], "out1")
        self.assertEqual(payloads[3]["line"], "out2")

    def test_replay_start_carries_verdict_and_end_boundary(self):
        ev = ps.build_replay_events("t", "FAIL", "o", "e")
        first = json.loads(ev[0][1])
        last = json.loads(ev[-1][1])
        self.assertEqual(first["stream"], "replay-start")
        self.assertEqual(first["verdict"], "FAIL")
        self.assertEqual(first["ts"], "t")
        self.assertEqual(last["stream"], "replay-end")
        self.assertEqual(last["ts"], "t")

    def test_empty_streams_produce_only_boundaries(self):
        ev = ps.build_replay_events("t", "PASS", "", "")
        self.assertEqual([n for n, _ in ev], ["replay-start", "replay-end"])

    def test_multiline_stdout_is_split_into_events(self):
        # splitlines() çok satırlı metni satır başına bir event'e böler;
        # hiçbir data alanı gerçek newline içermez (SSE tek fiziksel satır).
        ev = ps.build_replay_events("t", "PASS", "a\nb", "")
        lines = [json.loads(d)["line"] for n, d in ev if n == "stdout"]
        self.assertEqual(lines, ["a", "b"])
        for _, d in ev:
            self.assertNotIn("\n", d)


class FakeWfile:
    def __init__(self):
        self.buf = b""

    def write(self, b):
        self.buf += b

    def flush(self):
        pass


class ReplayHandlerTests(unittest.TestCase):
    """Handler._replay_last_run — SSE serileştirme (event: X\ndata: Y\n\n)."""

    def _replay(self, ts, verdict, stdout, stderr):
        h = type("FakeHandler", (), {"wfile": FakeWfile()})()
        ps.Handler._replay_last_run(h, ts, verdict, stdout, stderr)
        return h.wfile.buf.decode("utf-8")

    def test_writes_sse_events_in_order(self):
        out = self._replay("t", "PASS", "o1\no2", "e1")
        self.assertTrue(out.startswith("event: replay-start\n"))
        self.assertIn("event: stderr\ndata: ", out)
        self.assertIn("event: stdout\ndata: ", out)
        # stderr satırı stdout'tan ÖNCE gelir (canlı akıştaki zamansal sıra)
        self.assertLess(out.index("event: stderr"), out.index("event: stdout"))
        self.assertTrue(
            out.rstrip().endswith(
                'event: replay-end\ndata: {"stream": "replay-end", "ts": "t"}'))

    def test_no_ts_writes_nothing(self):
        self.assertEqual(self._replay(None, "PASS", "o", "e"), "")
        self.assertEqual(self._replay("", "PASS", "o", "e"), "")


if __name__ == "__main__":
    unittest.main()
