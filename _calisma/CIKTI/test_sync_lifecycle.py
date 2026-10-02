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


if __name__ == "__main__":
    unittest.main()
