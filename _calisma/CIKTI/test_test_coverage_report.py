"""test_test_coverage_report.py — test_coverage_report.py regresyon kapısı.
Test edilen:
- discover_test_files: en az 60 dosya, test_budget_scan.js dahil
- build_hook_map: check-unit-tests en büyük, check-plist-drift 2 dosya
- build_ci_job_map: verify ve ci-simulate ALL
- detect_gaps: coverage_report + preview_reload_smoke exempt
- render_markdown: başlık, tablo, gap section
- --check exit 0 (bilinen exempt'lerle)
"""
import io
import json
import os
import pathlib
import sys
import tempfile
import unittest

# repo root relative import
_here = pathlib.Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_here / "_calisma" / "CIKTI"))
import test_coverage_report as tcr


class TestDiscover(unittest.TestCase):
    def test_finds_60_plus_files(self):
        files = tcr.discover_test_files()
        self.assertGreater(len(files), 60)

    def test_finds_budget_scan_js(self):
        files = tcr.discover_test_files()
        self.assertIn("test_budget_scan.js", files)
        # 67 budget scan test assertion call'ları
        self.assertGreater(files["test_budget_scan.js"]["test_count"], 60)

    def test_colorize_rules_has_100_plus_tests(self):
        files = tcr.discover_test_files()
        self.assertIn("test_colorize_rules.py", files)
        self.assertGreater(files["test_colorize_rules.py"]["test_count"], 100)


class TestHookMap(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.files = tcr.discover_test_files()
        cls.hmap = tcr.build_hook_map(tcr.HOOK_COVERAGE, cls.files)

    def test_check_unit_tests_largest(self):
        self.assertIn("check-unit-tests", self.hmap)
        self.assertGreater(self.hmap["check-unit-tests"]["test_count"], 900)

    def test_check_plist_drift_two_files(self):
        self.assertIn("check-plist-drift", self.hmap)
        self.assertEqual(len(self.hmap["check-plist-drift"]["test_files"]), 2)

    def test_check_repro_manifest_one_file(self):
        self.assertIn("check-repro-manifest", self.hmap)
        self.assertEqual(len(self.hmap["check-repro-manifest"]["test_files"]), 1)

    def test_check_repro_manifest_covers_k10_cross_validation(self):
        """K10 çapraz doğrulama testleri (config/lineage/summary/precheck_report/
        python3_shell/plist_check combined_sha256 + manifest.sha256 çift tespiti)
        check-repro-manifest hook'unun kapısında koşmalı — coverage map, hook'un
        kapsadığı test dosyasının (test_gen_repro_manifest.py) içinde bu testlerin
        VAR olduğunu kanıtlamalı."""
        files = self.hmap["check-repro-manifest"]["test_files"]
        self.assertEqual(files, ["test_gen_repro_manifest.py"])
        src = pathlib.Path(__file__).resolve().parent / "test_gen_repro_manifest.py"
        text = src.read_text(encoding="utf-8")
        for name in (
            "test_k10_detects_config_combined_tamper",
            "test_k10_detects_lineage_combined_tamper_dual",
            "test_k10_detects_summary_combined_tamper_dual",
            "test_k10_detects_precheck_report_combined_tamper_dual",
            "test_k10_detects_python3_shell_combined_tamper_dual",
            "test_k10_detects_plist_check_combined_tamper_dual",
        ):
            self.assertIn(f"def {name}(", text,
                          f"K10 çapraz testi hook kapsamında değil: {name}")


class TestCiJobMap(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.files = tcr.discover_test_files()
        cls.cmap = tcr.build_ci_job_map(tcr.CI_JOB_COVERAGE, cls.files)

    def test_verify_and_ci_simulate_are_all(self):
        for jid in ("verify", "ci-simulate"):
            self.assertIn(jid, self.cmap)
            self.assertEqual(self.cmap[jid]["test_count"],
                             sum(v["test_count"] for v in self.files.values()))


class TestDetectGaps(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.files = tcr.discover_test_files()
        cls.hmap = tcr.build_hook_map(tcr.HOOK_COVERAGE, cls.files)

    def test_exempt_files_not_flagged_as_zero_tests(self):
        """Standalone smoke script'leri exempt — --check FAIL etmez."""
        gaps = tcr.detect_gaps(self.files, self.hmap)
        exempt = {"test_coverage_report.py", "test_preview_reload_smoke.py",
                  "test_all_hooks_smoke.py"}
        actual_uncovered = set(gaps["not_covered_by_any_hook"]) - exempt
        self.assertEqual(actual_uncovered, set(),
                         f"Unexpected uncovered: {actual_uncovered}")


class TestRenderMarkdown(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.files = tcr.discover_test_files()
        cls.hmap = tcr.build_hook_map(tcr.HOOK_COVERAGE, cls.files)
        cls.cmap = tcr.build_ci_job_map(tcr.CI_JOB_COVERAGE, cls.files)
        cls.hook_names = tcr.discover_hook_entries()
        cls.report = tcr.build_report(cls.files, cls.hmap, cls.cmap, cls.hook_names)

    def test_has_summary_table(self):
        md = tcr.render_markdown(self.report)
        self.assertIn("## Summary", md)
        self.assertIn("Test files", md)
        self.assertIn("Test methods", md)

    def test_has_hook_table(self):
        md = tcr.render_markdown(self.report)
        self.assertIn("## Pre-commit Hook Coverage", md)
        self.assertIn("check-unit-tests", md)
        self.assertIn("check-plist-drift", md)

    def test_has_ci_job_table(self):
        md = tcr.render_markdown(self.report)
        self.assertIn("## CI Job Test Coverage", md)
        self.assertIn("verify", md)

    def test_has_gaps_section(self):
        md = tcr.render_markdown(self.report)
        self.assertIn("Gaps", md)


class TestCheckMode(unittest.TestCase):
    def test_check_exit_zero_with_exempt(self):
        with tempfile.TemporaryDirectory() as td:
            md_out = os.path.join(td, "report.md")
            rc = tcr.main(["--check", "--md", md_out])
            self.assertEqual(rc, 0)

    def test_check_mode_coverage_ok(self):
        """--check mode: bilinen exempt'ler dışında uncovered yok."""
        rc = tcr.main(["--check"])
        self.assertEqual(rc, 0)


if __name__ == "__main__":
    unittest.main()