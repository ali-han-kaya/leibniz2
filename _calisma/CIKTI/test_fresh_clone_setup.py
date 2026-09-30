#!/usr/bin/env python3
"""fresh_clone_setup.sh — TCC-safe fresh-clone kurulum betiğinin birim testleri.

Beş artefaktın tümü FAKE HOME altında kurulur/denetlenir (gerçek
~/Library/Caches/com.freebuff + ~/Library/LaunchAgents'a DOKUNMAZ; bu yüzden
Linux CI'da da çalışır):

  1) Repo venv        REPO_VENV   (FC_TEST_FAKE_VENV=1 ile import denetimi atlanır)
  2) Mirror venv      MIRROR_VENV (aynı)
  3) Preview mirror   PREVIEW_MIRROR (preview_server.py + _daemonize.py)
  4) Verify mirror    MIRROR_DIR  (sync_verify_mirror.sh — varsayılan $HOME yolu)
  5) HTML + plist     update_preview.sh --bootstrap (varsayılan $HOME yolları)
  6) Daemon rotası    daemon_http_test.py MIRROR kopyasıyla HTTP smoke
                     (SSE/run-now dahil; test'te fake venv → vâkıf değil, trivially
                     exit 0 — gerçek kurulumda gerçek daemon smoke'u koşar)

Sözleşme: --check → 0 = TAMAM / 1 = EKSİK-bayat / 2 = hata (bilinmeyen mod).
setup modu fail-closed: her adımda hata → exit ≠ 0. --start ayrıca fake
launchctl + HTTP readiness shim'leriyle bootstrap ve idempotence sözleşmesini
kapsar.
"""
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
FRESH_SETUP = os.path.join(HERE, "fresh_clone_setup.sh")
if HERE not in sys.path:
    sys.path.insert(0, HERE)

# Fake launchctl/curl shimleri gerçek launchd/HTTP servisine dokunmadan
# --start zincirinin tamamını fake HOME altında çalıştırmak için kullanılır.
from check_bootstrap_start_smoke import (  # noqa: E402
    create_full_shim_set,
    parse_launchctl_log,
)


def run(home, *args, extra_env=None):
    """HOME'u fake dizine sabitleyip komutu koş; CompletedProcess döner."""
    env = dict(os.environ)
    env["HOME"] = home
    # TEST-ONLY: venv import denetimini atla (offline — gerçek kurulumda yok).
    env["FC_TEST_FAKE_VENV"] = "1"
    if extra_env:
        env.update(extra_env)
    return subprocess.run(list(args), env=env, capture_output=True,
                          text=True, timeout=600)


def fake_venv(path):
    """Asgari venv iskeleti: FC_TEST_FAKE_VENV=1 altında yeterli olan bin/python3."""
    os.makedirs(os.path.join(path, "bin"), exist_ok=True)
    py = os.path.join(path, "bin", "python3")
    if not os.path.exists(py):
        with open(py, "w", encoding="utf-8") as f:
            f.write("#!/bin/sh\nexit 0\n")
        os.chmod(py, 0o755)


def env_overrides(home):
    """Beş artefaktı da fake HOME altına yönlendiren env sözlüğü."""
    return {
        "REPO_VENV": os.path.join(home, "repo_venv"),
        "MIRROR_VENV": os.path.join(home, "mirror_venv"),
        "PREVIEW_MIRROR": os.path.join(home, "Library", "Caches",
                                       "com.freebuff", "preview"),
        # MIRROR_DIR/LEAN_MIRROR_DIR bilinçli OLARAK verilmez: sync ve
        # bootstrap, varsayılan $HOME yollarını kullanmalı (üretimle birebir).
    }


class TestFreshCloneSetupCheck(unittest.TestCase):
    """--check → 0=TAMAM / 1=EKSİK / 2=hata."""

    def test_check_exit_1_when_nothing_built(self):
        with tempfile.TemporaryDirectory(prefix="fc-setup-") as home:
            r = run(home, "bash", FRESH_SETUP, "--check",
                    extra_env=env_overrides(home))
            self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
            self.assertIn("EKSİK", r.stdout)

    def test_check_exit_0_after_full_setup(self):
        with tempfile.TemporaryDirectory(prefix="fc-setup-") as home:
            env = env_overrides(home)
            # 1-2: fake venv iskeletleri (FC_TEST_FAKE_VENV ile yeterli).
            fake_venv(env["REPO_VENV"])
            fake_venv(env["MIRROR_VENV"])
            # 3-5: tam kurulum (mirror + preview mirror + HTML + plist).
            r = run(home, "bash", FRESH_SETUP, extra_env=env)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("FRESH-CLONE KURULUM: tamam", r.stdout)
            # Tümü hazır → --check exit 0.
            r = run(home, "bash", FRESH_SETUP, "--check", extra_env=env)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("TAMAM", r.stdout)

    def test_unknown_mode_exit_2(self):
        with tempfile.TemporaryDirectory(prefix="fc-setup-") as home:
            r = run(home, "bash", FRESH_SETUP, "--nope",
                    extra_env=env_overrides(home))
            self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
            self.assertIn("bilinmeyen mod", r.stderr)


class TestFreshCloneSetupArtifacts(unittest.TestCase):
    """Tam kurulum beş artefaktın tümünü fake HOME altında üretir."""

    def _artifacts(self, home):
        return {
            "repo_venv": os.path.join(home, "repo_venv", "bin", "python3"),
            "mirror_venv": os.path.join(home, "mirror_venv", "bin", "python3"),
            "preview_server": os.path.join(
                home, "Library", "Caches", "com.freebuff", "preview",
                "preview_server.py"),
            "verify_mirror": os.path.join(
                home, "Library", "Caches", "com.freebuff", "verify",
                "verify_delivery.py"),
            "html": os.path.join(
                home, "Library", "Caches", "com.freebuff", "preview",
                "preview.html"),
            "plist": os.path.join(
                home, "Library", "LaunchAgents",
                "com.freebuff.preview-leibniz2.plist"),
        }

    def test_all_five_artifacts_created(self):
        with tempfile.TemporaryDirectory(prefix="fc-setup-") as home:
            env = env_overrides(home)
            fake_venv(env["REPO_VENV"])
            fake_venv(env["MIRROR_VENV"])
            r = run(home, "bash", FRESH_SETUP, extra_env=env)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            for name, p in self._artifacts(home).items():
                self.assertTrue(os.path.exists(p),
                                f"{name} üretilmedi: {p}")

    def test_idempotent_second_setup(self):
        with tempfile.TemporaryDirectory(prefix="fc-setup-") as home:
            env = env_overrides(home)
            fake_venv(env["REPO_VENV"])
            fake_venv(env["MIRROR_VENV"])
            r1 = run(home, "bash", FRESH_SETUP, extra_env=env)
            self.assertEqual(r1.returncode, 0, r1.stdout + r1.stderr)
            r2 = run(home, "bash", FRESH_SETUP, extra_env=env)
            self.assertEqual(r2.returncode, 0, r2.stdout + r2.stderr)
            # İkinci koşu --check ile hâlâ TAMAM.
            r3 = run(home, "bash", FRESH_SETUP, "--check", extra_env=env)
            self.assertEqual(r3.returncode, 0, r3.stdout + r3.stderr)


class TestFreshCloneSetupAgentMirror(unittest.TestCase):
    """launchd agent'ın plist'teki mirror yolları --check ile karşılaştırılır."""

    def _build(self, home):
        env = env_overrides(home)
        fake_venv(env["REPO_VENV"])
        fake_venv(env["MIRROR_VENV"])
        r = run(home, "bash", FRESH_SETUP, extra_env=env)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return env

    def _plist_path(self, home):
        return os.path.join(home, "Library", "LaunchAgents",
                            "com.freebuff.preview-leibniz2.plist")

    def test_agent_mirror_matches_check_after_setup(self):
        with tempfile.TemporaryDirectory(prefix="fc-setup-") as home:
            self._build(home)
            r = run(home, "bash", FRESH_SETUP, "--check",
                    extra_env=env_overrides(home))
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("launchd agent mirror'ı --check ile aynı", r.stdout)

    def test_agent_plist_missing_is_informational(self):
        # Plist yoksa (agent kurulu değil) BİLGİ notu; EKSİK sayılmaz —
        # ancak venv'ler de yoksa --check yine exit 1 (fail-closed).
        with tempfile.TemporaryDirectory(prefix="fc-setup-") as home:
            env = env_overrides(home)
            fake_venv(env["REPO_VENV"])
            fake_venv(env["MIRROR_VENV"])
            # Mirrors + plist'siz ortam: sync mirror'ı kurar ama plist yok.
            r = run(home, "bash", FRESH_SETUP, extra_env=env)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            os.remove(self._plist_path(home))
            r = run(home, "bash", FRESH_SETUP, "--check", extra_env=env)
            self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
            self.assertIn("launchd agent kurulu değil", r.stdout)

    def test_agent_plist_mirror_drift_fail_closed(self):
        # Plist'teki --preview-dir farklı bir yola işaret ederse → DRIFT (exit 1).
        with tempfile.TemporaryDirectory(prefix="fc-setup-") as home:
            self._build(home)
            plist = self._plist_path(home)
            with open(plist, "rb") as f:
                import plistlib
                d = plistlib.load(f)
            args = d["ProgramArguments"]
            idx = args.index("--")
            i = args.index("--preview-dir", idx)
            args[i + 1] = os.path.join(home, "OTHER-preview")
            with open(plist, "wb") as f:
                plistlib.dump(d, f)
            r = run(home, "bash", FRESH_SETUP, "--check",
                    extra_env=env_overrides(home))
            self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
            self.assertIn("DRIFT", r.stderr)
            self.assertIn("OTHER-preview", r.stderr)


class TestFreshCloneSetupCheckCI(unittest.TestCase):
    """--check-ci: CI runner'da beş artefaktı doğrula (daemon + mirror venv atla)."""

    def test_check_ci_exit_1_when_nothing_built(self):
        with tempfile.TemporaryDirectory(prefix="fc-setup-") as home:
            r = run(home, "bash", FRESH_SETUP, "--check-ci",
                    extra_env=env_overrides(home))
            self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
            self.assertIn("EKSİK", r.stdout)

    def test_check_ci_exit_0_after_sync(self):
        """mirror sync + repo venv + HTML/plist → --check-ci exit 0 (daemon atlanır)."""
        with tempfile.TemporaryDirectory(prefix="fc-setup-") as home:
            env = env_overrides(home)
            fake_venv(env["REPO_VENV"])
            # MIRROR_VENV'yi oluşturma (CI'da farklı yolda, --check-ci atlar).
            r = run(home, "bash", FRESH_SETUP, extra_env=env)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            r = run(home, "bash", FRESH_SETUP, "--check-ci", extra_env=env)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("TAMAM", r.stdout)
            # Daemon rotası --check-ci'de çalıştırılmaz.
            self.assertNotIn("daemon", r.stdout.lower())

    def test_check_ci_skips_daemon_http_smoke(self):
        """--check-ci mirror sync --check çalıştırır (daemon dosyası dahil)
        ama daemon HTTP smoke (boş portta sunucu başlatma) çalıştırMAZ.
        Mirror'dan daemon_http_test.py silinince sync --check bayat yakalar."""
        with tempfile.TemporaryDirectory(prefix="fc-setup-") as home:
            env = env_overrides(home)
            fake_venv(env["REPO_VENV"])
            r = run(home, "bash", FRESH_SETUP, extra_env=env)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            # --check-ci daemon smoke (step 6) çalıştırmasaydı,
            # mirror sync hala dosya bütünlüğünü doğrulardı:
            # daemon_http_test.py silinince sync --check EKSİK yakalar.
            dtest = os.path.join(home, "Library", "Caches", "com.freebuff",
                                 "verify", "daemon_http_test.py")
            if os.path.exists(dtest):
                os.remove(dtest)
            r = run(home, "bash", FRESH_SETUP, "--check-ci", extra_env=env)
            self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
            self.assertIn("daemon_http_test.py", r.stdout + r.stderr)

    def test_check_ci_fails_on_mirror_drift(self):
        """mirror bayatsa --check-ci yine exit 1."""
        with tempfile.TemporaryDirectory(prefix="fc-setup-") as home:
            env = env_overrides(home)
            fake_venv(env["REPO_VENV"])
            r = run(home, "bash", FRESH_SETUP, extra_env=env)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            pv = os.path.join(home, "Library", "Caches", "com.freebuff",
                              "preview", "preview_server.py")
            with open(pv, "a", encoding="utf-8") as f:
                f.write("\n# drift\n")
            r = run(home, "bash", FRESH_SETUP, "--check-ci", extra_env=env)
            self.assertEqual(r.returncode, 1, r.stdout + r.stderr)


class TestFreshCloneSetupStart(unittest.TestCase):
    """--start: kurulum + launchd bootstrap + readiness tek akışta."""

    def test_start_installs_bootstraps_and_reports_dashboard_url(self):
        with tempfile.TemporaryDirectory(prefix="fc-start-") as home, \
             tempfile.TemporaryDirectory(prefix="fc-start-shim-") as shim_root:
            env = env_overrides(home)
            fake_venv(env["REPO_VENV"])
            fake_venv(env["MIRROR_VENV"])
            shim_dir, launch_log, curl_log = create_full_shim_set(shim_root)
            env.update({
                "PATH": shim_dir + os.pathsep + os.environ.get("PATH", ""),
                "LAUNCHCTL_LOG": launch_log,
                "CURL_LOG": curl_log,
            })

            result = run(home, "bash", FRESH_SETUP, "--start", extra_env=env)
            output = result.stdout + result.stderr
            self.assertEqual(result.returncode, 0, output)
            self.assertIn("=== 6/6: launchd bootstrap + HTTP health (--start) ===",
                          result.stdout)
            self.assertIn("DASHBOARD_URL: http://127.0.0.1:8000/preview.html",
                          result.stdout)
            self.assertIn("READY: Live CI Dashboard", result.stdout)
            self.assertTrue(parse_launchctl_log(launch_log))
            self.assertTrue(any(entry["cmd"] == "bootstrap"
                                for entry in parse_launchctl_log(launch_log)))
            self.assertTrue(os.path.isfile(curl_log),
                            "readiness curl shim logu oluşmalı")
            with open(curl_log, encoding="utf-8") as f:
                curl_calls = f.read()
            self.assertIn("/api/health", curl_calls)
            self.assertIn("/preview.html", curl_calls)

            # Aynı komut ikinci kez çalıştığında da bootstrap + readiness
            # korunur; installer'ın idempotent sözleşmesi regresyonla korunur.
            second = run(home, "bash", FRESH_SETUP, "--start", extra_env=env)
            second_output = second.stdout + second.stderr
            self.assertEqual(second.returncode, 0, second_output)
            self.assertIn("DASHBOARD_URL: http://127.0.0.1:8000/preview.html",
                          second.stdout)

    def test_start_preview_source_does_not_kill_arbitrary_port_owner(self):
        """Port 8000 sahibi başka bir servis olsa da onu öldürmeyelim."""
        with open(os.path.join(HERE, "start_preview.sh"), encoding="utf-8") as f:
            source = f.read()
        self.assertNotIn("kill -9", source)
        self.assertNotIn("lsof ", source)
        self.assertIn("update_preview.sh", source)


class TestFreshCloneSetupFailClosed(unittest.TestCase):
    """Eksik ön-koşul → hata ile dur (fail-closed, exit ≠ 0)."""

    def test_missing_venv_fails_setup(self):
        # python3 bulunamazsa venv kurulamaz; ama sistemde python3 VARSA
        # gerçek pip kurulumu yapar (ağ!). Bu yüzden yalnızca --check'in
        # eksik venv'i exit 1 ile raporladığını doğrularız (setup'ı değil).
        with tempfile.TemporaryDirectory(prefix="fc-setup-") as home:
            env = env_overrides(home)
            # REPO_VENV fake iskeleti YOK → --check exit 1.
            r = run(home, "bash", FRESH_SETUP, "--check", extra_env=env)
            self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
            self.assertIn("repo venv eksik/bozuk", r.stderr)

    def test_check_reports_preview_drift_after_build(self):
        with tempfile.TemporaryDirectory(prefix="fc-setup-") as home:
            env = env_overrides(home)
            fake_venv(env["REPO_VENV"])
            fake_venv(env["MIRROR_VENV"])
            r = run(home, "bash", FRESH_SETUP, extra_env=env)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            # Preview mirror'daki dosyayı boz → --check bayatlığı yakalar.
            pv = os.path.join(home, "Library", "Caches", "com.freebuff",
                              "preview", "preview_server.py")
            with open(pv, "a", encoding="utf-8") as f:
                f.write("\n# drift\n")
            r = run(home, "bash", FRESH_SETUP, "--check", extra_env=env)
            self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
            self.assertIn("EKSİK", r.stdout)
            # Bayat dosya listesi komut satırında raporlanmalı (dosya adıyla).
            self.assertIn("preview/verify mirror bayat/eksik", r.stderr)
            self.assertIn("preview_server.py", r.stderr)

    def test_check_reports_missing_daemon_test_fail_closed(self):
        # Daemon rotası kapsamda: mirror'daki daemon_http_test.py silinirse
        # --check exit 1 + "daemon" hatası (fail-closed).
        with tempfile.TemporaryDirectory(prefix="fc-setup-") as home:
            env = env_overrides(home)
            fake_venv(env["REPO_VENV"])
            fake_venv(env["MIRROR_VENV"])
            r = run(home, "bash", FRESH_SETUP, extra_env=env)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            dtest = os.path.join(home, "Library", "Caches", "com.freebuff",
                                 "verify", "daemon_http_test.py")
            self.assertTrue(os.path.exists(dtest), "daemon_http_test.py mirror'da olmalı")
            os.remove(dtest)
            r = run(home, "bash", FRESH_SETUP, "--check", extra_env=env)
            self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
            self.assertIn("daemon", r.stderr.lower())


if __name__ == "__main__":
    unittest.main()
