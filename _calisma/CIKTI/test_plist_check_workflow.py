#!/usr/bin/env python3
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "verify.yml"


class PlistWorkflowContractTests(unittest.TestCase):
    def setUp(self):
        self.text = WORKFLOW.read_text(encoding="utf-8")
        start = self.text.index("  plist-check:")
        end = self.text.index("  # DAEMON MODE HTTP 200", start)
        self.job = self.text[start:end]

    def test_p0_has_explicit_fail_closed_step(self):
        self.assertIn("Fail plist-check on P0 finding", self.job)
        self.assertIn('has_p0=$(python3 -c', self.job)
        self.assertIn('echo "K12-PLIST-EXTRA P0: plist drift job fail-closed"', self.job)
        self.assertIn("exit 1", self.job)

    def test_self_heal_does_not_hide_p0(self):
        self.assertIn("Self-heal extra plist drift (P0)", self.job)
        self.assertIn("Fail plist-check on P0 finding", self.job)
        self.assertLess(self.job.index("Self-heal extra plist drift (P0)"),
                        self.job.index("Fail plist-check on P0 finding"))

    def test_p1_fails_closed(self):
        """P1 (bayat/eksik/geçersiz) ADVISORY değil: adım exit 1 eder.

        Sinyal post-self-heal sidecar'ından okunur — `fail_closed`
        (= has_p0 or has_p1) — böylece P0 temizliği P1'i maskelemez. Sidecar
        okunamazsa adım 1'in rc'si yedek fail-closed sinyaldir.
        """
        self.assertIn("Fail plist-check on P1 finding", self.job)
        self.assertIn("plist_drift_golden.json", self.job)
        self.assertIn('d.get("fail_closed")', self.job)
        self.assertIn('DRIFT_RC', self.job)
        self.assertIn("exit 1", self.job)
        # Advisory rapor satırı kaldırıldı — P1 sessizce geçemez.
        self.assertNotIn("P1 drift: advisory", self.job)
        self.assertNotIn("Write plist P1 advisory note", self.job)
        # P1 adımı P0 adımından SONRA koşar (tanı sırası korunur).
        self.assertLess(self.job.index("Fail plist-check on P0 finding"),
                        self.job.index("Fail plist-check on P1 finding"))

    def test_p1_step_is_not_continue_on_error(self):
        """P1 adımı continue-on-error taşımaz (fail-closed)."""
        start = self.job.index("Fail plist-check on P1 finding")
        header = self.job[start:].split("- name:")[0]
        self.assertNotIn("continue-on-error", header)

    def test_k12_scenario_sidecar_step_in_verify_job(self):
        """K13 deseni: verify job'ı [K12-SCENARIO] satırını ayrıştırıp
        logs/k12_repro_manifest.json sidecar'ına scenarios alanı olarak
        yazar (precommit-logs artifact'ı → precommit_logs manifest bölümü)."""
        self.assertIn("Run K12 scenarios (K13 pattern)", self.text)
        self.assertIn("[K12-SCENARIO]", self.text)
        self.assertIn("logs/k12_repro_manifest.json", self.text)
        self.assertIn('"scenarios": scenarios', self.text)


if __name__ == "__main__":
    unittest.main()
