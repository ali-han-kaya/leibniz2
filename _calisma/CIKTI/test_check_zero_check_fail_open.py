#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_check_zero_check_fail_open.py — meta-kapının kendi kanıtı.

Kapsanan iddialar:

  1. Sınıflandırıcı: "Ran N / OK (skipped=K)" çıktısında N-K <= 0 ise
     vakuum; kısmi skip gerçek koşumdur; "Ran" yoksa ölçüm yoktur.
  2. Beş gerçek sonda (a11y, keyboard scope, Playwright skips, prettier,
     changelog hook) `ok` döner — yani her biri sıfır-iş başarısını
     gerçekten kırmızıya çevirir.
  3. Runner entegrasyonu: hook, tek testi bile atlanan bir süiti
     "PASS" değil "VACUOUS" sayar; gerçek test koşan süiti PASS sayar.
     İkinci yön olmadan birinci yön "her şeyi kırmızıya çevir" demek olurdu.
  4. Ortam-skip kararı: CI'da meşru TAM-SKIP yalnız allowlist'e kayıtlı ve
     ölçülü (Ran N>0, skipped=N) dosyadır → ALLOWED. Kayıtsız tam-skip ve
     ölçüm yokluğu asla kurtarılmaz. TestCiFullSkipAllowlist karar
     tablosunu birebir sabitler (ekleme = bu test değişikliği = review'da
     görünür); karar doc'ü: docs/CI_GATE_TRIAGE.md.

stdlib-only, OFFLINE.
"""

import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import check_zero_check_fail_open as gate  # noqa: E402

PRETTIER = HERE.parent.parent / "apps" / "dashboard-next" / "node_modules" / ".bin" / "prettier"


def _prettier_available():
    """Kayıt sondası ölçülebilir mi? CI birim job'u dashboard node_modules kurmaz.

    Sonda "ölçüm imkânsız" derse bu test kırmızıya dönerdi; sınıflandırıcının
    fail-closed sözleşmesi DEĞİŞMEZ — yalnız kendi kayıt testi ortam eksiğinde
    SKIP eder (tarayıcı tabanı SKIP'leriyle aynı desen).
    """
    return os.path.isfile(PRETTIER)


ALL_SKIPPED_TEST = """import unittest


class T(unittest.TestCase):
    @unittest.skip("probe: all tests skipped")
    def test_never_runs(self):
        pass
"""

REAL_TEST = """import unittest


class T(unittest.TestCase):
    def test_really_runs(self):
        self.assertTrue(True)
"""

SYNC_STUB = "import sys\nsys.exit(0)\n"


class TestUnittestLogClassifier(unittest.TestCase):
    def test_all_skipped_is_vacuous(self):
        r = gate.classify_unittest_log(
            "Ran 18 tests in 0.000s\n\nOK (skipped=18)\n")
        self.assertEqual(r.status, "vacuous", r.detail)
        self.assertIn("0 gerçek test", r.detail)

    def test_zero_ran_is_vacuous(self):
        r = gate.classify_unittest_log("Ran 0 tests in 0.000s\n\nOK\n")
        self.assertEqual(r.status, "vacuous", r.detail)

    def test_early_ok_from_test_output_does_not_mask_all_skip(self):
        # unittest, testin kendi stdout'unu "Ran ..." satırından ÖNCE basar.
        # İlk "OK" eşleşmesi alınırsa 4/4 skip yeşil görünürdü.
        log = ("OK\n\n" "----------------------------------------------------------------------\n"
               "Ran 4 tests in 0.100s\n\n" "OK (skipped=4)\n")
        r = gate.classify_unittest_log(log)
        self.assertEqual(r.status, "vacuous", r.detail)

    def test_missing_ran_line_is_vacuous(self):
        r = gate.classify_unittest_log("OK\n")
        self.assertEqual(r.status, "vacuous", r.detail)

    def test_partial_skip_is_a_real_run(self):
        r = gate.classify_unittest_log(
            "Ran 18 tests in 1.000s\n\nOK (skipped=2)\n")
        self.assertEqual(r.status, "ok", r.detail)
        self.assertIn("16 gerçek test", r.detail)

    def test_no_skip_is_a_real_run(self):
        r = gate.classify_unittest_log("Ran 3 tests in 0.1s\n\nOK\n")
        self.assertEqual(r.status, "ok", r.detail)

    def test_nonzero_exit_is_already_a_failure_not_a_pass(self):
        r = gate.classify_unittest_log("Ran 1 test in 0.1s\n\nFAILED\n", 1)
        self.assertEqual(r.status, "ok", r.detail)
        self.assertIn("rc=1", r.detail)

    def test_cli_mode_returns_one_for_all_skip(self):
        with tempfile.TemporaryDirectory() as td:
            log = Path(td) / "unit.log"
            log.write_text("Ran 4 tests in 0.0s\n\nOK (skipped=4)\n",
                           encoding="utf-8")
            proc = subprocess.run(
                [sys.executable, str(HERE / "check_zero_check_fail_open.py"),
                 "--unittest-log", str(log)],
                capture_output=True, text=True)
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("VACUOUS", proc.stdout)


class TestRegistry(unittest.TestCase):
    def test_registry_covers_all_five_checks(self):
        self.assertEqual(
            [key for key, _title, _fn in gate.PROBES],
            ["a11y_gate", "keyboard_scope", "playwright_skips",
             "prettier", "changelog_hook"])

    @unittest.skipUnless(_prettier_available(),
                         "prettier yok (CI birim job'u node_modules kurmaz)")
    def test_every_real_probe_reports_ok(self):
        results = gate.run_probes()
        bad = [(r.key, r.status, r.detail)
               for r in results if r.status != "ok"]
        self.assertEqual(bad, [], "meta-kapı sondaları kırmızı:\n" + "\n".join(
            "%s: %s — %s" % row for row in bad))

    def test_empty_registry_is_not_a_pass(self):
        """0 sonda = 0 ölçüm; "0/0 PASS" meta fail-open olurdu."""
        with mock.patch.object(gate, "PROBES", ()):
            with contextlib.redirect_stdout(io.StringIO()) as out:
                with contextlib.redirect_stderr(io.StringIO()) as err:
                    rc = gate.main([])
        self.assertEqual(rc, 1)
        self.assertIn("BOŞ", err.getvalue())
        self.assertNotIn("verdict: PASS", out.getvalue())

    @unittest.skipUnless(_prettier_available(),
                         "prettier yok (CI birim job'u node_modules kurmaz)")
    def test_json_mode_is_one_document(self):
        proc = subprocess.run(
            [sys.executable, str(HERE / "check_zero_check_fail_open.py"),
             "--json"],
            capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        doc = json.loads(proc.stdout)
        self.assertEqual(doc["verdict"], "PASS")
        self.assertEqual(len(doc["probes"]), 5)


class TestRunnerAllSkipIntegration(unittest.TestCase):
    """Hook, tümü atlanan süiti PASS saymamalı; gerçek testi PASS saymalı."""

    def _sandbox(self, test_body, name="test_probe.py"):
        td = tempfile.TemporaryDirectory(prefix="zero_check_runner_")
        self.addCleanup(td.cleanup)
        root = Path(td.name)
        cikti = root / "_calisma" / "CIKTI"
        cikti.mkdir(parents=True)
        shutil.copy2(HERE / "check_unit_tests_hook.sh", cikti)
        shutil.copy2(HERE / "check_zero_check_fail_open.py", cikti)
        (cikti / name).write_text(test_body, encoding="utf-8")
        (cikti / "check_unit_tests.list").write_text(
            name + "\n", encoding="utf-8")
        (cikti / "sync_check_unit_tests.py").write_text(
            SYNC_STUB, encoding="utf-8")
        (cikti / "select_affected_tests.py").write_text(
            SYNC_STUB, encoding="utf-8")
        subprocess.run(["git", "init", "-q"], cwd=str(root), check=True,
                       capture_output=True, text=True)
        subprocess.run(["git", "add", "-A"], cwd=str(root), check=True,
                       capture_output=True, text=True)
        return root

    def _run_hook(self, root):
        return subprocess.run(
            ["bash", "_calisma/CIKTI/check_unit_tests_hook.sh"],
            cwd=str(root), capture_output=True, text=True, timeout=60)

    def test_all_skipped_suite_is_blocked(self):
        root = self._sandbox(ALL_SKIPPED_TEST)
        proc = self._run_hook(root)
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("VACUOUS", proc.stderr)
        self.assertIn("0 gerçek test", proc.stderr)
        self.assertNotIn("test dosyası PASS", proc.stdout)
        # Skip sayısı görünür olmalı: vakuum dosya sessizce yutulmaz.
        self.assertIn("toplam 1 test, 1 skip", proc.stderr)

    def test_real_test_suite_still_passes(self):
        root = self._sandbox(REAL_TEST)
        proc = self._run_hook(root)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("1 test dosyası PASS", proc.stdout)
        # PASS satırı toplam test/skip sayısını taşır.
        self.assertIn("1 test, 0 skip", proc.stdout)

    def test_allowlisted_suite_passes_hook_with_visible_note(self):
        """İzinli ölçülü tam-skip hook'tan geçer ve görünür not basar."""
        root = self._sandbox(ALL_SKIPPED_TEST,
                             name="test_z3_slide_reproducibility.py")
        proc = self._run_hook(root)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("test dosyası PASS", proc.stdout)
        self.assertIn("izinli tam-skip", proc.stdout)
        self.assertIn("tectonic", proc.stdout)
        self.assertNotIn("BAŞARISIZ", proc.stdout + proc.stderr)


class TestCiFullSkipAllowlist(unittest.TestCase):
    """Karar: CI'da meşru tam-skip = allowlist'e kayıtlı + ölçülü dosya."""

    ALL_SKIP = "Ran 3 tests in 0.010s\n\nOK (skipped=3)\n"
    Z3 = "test_z3_slide_reproducibility.py"

    def test_allowlisted_measured_all_skip_is_allowed(self):
        r = gate.classify_unittest_log(self.ALL_SKIP, 0, suite=self.Z3)
        self.assertEqual(r.status, "allowed", r.detail)
        self.assertIn("tectonic", r.detail)

    def test_suite_name_is_normalized(self):
        r = gate.classify_unittest_log(self.ALL_SKIP, 0,
                                       suite="test_z3_slide_reproducibility")
        self.assertEqual(r.status, "allowed", r.detail)

    def test_unknown_suite_all_skip_stays_vacuous(self):
        r = gate.classify_unittest_log(self.ALL_SKIP, 0, suite="test_probe.py")
        self.assertEqual(r.status, "vacuous", r.detail)

    def test_missing_measurement_is_never_allowlisted(self):
        r = gate.classify_unittest_log("OK\n", 0, suite=self.Z3)
        self.assertEqual(r.status, "vacuous", r.detail)

    def test_ran_zero_is_never_allowlisted(self):
        r = gate.classify_unittest_log("Ran 0 tests in 0.000s\n\nOK\n", 0,
                                       suite=self.Z3)
        self.assertEqual(r.status, "vacuous", r.detail)

    def test_partial_skip_is_plain_ok_even_for_allowlisted_file(self):
        r = gate.classify_unittest_log(
            "Ran 3 tests in 0.100s\n\nOK (skipped=1)\n", 0, suite=self.Z3)
        self.assertEqual(r.status, "ok", r.detail)

    def test_decision_is_pinned(self):
        """Karar tablosu birebir sabit: değişiklik = bu test = review'da görünür."""
        self.assertEqual(set(gate.CI_FULL_SKIP_ALLOWANCE), {self.Z3})
        self.assertIn("tectonic", gate.CI_FULL_SKIP_ALLOWANCE[self.Z3])
        self.assertIn("determinism-trend",
                      gate.CI_FULL_SKIP_ALLOWANCE[self.Z3])

    def test_cli_allows_only_with_suite_and_measurement(self):
        with tempfile.TemporaryDirectory() as td:
            log = Path(td) / "unit.log"
            log.write_text(self.ALL_SKIP, encoding="utf-8")
            base = [sys.executable,
                    str(HERE / "check_zero_check_fail_open.py"),
                    "--unittest-log", str(log)]
            allowed = subprocess.run(
                base + ["--suite", "test_z3_slide_reproducibility"],
                capture_output=True, text=True)
            blocked = subprocess.run(base, capture_output=True, text=True)
        self.assertEqual(allowed.returncode, 0,
                         allowed.stdout + allowed.stderr)
        self.assertIn("ALLOWED", allowed.stdout)
        self.assertIn("tectonic", allowed.stdout)
        self.assertEqual(blocked.returncode, 1, blocked.stdout + blocked.stderr)
        self.assertIn("VACUOUS", blocked.stdout)


class TestVerboseExecutedCounting(unittest.TestCase):
    """-v test-başına sayım: setUpClass sahte-skip özet aritmetiğini bozmaz."""

    # Ölçülen gerçek olay: statik katman koştu ("... ok"), live katman
    # setUpClass'ta atlandı → özet "Ran 2 / skipped=2" gösterir ama 1 test
    # gerçekten koşmuştur. Eski aritmetik bu dosyayı sahte VACUOUS yapıyordu.
    SET_UP_CLASS_LOG = (
        "test_static_panel_contract_matches_live_selectors "
        "(m.C.test_static_panel_contract_matches_live_selectors) ... ok\n"
        "test_safedriver_availability_is_bounded "
        "(m.C.test_safedriver_availability_is_bounded)\n"
        "Live katman skip'i ... ... skipped 'safedriver yok'\n"
        "setUpClass (m.WebkitSmokeLiveBase) ... skipped "
        "'safedriver yok (Xcode/CLT)'\n"
        "\n----------------------------------------------------------------------\n"
        "Ran 2 tests in 0.001s\n\nOK (skipped=2)\n"
    )

    ALL_SKIP_VERBOSE = (
        "test_a (m.C.test_a) ... skipped 'araç yok'\n"
        "setUpClass (m.LiveBase) ... skipped 'araç yok'\n"
        "\nRan 1 tests in 0.010s\n\nOK (skipped=2)\n"
    )
    Z3 = "test_z3_slide_reproducibility.py"

    def test_class_level_skip_does_not_vacuate_a_run_test(self):
        r = gate.classify_unittest_log(self.SET_UP_CLASS_LOG, 0)
        self.assertEqual(r.status, "ok", r.detail)
        self.assertIn("1 gerçek test", r.detail)

    def test_verbose_all_skip_without_ok_line_stays_vacuous(self):
        r = gate.classify_unittest_log(self.ALL_SKIP_VERBOSE, 0)
        self.assertEqual(r.status, "vacuous", r.detail)

    def test_verbose_all_skip_allowlisted_with_suite(self):
        r = gate.classify_unittest_log(self.ALL_SKIP_VERBOSE, 0, suite=self.Z3)
        self.assertEqual(r.status, "allowed", r.detail)

    def test_summary_only_log_still_takes_allowlist_path(self):
        # -v'siz (eski) log biçimi: aritmetik + allowlist yolu korunur.
        r = gate.classify_unittest_log(
            "Ran 3 tests in 0.010s\n\nOK (skipped=3)\n", 0, suite=self.Z3)
        self.assertEqual(r.status, "allowed", r.detail)


if __name__ == "__main__":
    unittest.main(verbosity=2)
