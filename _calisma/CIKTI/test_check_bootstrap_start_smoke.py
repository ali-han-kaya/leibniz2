"""Unit tests for check_bootstrap_start_smoke.py — K21-START fake launchctl shim."""

import os
import sys
import tempfile
import unittest

# Shim modülünü import et
sys.path.insert(0, os.path.dirname(__file__))
from check_bootstrap_start_smoke import (
    create_launchctl_shim,
    create_curl_shim,
    create_full_shim_set,
    parse_launchctl_log,
    had_bootstrap_call,
)


class TestCreateLaunchctlShim(unittest.TestCase):
    """Shim oluşturma ve temel özellikleri."""

    def test_shim_file_created_and_executable(self):
        shim_dir, shim_path, log_path = create_launchctl_shim()
        self.assertTrue(os.path.isfile(shim_path))
        self.assertTrue(os.access(shim_path, os.X_OK))

    def test_shim_content_has_case_statement(self):
        shim_dir, shim_path, log_path = create_launchctl_shim()
        with open(shim_path) as f:
            content = f.read()
        self.assertIn("bootstrap", content)
        self.assertIn("bootout", content)
        self.assertIn("LAUNCHCTL_LOG", content)

    def test_shim_in_custom_dir(self):
        with tempfile.TemporaryDirectory() as td:
            shim_dir, shim_path, log_path = create_launchctl_shim(td)
            self.assertTrue(shim_path.startswith(td))

    def test_log_path_is_in_dest_dir(self):
        with tempfile.TemporaryDirectory() as td:
            shim_dir, shim_path, log_path = create_launchctl_shim(td)
            self.assertTrue(log_path.startswith(td))
            self.assertTrue(log_path.endswith("launchctl.log"))


class TestParseLaunchctlLog(unittest.TestCase):
    """Log ayrıştırma."""

    def test_empty_log(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".log",
                                          delete=False) as f:
            f.write("")
            f.flush()
            log_path = f.name
        try:
            entries = parse_launchctl_log(log_path)
            self.assertEqual(entries, [])
        finally:
            os.unlink(log_path)

    def test_single_bootstrap_entry(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".log",
                                          delete=False) as f:
            f.write("2026-08-27T12:00:00Z launchctl bootstrap gui/501 /tmp/test.plist\n")
            f.flush()
            log_path = f.name
        try:
            entries = parse_launchctl_log(log_path)
            self.assertEqual(len(entries), 1)
            self.assertEqual(entries[0]["cmd"], "bootstrap")
            self.assertEqual(entries[0]["args"], ["gui/501", "/tmp/test.plist"])
        finally:
            os.unlink(log_path)

    def test_multiple_entries(self):
        lines = [
            "2026-08-27T12:00:00Z launchctl bootout gui/501 /tmp/a.plist",
            "2026-08-27T12:00:01Z launchctl bootstrap gui/501 /tmp/a.plist",
            "2026-08-27T12:00:02Z launchctl enable gui/501/com.freebuff",
        ]
        with tempfile.NamedTemporaryFile(mode="w", suffix=".log",
                                          delete=False) as f:
            f.write("\n".join(lines) + "\n")
            f.flush()
            log_path = f.name
        try:
            entries = parse_launchctl_log(log_path)
            self.assertEqual(len(entries), 3)
            cmds = [e["cmd"] for e in entries]
            self.assertEqual(cmds, ["bootout", "bootstrap", "enable"])
        finally:
            os.unlink(log_path)

    def test_nonexistent_log(self):
        entries = parse_launchctl_log("/tmp/_nonexistent_log_12345.log")
        self.assertEqual(entries, [])


class TestHadBootstrapCall(unittest.TestCase):
    """Bootstrap çağrısı tespiti."""

    def test_no_bootstrap(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".log",
                                          delete=False) as f:
            f.write("2026-08-27T12:00:00Z launchctl bootout gui/501 /tmp/a.plist\n")
            f.flush()
            log_path = f.name
        try:
            self.assertFalse(had_bootstrap_call(log_path))
        finally:
            os.unlink(log_path)

    def test_has_bootstrap(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".log",
                                          delete=False) as f:
            f.write("2026-08-27T12:00:00Z launchctl bootstrap gui/501 /tmp/a.plist\n")
            f.flush()
            log_path = f.name
        try:
            self.assertTrue(had_bootstrap_call(log_path))
        finally:
            os.unlink(log_path)

    def test_empty_log_no_bootstrap(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".log",
                                          delete=False) as f:
            f.write("")
            f.flush()
            log_path = f.name
        try:
            self.assertFalse(had_bootstrap_call(log_path))
        finally:
            os.unlink(log_path)

    def test_bootstrap_among_many_commands(self):
        lines = [
            "2026-08-27T12:00:00Z launchctl list",
            "2026-08-27T12:00:01Z launchctl bootout gui/501 /tmp/a.plist",
            "2026-08-27T12:00:02Z launchctl bootstrap gui/501 /tmp/a.plist",
            "2026-08-27T12:00:03Z launchctl enable gui/501/com.freebuff",
        ]
        with tempfile.NamedTemporaryFile(mode="w", suffix=".log",
                                          delete=False) as f:
            f.write("\n".join(lines) + "\n")
            f.flush()
            log_path = f.name
        try:
            self.assertTrue(had_bootstrap_call(log_path))
        finally:
            os.unlink(log_path)


class TestShimIntegration(unittest.TestCase):
    """Shim'i gerçekten çalıştırarak test et."""

    def test_shim_executes_and_logs(self):
        """Shim gerçekten çalıştırıldığında log yazdığını doğrula."""
        import subprocess
        shim_dir, shim_path, log_path = create_launchctl_shim()
        env = dict(os.environ)
        env["LAUNCHCTL_LOG"] = log_path
        env["PATH"] = shim_dir + ":" + env.get("PATH", "")
        r = subprocess.run(
            ["launchctl", "bootstrap", "gui/501", "/tmp/test.plist"],
            env=env, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0)
        entries = parse_launchctl_log(log_path)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["cmd"], "bootstrap")

    def test_shim_bootout_returns_zero(self):
        """Shim bootout çağrısında exit 0 dönmeli."""
        import subprocess
        shim_dir, shim_path, log_path = create_launchctl_shim()
        env = dict(os.environ)
        env["LAUNCHCTL_LOG"] = log_path
        env["PATH"] = shim_dir + ":" + env.get("PATH", "")
        r = subprocess.run(
            ["launchctl", "bootout", "gui/501", "/tmp/test.plist"],
            env=env, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0)

    def test_shim_list_returns_empty_json(self):
        """Shim list çağrısında '[]' stdout'a basmalı."""
        import subprocess
        shim_dir, shim_path, log_path = create_launchctl_shim()
        env = dict(os.environ)
        env["LAUNCHCTL_LOG"] = log_path
        env["PATH"] = shim_dir + ":" + env.get("PATH", "")
        r = subprocess.run(
            ["launchctl", "list"],
            env=env, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0)
        self.assertIn("[]", r.stdout)


class TestCurlShim(unittest.TestCase):
    """Fake curl shim testleri."""

    def test_create_curl_shim(self):
        with tempfile.TemporaryDirectory() as td:
            shim_dir, shim_path, log_path = create_curl_shim(td)
            self.assertTrue(os.path.isfile(shim_path))
            self.assertTrue(os.access(shim_path, os.X_OK))

    def test_curl_shim_returns_200_for_http_code_format(self):
        import subprocess
        with tempfile.TemporaryDirectory() as td:
            shim_dir, shim_path, log_path = create_curl_shim(td)
            env = dict(os.environ)
            env["CURL_LOG"] = log_path
            env["PATH"] = shim_dir + ":" + env.get("PATH", "")
            r = subprocess.run(
                ["curl", "-sf", "-o", "/dev/null", "-w", "%{http_code}",
                 "http://127.0.0.1:8000/api/latest"],
                env=env, capture_output=True, text=True)
            self.assertEqual(r.returncode, 0)
            self.assertIn("200", r.stdout)

    def test_curl_shim_logs_calls(self):
        import subprocess
        with tempfile.TemporaryDirectory() as td:
            shim_dir, shim_path, log_path = create_curl_shim(td)
            env = dict(os.environ)
            env["CURL_LOG"] = log_path
            env["PATH"] = shim_dir + ":" + env.get("PATH", "")
            subprocess.run(
                ["curl", "-sf", "-o", "/dev/null", "-w", "%{http_code}",
                 "http://127.0.0.1:8000/api/latest"],
                env=env, capture_output=True)
            self.assertTrue(os.path.isfile(log_path))
            with open(log_path) as f:
                content = f.read()
            self.assertIn("curl", content)
            self.assertIn("api/latest", content)


class TestFullShimSet(unittest.TestCase):
    """create_full_shim_set() entegrasyon testleri."""

    def test_full_set_creates_both_shims(self):
        with tempfile.TemporaryDirectory() as td:
            shim_dir, lc_log, curl_log = create_full_shim_set(td)
            self.assertTrue(os.path.isfile(os.path.join(shim_dir, "launchctl")))
            self.assertTrue(os.path.isfile(os.path.join(shim_dir, "curl")))

    def test_full_set_both_logs_separate(self):
        with tempfile.TemporaryDirectory() as td:
            shim_dir, lc_log, curl_log = create_full_shim_set(td)
            self.assertNotEqual(lc_log, curl_log)

    def test_full_set_launchctl_in_path(self):
        import subprocess
        with tempfile.TemporaryDirectory() as td:
            shim_dir, lc_log, curl_log = create_full_shim_set(td)
            env = dict(os.environ)
            env["LAUNCHCTL_LOG"] = lc_log
            env["CURL_LOG"] = curl_log
            env["PATH"] = shim_dir + ":" + env.get("PATH", "")
            r = subprocess.run(
                ["launchctl", "list"],
                env=env, capture_output=True, text=True)
            self.assertEqual(r.returncode, 0)

    def test_full_set_curl_in_path(self):
        import subprocess
        with tempfile.TemporaryDirectory() as td:
            shim_dir, lc_log, curl_log = create_full_shim_set(td)
            env = dict(os.environ)
            env["LAUNCHCTL_LOG"] = lc_log
            env["CURL_LOG"] = curl_log
            env["PATH"] = shim_dir + ":" + env.get("PATH", "")
            r = subprocess.run(
                ["curl", "-sf", "-o", "/dev/null", "-w", "%{http_code}",
                 "http://127.0.0.1:8000/api/latest"],
                env=env, capture_output=True, text=True)
            self.assertEqual(r.returncode, 0)
            self.assertIn("200", r.stdout)


class TestBootstrapSkipFlags(unittest.TestCase):
    """--no-mirror / --no-html flag parsing testleri."""

    def test_no_mirror_flag_parsed(self):
        """--no-mirror flag'i bootstrap_all() tarafından tanınmalı."""
        import subprocess
        with tempfile.TemporaryDirectory() as td:
            shim_dir, lc_log, curl_log = create_full_shim_set(td)
            fake_home = os.path.join(td, "home")
            os.makedirs(fake_home, exist_ok=True)
            env = dict(os.environ)
            env["HOME"] = fake_home
            env["LAUNCHCTL_LOG"] = lc_log
            env["CURL_LOG"] = curl_log
            env["PATH"] = shim_dir + ":" + env.get("PATH", "")
            # --no-mirror ile --bootstrap --start --verify çalıştır
            # mirror sync symlink sorunu olacağından
            # doğrudan update_preview.sh çağırmak yerine bayrak parsing doğrulaması
            # pwd'deki script'i kullanarak exitedtat kontrolü yap
            here = os.path.dirname(os.path.abspath(__file__))
            script = os.path.join(here, "update_preview.sh")
            if not os.path.isfile(script):
                self.skipTest("update_preview.sh yok")
            r = subprocess.run(
                ["bash", script, "--bootstrap", "--start", "--no-mirror",
                 "--no-html", "--verify", fake_home],
                capture_output=True, text=True, timeout=120, env=env)
            txt = (r.stdout + r.stderr).strip()
            # --no-mirror çıktısı ATLANDI olarak görünmeli
            self.assertIn("ATLANDI", txt)
            self.assertIn("--no-mirror", txt)
            self.assertIn("--no-html", txt)

    def test_no_html_flag_parsed(self):
        """--no-html flag'i bootstrap_all() tarafından tanınmalı."""
        import subprocess
        with tempfile.TemporaryDirectory() as td:
            shim_dir, lc_log, curl_log = create_full_shim_set(td)
            fake_home = os.path.join(td, "home")
            os.makedirs(fake_home, exist_ok=True)
            env = dict(os.environ)
            env["HOME"] = fake_home
            env["LAUNCHCTL_LOG"] = lc_log
            env["CURL_LOG"] = curl_log
            env["PATH"] = shim_dir + ":" + env.get("PATH", "")
            here = os.path.dirname(os.path.abspath(__file__))
            script = os.path.join(here, "update_preview.sh")
            if not os.path.isfile(script):
                self.skipTest("update_preview.sh yok")
            r = subprocess.run(
                ["bash", script, "--bootstrap", "--start",
                 "--no-html", "--verify", fake_home],
                capture_output=True, text=True, timeout=120, env=env)
            txt = (r.stdout + r.stderr).strip()
            self.assertIn("ATLANDI", txt)
            self.assertIn("--no-html", txt)
            # mirror ATLANDI olmamalı (sadece --no-html)
            self.assertNotIn("--no-mirror", txt)

    def test_both_skip_flags(self):
        """Her iki flag birlikte verildiğinde her iki adım da atlanmalı."""
        import subprocess
        with tempfile.TemporaryDirectory() as td:
            shim_dir, lc_log, curl_log = create_full_shim_set(td)
            fake_home = os.path.join(td, "home")
            os.makedirs(fake_home, exist_ok=True)
            env = dict(os.environ)
            env["HOME"] = fake_home
            env["LAUNCHCTL_LOG"] = lc_log
            env["CURL_LOG"] = curl_log
            env["PATH"] = shim_dir + ":" + env.get("PATH", "")
            here = os.path.dirname(os.path.abspath(__file__))
            script = os.path.join(here, "update_preview.sh")
            if not os.path.isfile(script):
                self.skipTest("update_preview.sh yok")
            r = subprocess.run(
                ["bash", script, "--bootstrap", "--start",
                 "--no-mirror", "--no-html", fake_home],
                capture_output=True, text=True, timeout=120, env=env)
            txt = (r.stdout + r.stderr).strip()
            # Her iki adım da atlanmalı
            self.assertIn("ATLANDI", txt)
            # plist üretimi hâlâ yapılmalı
            self.assertIn("plist", txt.lower())


if __name__ == "__main__":
    unittest.main()
