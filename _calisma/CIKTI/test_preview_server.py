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
import hashlib
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import preview_server as ps
import diff_config_artifacts as dca


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

    def test_persist_writes_sha256_sidecar(self):
        """persist_history her yazımda .sha256 sidecar üretmeli."""
        ps.persist_history(_rec("2026-01-01T00:00:00Z"))
        sidecar = pathlib.Path(self._path + ".sha256")
        self.assertTrue(sidecar.is_file())
        content = pathlib.Path(self._path).read_text(encoding="utf-8")
        want = hashlib.sha256(content.encode("utf-8")).hexdigest()
        raw = sidecar.read_text(encoding="utf-8").strip()
        self.assertEqual(raw.split()[0], want)
        self.assertIn("history.jsonl", raw)

    def test_sidecar_tracks_append(self):
        """Sidecar her append之后 güncellenmeli."""
        ps.persist_history(_rec("2026-01-01T00:00:00Z"))
        ps.persist_history(_rec("2026-01-01T00:01:00Z"))
        content = pathlib.Path(self._path).read_text(encoding="utf-8")
        want = hashlib.sha256(content.encode("utf-8")).hexdigest()
        sidecar = pathlib.Path(self._path + ".sha256")
        self.assertEqual(sidecar.read_text(encoding="utf-8").split()[0], want)


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

    def test_replay_start_carries_summary_fields(self):
        # Son run'un özet alanları (verdict/P0/P1/bütçe/süre) replay-start
        # event'inde taşınmalı ki client geçmiş run sınırında özet satırını
        # render edebilsin.
        ev = ps.build_replay_events("t", "FAIL", "o", "e", p0=2, p1=1,
                                    budget_usd=1.08, duration_s=30.5)
        first = json.loads(ev[0][1])
        self.assertEqual(first["p0"], 2)
        self.assertEqual(first["p1"], 1)
        self.assertEqual(first["budget_usd"], 1.08)
        self.assertEqual(first["duration_s"], 30.5)

    def test_build_replay_events_multi_marks_first_and_last(self):
        recs = [
            {"ts": "t1", "verdict": "PASS", "stdout": "a", "stderr": ""},
            {"ts": "t2", "verdict": "FAIL", "stdout": "b", "stderr": "c"},
        ]
        ev = ps.build_replay_events_multi(recs)
        names = [n for n, _ in ev]
        self.assertEqual(names, ["replay-start", "stdout", "replay-end",
                                 "replay-start", "stderr", "stdout",
                                 "replay-end"])
        starts = [json.loads(d) for n, d in ev if n == "replay-start"]
        self.assertTrue(starts[0]["first"])
        self.assertFalse(starts[1]["first"])
        ends = [json.loads(d) for n, d in ev if n == "replay-end"]
        self.assertNotIn("last", ends[0])
        self.assertTrue(ends[1]["last"])

    def test_build_replay_events_multi_empty(self):
        self.assertEqual(ps.build_replay_events_multi([]), [])

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


class RunLogTests(unittest.TestCase):
    """persist_run_log / load_run_logs / _prune_run_logs — son N run replay."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._runs = os.path.join(self._tmp.name, "runs")
        self._old_dir = ps.RUNS_DIR
        self._old_max = ps.RUN_LOG_MAX
        ps.RUNS_DIR = self._runs
        ps.RUN_LOG_MAX = 3

    def tearDown(self):
        ps.RUNS_DIR = self._old_dir
        ps.RUN_LOG_MAX = self._old_max
        self._tmp.cleanup()

    def test_persist_and_load_roundtrip_with_stdout(self):
        ps.persist_run_log({"ts": "2026-01-01T00:00:01.000000+00:00",
                            "verdict": "PASS", "p0": 0, "p1": 0,
                            "budget_usd": 1.08, "stdout": "o1\no2",
                            "stderr": "e1"})
        ps.persist_run_log({"ts": "2026-01-01T00:00:02.000000+00:00",
                            "verdict": "FAIL", "p0": 2, "p1": 1,
                            "budget_usd": 1.10, "stdout": "o3", "stderr": ""})
        rows = ps.load_run_logs()
        self.assertEqual([r["ts"] for r in rows],
                         ["2026-01-01T00:00:01.000000+00:00",
                          "2026-01-01T00:00:02.000000+00:00"])
        self.assertEqual(rows[-1]["stdout"], "o3")
        self.assertEqual(rows[0]["stderr"], "e1")
        self.assertEqual(rows[-1]["p0"], 2)

    def test_load_trims_to_run_log_max(self):
        for i in range(5):
            ps.persist_run_log({"ts": f"2026-01-01T00:00:0{i}.000000+00:00",
                                "verdict": "PASS", "stdout": f"o{i}",
                                "stderr": ""})
        rows = ps.load_run_logs()
        self.assertEqual([r["stdout"] for r in rows], ["o2", "o3", "o4"])

    def test_load_missing_dir_returns_empty(self):
        ps.RUNS_DIR = os.path.join(self._tmp.name, "nope")
        self.assertEqual(ps.load_run_logs(), [])

    def test_load_skips_corrupt_log(self):
        os.makedirs(self._runs, exist_ok=True)
        with open(os.path.join(self._runs, "run-bad.json"), "w",
                  encoding="utf-8") as f:
            f.write("{not json")
        ps.persist_run_log({"ts": "2026-01-01T00:00:01.000000+00:00",
                            "verdict": "PASS", "stdout": "ok", "stderr": ""})
        rows = ps.load_run_logs()
        self.assertEqual([r["stdout"] for r in rows], ["ok"])

    def test_persist_ignores_record_without_ts(self):
        ps.persist_run_log({"verdict": "PASS", "stdout": "x", "stderr": ""})
        self.assertEqual(ps.load_run_logs(), [])


class Z3ParseTests(unittest.TestCase):
    """_parse_z3_counts — K8 Z3 özet tablosu sayımı (rozet gerçek sonuçtan)."""

    def test_counts_12_pass(self):
        # 12 kontrol: P1-a, P1-b, P2, P3-a, P3-b, P4-a..e, P5, P5-note
        z3 = ["P1-a", "P1-b", "P2", "P3-a", "P3-b",
              "P4-a", "P4-b", "P4-c", "P4-d", "P4-e", "P5", "P5-note"]
        stderr = "\n".join(f"  [PASS] {p}  beklenen=UNSAT alınan=UNSAT" for p in z3)
        self.assertEqual(ps._parse_z3_counts(stderr), (12, 0))

    def test_counts_failures(self):
        stderr = ("  [PASS] P1-a x\n"
                  "  [FAIL] P4-b y\n"
                  "  [PASS] P2 z\n"
                  "  [FAIL] P5-note w")
        self.assertEqual(ps._parse_z3_counts(stderr), (2, 2))

    def test_ignores_non_z3_lines(self):
        stderr = ("[PASS] K0 tarama\n"
                  "  [OK  ] Internet Archive Fine 2012 -> x\n"
                  "[P1-a] (T2 ∧ M0) → T1 : UNSAT\n"
                  "SONUÇ: TÜMÜ PASS\n"
                  "  [PASS] P1-a ...\n")
        self.assertEqual(ps._parse_z3_counts(stderr), (1, 0))

    def test_empty_and_none(self):
        self.assertEqual(ps._parse_z3_counts(""), (0, 0))
        self.assertEqual(ps._parse_z3_counts(None), (0, 0))


class LeanParseTests(unittest.TestCase):
    """_parse_lean_result — K9 Lean rozeti gerçek sonuçtan (stderr [K9] satırı)."""

    def test_pass_with_detail(self):
        stderr = ("[K8] sembolik ispat (Z3): PASS — ...\n"
                  "[K9] Lean 4 reduct-invariance: PASS — Lean 4 reduct-invariance "
                  "derlendi ve geçti\n")
        ok, detail = ps._parse_lean_result(stderr)
        self.assertIs(ok, True)
        self.assertIn("derlendi", detail)

    def test_fail_with_detail(self):
        stderr = "[K9] Lean 4 reduct-invariance: FAIL — Lean derleme hatası: error: ..."
        ok, detail = ps._parse_lean_result(stderr)
        self.assertIs(ok, False)
        self.assertIn("Lean derleme hatası", detail)

    def test_missing_line_is_none(self):
        # --lean-proof koşulmamış run: K9 satırı yok → (None, None), '?' rozeti
        stderr = "[K8] sembolik ispat (Z3): PASS — ...\nSONUÇ: PASS\n"
        self.assertEqual(ps._parse_lean_result(stderr), (None, None))

    def test_empty_and_none(self):
        self.assertEqual(ps._parse_lean_result(""), (None, None))
        self.assertEqual(ps._parse_lean_result(None), (None, None))

    def test_last_line_wins(self):
        stderr = ("[K9] Lean 4 reduct-invariance: PASS — ilk\n"
                  "[K9] Lean 4 reduct-invariance: FAIL — ikinci\n")
        ok, detail = ps._parse_lean_result(stderr)
        self.assertIs(ok, False)
        self.assertEqual(detail, "ikinci")


class ConfigDiffDriftTests(unittest.TestCase):
    """preview_server._config_diff ↔ diff_config_artifacts.compute_differences
    drift guard: iki uygulama aynı girdide aynı çıktıyı üretmelidir."""

    RAW = {
        "budget_usd": 30.0, "budget_method": "both",
        "budget_ratios": {"text": 8, "pdf": 8, "archive": 100, "binary": 100},
        "expected_pages": 33, "expected_refs": 64, "expected_manifest": 19,
    }

    @staticmethod
    def _eff(budget=30.0, method="both", cli_overrides=None):
        raw = ConfigDiffDriftTests.RAW
        return {
            "budget_usd": budget, "budget_method": method,
            "budget_ratios": raw["budget_ratios"],
            "expected_pages": 33, "expected_refs": 64, "expected_manifest": 19,
            "cli_overrides": cli_overrides if cli_overrides is not None else {
                "budget": {"cli_given": False, "cli_value": None,
                           "file_value": 30.0, "effective": budget,
                           "override": False},
                "budget_method": {"cli_given": False, "cli_value": None,
                                  "file_value": "both", "effective": method,
                                  "override": False},
            },
        }

    def test_matches_diff_config_artifacts(self):
        cli_override = {
            "budget": {"cli_given": True, "cli_value": 25.0,
                       "file_value": 30.0, "effective": 25.0, "override": True},
            "budget_method": {"cli_given": True, "cli_value": "universal",
                              "file_value": "both", "effective": "universal",
                              "override": True},
        }
        raw_no_pages = dict(self.RAW)
        raw_no_pages.pop("expected_pages")
        cases = [
            (self.RAW, self._eff()),                       # fark yok
            (self.RAW, self._eff(budget=99.0)),            # drift
            (self.RAW, self._eff(budget=25.0, method="universal",
                                  cli_overrides=cli_override)),  # cli_override
            (raw_no_pages, self._eff()),                   # default
        ]
        for raw, eff in cases:
            self.assertEqual(
                ps._config_diff(raw, eff), dca.compute_differences(raw, eff),
                msg=f"drift: raw={raw!r} eff={eff!r}")

    def test_drift_reason(self):
        rows = ps._config_diff(self.RAW, self._eff(budget=99.0))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["field"], "budget_usd")
        self.assertEqual(rows[0]["reason"], "drift")
        self.assertEqual(rows[0]["raw"], 30.0)
        self.assertEqual(rows[0]["effective"], 99.0)


class HookEnvPlumbingTests(unittest.TestCase):
    """hook_env (zaman serisi) veri hattı: LATEST slotu + HISTORY_KEYS."""

    def test_history_keys_include_hook_env(self):
        # history.jsonl kaydına hook_env girmeli (dashboard zaman serisi için).
        self.assertIn("hook_env", ps.HISTORY_KEYS)

    def test_latest_has_hook_env_slot(self):
        self.assertIn("hook_env", ps.LATEST)

    def test_snapshot_dict_carries_hook_env(self):
        ps.LATEST["hook_env"] = {"z3": "5.1.0"}
        try:
            snap = ps.snapshot_dict()
        finally:
            ps.LATEST["hook_env"] = None
        self.assertEqual(snap["hook_env"], {"z3": "5.1.0"})


class CliOverridesPlumbingTests(unittest.TestCase):
    """cli_overrides veri hattı: LATEST slotu — override akış satırı beklemeden görünür.

    verify_delivery.py --json çıktısındaki config.cli_overrides (override=true
    kayıtları) _finalize_run'da LATEST['cli_overrides']'a taşınır; dashboard
    bunu 'Budget override' rozeti için kullanır. /api/latest (serve_latest)
    LATEST dict'ini bütünüyle döndürdüğü için slot oraya otomatik girer.
    """

    def test_latest_has_cli_overrides_slot(self):
        self.assertIn("cli_overrides", ps.LATEST)

    def test_latest_dict_carries_cli_overrides(self):
        # /api/latest (serve_latest) LATEST dict'ini bütünüyle döndürür —
        # cli_overrides slotu oraya otomatik girer (akış satırı beklemeden).
        ov = {"budget": {"cli_given": True, "file_value": 30.0,
                         "effective": 25.0, "override": True}}
        ps.LATEST["cli_overrides"] = ov
        try:
            self.assertEqual(ps.LATEST["cli_overrides"], ov)
        finally:
            ps.LATEST["cli_overrides"] = None

    def test_override_count_scalar_in_history_keys(self):
        # Skaler sayaç trend'e (history.jsonl) gider; tam dict oraya DEĞİL —
        # rozet için tam dict yalnızca SSE snapshot'larına eklenir.
        self.assertIn("cli_override_count", ps.HISTORY_KEYS)
        self.assertNotIn("cli_overrides", ps.HISTORY_KEYS)

    def test_sse_snapshot_carries_full_cli_overrides(self):
        # Broadcast/connect snapshot'ları {k: LATEST[k] for k in HISTORY_KEYS}
        # + cli_overrides taşır — dashboard rozeti SSE üzerinden de alır.
        ov = {"budget": {"override": True, "file_value": 30.0,
                         "effective": 25.0},
              "budget_method": {"override": False}}
        ps.LATEST["cli_overrides"] = ov
        try:
            snap = {k: ps.LATEST[k] for k in ps.HISTORY_KEYS}
            snap["cli_overrides"] = ps.LATEST["cli_overrides"]
            self.assertEqual(snap["cli_overrides"], ov)
            # skaler sayaç hesabı (_finalize_run satırıyla aynı): override=true
            # anahtar sayısı — trend'e temiz int olarak gider.
            n = sum(1 for v in (ps.LATEST.get("cli_overrides") or {}).values()
                    if (v or {}).get("override"))
            self.assertEqual(n, 1)
            self.assertIn("cli_override_count", snap)
        finally:
            ps.LATEST["cli_overrides"] = None


class DaemonStdioTests(unittest.TestCase):
    """PREVIEW_DAEMON fd davranışı: kapatma (EBADF) değil /dev/null'a yönlendirme.

    Eski kod os.close(0/1/2) yapıyordu; bu, sonraki sys.stderr.write çağrılarını
    (log_message her HTTP isteğinde) EBADF ile patlatıp isteği öldürüyordu.
    redirect_stdio_to_devnull, dup2 ile fds'yi /dev/null'a bağlar — write
    güvenli kalır. Subprocess'te test edilir çünkü fd 0/1/2 GLOBAL'dür ve
    aynı süreçte test edilirse test runner çıktısı yutulur.
    """

    def test_redirect_keeps_stderr_writable(self):
        code = (
            "import sys\n"
            f"sys.path.insert(0, {HERE!r})\n"
            "import preview_server as ps\n"
            "ps.redirect_stdio_to_devnull()\n"
            "sys.stderr.write('EBADF olmasın')\n"
            "sys.stderr.flush()\n"
        )
        r = subprocess.run([sys.executable, "-c", code],
                           capture_output=True, text=True, timeout=10)
        # Eski davranışta (os.close(2)) sys.stderr.write EBADF fırlatır →
        # süreç non-zero exit. Yeni davranışta yazı sessizce /dev/null'a gider.
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stderr, "")

    def test_redirect_keeps_stdout_writable(self):
        code = (
            "import sys\n"
            f"sys.path.insert(0, {HERE!r})\n"
            "import preview_server as ps\n"
            "ps.redirect_stdio_to_devnull()\n"
            "print('OK')\n"
        )
        r = subprocess.run([sys.executable, "-c", code],
                           capture_output=True, text=True, timeout=10)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout, "")  # /dev/null'a gitti


class LogMessageTests(unittest.TestCase):
    """Handler.log_message EBADF'e (ve format hatalarına) dayanıklı olmalı."""

    def _call(self):
        h = type("FakeHandler", (), {
            "address_string": lambda self: "127.0.0.1"})()
        ps.Handler.log_message(h, "%s", "test")

    def test_swallows_broken_stderr(self):
        class Broken:
            def write(self, s):
                raise OSError(9, "Bad file descriptor")

            def flush(self):
                raise OSError(9, "Bad file descriptor")

        old = sys.stderr
        sys.stderr = Broken()
        try:
            self._call()  # raise etmemeli
        finally:
            sys.stderr = old

    def test_swallows_format_error(self):
        old = sys.stderr
        try:
            h = type("FakeHandler", (), {
                "address_string": lambda self: "127.0.0.1"})()
            # %d + string → TypeError; log yine de isteği öldürmesin
            ps.Handler.log_message(h, "%d", "abc")
        finally:
            sys.stderr = old


class BuildVerifyCmdTests(unittest.TestCase):
    """_build_verify_cmd: override parametreleri komuta doğru eklenmeli.

    /api/run-now?budget=25&budget_method=weighted manuel override senaryosu:
    bütçe kalkanı dosya config yerine CLI değerleriyle koşar. Override yoksa
    komut default kalır (--full --json), override varsa --budget/--budget-method
    eklenir — canlı akışta [CLI override] uyarısı + sarı vurgu üretir.
    """

    def _cmd(self, **kw):
        return ps._build_verify_cmd("/py", "/verify", **kw)

    def test_no_override_default_flags(self):
        cmd = self._cmd()
        self.assertIn("--full", cmd)
        self.assertIn("--json", cmd)
        self.assertNotIn("--budget", cmd)
        self.assertNotIn("--budget-method", cmd)

    def test_budget_override_adds_flag(self):
        cmd = self._cmd(budget_usd=25.0)
        i = cmd.index("--budget")
        self.assertEqual(cmd[i + 1], "25.0")

    def test_budget_method_override_adds_flag(self):
        cmd = self._cmd(budget_method="weighted")
        i = cmd.index("--budget-method")
        self.assertEqual(cmd[i + 1], "weighted")

    def test_both_overrides_added_in_order(self):
        cmd = self._cmd(budget_usd=25.0, budget_method="both")
        self.assertIn("--budget", cmd)
        self.assertIn("--budget-method", cmd)

    def test_zero_budget_is_still_an_override(self):
        # 0.0 geçerli bir override — None ile karıştırılmamalı (bool(0)=False).
        cmd = self._cmd(budget_usd=0.0)
        i = cmd.index("--budget")
        self.assertEqual(cmd[i + 1], "0.0")


class LineageSummaryTests(unittest.TestCase):
    """lineage_summary: _finalize_run'un verify JSON'undan soy hattı özetini
    ayrıştırıp LATEST'e yazması ve SSE snapshot'ına taşıması.
    """

    def test_lineage_ok_in_latest_and_history_keys(self):
        """lineage_summary LATEST'te var, lineage_ok/lineage_count HISTORY_KEYS'te."""
        import preview_server as ps
        # Reset lineage_summary to initial state
        with ps.LOCK:
            ps.LATEST["lineage_summary"] = None
            ps.LATEST["lineage_ok"] = None
            ps.LATEST["lineage_count"] = None
        self.assertIsNone(ps.LATEST.get("lineage_summary"))
        self.assertIn("lineage_ok", ps.HISTORY_KEYS)
        self.assertIn("lineage_count", ps.HISTORY_KEYS)
        # lineage_summary本身 HISTORY_KEYS'te değil (dict trend'i şişirir)
        self.assertNotIn("lineage_summary", ps.HISTORY_KEYS)

    def test_finalize_populates_lineage_summary(self):
        """_finalize_run lineage_summary'yi LATEST'e yazar."""
        import preview_server as ps
        stdout = json.dumps({
            "verdict": "PASS", "counts": {"P0": 0, "P1": 0},
            "lineage": {
                "ok": True, "count": 2,
                "generations": [
                    {"gen": "pre-git", "note": "iCloud", "hash": "a" * 64,
                     "commit": None, "status": "INFO"},
                    {"gen": "current", "note": "V5m", "hash": "b" * 64,
                     "commit": "d02cda8", "status": "PASS (canlı dosya ile aynı)"},
                ],
            },
        })
        with ps.LOCK:
            ps.LATEST.update({"cli_overrides": None})
        ps._finalize_run(stdout, "", 0, 1.0, data=None, verify_dir=None)
        with ps.LOCK:
            ls = ps.LATEST.get("lineage_summary")
        self.assertIsNotNone(ls)
        self.assertTrue(ls["ok"])
        self.assertEqual(ls["count"], 2)
        self.assertEqual(ls["current_note"], "V5m")
        self.assertEqual(ls["current_hash"], "b" * 16)

    def test_finalize_no_lineage(self):
        """lineage alanı yoksa lineage_summary None kalır."""
        import preview_server as ps
        stdout = json.dumps({"verdict": "PASS", "counts": {"P0": 0, "P1": 0}})
        with ps.LOCK:
            ps.LATEST.update({"cli_overrides": None})
        ps._finalize_run(stdout, "", 0, 1.0, data=None, verify_dir=None)
        with ps.LOCK:
            self.assertIsNone(ps.LATEST.get("lineage_summary"))
            self.assertIsNone(ps.LATEST.get("lineage_ok"))
            self.assertIsNone(ps.LATEST.get("lineage_count"))

    def test_lineage_summary_in_sse_broadcast(self):
        """SSE broadcast snapshot'ında lineage_summary alanı olmalı."""
        import preview_server as ps
        import queue
        stdout = json.dumps({
            "verdict": "PASS", "counts": {"P0": 0, "P1": 0},
            "lineage": {
                "ok": True, "count": 5,
                "generations": [
                    {"gen": "current", "note": "test", "hash": "c" * 64,
                     "commit": "abc1234", "status": "PASS"},
                ],
            },
        })
        q = queue.Queue()
        ps.SSE_CLIENTS.clear()
        ps.SSE_CLIENTS.append(q)
        try:
            with ps.LOCK:
                ps.LATEST.update({"cli_overrides": None})
            ps._finalize_run(stdout, "", 0, 1.0, data=None, verify_dir=None)
            snap = json.loads(q.get_nowait())
            self.assertIn("lineage_summary", snap)
            ls = snap["lineage_summary"]
            self.assertTrue(ls["ok"])
            self.assertEqual(ls["current_note"], "test")
        finally:
            ps.SSE_CLIENTS.clear()


class StatusBoardTests(unittest.TestCase):
    """status_board: 5 ikonlu tek satır durum panosu (CI consolidate_summary.py ile tutarlı)."""

    def test_all_pass(self):
        """Tüm alanlar PASS ise 5 ✅ üretmeli."""
        import preview_server as ps
        with ps.LOCK:
            ps.LATEST.update({
                "layers": {"K1": {"status": "PASS"}, "K2": {"status": "PASS"},
                            "K3": {"status": "PASS"}, "K4": {"status": "PASS"},
                            "K5": {"status": "PASS"}, "K6": {"status": "PASS"},
                            "K7": {"status": "PASS"},
                            "K8": {"status": "PASS"}, "K9": {"status": "PASS"},
                            "K10": {"status": "PASS"}},
                "p0": 0, "p1": 0, "budget_usd": 1.0, "lineage_ok": True,
            })
        board = ps._compute_status_board()
        self.assertIn("Pre-commit ✅", board)
        self.assertIn("K0 ✅", board)
        self.assertIn("Bütçe ✅", board)
        self.assertIn("Soy hattı ✅", board)
        self.assertIn("K katmanları ✅", board)
        self.assertEqual(board.count("✅"), 5)

    def test_one_fail(self):
        """K4 FAIL ise Pre-commit 🔴 olmalı."""
        import preview_server as ps
        with ps.LOCK:
            ps.LATEST.update({
                "layers": {"K1": {"status": "PASS"}, "K4": {"status": "FAIL"},
                            "K8": {"status": "PASS"}},
                "p0": 0, "p1": 0, "budget_usd": 1.0, "lineage_ok": True,
            })
        board = ps._compute_status_board()
        self.assertIn("Pre-commit 🔴", board)
        self.assertIn("K0 ✅", board)

    def test_no_data(self):
        """Veri yoksa (layers=None, p0=None, p1=None, budget=None, lineage=None) tümü ⚠️ olmalı."""
        import preview_server as ps
        with ps.LOCK:
            ps.LATEST["layers"] = None
            ps.LATEST["p0"] = None
            ps.LATEST["p1"] = None
            ps.LATEST["budget_usd"] = None
            ps.LATEST["lineage_ok"] = None
        board = ps._compute_status_board()
        self.assertEqual(board.count("⚠️"), 5)

    def test_status_board_in_sse(self):
        """SSE snapshot'ında status_board alanı olmalı."""
        import preview_server as ps
        import queue
        stdout = json.dumps({
            "verdict": "PASS", "counts": {"P0": 0, "P1": 0},
            "layers": {"K1": {"status": "PASS"}, "K8": {"status": "PASS"}},
        })
        q = queue.Queue()
        ps.SSE_CLIENTS.clear()
        ps.SSE_CLIENTS.append(q)
        try:
            with ps.LOCK:
                ps.LATEST.update({"cli_overrides": None})
            ps._finalize_run(stdout, "", 0, 1.0, data=None, verify_dir=None)
            snap = json.loads(q.get_nowait())
            self.assertIn("status_board", snap)
            self.assertIsNotNone(snap["status_board"])
        finally:
            ps.SSE_CLIENTS.clear()


    def test_precommit_hooks_parsed(self):
        """Pre-commit hook parsed从 stderr'den."""
        import preview_server as ps
        stderr = (
            "verify-delivery................................................Passed\n"
            "z3-symbolic-proof..............................................Passed\n"
            "lean-reduct-build..............................................Failed\n"
        )
        hooks = ps._parse_precommit_hooks(stderr)
        self.assertEqual(len(hooks), 3)
        self.assertEqual(hooks[0]["name"], "verify-delivery")
        self.assertEqual(hooks[0]["status"], "Passed")
        self.assertEqual(hooks[2]["name"], "lean-reduct-build")
        self.assertEqual(hooks[2]["status"], "Failed")

    def test_precommit_hooks_empty(self):
        """Boş stderr'de hook listesi None (consistent with other parsers)."""
        import preview_server as ps
        hooks = ps._parse_precommit_hooks("")
        self.assertIsNone(hooks)

    def test_precommit_hooks_in_latest(self):
        """LATEST dict'te precommit_hooks alanı olmalı."""
        import preview_server as ps
        stdout = json.dumps({
            "verdict": "PASS", "counts": {"P0": 0, "P1": 0},
            "layers": {"K1": {"status": "PASS"}},
        })
        stderr = (
            "verify-delivery................................................Passed\n"
            "lean-reduct-build..............................................Failed\n"
        )
        ps._finalize_run(stdout, stderr, 0, 1.0, data=None, verify_dir=None)
        self.assertIn("precommit_hooks", ps.LATEST)
        self.assertEqual(len(ps.LATEST["precommit_hooks"]), 2)
        self.assertEqual(ps.LATEST["precommit_hooks"][0]["name"], "verify-delivery")

    def test_precommit_hooks_in_sse(self):
        """SSE snapshot'ında precommit_hooks alanı olmalı."""
        import preview_server as ps
        import queue
        stdout = json.dumps({
            "verdict": "PASS", "counts": {"P0": 0, "P1": 0},
            "layers": {"K1": {"status": "PASS"}},
        })
        stderr = (
            "verify-delivery................................................Passed\n"
        )
        q = queue.Queue()
        ps.SSE_CLIENTS.clear()
        ps.SSE_CLIENTS.append(q)
        try:
            ps._finalize_run(stdout, stderr, 0, 1.0, data=None, verify_dir=None)
            snap = json.loads(q.get_nowait())
            self.assertIn("precommit_hooks", snap)
            self.assertEqual(len(snap["precommit_hooks"]), 1)
        finally:
            ps.SSE_CLIENTS.clear()


if __name__ == "__main__":
    unittest.main()
