#!/usr/bin/env python3
import pathlib
import sys
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

    def test_p1_remains_advisory(self):
        self.assertIn("K12 P1 drift: advisory (P0 yok)", self.job)

    def test_k12_scenario_sidecar_step_in_verify_job(self):
        """K13 deseni: verify job'ı [K12-SCENARIO] satırını ayrıştırıp
        logs/k12_repro_manifest.json sidecar'ına scenarios alanı olarak
        yazar (precommit-logs artifact'ı → precommit_logs manifest bölümü)."""
        self.assertIn("Run K12 scenarios (K13 pattern)", self.text)
        self.assertIn("[K12-SCENARIO]", self.text)
        self.assertIn("logs/k12_repro_manifest.json", self.text)
        self.assertIn('"scenarios": scenarios', self.text)


class PlistP1FailClosedJobTests(unittest.TestCase):
    """P1 drift (eksik / bayat / yapısal geçersiz plist) AYRI ve fail-closed
    bir job'da bloke eder — macOS `plist-check` advisory job'ından bağımsız.

    Sözleşme:
      1. Linux'ta koşar (render saf bash; plutil yoksa plistlib fallback),
         böylece P1 sinyali macOS runner'a bağlı kalmaz.
      2. Gerçek kapıyı çağırır (`check_plist_drift.py --json`) — yeniden
         yazılmış bir karşılaştırma değil, tek kaynak.
      3. `continue-on-error` YOK: script'in exit kodu (1 = P0/P1 drift,
         2 = koşulamadı) doğrudan job sonucudur.
      4. Türetilen required sette DEĞİL (GATE_EXCLUDE): canlı branch
         protection henüz bu check'i içermiyor; türetim ile canlı koruma
         drift'e düşmesin.
    """

    def setUp(self):
        self.text = WORKFLOW.read_text(encoding="utf-8")
        start = self.text.index("  plist-p1:")
        # Bir sonraki job ayracı: 2 boşluklu uzun çizgi yorum satırı.
        end = self.text.index("  # ─", start)
        self.job = self.text[start:end]

    def test_job_runs_real_gate_on_linux(self):
        self.assertIn("runs-on: ubuntu-latest", self.job)
        self.assertIn("check_plist_drift.py --json", self.job)

    def test_job_is_not_advisory(self):
        self.assertNotIn("continue-on-error", self.job,
                         "P1 kapısı advisory sınıfına düşürülmüş")
        self.assertIn('exit "$rc"', self.job,
                      "kapının exit kodu job'a iletilmiyor")

    def test_gate_exit_is_captured_and_reported(self):
        self.assertIn("rc=$?", self.job)
        self.assertIn("PLIST-P1: PASS", self.job)
        self.assertIn("fail_closed", self.job)

    def test_job_excluded_from_derived_required_set(self):
        sys.path.insert(0, str(ROOT / "_calisma" / "CIKTI"))
        import status_checks  # noqa: E402 — yol kurulduktan sonra
        self.assertIn("plist-p1", status_checks.GATE_EXCLUDE)
        self.assertNotIn("plist-p1", status_checks.gate_jobs())

    def test_macos_advisory_job_points_at_blocking_gate(self):
        self.assertIn("blokaj plist-p1 job'ında", self.text)



if __name__ == "__main__":
    unittest.main()
