"""trend_db_sync — history.jsonl → Neon `trend_runs` otomatik senkron sözleşmesi.

Test edilen YÜZEY (hepsi kimlik bilgisi/node/DB olmadan koşar):

1. `run_sync` sonuç sözlüğü: state ∈ {synced, up-to-date, skipped, failed},
   `ok` yalnız gerçek yüklemede true, `reason` atlamayı GİZLEMEZ.
2. Sayaç ayrıştırma: `(N eklendi)` → N; desen yoksa None (uydurma yok).
3. `HistorySync`: debounce birleştirmesi (N append → 1 yükleme), değişmeyen
   digest'te alt süreç yok, durum dosyası atomik JSON, hata daemon'ı düşürmez.
4. `provision_loader`: cache dışına kopyalamayı REDDEDER (fail-closed),
   `scripts/load.ts` yoksa kaynağı reddeder, kopyada `.env` 0600 olur.
5. Daemon kablolaması (statik): persist_history → `TREND_SYNC.request`,
   `/api/trend-sync` rotası, mirror listelerinde modül.

Sahte yükleyici: `node_modules/.bin/tsx` yerine Python betiği konur ve
`node=sys.executable` verilir — yükleme komutu aynen produkisyon yolundan
(`build_command`) geçer, alt süreç gerçekten spawn edilir.
"""
import contextlib
import hashlib
import io
import json
import os
import pathlib
import plistlib
import re
import stat
import sys
import tempfile
import time
import unittest
from unittest import mock

HERE = pathlib.Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1] if HERE.name == "CIKTI" else HERE.parents[2]
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import trend_db_sync as tsync  # noqa: E402
import preview_server as ps  # noqa: E402


def _write_fake_loader(root, *, inserted=1, exit_code=0, sleep=0.0,
                       stdout=None, stderr=None):
    """Geçici `apps/trend-db` benzeri ağaç: scripts/load.ts + .bin/tsx."""
    root = pathlib.Path(root)
    (root / "scripts").mkdir(parents=True, exist_ok=True)
    (root / "scripts" / "load.ts").write_text("// sahte yükleyici\n",
                                              encoding="utf-8")
    bin_dir = root / "node_modules" / ".bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    lines = ["#!%s" % sys.executable, "import sys, time"]
    if sleep:
        lines.append("time.sleep(%r)" % sleep)
    if stderr:
        lines.append("sys.stderr.write(%r)" % stderr)
    out = stdout if stdout is not None else (
        "kaynak: sahte (1 satır, sha256 abc)\n"
        "bitti: 1 kayıt işlendi (%d eklendi), 0 atlandı\n" % inserted)
    lines.append("sys.stdout.write(%r)" % out)
    lines.append("sys.exit(%d)" % exit_code)
    tsx = bin_dir / "tsx"
    tsx.write_text("\n".join(lines) + "\n", encoding="utf-8")
    tsx.chmod(0o755)
    # .env: DATABASE_URL yalnız VARLIĞI kontrol edilir (değer okunmaz).
    (root / ".env").write_text("DATABASE_URL=postgres://sahte\n",
                               encoding="utf-8")
    return root


class TempWorkspace(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = pathlib.Path(self._tmp.name)
        self.history = self.tmp / "history.jsonl"
        self.history.write_text('{"ts": "2026-01-01T00:00:00Z"}\n',
                                encoding="utf-8")
        self.env = {"PATH": os.environ.get("PATH", "")}
        self._orig_cache = tsync.CACHE_LOADER_DIR
        self._orig_desktop = tsync._DESKTOP_LOADER_DIR
        # Testler geçici dizinde koşar: gerçek TCC önekleri (Desktop/…) bir
        # testin cache'e yazmasına yol açmasın; TCC testleri kendi önekini kurar.
        self._orig_tcc = tsync._TCC_RISK_PREFIXES
        tsync.CACHE_LOADER_DIR = str(self.tmp / "cache-loader")
        tsync._DESKTOP_LOADER_DIR = str(self.tmp / "desktop-loader")
        tsync._TCC_RISK_PREFIXES = ()

    def tearDown(self):
        tsync.CACHE_LOADER_DIR = self._orig_cache
        tsync._DESKTOP_LOADER_DIR = self._orig_desktop
        tsync._TCC_RISK_PREFIXES = self._orig_tcc
        self._tmp.cleanup()


class TestRunSync(TempWorkspace):
    def test_success_reports_inserted_count(self):
        loader = _write_fake_loader(self.tmp / "loader", inserted=3)
        result = tsync.run_sync(str(self.history), loader_dir=str(loader),
                                node=sys.executable, env=self.env)
        self.assertEqual(result["state"], "synced")
        self.assertTrue(result["ok"])
        self.assertEqual(result["inserted"], 3)
        self.assertEqual(result["history_sha256"],
                         tsync.history_digest(str(self.history)))
        self.assertIsInstance(result["duration_ms"], int)
        self.assertIn("bitti:", result["stdout_tail"])

    def test_zero_inserted_is_up_to_date_not_pass(self):
        loader = _write_fake_loader(self.tmp / "loader", inserted=0)
        result = tsync.run_sync(str(self.history), loader_dir=str(loader),
                                node=sys.executable, env=self.env)
        self.assertEqual(result["state"], "up-to-date")
        self.assertTrue(result["ok"])
        self.assertEqual(result["inserted"], 0)

    def test_nonzero_exit_is_failed_and_keeps_stderr(self):
        loader = _write_fake_loader(self.tmp / "loader", exit_code=1,
                                    stderr="bağlantı reddedildi\n")
        result = tsync.run_sync(str(self.history), loader_dir=str(loader),
                                node=sys.executable, env=self.env)
        self.assertEqual(result["state"], "failed")
        self.assertFalse(result["ok"])
        self.assertTrue(result["reason"].startswith("exit-1"))
        self.assertIn("bağlantı reddedildi", result["stderr_tail"])

    def test_timeout_is_failed_not_exception(self):
        loader = _write_fake_loader(self.tmp / "loader", sleep=2.0)
        result = tsync.run_sync(str(self.history), loader_dir=str(loader),
                                node=sys.executable, timeout=0.3,
                                env=self.env)
        self.assertEqual(result["state"], "failed")
        self.assertEqual(result["reason"], "timeout")
        self.assertFalse(result["ok"])

    def test_missing_history_is_skipped(self):
        result = tsync.run_sync(str(self.tmp / "yok.jsonl"),
                                env=self.env)
        self.assertEqual(result["state"], "skipped")
        self.assertEqual(result["reason"], "history-missing")
        self.assertFalse(result["ok"])

    def test_missing_database_url_is_visible_skip(self):
        loader = _write_fake_loader(self.tmp / "loader")
        (loader / ".env").unlink()
        result = tsync.run_sync(str(self.history), loader_dir=str(loader),
                                node=sys.executable, env=self.env)
        self.assertEqual(result["state"], "skipped")
        self.assertEqual(result["reason"], "no-database-url")
        self.assertFalse(result["ok"])

    def test_missing_loader_is_visible_skip(self):
        result = tsync.run_sync(str(self.history), repo_root=str(self.tmp),
                                env=self.env)
        self.assertEqual(result["state"], "skipped")
        self.assertEqual(result["reason"], "loader-missing")

    def test_unreadable_loader_is_distinguished_from_missing(self):
        loader = self.tmp / "blocked-apps" / "apps" / "trend-db"
        (loader / "scripts").mkdir(parents=True)
        script = loader / "scripts" / "load.ts"
        script.write_text("x", encoding="utf-8")
        script.chmod(0o000)
        result = tsync.run_sync(str(self.history), repo_root=str(
            self.tmp / "blocked-apps"), env=self.env)
        script.chmod(0o644)
        self.assertEqual(result["state"], "skipped")
        self.assertEqual(result["reason"], "loader-unreadable")

    def test_runner_missing_when_no_tsx_and_no_npm(self):
        loader = _write_fake_loader(self.tmp / "loader")
        (loader / "node_modules" / ".bin" / "tsx").unlink()
        with mock.patch.object(tsync.shutil, "which", return_value=None):
            result = tsync.run_sync(str(self.history),
                                    loader_dir=str(loader), env=self.env)
        self.assertEqual(result["state"], "skipped")
        self.assertEqual(result["reason"], "runner-missing")

    def test_unparsed_output_is_warning_not_silent_zero(self):
        loader = _write_fake_loader(self.tmp / "loader", stdout="bitti\n")
        result = tsync.run_sync(str(self.history), loader_dir=str(loader),
                                node=sys.executable, env=self.env)
        self.assertEqual(result["state"], "synced")
        self.assertTrue(result["ok"])
        self.assertIsNone(result["inserted"])
        self.assertEqual(result["reason"], "unparsed-output")


class TestParseInserted(unittest.TestCase):
    def test_parses_last_summary_line(self):
        out = ("bitti: 100 kayıt işlendi (7 eklendi), 93 atlandı\n")
        self.assertEqual(tsync.parse_inserted(out), 7)

    def test_no_match_returns_none(self):
        self.assertIsNone(tsync.parse_inserted(""))

    def test_dry_run_prose_does_not_fake_count(self):
        # Dry-run satırı eklenecek sayısını "en çok" olarak verir; ayrıştırıcı
        # onu YÜKLENEN sayı sanmamalı (desen "(N eklendi)" değil).
        self.assertIsNone(tsync.parse_inserted(
            "[DRY-RUN] eklenecek (en çok): 7 · atlanacak (en az): 3\n"))


class TestHistorySync(TempWorkspace):
    def _wait_status(self, sync, predicate, timeout=5.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            status = sync.status()
            if predicate(status):
                return status
            time.sleep(0.02)
        self.fail("durum beklenen koşula ulaşmadı: %r" % (sync.status(),))

    def test_debounce_coalesces_burst_into_one_run(self):
        calls = []

        def runner(**kwargs):
            calls.append(kwargs["history_path"])
            return {"state": "synced", "ok": True, "ts": "t",
                    "inserted": 1, "reason": None}

        sync = tsync.HistorySync(str(self.history),
                                 preview_dir=str(self.tmp),
                                 debounce=0.15, runner=runner,
                                 env=self.env)
        sync.start()
        try:
            for i in range(5):
                sync.request("d%d" % i)
                time.sleep(0.01)
            self._wait_status(sync, lambda s: s.get("state") == "synced")
        finally:
            sync.stop()
        self.assertEqual(len(calls), 1, "debounce birleştirmesi çalışmadı")
        self.assertEqual(sync.status()["runs"], 1)

    def test_unchanged_digest_does_not_spawn_runner(self):
        calls = []

        def runner(**kwargs):
            calls.append(1)
            return {"state": "up-to-date", "ok": True, "ts": "t"}

        sync = tsync.HistorySync(str(self.history),
                                 preview_dir=str(self.tmp),
                                 debounce=0.05, runner=runner, env=self.env)
        sync.start()
        try:
            sync.request("sabit")
            self._wait_status(sync, lambda s: s.get("state") == "up-to-date")
            # Aynı digest ikinci kez: ne koşmalı ne de state bozulmalı.
            self.assertFalse(sync.request("sabit"))
            time.sleep(0.2)
        finally:
            sync.stop()
        self.assertEqual(len(calls), 1)

    def test_status_file_is_written_and_failure_stays_not_ok(self):
        def runner(**kwargs):
            return {"state": "failed", "ok": False, "ts": "t",
                    "reason": "exit-1: BAĞLANTI", "inserted": None}

        sync = tsync.HistorySync(str(self.history),
                                 preview_dir=str(self.tmp),
                                 debounce=0.05, runner=runner, env=self.env)
        sync.start()
        try:
            sync.request("d")
            self._wait_status(sync, lambda s: s.get("state") == "failed")
        finally:
            sync.stop()
        on_disk = tsync.read_status(str(self.tmp / tsync.STATUS_FILE_NAME))
        self.assertIsNotNone(on_disk)
        self.assertFalse(on_disk["ok"])
        self.assertEqual(on_disk["state"], "failed")
        self.assertIsNone(on_disk["last_synced_sha256"])

    def test_success_persists_last_synced_digest_for_restart(self):
        def runner(**kwargs):
            return {"state": "synced", "ok": True, "ts": "2026-01-01T00:00:00Z",
                    "inserted": 2}

        sync = tsync.HistorySync(str(self.history),
                                 preview_dir=str(self.tmp),
                                 debounce=0.05, runner=runner, env=self.env)
        sync.start()
        try:
            sync.request("abc123")
            self._wait_status(sync, lambda s: s.get("state") == "synced")
        finally:
            sync.stop()
        revived = tsync.HistorySync(str(self.history),
                                    preview_dir=str(self.tmp),
                                    debounce=0.05, runner=runner,
                                    env=self.env)
        self.assertEqual(revived.status().get("last_synced_sha256"), "abc123")

    def test_failed_same_digest_is_not_retried_in_a_tight_loop(self):
        calls = []

        def runner(**kwargs):
            calls.append(1)
            return {"state": "failed", "ok": False, "ts": "t",
                    "reason": "exit-1: BAĞLANTI"}

        sync = tsync.HistorySync(str(self.history),
                                 preview_dir=str(self.tmp),
                                 debounce=0.05, runner=runner, env=self.env)
        sync.start()
        try:
            self.assertTrue(sync.request("ayni"))
            self._wait_status(sync, lambda s: s.get("state") == "failed")
            # watch modu aynı digest'i her saniye sorar; tekrar denememeli.
            self.assertFalse(sync.request("ayni"))
            time.sleep(0.2)
            # Yeni bir koşum (yeni digest) hâlâ denenir.
            self.assertTrue(sync.request("yeni"))
            self._wait_status(sync, lambda s: s.get("runs") == 2)
        finally:
            sync.stop()
        self.assertEqual(len(calls), 2)

    def test_disabled_worker_never_requests(self):
        sync = tsync.HistorySync(str(self.history),
                                 preview_dir=str(self.tmp), enabled=False,
                                 env=self.env)
        self.assertFalse(sync.request("d"))
        self.assertFalse(sync.start())
        self.assertEqual(sync.status()["state"], "disabled")


class TestProvision(unittest.TestCase):
    def test_refuses_destination_outside_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = _write_fake_loader(pathlib.Path(tmp) / "src")
            result = tsync.provision_loader(str(src),
                                            dst_dir=os.path.join(tmp, "out"))
            self.assertFalse(result["ok"])
            self.assertEqual(result["reason"], "destination-outside-cache")
            self.assertFalse(os.path.exists(os.path.join(tmp, "out",
                                                         "scripts")))

    def test_refuses_source_without_loader_script(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = tsync.provision_loader(tmp, dst_dir=os.path.join(
                tmp, "out"), allow_outside=True)
            self.assertFalse(result["ok"])
            self.assertEqual(result["reason"], "source-not-loader")

    def test_copies_loader_and_tightens_env_permissions(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = _write_fake_loader(pathlib.Path(tmp) / "src")
            dst = pathlib.Path(tmp) / "dst"
            result = tsync.provision_loader(str(src), dst_dir=str(dst),
                                            allow_outside=True)
            self.assertTrue(result["ok"], result)
            self.assertTrue((dst / "scripts" / "load.ts").is_file())
            self.assertTrue((dst / "node_modules" / ".bin" / "tsx").is_file())
            mode = stat.S_IMODE(os.stat(dst / ".env").st_mode)
            self.assertEqual(mode, 0o600)


class TestDaemonWiring(unittest.TestCase):
    """Statik kablolama: daemon'ın gerçekten tetiklediği yol."""

    def setUp(self):
        self.src = (HERE / "preview_server.py").read_text(encoding="utf-8")

    def test_persist_history_notifies_sync_after_sidecar(self):
        m = re.search(r"def persist_history\(rec\):(.*?)\ndef ", self.src, re.S)
        self.assertIsNotNone(m)
        body = m.group(1)
        self.assertIn("TREND_SYNC.request(digest)", body)
        # Sıra sözleşmesi: sidecar digest'i yazıldıktan SONRA bildirilir.
        self.assertLess(body.index("history_sidecar_sha256"),
                        body.index("TREND_SYNC.request(digest)"))

    def test_route_registered_in_rebinding_gate_and_router(self):
        self.assertIn("trend_sync", ps._API_GET_ROUTES)
        self.assertEqual(ps._route("/api/trend-sync"), "trend_sync")
        self.assertIn('route == "trend_sync"', self.src)

    def test_snapshot_only_mode_does_not_start_sync(self):
        # Sentetik replay koşumları canlı arşive yazılmamalı.
        self.assertIn("if not args.no_verify and _trend_db_sync is not None",
                      self.src)

    def test_import_failure_is_visible_not_silent(self):
        self.assertIn('"reason": "import-error"', self.src)

    def test_persist_history_really_notifies_with_written_digest(self):
        class Recorder:
            def __init__(self):
                self.digests = []

            def request(self, digest=None):
                self.digests.append(digest)
                return True

        orig_history, orig_sync = ps.HISTORY_PATH, ps.TREND_SYNC
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "history.jsonl")
            recorder = Recorder()
            ps.HISTORY_PATH, ps.TREND_SYNC = path, recorder
            try:
                ps.persist_history({"ts": "2026-01-01T00:00:00Z",
                                    "verdict": "PASS"})
            finally:
                ps.HISTORY_PATH, ps.TREND_SYNC = orig_history, orig_sync
            with open(path, encoding="utf-8") as f:
                expected = hashlib.sha256(f.read().encode("utf-8")).hexdigest()
        self.assertEqual(recorder.digests, [expected])


class TestTrendSyncRoute(unittest.TestCase):
    """`/api/trend-sync` gövdesi: durum her zaman dolu, "yüklenmedi" PASS değil."""

    class _Handler:
        def __init__(self):
            self.sent = []

        def _send(self, status, body,
                  content_type="text/plain; charset=utf-8", extra_headers=None):
            self.sent.append((status, body, content_type))

    def _call(self):
        handler = self._Handler()
        ps.Handler.serve_trend_sync(handler)
        self.assertEqual(len(handler.sent), 1)
        status, body, content_type = handler.sent[0]
        self.assertEqual(status, 200)
        self.assertIn("application/json", content_type)
        return json.loads(body)

    def test_worker_status_is_served_as_json(self):
        class FakeSync:
            def status(self):
                return {"state": "synced", "ok": True, "inserted": 2}

        orig = ps.TREND_SYNC
        ps.TREND_SYNC = FakeSync()
        try:
            payload = self._call()
        finally:
            ps.TREND_SYNC = orig
        self.assertEqual(payload, {"state": "synced", "ok": True,
                                   "inserted": 2})

    def test_no_worker_is_disabled_with_reason(self):
        orig_sync, orig_err = ps.TREND_SYNC, ps.TREND_SYNC_IMPORT_ERROR
        ps.TREND_SYNC, ps.TREND_SYNC_IMPORT_ERROR = None, None
        try:
            payload = self._call()
        finally:
            ps.TREND_SYNC, ps.TREND_SYNC_IMPORT_ERROR = orig_sync, orig_err
        self.assertEqual(payload["state"], "disabled")
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["reason"], "sync-not-started")

    def test_import_error_is_reported_as_failure(self):
        orig_sync, orig_err = ps.TREND_SYNC, ps.TREND_SYNC_IMPORT_ERROR
        ps.TREND_SYNC, ps.TREND_SYNC_IMPORT_ERROR = None, "ImportError: yok"
        try:
            payload = self._call()
        finally:
            ps.TREND_SYNC, ps.TREND_SYNC_IMPORT_ERROR = orig_sync, orig_err
        self.assertEqual(payload["state"], "failed")
        self.assertEqual(payload["reason"], "import-error")
        self.assertIn("ImportError", payload["detail"])


class TestMirrorLists(unittest.TestCase):
    """Mirror'da eksik modül = launchd daemon'ında import hatası."""

    def test_preview_mirror_copies_sync_module(self):
        sh = (HERE / "sync_verify_mirror.sh").read_text(encoding="utf-8")
        self.assertIn('"trend_db_sync.py|trend_db_sync.py"', sh)

    def test_mirror_coverage_expects_sync_module(self):
        cov = (HERE / "check_mirror_coverage.py").read_text(encoding="utf-8")
        self.assertIn('"trend_db_sync.py"', cov)


def _write_fake_launchctl(root, *, bootstrap_rc=0, loaded_before=False):
    """Sahte `launchctl`: çağrıları JSONL'e yazar, yüklü durumu marker'da tutar.

    Gerçek launchd'a DOKUNMAZ (test makinesinde agent kurulmaz); `print`
    yalnız marker varsa rc=0 döner — yani "yüklendi mi?" gerçekten ölçülür,
    sabit 0 dönen bir sahte kapı sözleşmeyi vacuous yapardı.
    """
    root = pathlib.Path(root)
    root.mkdir(parents=True, exist_ok=True)
    log = root / "launchctl.jsonl"
    marker = root / "loaded"
    if loaded_before:
        marker.write_text("", encoding="utf-8")
    body = (
        "#!{py}\n"
        "import json, os, sys\n"
        "args = sys.argv[1:]\n"
        "with open({log!r}, 'a', encoding='utf-8') as f:\n"
        "    f.write(json.dumps(args) + '\\n')\n"
        "marker = {marker!r}\n"
        "if args and args[0] == 'print':\n"
        "    sys.exit(0 if os.path.exists(marker) else 1)\n"
        "if args and args[0] == 'bootstrap':\n"
        "    if {rc} == 0:\n"
        "        open(marker, 'w').close()\n"
        "    sys.exit({rc})\n"
        "if args and args[0] == 'bootout':\n"
        "    if os.path.exists(marker):\n"
        "        os.remove(marker)\n"
        "        sys.exit(0)\n"
        "    sys.exit(1)\n"
        "sys.exit(0)\n"
    )
    script = root / "launchctl"
    script.write_text(body.format(py=sys.executable, log=str(log),
                                  marker=str(marker), rc=bootstrap_rc),
                      encoding="utf-8")
    script.chmod(0o755)
    return script, log, marker


def _launchctl_calls(log):
    if not pathlib.Path(log).exists():
        return []
    return [json.loads(line) for line in
            pathlib.Path(log).read_text(encoding="utf-8").splitlines() if line.strip()]


class TestSchedule(TempWorkspace):
    """Zamanlanmış adım: plist sözleşmesi + launchctl fail-closed yolları."""

    def _setup(self, *, bootstrap_rc=0, loaded_before=False):
        loader = _write_fake_loader(self.tmp / "loader")
        agents = self.tmp / "LaunchAgents"
        script, log, marker = _write_fake_launchctl(
            self.tmp / "bin", bootstrap_rc=bootstrap_rc,
            loaded_before=loaded_before)
        env = {"PATH": os.environ.get("PATH", ""),
               tsync.ENV_LAUNCHCTL: str(script)}
        return loader, agents, env, log, marker

    def test_plist_watches_history_and_has_start_interval(self):
        loader, agents, env, _log, _marker = self._setup()
        result = tsync.install_schedule(str(self.history), str(loader),
                                        str(agents), env=env,
                                        script=str(HERE / "trend_db_sync.py"))
        self.assertTrue(result["ok"], result)
        self.assertTrue(result["loaded"], result)
        with open(result["plist"], "rb") as f:
            data = plistlib.load(f)
        self.assertEqual(data["Label"], tsync.SCHEDULE_LABEL)
        self.assertEqual(data["WatchPaths"], [str(self.history)])
        self.assertEqual(data["StartInterval"], tsync.SCHEDULE_INTERVAL_SECONDS)
        self.assertEqual(data["ThrottleInterval"],
                         tsync.SCHEDULE_THROTTLE_SECONDS)
        self.assertTrue(data["RunAtLoad"])
        argv = data["ProgramArguments"]
        self.assertIn("--once", argv)
        self.assertIn("--dir", argv)
        self.assertIn(str(loader), argv)
        self.assertTrue(os.path.isfile(argv[1]))
        self.assertIn(os.path.join("Library", "Logs"), data["StandardOutPath"])
        self.assertEqual(stat.S_IMODE(os.stat(result["plist"]).st_mode), 0o644)

    def test_interval_zero_keeps_only_watchpaths(self):
        loader, agents, env, _log, _marker = self._setup()
        result = tsync.install_schedule(str(self.history), str(loader),
                                        str(agents), env=env, interval=0)
        self.assertTrue(result["ok"], result)
        with open(result["plist"], "rb") as f:
            data = plistlib.load(f)
        self.assertNotIn("StartInterval", data)
        self.assertEqual(data["WatchPaths"], [str(self.history)])

    def test_build_plist_escapes_special_characters(self):
        loader, _agents, _env, _log, _marker = self._setup()
        weird = self.tmp / "a & b <c>"
        weird.mkdir()
        history = weird / "history.jsonl"
        history.write_text("{}\n", encoding="utf-8")
        payload = tsync.render_schedule_plist(str(history), str(loader))
        data = plistlib.loads(payload)
        self.assertEqual(data["WatchPaths"], [str(history)])
        self.assertIn(b"&amp;", payload)

    def test_install_bootstraps_and_reinstall_is_unchanged(self):
        loader, agents, env, log, _marker = self._setup()
        first = tsync.install_schedule(str(self.history), str(loader),
                                      str(agents), env=env)
        self.assertTrue(first["ok"], first)
        self.assertTrue(first["changed"])
        second = tsync.install_schedule(str(self.history), str(loader),
                                       str(agents), env=env)
        self.assertTrue(second["ok"], second)
        self.assertFalse(second["changed"])
        calls = _launchctl_calls(log)
        verbs = [c[0] for c in calls]
        self.assertEqual(verbs.count("bootstrap"), 2)
        # Yüklü agent yeniden kurulurken ÖNCE indirilir; yoksa bootstrap
        # "already bootstrapped" ile düşer ve eski tanım çalışmaya devam eder.
        self.assertEqual(verbs.count("bootout"), 1)
        self.assertLess(verbs.index("bootout"), len(verbs) - 1)

    def test_install_refuses_foreign_plist(self):
        loader, agents, env, log, _marker = self._setup()
        agents.mkdir(parents=True, exist_ok=True)
        path = agents / tsync.SCHEDULE_PLIST_NAME
        foreign = b"<?xml version=\"1.0\"?><plist version=\"1.0\"><dict>" \
                  b"<key>Label</key><string>com.baska.arac</string></dict></plist>"
        path.write_bytes(foreign)
        result = tsync.install_schedule(str(self.history), str(loader),
                                        str(agents), env=env)
        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "plist-foreign")
        self.assertEqual(path.read_bytes(), foreign)
        self.assertEqual(_launchctl_calls(log), [])

    def test_install_refuses_unreadable_plist(self):
        loader, agents, env, _log, _marker = self._setup()
        agents.mkdir(parents=True, exist_ok=True)
        path = agents / tsync.SCHEDULE_PLIST_NAME
        path.write_text("bu bir plist değil\n", encoding="utf-8")
        result = tsync.install_schedule(str(self.history), str(loader),
                                        str(agents), env=env)
        self.assertFalse(result["ok"])
        self.assertTrue(result["reason"].startswith("plist-unreadable"), result)
        self.assertEqual(path.read_text(encoding="utf-8"), "bu bir plist değil\n")

    def test_install_without_loader_is_not_silent(self):
        agents = self.tmp / "LaunchAgents"
        script, _log, _marker = _write_fake_launchctl(self.tmp / "bin")
        env = {"PATH": os.environ.get("PATH", ""),
               tsync.ENV_LAUNCHCTL: str(script)}
        result = tsync.install_schedule(str(self.history), None, str(agents),
                                        env=env)
        self.assertFalse(result["ok"])
        self.assertIn(result["reason"],
                      ("loader-missing", "loader-unreadable"), result)
        self.assertFalse((agents / tsync.SCHEDULE_PLIST_NAME).exists())

    def test_install_refuses_tcc_loader(self):
        loader, agents, env, _log, _marker = self._setup()
        desktop = self.tmp / "Desktop" / "leibniz2" / "apps" / "trend-db"
        _write_fake_loader(desktop)
        orig = tsync._TCC_RISK_PREFIXES
        tsync._TCC_RISK_PREFIXES = (str(self.tmp / "Desktop"),)
        try:
            result = tsync.install_schedule(str(self.history), str(desktop),
                                            str(agents), env=env)
        finally:
            tsync._TCC_RISK_PREFIXES = orig
        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "loader-needs-provision")
        self.assertTrue(result["warnings"])
        self.assertFalse((agents / tsync.SCHEDULE_PLIST_NAME).exists())

    def test_install_falls_back_to_cache_when_repo_is_tcc(self):
        """Keşif repo'yu bulur ama launchd okuyamaz; cache kopyası varsa ona geç."""
        _write_fake_loader(tsync.CACHE_LOADER_DIR)
        repo = self.tmp / "Desktop" / "leibniz2" / "apps" / "trend-db"
        _write_fake_loader(repo)
        agents = self.tmp / "LaunchAgents"
        script, _log, _marker = _write_fake_launchctl(self.tmp / "bin")
        # Keşif sırası: TREND_SYNC_DIR → cache → Desktop. Daemon'ın yazdığı
        # TREND_SYNC_DIR repo'yu gösterirse (TCC'li) cache'e düşülmeli.
        env = {"PATH": os.environ.get("PATH", ""),
               tsync.ENV_LAUNCHCTL: str(script),
               tsync.ENV_DIR: str(repo)}
        orig = tsync._TCC_RISK_PREFIXES
        tsync._TCC_RISK_PREFIXES = (str(self.tmp / "Desktop"),)
        try:
            result = tsync.install_schedule(str(self.history), None,
                                            str(agents), env=env)
        finally:
            tsync._TCC_RISK_PREFIXES = orig
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["loader_dir"], str(tsync.CACHE_LOADER_DIR))
        self.assertEqual(result["loader_source"], str(repo))
        self.assertTrue(result["warnings"])

    def test_script_is_staged_out_of_tcc(self):
        """TCC'li repo betiği doğrudan plist'e yazılsa iş hiç başlamazdı."""
        loader, agents, env, _log, _marker = self._setup()
        repo_dir = self.tmp / "Desktop" / "leibniz2" / "_calisma" / "CIKTI"
        repo_dir.mkdir(parents=True)
        source = repo_dir / "trend_db_sync.py"
        source.write_text("# gerçek modül\n", encoding="utf-8")
        staged = self.tmp / "staged"
        orig = tsync._TCC_RISK_PREFIXES
        tsync._TCC_RISK_PREFIXES = (str(self.tmp / "Desktop"),)
        try:
            result = tsync.install_schedule(
                str(self.history), str(loader), str(agents), env=env,
                script=str(source), staged_dir=str(staged))
        finally:
            tsync._TCC_RISK_PREFIXES = orig
        self.assertTrue(result["ok"], result)
        self.assertTrue(result["script_staged"])
        self.assertEqual(result["script_source"], str(source))
        with open(result["plist"], "rb") as f:
            data = plistlib.load(f)
        self.assertEqual(data["ProgramArguments"][1], result["script"])
        self.assertTrue(result["script"].startswith(str(staged)))
        self.assertEqual(pathlib.Path(result["script"]).read_text(encoding="utf-8"),
                         "# gerçek modül\n")

    def test_bootstrap_failure_is_visible_and_keeps_plist(self):
        loader, agents, env, _log, _marker = self._setup(bootstrap_rc=1)
        result = tsync.install_schedule(str(self.history), str(loader),
                                        str(agents), env=env)
        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "bootstrap-failed")
        self.assertTrue(result["installed"])
        self.assertFalse(result["loaded"])
        self.assertTrue((agents / tsync.SCHEDULE_PLIST_NAME).exists())

    def test_missing_launchctl_is_distinct_reason(self):
        loader, agents, env, _log, _marker = self._setup()
        env[tsync.ENV_LAUNCHCTL] = str(self.tmp / "yok" / "launchctl")
        result = tsync.install_schedule(str(self.history), str(loader),
                                        str(agents), env=env)
        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "launchctl-missing")

    def test_schedule_no_load_writes_plist_only(self):
        loader, agents, env, log, _marker = self._setup()
        result = tsync.install_schedule(str(self.history), str(loader),
                                        str(agents), env=env, load=False)
        self.assertTrue(result["ok"], result)
        self.assertFalse(result["loaded"])
        self.assertTrue((agents / tsync.SCHEDULE_PLIST_NAME).exists())
        self.assertEqual(_launchctl_calls(log), [])

    def test_uninstall_removes_plist_and_boots_out(self):
        loader, agents, env, log, _marker = self._setup()
        tsync.install_schedule(str(self.history), str(loader), str(agents),
                              env=env)
        result = tsync.uninstall_schedule(str(agents), env=env)
        self.assertTrue(result["ok"], result)
        self.assertTrue(result["removed"])
        self.assertTrue(result["booted_out"])
        self.assertFalse((agents / tsync.SCHEDULE_PLIST_NAME).exists())
        self.assertEqual([c[0] for c in _launchctl_calls(log)].count("bootout"), 1)

    def test_uninstall_without_plist_is_idempotent(self):
        agents = self.tmp / "LaunchAgents"
        script, _log, _marker = _write_fake_launchctl(self.tmp / "bin")
        env = {"PATH": os.environ.get("PATH", ""),
               tsync.ENV_LAUNCHCTL: str(script)}
        result = tsync.uninstall_schedule(str(agents), env=env)
        self.assertTrue(result["ok"], result)
        self.assertFalse(result["removed"])
        self.assertFalse(result["booted_out"])

    def test_cli_install_prints_single_json_line(self):
        loader, agents, env, _log, _marker = self._setup()
        out = io.StringIO()
        with mock.patch.dict(os.environ, env, clear=False), \
                contextlib.redirect_stdout(out):
            rc = tsync.main(["--install-schedule", "--json",
                             "--history", str(self.history),
                             "--dir", str(loader),
                             "--launch-agents-dir", str(agents)])
        self.assertEqual(rc, 0)
        lines = [ln for ln in out.getvalue().splitlines() if ln.strip()]
        self.assertEqual(len(lines), 1, out.getvalue())
        payload = json.loads(lines[0])
        self.assertTrue(payload["ok"], payload)
        self.assertEqual(payload["label"], tsync.SCHEDULE_LABEL)

    def test_cli_rejects_install_and_uninstall_together(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            rc = tsync.main(["--install-schedule", "--uninstall-schedule"])
        self.assertEqual(rc, 2)
        self.assertIn("aynı çağrıda", err.getvalue())


if __name__ == "__main__":
    unittest.main()
