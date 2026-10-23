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
# SDE sabitlenmiş CI-linux + yerel bağlamlar (2026-10-02 olçümü). Kanonik
# hash SOURCE_DATE_EPOCH'a BAĞLIDIR; bu iki satır aynı SDE ile ölçüldü.
PINNED_SDE = "1786924800"
CI_PINNED = ("ca3c591805eff4cbae403a77cba9b873"
             "4bf9c23ed42e766b937207e36a159573")
LOCAL_PINNED = ("10d44856ba56c6f7335b7ed048f8359"
                "5eb298999744f0c26cec022d52227e2db")
CI_IMAGE_DIGEST = ("a853f94d226358a79c740cfc7bce0c28"
                   "9748f3fe3488d921d038ccd752c61b60")

MAKEFILE = ROOT / "docs" / "Makefile.texlive"
WORKFLOW = ROOT / ".github" / "workflows" / "verify.yml"


class TestSourceDateEpochContract(unittest.TestCase):
    """`check`/`accept` de `pdf` ile AYNI epoch'u kullanmalı.

    OLCUM 2026-10-02: `pdf` hedefi epoch'u ihraç ediyordu, `check`/`accept`
    etmiyordu; determinizm betiği varsayılanına (`:-0`) düşüyordu. Sonuç:
    kabul edilen PDF ile teslim edilen PDF FARKLI epoch ile derleniyordu
    (pdf → 57c91a07…, check → 544516b0…). Ihraç geri alınırsa kabul yine
    üretileni yargılamaz.
    """

    def setUp(self):
        self.assertTrue(MAKEFILE.is_file(), "docs/Makefile.texlive yok")
        self.text = MAKEFILE.read_text(encoding="utf-8")

    def _check_recipe_env(self):
        """check tarifinin ortam blogu (TEX_SOURCE → bash satırı)."""
        start = self.text.index("TEX_SOURCE=")
        return self.text[start:self.text.index('bash "$(DETERMINISM_SCRIPT)"', start)]

    def test_check_recipe_exports_source_date_epoch(self):
        env = self._check_recipe_env()
        self.assertIn('SOURCE_DATE_EPOCH="$(SOURCE_DATE_EPOCH)"', env,
                      "check/accept epoch'u ihraç etmiyor — kabul edilen byte'lar "
                      "üretilen byte'lar değil")

    def test_pdf_recipe_still_exports_epoch(self):
        self.assertIn('SOURCE_DATE_EPOCH="$(SOURCE_DATE_EPOCH)"', self.text)


class TestPinnedCiContext(unittest.TestCase):
    """R3 kapanışı: CI-linux kabulü digest-pini bağlamda koşmalı.

    OLCUM 2026-10-02: §4 satır 6 (`092154a0…`) oluşturulduğu gün birebir
    tekrarlanıyordu; aynı tarif bugün farklı hash veriyor (pdfTeX 1.40.29 →
    1.40.25). `runs-on: ubuntu-latest` üzerinde kabul koşmak aynı borcu
    yeniden üretir — pin kaldırılırsa bu test kırmızıya döner.
    """

    def setUp(self):
        self.assertTrue(WORKFLOW.is_file(), "verify.yml yok")
        self.wf = WORKFLOW.read_text(encoding="utf-8")
        self.assertTrue(REPORT.is_file())
        self.doc = REPORT.read_text(encoding="utf-8")

    def test_ci_job_runs_accept_in_pinned_container(self):
        self.assertIn("texlive-accept:", self.wf)
        self.assertIn("Makefile.texlive accept", self.wf)
        self.assertIn(CI_IMAGE_DIGEST, self.wf,
                      "CI kabulü digest-pini konteyner olmaktan çıktı — apt "
                      "TeXLive sürüm kaymasına açık")

    def test_ci_job_pins_source_date_epoch(self):
        self.assertIn("SOURCE_DATE_EPOCH=%s make" % PINNED_SDE, self.wf,
                      "CI kabulü SDE'yi sabitlemiyor — kanonik hash kayar")

    def test_ledger_pins_both_contexts_with_full_hashes(self):
        for h in (CI_PINNED, LOCAL_PINNED):
            self.assertIn(h, self.doc, "SDE sabitli bağlam satırı eksik: %s…" % h[:8])

    def test_ledger_rows_record_the_sde(self):
        """Kanonik hash SDE'ye bağlı; satır SDE taşımıyorsa yeniden
        üretilemez."""
        for h in (CI_PINNED, LOCAL_PINNED):
            row = next((ln for ln in self.doc.splitlines()
                        if h[:16] in ln), None)
            self.assertIsNotNone(row, "satır bulunamadı: %s…" % h[:8])
            self.assertIn(PINNED_SDE, row, "satır SDE'yi taşımıyor")

    def test_stale_ci_row_is_explained_not_deleted(self):
        """Satır 6 üretilmiyor ama SİLİNMEDİ — protokol yeni bağlam → yeni
        satır der; açıklama satırın yanında durmalı."""
        self.assertIn("092154a0", self.doc)
        self.assertIn("artık üretilmiyor", self.doc)


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
