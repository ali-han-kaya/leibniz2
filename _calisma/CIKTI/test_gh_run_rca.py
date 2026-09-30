#!/usr/bin/env python3
"""test_gh_run_rca.py — gh_run_rca.py sözleşme-süiti.

Repo geleneği: yeni kapı/betiğin sözleşmesi önce TDD-kırmızıyla sabitlenir.
Bu süit:

  1) RULES sıralaması: özel-desen önce — manifest-drift < octokit < trivy
     < timeout < unittest < failure_summary < hook < exit-code.
  2) analyze_log: her sınıf-kanonu (sentetik log'larda) doğru kuralla
     sınıflanır; kural-yoksa genel exit-code-kanonu.
  3) build_table: deterministik sıralama (KURAL,JOB,STEP), sütun-bütünlüğü
     (adlarından bağımsız), determinizm (iki üretim birebir).
  4) main() uçları: --log-file fail-closed (hata-rc=2), default-rc=1
     (kırmızı-koşumda çıktı + hedefli-remedy), --out belirtilen yola yazar.
  5) Gerçek-gh yolu: subprocess-call yüzeyi gmock-gh ile birebir sabit;
     gh yoksa rc=2 (fail-closed — sessiz-çözümleme yok).
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import gh_run_rca as rca  # noqa: E402

FAIL_MSG = "check-unit-tests: manifest/HOOK_COVERAGE drift — commit bloke."


def _log(lines):
    return "\n".join(lines)


class TestRuleOrdering(unittest.TestCase):
    def test_rules_special_before_general(self):
        """Manifest-drift en özel, exit-code en genel — indeks sırası sabit."""
        names = [name for name, _, _ in rca.RULES]
        self.assertLess(names.index("manifest-drift"),
                        names.index("exit-code"))
        self.assertLess(names.index("octokit"),
                        names.index("unittest"))
        self.assertLess(names.index("trivy"), names.index("unittest"))
        self.assertLess(names.index("unittest"), names.index("failure_summary"))
        self.assertLess(names.index("failure_summary"), names.index("hook"))
        self.assertLess(names.index("hook"), names.index("exit-code"))


class TestAnalyzeLog(unittest.TestCase):
    """Her sınıf-kanonu sentetik log'da doğru kuralla sınıflanır."""

    def _classify(self, lines):
        e, r = rca.analyze_log(_log(lines))
        return e, r

    def test_manifest_drift(self):
        err, rule = self._classify([
            "Unit tests for new gates (fail-closed manifest)...............Failed",
            "check-unit-tests: manifest/HOOK_COVERAGE drift — commit bloke.",
            "  remedy: python3 _calisma/CIKTI/sync_check_unit_tests.py --update",
        ])
        self.assertEqual(rule, "manifest-drift")

    def test_octokit(self):
        err, rule = self._classify([
            "Octokit metod adı denetimi (fail-closed).................Failed",
            "bad.js: orgs.get — bilinmeyen Octokit metodu (izinli listede yok)",
        ])
        self.assertEqual(rule, "octokit")

    def test_trivy_fail_closed(self):
        err, rule = self._classify([
            "Annotate PR with Trivy findings (fail-closed)............Failed",
            "Trivy SARIF bulunamadı veya bozuk: trivy.sarif",
        ])
        self.assertEqual(rule, "trivy")

    def test_timeout(self):
        err, rule = self._classify([
            "verify-delivery (K1-K14)...The job running on runner "
            "localhost has exceeded the maximum execution time of 120 minutes.",
        ])
        self.assertEqual(rule, "timeout")

    def test_unittest(self):
        err, rule = self._classify([
            "======================================================================",
            "FAIL: test_missing_permissions_fails "
            "(_calisma.CIKTI.test_ci_hygiene_gate.TestC)",
            "AssertionError: 0 is not true",
            "----------------------------------------------------------------------",
            "Ran 9 tests in 0.96s",
            "FAILED (failures=1)",
        ])
        self.assertEqual(rule, "unittest")
        self.assertIn("test_missing_permissions_fails", err[0])

    def test_failure_summary_prefers_failing_name(self):
        """Çoklu-adım log'unda başarılı-adları sınıfta düşer (FP-önleme)."""
        err, rule = self._classify([
            "Octokit metod adı denetimi (fail-closed).................Passed",
            "check-colorize-rules regression gate...........Failed",
            "FAILED: 1 check-colorize-rules hücresi kırmızı",
        ])
        self.assertEqual(rule, "failure_summary")
        self.assertIn("check-colorize-rules", err[0])

    def test_hook(self):
        err, rule = self._classify([
            "extract unstaged dependency findings from hook output...Failed",
            "- hook id: check-colorize-rules",
            "- exit code: 1",
        ])
        self.assertEqual(rule, "hook")
        self.assertIn("hook id: check-colorize-rules", err[0])

    def test_generic_exit_code(self):
        err, rule = self._classify([
            "some job step output",
            "##[error] Process completed with exit code 1.",
        ])
        self.assertEqual(rule, "exit-code")
        self.assertIn("##[error]", err[0])

    def test_no_match_fails_closed(self):
        err, rule = self._classify(["everything looks fine"])
        self.assertIsNone(rule)
        self.assertEqual(err, [])


class TestBuildTable(unittest.TestCase):
    def test_rows_sorted_and_complete(self):
        rows = rca.build_table([
            {"rule": "hook", "job": "verify", "step": "Extract …", "err": "hook id: b"},
            {"rule": "manifest-drift", "job": "verify", "step": "Unit tests …", "err": "drift"},
            {"rule": "exit-code", "job": "docker-security", "step": "Scan …", "err": "exit code 1"},
        ])
        self.assertEqual([r["RULE"] for r in rows],
                         ["exit-code", "hook", "manifest-drift"])
        for row in rows:
            self.assertEqual(list(row.keys()),
                             ["RULE", "JOB", "STEP", "KÖK-NEDEN KANITI", "REMEDY"])

    def test_deterministic(self):
        rows_in = [{"rule": "hook", "job": "j", "step": "s", "err": "e"}]
        self.assertEqual(rca.build_table(rows_in), rca.build_table(rows_in))


GH_VIEW_JS = json.dumps({
    "conclusion": "failure", "displayTitle": "verify",
    "jobs": [{"name": "verify / build", "conclusion": "failure",
              "steps": [{"name": "Unit tests for new gates (fail-closed manifest)",
                         "conclusion": "failure"}]}]})


class TestMainFlow(unittest.TestCase):
    """main() uçları: --log-file fail-closed, default-rc=1, --out."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="rca_test_")
        self._old_gh = rca.GH

    def tearDown(self):
        rca.GH = self._old_gh

    def test_log_file_ok_rc1(self):
        log = os.path.join(self.tmp, "f.txt")
        with open(log, "w", encoding="utf-8") as f:
            f.write("check-unit-tests: manifest/HOOK_COVERAGE drift — commit bloke.\n")
        out = rca.main(["--log-file", log])
        self.assertEqual(out, 1)

    def test_log_file_bad_rc2(self):
        out = rca.main(["--log-file", "/nonexistent/xyz"])
        self.assertEqual(out, 2)

    def test_out_writes_report(self):
        log = os.path.join(self.tmp, "f.txt")
        with open(log, "w", encoding="utf-8") as f:
            f.write("check-unit-tests: manifest/HOOK_COVERAGE drift — commit bloke.\n")
        rep = os.path.join(self.tmp, "rapor.md")
        out = rca.main(["--log-file", log, "--out", rep])
        self.assertEqual(out, 1)
        self.assertTrue(os.path.isfile(rep))
        with open(rep, encoding="utf-8") as f:
            body = f.read()
        self.assertIn("KÖK-NEDEN KANITI", body)
        self.assertIn("sync_check_unit_tests.py --update", body)

    def test_gh_path_uses_view_and_log_failed(self):
        """--run yolu gh run view --json jobs + log-failed yüzeyini kullanır
        (gmock-gh ile birebir sabit); gh yoksa rc=2 fail-closed."""
        calls = []
        log = os.path.join(self.tmp, "f.txt")
        with open(log, "w", encoding="utf-8") as f:
            f.write("check-unit-tests: manifest/HOOK_COVERAGE drift — commit bloke.\n")

        def fake_gh(argv):
            calls.append(list(argv))
            # --log-failed ÖNCE: argv[:3] ön-ek-karşılaştırması ikinci
            # çağrımı da yakalar (testsahibi-tuzak — üretim etkilenmez).
            if "--log-failed" in argv:
                with open(log, encoding="utf-8") as f:
                    return 0, f.read()
            if argv[:3] == ["run", "view", "123"]:
                return 0, GH_VIEW_JS
            return 1, "unexpected"

        rca.GH = fake_gh
        out = rca.main(["--run", "123"])
        self.assertEqual(out, 1)
        self.assertEqual(calls[0][:3], ["run", "view", "123"])
        self.assertIn("--json jobs", " ".join(calls[0]))
        self.assertTrue(any("--log-failed" in c for c in calls))

    def test_gh_missing_is_usage_error(self):
        rca.GH = None
        out = rca.main(["--run", "123"])
        self.assertEqual(out, 2)


if __name__ == "__main__":
    unittest.main()
