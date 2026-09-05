#!/usr/bin/env python3
import pathlib
import unittest

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent.parent


class K13CoverageSyncTests(unittest.TestCase):
    def setUp(self):
        self.coverage = (HERE / "test_coverage_report.py").read_text(encoding="utf-8")
        self.unit_list = (HERE / "check_unit_tests.list").read_text(encoding="utf-8").splitlines()
        self.mirror = (HERE / "sync_verify_mirror.sh").read_text(encoding="utf-8")
        self.summary = (HERE / "consolidate_summary.py").read_text(encoding="utf-8")
        self.k13 = (HERE / "run_summary_k13.py").read_text(encoding="utf-8")

    def test_k13_summary_is_registered_in_coverage(self):
        self.assertIn('"check-repro-manifest":', self.coverage)
        self.assertIn('"test_run_summary_k13.py"', self.coverage)

    def test_k13_summary_is_in_unit_test_list(self):
        self.assertIn("test_run_summary_k13.py", self.unit_list)

    def test_all_runtime_summary_modules_are_mirrored(self):
        modules = sorted(p.name for p in HERE.glob("run_summary_*.py"))
        for name in modules + ["consolidate_summary.py"]:
            self.assertIn(f'"{name}|{name}"', self.mirror)
        self.assertEqual(
            set(modules),
            {line.split('|', 1)[0].strip().strip('"')
             for line in self.mirror.splitlines()
             if 'run_summary_' in line and '|' in line},
        )

    def test_consolidator_and_summary_module_share_k13_contract(self):
        self.assertIn('("k13", "K13 ayrı-step", _k13.render, _k13.status)', self.summary)
        self.assertIn('logs/k13_repro_manifest.json', self.summary)
        self.assertIn('def status(', self.k13)
        self.assertIn('def render(', self.k13)


if __name__ == "__main__":
    unittest.main()
