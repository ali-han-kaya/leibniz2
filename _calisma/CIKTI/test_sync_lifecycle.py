#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_sync_lifecycle.py — sync aracının uçtan-uca yaşam-döngüsü regresyon kapısı.

Önceki oturumun ad-hoc "SYNC_LIFECYCLE_OK" kanıt koşumunu kalıcılaştırır:
CLI'yi SUBPROCESS ile koşar (in-process import değil), temp dizin sandbox'ında
tam yaşam-döngüsünü sınar:

  1. --update → boş başlangıçtan senkron: manifest + HOOK_COVERAGE doldurulur
  2. --check  → senkron ağaçta rc=0
  3. drift    → yeni test_*.py düşürülür → --check FAIL-CLOSED (rc=1, remedy)
  4. --update → drift'i yer
  5. --check  → yeniden yeşil
  6. prune    → dosya silinir → --update orphan'ı düşürür → yeşil

Ayrıca:
  - --list CLI stdout sözleşmesi discover() ile birebir
  - gerçek hook script'i (check_unit_tests_hook.sh) sandbox'ta: drift'i
    BLOKLAMALI, sessizce düzeltmemeli (okuma-hook invariantı)

Gerçek repo ağacına dokunmaz: tüm yazmalar temp sandbox'ta; gerçek
manifest/coverage'a karşı yalnız okuma modül-yardımcılarıyla yapılır.

stdlib only — OFFLINE, temp dizinlerle izole.
"""

import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SYNC = os.path.join(HERE, "sync_check_unit_tests.py")
HOOK = os.path.join(HERE, "check_unit_tests_hook.sh")

STUB_TEST_BODY = ("import unittest\n\n\nclass T(unittest.TestCase):\n"
                  "    def test_ok(self):\n        pass\n")

# Sandbox coverage dosyası kendisi keşfedilen bir testtir (gerçek repo düzeni):
# sync-sonrası manifest/HOOK kümesi = stub'lar + bu dosya.
COV_NAME = "test_coverage_report.py"
BASE3 = ["test_a.py", "test_b.py", COV_NAME]

# Sandbox coverage dosyası: statik-parse formatı (ci_full_discover_drift_guard
# okuyabilsin) + stub test gövdesi (dosyanın kendisi keşfedilen bir test olsun,
# gerçek repodaki test_coverage_report.py düzeni gibi).
COVERAGE_TEMPLATE = '''import pathlib
HOOK_COVERAGE = {
    "other-hook": ["test_other.py"],
    "check-unit-tests": [
{ENTRIES}    ],
}
'''


def _write_coverage(path, entries):
    lines = "".join('        "%s",\n' % e for e in entries)
    with open(path, "w", encoding="utf-8") as f:
        f.write(COVERAGE_TEMPLATE.replace("{ENTRIES}", lines))


if HERE not in sys.path:
    sys.path.insert(0, HERE)
import sync_check_unit_tests as s  # noqa: E402
import run_unit_tests_parallel as parallel  # noqa: E402


def _iso(sb):
    """İzole-koşum argümanları: gerçek repo yollarına dokunma."""
    return ["--dir", sb.cikti, "--manifest", sb.manifest, "--coverage", sb.cov]


class Sandbox:
    """Gerçek sync aracı + gerçek hook script'iyle izole repo kökü."""

    def __init__(self):
        self.td = tempfile.TemporaryDirectory()
        self.root = self.td.name
        cikti = self.cikti
        os.makedirs(cikti)
        shutil.copy(SYNC, cikti)
        shutil.copy(HOOK, cikti)
        # Hook, rc=0'ı tek başına PASS saymaz: çıktıyı bu sınıflandırıcıya
        # verir (all-skip = FAIL). Gerçek bağımlılık sandbox'a da kopyalanır.
        shutil.copy(os.path.join(HERE, "check_zero_check_fail_open.py"), cikti)
        _write_coverage(self.cov, [])
        with open(self.cov, "a", encoding="utf-8") as f:
            f.write(STUB_TEST_BODY)

    @property
    def cikti(self):
        return os.path.join(self.root, "_calisma", "CIKTI")

    @property
    def manifest(self):
        return os.path.join(self.cikti, "check_unit_tests.list")

    @property
    def cov(self):
        return os.path.join(self.cikti, "test_coverage_report.py")

    def add_test(self, name):
        with open(os.path.join(self.cikti, name), "w", encoding="utf-8") as f:
            f.write(STUB_TEST_BODY)

    def remove_test(self, name):
        os.remove(os.path.join(self.cikti, name))

    def run_cli(self, *args):
        """CLI'yi subprocess ile koşturur; (rc, stdout+stderr) döndürür."""
        r = subprocess.run(
            [sys.executable, SYNC] + list(args),
            capture_output=True, text=True, cwd=self.root, timeout=60,
            check=False)
        return r.returncode, (r.stdout + r.stderr)

    def run_hook(self):
        """check_unit_tests_hook.sh'ı sandbox kökünde koşturur."""
        return subprocess.run(
            ["bash", os.path.join(self.cikti, "check_unit_tests_hook.sh")],
            capture_output=True, text=True, cwd=self.root, timeout=60,
            check=False)

    def cleanup(self):
        self.td.cleanup()


class TestSyncLifecycle(unittest.TestCase):
    """Ad-hoc SYNC_LIFECYCLE_OK kanıt koşumunun kalıcı, sabit sürümü."""

    def test_full_lifecycle_update_check_drift_failclosed_update_green_prune(self):
        sb = Sandbox()
        try:
            # 1) Boş başlangıçtan --update: her iki hedefi doldurur, rc=0.
            sb.add_test("test_a.py")
            sb.add_test("test_b.py")
            rc, out = sb.run_cli("--update", "--no-stage", *_iso(sb))
            self.assertEqual(rc, 0, out)
            self.assertEqual(s.read_manifest(sb.manifest), BASE3)
            self.assertEqual(s.read_hook_coverage(sb.cov), BASE3)

            # 2) Senkron ağaçta --check yeşil.
            rc, out = sb.run_cli("--check", *_iso(sb))
            self.assertEqual(rc, 0, out)

            # 3-4) Drift: yeni test dosyası → --check FAIL-CLOSED, remedy
            # gösterir, manifest'i KENDİSİ DEĞİŞTİRMEZ (okuma-kapısı).
            sb.add_test("test_c.py")
            rc, out = sb.run_cli("--check", *_iso(sb))
            self.assertEqual(rc, 1, out)
            self.assertIn("test_c.py", out)
            self.assertIn("--update", out, "remedy komutu gösterilmeli")
            self.assertEqual(s.read_manifest(sb.manifest), BASE3)

            # 5) --update drift'i yer.
            rc, out = sb.run_cli("--update", "--no-stage", *_iso(sb))
            self.assertEqual(rc, 0, out)
            self.assertIn("test_c.py", s.read_manifest(sb.manifest))

            # 6) Yeniden yeşil.
            rc, out = sb.run_cli("--check", *_iso(sb))
            self.assertEqual(rc, 0, out)

            # 7) Prune: dosya silinir → --update orphan'ı düşürür → yeşil.
            sb.remove_test("test_c.py")
            rc, out = sb.run_cli("--update", "--no-stage", *_iso(sb))
            self.assertEqual(rc, 0, out)
            self.assertNotIn("test_c.py", s.read_manifest(sb.manifest))
            rc, out = sb.run_cli("--check", *_iso(sb))
            self.assertEqual(rc, 0, out)
        finally:
            sb.cleanup()

    def test_list_stdout_matches_discovery(self):
        """--list CLI çıkışı discover() sırasıyla birebir (stdout sözleşmesi)."""
        sb = Sandbox()
        try:
            sb.add_test("test_a.py")
            sb.add_test("test_b.py")
            rc, out = sb.run_cli("--list", "--dir", sb.cikti)
            self.assertEqual(rc, 0, out)
            self.assertEqual(out.split(), BASE3)
        finally:
            sb.cleanup()


class TestHookEntryFailClosed(unittest.TestCase):
    """Gerçek hook script'i sandbox'ta: drift BLOKLANIR, sessizce düzeltilmez."""

    def test_hook_blocks_drift_and_stays_read_only(self):
        sb = Sandbox()
        try:
            sb.add_test("test_a.py")
            sb.add_test("test_b.py")
            with open(sb.manifest, "w", encoding="utf-8") as f:
                f.write("test_a.py\n")
            # Disk 3 keşif, manifest 1 giriş, HOOK bloğu boş → çift-hedef drift.
            r = sb.run_hook()
            self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("--update", r.stderr + r.stdout,
                          "remedy komutu gösterilmeli")
            self.assertEqual(s.read_manifest(sb.manifest), ["test_a.py"],
                             "okuma-hook invariantı: drift bloklanır, düzeltilmez")
            self.assertEqual(s.read_hook_coverage(sb.cov), [],
                             "okuma-hook invariantı: coverage bloğu değişmez")
        finally:
            sb.cleanup()

    def test_hook_passes_on_synced_tree(self):
        sb = Sandbox()
        try:
            sb.add_test("test_a.py")
            rc, out = sb.run_cli("--update", "--no-stage", *_iso(sb))
            self.assertEqual(rc, 0, out)
            r = sb.run_hook()
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("PASS", r.stdout)
        finally:
            sb.cleanup()


# Hızlı yol sözleşmesi: her dosya YİNE kendi yorumlayıcısında koşar (izolasyon
# korunur); yalnız koşum eşzamanlıdır ve PARALLEL_BUDGET_S ile sınırlıdır.
# Bütçe aşımı sıralı (katı) yola düşer — yanlış-pozitif değil, yavaşlama.
MARK_STUB = ("import pathlib\nimport unittest\n\n\nclass T(unittest.TestCase):\n"
             "    def test_ok(self):\n"
             "        pathlib.Path('ran_{name}.flag').write_text('1',\n"
             "            encoding='utf-8')\n")
SLOW_STUB = ("import pathlib\nimport time\nimport unittest\n\n\n"
             "class T(unittest.TestCase):\n"
             "    def test_slow(self):\n        time.sleep(2.0)\n"
             "        pathlib.Path('ran_slow.flag').write_text('1',\n"
             "            encoding='utf-8')\n")
MANIFEST3 = ["test_a.py", "test_b.py", "test_slow.py"]


class TestHookParallelBudget(unittest.TestCase):
    """Bütçe sabiti test edilebilir; aşım hook'u sıralı koşuma düşürür."""

    def test_budget_constant_is_the_default(self):
        self.assertIsInstance(parallel.PARALLEL_BUDGET_S, float)
        self.assertGreater(parallel.PARALLEL_BUDGET_S, 0)
        self.assertEqual(parallel.resolve_budget({}),
                         parallel.PARALLEL_BUDGET_S)

    def test_budget_env_override_and_fail_safe(self):
        self.assertEqual(
            parallel.resolve_budget({"CHECK_UNIT_TEST_BUDGET_S": "7.5"}), 7.5)
        for raw in ("abc", "0", "-3", "", "  "):
            self.assertEqual(
                parallel.resolve_budget({"CHECK_UNIT_TEST_BUDGET_S": raw}),
                parallel.PARALLEL_BUDGET_S, raw)

    def test_jobs_resolution_is_fail_safe(self):
        # Sayı olmayan değer en katı tarafa (1 işçi) düşer.
        self.assertEqual(parallel.resolve_jobs({"CHECK_UNIT_TEST_JOBS": "x"}), 1)
        self.assertEqual(parallel.resolve_jobs({"CHECK_UNIT_TEST_JOBS": "2"}), 2)
        self.assertEqual(parallel.resolve_jobs({"CHECK_UNIT_TEST_JOBS": "0"}),
                         parallel.DEFAULT_JOBS)
        self.assertEqual(parallel.resolve_jobs({"CHECK_UNIT_TEST_JOBS": "999"}),
                         parallel.MAX_JOBS)

    def _sandbox(self):
        td = tempfile.TemporaryDirectory(prefix="hook_budget_")
        self.addCleanup(td.cleanup)
        root = pathlib.Path(td.name)
        cikti = root / "_calisma" / "CIKTI"
        cikti.mkdir(parents=True)
        for name in ("check_unit_tests_hook.sh", "run_unit_tests_parallel.py",
                     "check_zero_check_fail_open.py"):
            shutil.copy2(os.path.join(HERE, name), str(cikti))
        (cikti / "sync_check_unit_tests.py").write_text(
            "import sys\nsys.exit(0)\n", encoding="utf-8")
        for name in MANIFEST3:
            body = SLOW_STUB if name == "test_slow.py" else \
                MARK_STUB.replace("{name}", name[:-3])
            (cikti / name).write_text(body, encoding="utf-8")
        (cikti / "check_unit_tests.list").write_text(
            "".join(n + "\n" for n in MANIFEST3), encoding="utf-8")
        subprocess.run(["git", "init", "-q"], cwd=str(root), check=True,
                       capture_output=True, text=True)
        subprocess.run(["git", "add", "-A"], cwd=str(root), check=True,
                       capture_output=True, text=True)
        return root

    def _run_hook(self, root, env_extra=None):
        env = dict(os.environ)
        env.pop("CHECK_UNIT_TEST_JOBS", None)
        env.pop("CHECK_UNIT_TEST_BUDGET_S", None)
        env.update(env_extra or {})
        return subprocess.run(
            ["bash", "_calisma/CIKTI/check_unit_tests_hook.sh"],
            cwd=str(root), capture_output=True, text=True, timeout=180,
            env=env, check=False)

    def test_fast_path_inside_budget_runs_every_file(self):
        root = self._sandbox()
        r = self._run_hook(root, {"CHECK_UNIT_TEST_BUDGET_S": "120",
                                  "CHECK_UNIT_TEST_JOBS": "3"})
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("3 test dosyası PASS", r.stdout)
        self.assertNotIn("bütçe aşımı", r.stderr)
        for flag in ("ran_test_a.flag", "ran_test_b.flag", "ran_slow.flag"):
            self.assertTrue((root / flag).exists(),
                            "%s yok — hızlı yol o dosyayı koşmadı" % flag)

    def test_budget_overrun_falls_back_to_sequential_loop(self):
        root = self._sandbox()
        r = self._run_hook(root, {"CHECK_UNIT_TEST_BUDGET_S": "1",
                                  "CHECK_UNIT_TEST_JOBS": "3"})
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("hızlı yol tamamlanamadı", r.stderr)
        self.assertIn("sıralı koşuda", r.stderr)
        # Sıralı yol asılı/yarım kalan dosyayı yine de koşmalı: üçü de iz.
        self.assertIn("3 test dosyası PASS", r.stdout)
        for flag in ("ran_test_a.flag", "ran_test_b.flag", "ran_slow.flag"):
            self.assertTrue((root / flag).exists(),
                            "%s yok — sıralı yol dosyayı koşmadı" % flag)

    def test_fast_path_red_is_rechecked_in_isolation(self):
        """Hızlı yol kırmızısı kesin değil: izole koşu sonucu geçerlidir.

        İlk koşumda düşen, ikinci koşumda geçen stub = eşzamanlı komşunun
        bozduğu sahte kırmızı. Kapı yeşile dönmeli, ama UYARI basmalı.
        """
        root = self._sandbox()
        flaky = root / "_calisma" / "CIKTI" / "test_a.py"
        flaky.write_text(
            "import pathlib\nimport unittest\n\n\n"
            "class T(unittest.TestCase):\n"
            "    def test_once(self):\n"
            "        p = pathlib.Path('attempt.txt')\n"
            "        n = int(p.read_text()) if p.exists() else 0\n"
            "        p.write_text(str(n + 1))\n"
            "        self.assertEqual(n, 1, 'ilk koşum düşsün (sahte kırmızı)')\n"
            "        pathlib.Path('ran_test_a.flag').write_text('1')\n",
            encoding="utf-8")
        r = self._run_hook(root, {"CHECK_UNIT_TEST_BUDGET_S": "120",
                                  "CHECK_UNIT_TEST_JOBS": "3"})
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("izole koşuda doğrulanıyor", r.stderr)
        self.assertIn("UYARI test_a", r.stderr)
        self.assertIn("3 test dosyası PASS", r.stdout)
        self.assertEqual((root / "attempt.txt").read_text(), "2",
                         "doğrulama koşumu yapılmadı — tek deneme kaldı")

    def test_runner_exit_code_three_means_fall_back(self):
        root = self._sandbox()
        logs = root / "logs"
        proc = subprocess.run(
            [sys.executable,
             str(root / "_calisma" / "CIKTI" / "run_unit_tests_parallel.py"),
             "--manifest",
             str(root / "_calisma" / "CIKTI" / "check_unit_tests.list"),
             "--logs-dir", str(logs), "--discover-dir", "_calisma/CIKTI",
             "--jobs", "2", "--budget-s", "1"],
            cwd=str(root), capture_output=True, text=True, timeout=120,
            check=False)
        self.assertEqual(proc.returncode, 3, proc.stdout + proc.stderr)
        self.assertIn("bütçe", proc.stderr)
        # Tamamlanan dosyaların rc kayıtları yine yazılmış olmalı (kısmi iş
        # kaybolmaz; sıralı yol yalnız eksikleri koşar).
        self.assertTrue((logs / "test_a.rc").exists()
                        or (logs / "test_b.rc").exists())


if __name__ == "__main__":
    unittest.main()
