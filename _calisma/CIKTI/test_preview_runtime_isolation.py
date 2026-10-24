#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_preview_runtime_isolation.py — kapı testleri ağacı kirletmesin.

SÖZLEŞME: preview_server testlerde ÇALIŞIRKEN ürettiği dosyaları repo ağacına
bırakmaz. Sunucu yazımları (`history.jsonl` + `.sha256` sidecar,
`runs/run-*.json`, `logs/server_events.jsonl`, `klayers.json`,
`trend_sync.json`) `--runtime-dir`'e gider; `preview.html`/`preview.js` gibi
OKUMA yolları `--preview-dir`'den servis edilmeye devam eder.

Neden gerekliydi: kapı testleri gerçek sayfayı servis etmek için sunucuyu
`--preview-dir <repo>` ile başlatıyordu. O modda sunucu `history.jsonl`,
`runs/` ve `logs/server_events.jsonl` dosyalarını repo'ya yazıyordu —
gitignore'lu ama GERÇEK kanıt dosyaları. `logs/server_events.jsonl` bu yüzden
MB mertebesine çıktı ve "ağaçta ne değişti?" sorusu testin kendi çıktısıyla
karıştı. Ölçüldü (2026-10-20): `_calisma/CIKTI/logs/server_events.jsonl`
2.7 MB, `history.jsonl` 193 KB, `runs/` 18 dosya.

Fail-closed semantiği: hiçbir assert "dosya yok" varsayımına dayanmaz; repo
çalışma zamanı yollarının (mtime_ns, boyut) görüntüsü iki noktada alınır ve
ALINAN yeni/değişen yol olması kırmızıdır. Varsayılanın (bayraksız) hâlâ
`--preview-dir` olduğu ayrıca pinlenir — üretim davranışı sessizce değişmesin.
"""
from __future__ import annotations

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
SERVER_SCRIPT = os.path.join(HERE, "preview_server.py")

sys.path.insert(0, HERE)
from preview_test_env import (  # noqa: E402
    REPO_RUNTIME_RELPATHS,
    RuntimeProbe,
    runtime_args,
    runtime_dir,
)


def _free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_health(proc, port, timeout=20):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if proc.poll() is not None:
            return False
        try:
            with urllib.request.urlopen(
                    "http://127.0.0.1:%d/api/health" % port, timeout=1) as r:
                if r.status == 200:
                    return True
        except OSError:
            time.sleep(0.15)
    return False


def _stub_verify_dir(root):
    """`--dir` için stub: verify loop canlı olsa da zincir koşmaz."""
    os.makedirs(root, exist_ok=True)
    with open(os.path.join(root, "verify_delivery.py"), "w",
              encoding="utf-8") as f:
        f.write('print("{}")\n')
    return root


def _preview_dir_with_page(root):
    """Gerçek sayfa kabuğunu geçici preview-dir'e kopyala (okuma yolu)."""
    os.makedirs(root, exist_ok=True)
    shutil.copyfile(os.path.join(HERE, "preview.html"),
                    os.path.join(root, "preview.html"))
    return root


class HelperContractTests(unittest.TestCase):
    """`preview_test_env` yardımcısının kendi sözleşmesi."""

    def test_runtime_dir_lives_in_system_tempdir(self):
        path = runtime_dir("contract")
        self.assertTrue(os.path.isdir(path))
        temp_root = os.path.realpath(tempfile.gettempdir())
        self.assertEqual(os.path.realpath(os.path.dirname(path)), temp_root,
                         "çalışma zamanı dizini TMPDIR altında olmalı: %s" % path)
        self.assertNotIn(os.path.realpath(HERE), os.path.realpath(path),
                         "geçici dizin repo içine düşmemeli")

    def test_runtime_dir_is_unique_per_call(self):
        first, second = runtime_dir("uniq"), runtime_dir("uniq")
        self.assertNotEqual(first, second,
                            "iki sunucu aynı history.jsonl'i paylaşmamalı")

    def test_runtime_args_is_flag_pair(self):
        args = runtime_args("contract")
        self.assertEqual(args[0], "--runtime-dir")
        self.assertTrue(os.path.isdir(args[1]))

    def test_probe_detects_new_and_changed_paths_only(self):
        root = tempfile.mkdtemp(prefix="probe_")
        try:
            probe = RuntimeProbe(root)
            self.assertEqual(probe.changed(), [])
            target = os.path.join(root, "history.jsonl")
            with open(target, "w", encoding="utf-8") as f:
                f.write("{}\n")
            self.assertEqual(probe.changed(), ["history.jsonl"])
            probe2 = RuntimeProbe(root)
            with open(target, "w", encoding="utf-8") as f:
                f.write('{"ts": "x"}\n')  # boyut+mtime değişir
            self.assertEqual(probe2.changed(), ["history.jsonl"])
            # İzlenen yollar sabittir (sidecar + runs + logs + trend dosyaları).
            for rel in ("history.jsonl.sha256", "runs",
                        "logs/server_events.jsonl", "trend_sync.json"):
                self.assertIn(rel, REPO_RUNTIME_RELPATHS)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_cleanup_removes_dirs_at_exit(self):
        """atexit temizliği: dizin listesi boşalır (süreç sonu kanıtı)."""
        import preview_test_env as env
        created = runtime_dir("cleanup")
        self.assertIn(created, env._REGISTERED)
        env._cleanup()
        self.assertFalse(os.path.isdir(created))
        self.assertEqual(env._REGISTERED, [])


class GitignoreContractTests(unittest.TestCase):
    """Çalışma zamanı yolları .gitignore'da olmalı — yazımı yönlendirmek
    yalnız yarısıdır: geçici dizin yerine yanlışlıkla repoya yazan bir koşum,
    bu dosyaları "takip edilmemiş" olarak ağaçta bırakırdı.

    Kapı fail-closed: yolları tek tek `git check-ignore` ile sorar; biri
    ignore değilse kırmızı. Repo değilse (ör. kurulum kopyası) SKIP.
    """

    # Kapıların repo köküne bıraktığı sidecar'lar (CI'da artefakt/logs).
    ROOT_GATE_OUTPUTS = (
        "player_routes.json",
        "a11y_dashboard_dark.json",
        "a11y_video_light.json",
        "lighthouse_dashboard_dark.json",
    )

    REPO_ROOT = os.path.dirname(os.path.dirname(HERE))

    def _git(self, *args):
        return subprocess.run(["git", "-C", self.REPO_ROOT] + list(args),
                              capture_output=True, text=True)

    def setUp(self):
        if shutil.which("git") is None:
            self.skipTest("git yok")
        probe = self._git("rev-parse", "--is-inside-work-tree")
        if probe.returncode != 0:
            self.skipTest("git deposu değil: %s" % self.REPO_ROOT)

    def _not_ignored(self, paths):
        """Ignore DESENİNE göre sorar (`--no-index`).

        `--no-index` şart: onsuz git, izlenen her yol için 1 döndürür ve
        "desen var mı?" sorusu cevapsız kalır (ölçüldü: `_calisma/CIKTI/*`
        gibi fazla geniş bir desen testi kırmızıya düşürmüyordu).
        """
        missing = []
        for path in paths:
            proc = self._git("check-ignore", "-q", "--no-index", "--", path)
            if proc.returncode != 0:
                missing.append(path)
        return missing

    def test_server_runtime_paths_are_ignored(self):
        paths = [os.path.join(HERE, rel) for rel in REPO_RUNTIME_RELPATHS]
        self.assertEqual(self._not_ignored(paths), [],
                         "preview_server çalışma zamanı yolları .gitignore'da "
                         "değil")
        # Ignore deseni, TAKİPLİ bir dosyayı sessizce kurtarmaz: git izlenen
        # yolu hiçbir zaman "ignore edilmiş" saymaz. Bu yüzden ayrıca "index'te
        # durmamalı" denetlenir — aksi halde `git add` edilmiş bir runtime
        # dosyası kapıdan geçer ve her koşumda diff üretir.
        tracked = []
        for path in paths:
            proc = self._git("ls-files", "--error-unmatch", "--", path)
            if proc.returncode == 0:
                tracked.append(os.path.relpath(path, self.REPO_ROOT))
        self.assertEqual(tracked, [],
                         "takipli/index'te runtime dosyası: %r — `git rm "
                         "--cached` gerekir (dosya diskte kalabilir)" % tracked)

    def test_relative_preview_dir_artifact_is_ignored(self):
        """GÖRELİ `--preview-dir` artığı (iç içe ağaç) de ignore edilmeli.

        Ölçüldü: bir koşum `--preview-dir _calisma/CIKTI` göreli yolla
        başlatılmış, history/runs/logs `_calisma/CIKTI/_calisma/CIKTI/`
        altına düşmüş ve index'e eklenmişti (3 dosya).
        """
        nested = os.path.join(HERE, "_calisma", "CIKTI")
        paths = [os.path.join(nested, "history.jsonl"),
                 os.path.join(nested, "runs", "run-x.json"),
                 os.path.join(nested, "logs", "server_events.jsonl")]
        self.assertEqual(self._not_ignored(paths), [],
                         "göreli preview-dir artığı ignore edilmiyor")

    def test_gate_sidecars_are_ignored(self):
        paths = [os.path.join(self.REPO_ROOT, name)
                 for name in self.ROOT_GATE_OUTPUTS]
        self.assertEqual(self._not_ignored(paths), [],
                         "kapı sidecar'ları repo kökünde takip edilebilir "
                         "kalıyor")

    def test_tracked_config_is_not_swallowed(self):
        """Negatif kiriş: `/a11y_*.json` gibi desenler TAKİPLİ yapılandırmayı
        yutmamalı (`_calisma/CIKTI/a11y_gate_config.json` kaynak dosyadır)."""
        config = os.path.join(HERE, "a11y_gate_config.json")
        self.assertEqual(self._git("check-ignore", "-q", "--no-index", "--",
                                   config).returncode, 1,
                         "takip edilen a11y_gate_config.json "
                         "ignore edilmiş görünüyor — desen fazla geniş")


class SpawnSiteContractTests(unittest.TestCase):
    """Statik kapı: repo preview-dir'iyle başlatan test YAZIMI İZOLE ETMELİ.

    Sunucu repo dizininden servis ediyorsa (`--preview-dir HERE` /
    `str(CIKTI)`), aynı dosyada `runtime_args(...)` ya da açık
    `"--runtime-dir"` bulunmalıdır. Aksi halde test ağacı kirletir.
    """

    REPO_POINTING = (
        '"--preview-dir", HERE',
        '"--preview-dir", str(HERE)',
        '"--preview-dir", str(CIKTI)',
        '"--preview-dir", CIKTI',
    )

    def _test_files(self):
        for name in sorted(os.listdir(HERE)):
            if name.startswith("test_") and name.endswith(".py"):
                yield name, os.path.join(HERE, name)

    def test_no_repo_pointing_spawn_without_runtime_dir(self):
        offenders = []
        checked = 0
        for name, path in self._test_files():
            with open(path, encoding="utf-8") as f:
                text = f.read()
            if "preview_server" not in text:
                continue
            if not any(marker in text for marker in self.REPO_POINTING):
                continue
            checked += 1
            if "runtime_args(" not in text and '"--runtime-dir"' not in text:
                offenders.append(name)
        self.assertGreater(checked, 0,
                           "tarama hiç eşleşme bulmadı — kapı anlamsızlaştı "
                           "(marker seti koda uymuyor)")
        self.assertEqual(offenders, [],
                         "repo preview-dir'iyle sunucu başlatıp yazımı "
                         "izole etmeyen testler: %r" % offenders)

    def test_inline_spawn_lists_pass_runtime_args(self):
        """Gerçek spawn listeleri `*runtime_args(` taşır (bayrak gerçekten geçer)."""
        spawners = [
            "test_dashboard_budget_rh_filters.py",
            "test_dashboard_cls_budget.py",
            "test_dashboard_csp_nonce.py",
            "test_dashboard_keyboard_nav.py",
            "test_dashboard_playwright_smoke.py",
            "test_dashboard_webkit_smoke.py",
            "test_preview_escaping.py",
            "test_preview_hover_tooltip.py",
        ]
        missing = []
        for name in spawners:
            path = os.path.join(HERE, name)
            if not os.path.isfile(path):
                missing.append(name + " (dosya yok)")
                continue
            with open(path, encoding="utf-8") as f:
                text = f.read()
            if "*runtime_args(" not in text:
                missing.append(name)
        self.assertEqual(missing, [], "izolasyon bayrağı geçmeyen spawn "
                                     "listeleri: %r" % missing)


class RealProcessIsolationTests(unittest.TestCase):
    """Gerçek alt-süreç: yazımlar geçici dizinde, repo dokunulmamış."""

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="iso_root_")
        self.preview = _preview_dir_with_page(
            os.path.join(self.root, "preview"))
        self.verify = _stub_verify_dir(os.path.join(self.root, "verify"))
        self.proc = None

    def tearDown(self):
        if self.proc is not None and self.proc.poll() is None:
            self.proc.kill()
            self.proc.wait(timeout=10)
        shutil.rmtree(self.root, ignore_errors=True)

    def _spawn(self, port, extra):
        self.proc = subprocess.Popen(
            [sys.executable, SERVER_SCRIPT,
             "--dir", self.verify,
             "--preview-dir", self.preview,
             "--port", str(port), "--bind", "127.0.0.1",
             "--interval", "3600"] + extra,
            cwd=HERE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return _wait_health(self.proc, port)

    def _stop(self):
        self.proc.send_signal(signal.SIGTERM)
        try:
            self.proc.wait(timeout=20)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait(timeout=10)

    def _events(self, directory):
        path = os.path.join(directory, "logs", "server_events.jsonl")
        if not os.path.isfile(path):
            return []
        with open(path, encoding="utf-8") as f:
            return [json.loads(ln) for ln in f if ln.strip()]

    def test_writes_land_in_runtime_dir_and_repo_stays_clean(self):
        runtime = runtime_dir("real-proc")
        probe = RuntimeProbe(HERE)
        port = _free_port()
        self.assertTrue(self._spawn(port, ["--runtime-dir", runtime]),
                        "sunucu ayağa kalkmadı (port=%d)" % port)
        # Gerçek okuma yolu hâlâ preview-dir'den servis edilir.
        with urllib.request.urlopen(
                "http://127.0.0.1:%d/api/latest" % port, timeout=5) as r:
            self.assertEqual(r.status, 200)
        self._stop()

        names = [rec.get("event") for rec in self._events(runtime)]
        self.assertIn("signal_exit", names,
                      "SIGTERM kaydı runtime dizinine düşmeli: %r" % names)
        self.assertEqual(self._events(self.preview), [],
                         "olay kaydı preview-dir'e sızmamalı")
        self.assertEqual(probe.changed(), [],
                         "repo çalışma zamanı yolları değişti: %r"
                         % probe.changed())

    def test_default_runtime_dir_is_still_preview_dir(self):
        """Bayraksız davranış DEĞİŞMEZ (üretim sözleşmesi)."""
        port = _free_port()
        self.assertTrue(self._spawn(port, []), "sunucu ayağa kalkmadı")
        self._stop()
        names = [rec.get("event") for rec in self._events(self.preview)]
        self.assertIn("signal_exit", names,
                      "varsayılan yazım yeri preview-dir olmalı: %r" % names)

    def test_probe_detects_a_default_mode_write(self):
        """POZİTİF KONTROL: probe yazımı gerçekten görüyor mu?

        Yukarıdaki "repo temiz kaldı" iddiası, probe hiçbir zaman yazım
        göremiyorsa (ör. yollar yanlış) boş olurdu. Aynı probe'u bayraksız
        modda ön-dizine uygulayıp DEĞİŞİM görmesi, assert'i gerçek yapar.
        """
        probe = RuntimeProbe(self.preview)
        port = _free_port()
        self.assertTrue(self._spawn(port, []), "sunucu ayağa kalkmadı")
        self._stop()
        changed = probe.changed()
        # Olay-kaydı her koşumda düşer; run kaydı (history/runs) verify
        # turunun bitişine bağlıdır — zamanlamaya duyarlı iddia kurmamak
        # için "en az biri" aranır. Taban: olay-kaydı ZORUNLU.
        self.assertIn("logs/server_events.jsonl", changed,
                      "probe varsayılan moddaki yazımı görmedi: %r" % changed)
        self.assertTrue({"history.jsonl", "runs"} & set(changed),
                        "varsayılan mod run kaydını da yazmalıydı: %r" % changed)

    def test_unwritable_runtime_dir_fails_closed(self):
        """Runtime dizini oluşturulamıyorsa başlatma REDDEDİLİR (exit 2)."""
        blocker = os.path.join(self.root, "not-a-dir")
        with open(blocker, "w", encoding="utf-8") as f:
            f.write("x")
        proc = subprocess.run(
            [sys.executable, SERVER_SCRIPT,
             "--dir", self.verify,
             "--preview-dir", self.preview,
             "--runtime-dir", os.path.join(blocker, "child"),
             "--port", str(_free_port()), "--bind", "127.0.0.1",
             "--interval", "3600"],
            cwd=HERE, capture_output=True, text=True, timeout=60)
        self.assertEqual(proc.returncode, 2, proc.stderr)
        self.assertIn("runtime-dir oluşturulamadı", proc.stderr)


if __name__ == "__main__":
    unittest.main()
