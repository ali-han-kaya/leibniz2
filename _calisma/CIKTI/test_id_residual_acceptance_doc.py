#!/usr/bin/env python3
"""test_id_residual_acceptance_doc.py — Faz 3 kabul raporu sözleşmesi.

docs/ID_RESIDUAL_ACCEPTANCE.md:
  1) Hash geçiş defteri ölçülmüş tam kanonik hash'leri pinler
     (ad8fca69… tectonic tek-geçiş, a75c3409… pdfTeX tek-geçiş,
     544516b0… pdfTeX 3-geçiş) ve plan-donmuş çapraz-motor önekini
     (47681218…) sahte tam-hash üretmeden taşır.
  2) Teslim sidecar tectonic-era ikilisini (raw/stripped) kaydeder.
  3) Faz 4 referansı: verify_delivery.py --strict-determinism yeni
     semantiğine atıf içerir.

docs/FINAL_RC_REPORT.md kabul raporuna bağlanır.

stdlib-only, OFFLINE.
"""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
REPORT = ROOT / "docs" / "ID_RESIDUAL_ACCEPTANCE.md"
FINAL_RC = ROOT / "docs" / "FINAL_RC_REPORT.md"

TECTONIC_SINGLE = ("ad8fca69d4e4a2e1d67e497c8a7449f22"
                   "c8564f5e9b3790d0b6f85d90d318e1b")
PDFTEX_SINGLE = ("a75c340911801273b38be6ffb51a3482"
                 "0764b8f812d528dd2705d64117f1aa00")
PDFTEX_3PASS = ("544516b0d9d2f4c12b05b512b79b31ad"
                "238e82d3ca3aff81166a6bac1914f597")
DELIVERY_RAW = ("74b2cdbdb18fafbf5b3c87570c92f150"
                "0e7580469bcf4295b09734116df0779f")
DELIVERY_STRIPPED = ("50263bcf60f9ae176ac417f025bffbca"
                     "e4fd0ab6044566672827bee861f83732")


class TestIdResidualAcceptanceDoc(unittest.TestCase):
    def setUp(self):
        self.assertTrue(REPORT.is_file(),
                        "docs/ID_RESIDUAL_ACCEPTANCE.md yok (Faz 3 teslimi)")
        self.text = REPORT.read_text(encoding="utf-8")

    def test_ledger_pins_measured_canonical_hashes(self):
        for h, etiket in ((TECTONIC_SINGLE, "tectonic tek-geçiş"),
                          (PDFTEX_SINGLE, "pdfTeX tek-geçiş"),
                          (PDFTEX_3PASS, "pdfTeX 3-geçiş")):
            self.assertIn(h, self.text,
                          f"defter {etiket} tam kanonik hash pinlemeli")

    def test_ledger_marks_plan_frozen_cross_engine_prefix(self):
        # Plan probe'u tam hash'i dondurmadı — rapor öneki taşır ve
        # donmuş olduğunu işaretler (sahte tam-hash üretmez).
        self.assertIn("47681218", self.text)
        self.assertIn("donmuş", self.text)

    def test_delivery_sidecar_transition_row(self):
        self.assertIn(DELIVERY_RAW, self.text)
        self.assertIn(DELIVERY_STRIPPED, self.text)

    def test_phase4_strict_determinism_reference(self):
        self.assertIn("strict-determinism", self.text)
        self.assertIn("Faz 4", self.text)

    def test_final_rc_report_links_acceptance_report(self):
        final = FINAL_RC.read_text(encoding="utf-8")
        self.assertIn("docs/ID_RESIDUAL_ACCEPTANCE.md", final,
                      "FINAL_RC_REPORT kabul raporuna bağlanmalı")


if __name__ == "__main__":
    unittest.main()
