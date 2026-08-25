#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_incremental_doc_sync.py — publish_wrapper.sh --incremental doc-diff kapısı.

`docs/publish_wrapper.sh --incremental` akışı, `docs/PUBLISH_SCENARIO.md`
"INCREMENTAL PUSH — günlük döngü (repo canlı, 4 komut)" bölümündeki 4 adımla
birebir örtüşmelidir. Biri değişince diğeri bayat kalırsa bu test FAIL eder.

4 adımlı döngü (doc — tek kaynak):
  1) AŞAMA 0 kapıları:  bash docs/publish_precheck.sh --allow-remote
  2) Push:             git push origin main
  3) CI izleme:        RUN_ID=$(gh run list ...) + gh run watch $RUN_ID --exit-status
  4) Durum + artifact: gh run view $RUN_ID --json jobs + gh api ... artifacts

Wrapper, komutları `run` sarmalayıcısı + $OWNER/$REPO_NAME değişkenleriyle
yazar (dry-run'da `[DRY-RUN] çalıştırılacak: <komut>` basılır); doc literal
değerlerle yazar. Bu yüzden birebir satır diff'i yerine DEĞİŞMEMESİ GEREKEN
komut fiili/bayrak çapaları iki kaynakta da aranır. Ayrıca wrapper'ın
INCREMENTAL dalında 4 adımın SIRASIYLA (precheck → push → CI izle → durum)
yer aldığı statik olarak doğrulanır.

stdlib unittest — ağ/git çalıştırmaz (kaynak metin analizi).
"""
import pathlib
import re
import sys
import unittest

CIKTI = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(CIKTI))

import check_doc_wrapper_sync as sync  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[2]
DOC = ROOT / "docs" / "PUBLISH_SCENARIO.md"
WRAPPER = ROOT / "docs" / "publish_wrapper.sh"

# 4 adımlı INCREMENTAL döngü — her adımın komut fiili/bayrak çapaları.
# (adım etiketi, [İKİ dosyada da bulunması gereken literal parçalar])
INCREMENTAL_STEPS = [
    ("1-precheck", [
        "bash docs/publish_precheck.sh",
        "--allow-remote",
    ]),
    ("2-push", [
        "git push",
        "origin main",
    ]),
    ("3-ci-watch", [
        "gh run list",
        "gh run watch",
        "--exit-status",
    ]),
    ("4-status-artifacts", [
        "gh run view",
        "--json jobs",
        "--json artifacts",
        "actions/runs",
    ]),
]


class TestIncrementalDocSync(unittest.TestCase):
    """Doc'taki 4 adım ↔ wrapper --incremental dalı senkronu."""

    @classmethod
    def setUpClass(cls):
        cls.doc = DOC.read_text(encoding="utf-8")
        cls.wrap = WRAPPER.read_text(encoding="utf-8")

    def test_each_step_anchor_in_both_files(self):
        """Her adımın komut çapaları doc'ta VE wrapper'da mevcut."""
        missing = sync.check(self.doc, self.wrap, INCREMENTAL_STEPS)
        self.assertEqual(
            missing, [],
            f"INCREMENTAL doc↔wrapper drift: {missing}")

    def test_wrapper_has_incremental_flag(self):
        """Wrapper --incremental bayrağını tanımalı (akışın giriş noktası)."""
        self.assertIn("--incremental", self.wrap)
        self.assertIn("INCREMENTAL=1", self.wrap)

    def test_wrapper_incremental_skips_repo_creation(self):
        """--incremental: repo oluşturma atlanmalı (repo zaten canlı)."""
        # INCREMENTAL dalında 'repo oluşturma atlandı' log mesajı olmalı.
        self.assertIn("repo oluşturma atlandı", self.wrap)
        self.assertIn("--incremental — repo zaten canlı", self.wrap)

    def test_wrapper_incremental_requires_origin(self):
        """--incremental: origin remote ZORUNLU (ilk publish için değil)."""
        self.assertIn("origin remote gerektirir", self.wrap)

    def test_doc_has_four_step_section(self):
        """Doc'ta 'INCREMENTAL PUSH' 4 komutluk bölüm başlığı olmalı."""
        self.assertIn("INCREMENTAL PUSH", self.doc)
        self.assertIn("4 komut", self.doc)


class TestIncrementalStepOrder(unittest.TestCase):
    """Wrapper kaynağında 4 adımın SIRAYLA yer aldığını doğrular.

    Dry-run çıktısı wrapper'daki komut satırlarından türetildiği için,
    komutların kaynak içindeki sırası dry-run akışının sırasıdır.
    """

    @classmethod
    def setUpClass(cls):
        cls.wrap = WRAPPER.read_text(encoding="utf-8")

    def _index(self, needle):
        i = self.wrap.find(needle)
        self.assertNotEqual(i, -1, f"wrapper'da yok: {needle!r}")
        return i

    def test_precheck_before_push(self):
        self.assertLess(
            self._index("publish_precheck.sh"),
            self._index("git push -u origin main"))

    def test_push_before_ci_watch(self):
        self.assertLess(
            self._index("git push -u origin main"),
            self._index("gh run watch"))

    def test_ci_watch_before_status(self):
        self.assertLess(
            self._index("gh run watch"),
            self._index("gh run view"))

    def test_status_jobs_after_watch(self):
        # AŞAMA 4 (INCREMENTAL) job durumları, CI izlemeden sonra.
        self.assertLess(
            self._index("gh run watch"),
            self._index("--json jobs"))


class TestDryRunFlowAnchors(unittest.TestCase):
    """Dry-run çıktısının üreteceği komut çapaları wrapper'da mevcut.

    Dry-run modunda `run()` → `[DRY-RUN] çalıştırılacak: <komut>` basar ve
    bazı adımlar açık `[DRY-RUN]` log satırları yazar. Bu test, bu satırların
    üreteceği 4 adımlık komut fiillerinin wrapper kaynağında var olduğunu
    doğrular (birebir örtüşme kapısı).
    """

    @classmethod
    def setUpClass(cls):
        cls.wrap = WRAPPER.read_text(encoding="utf-8")

    def test_dry_run_preview_line_exists(self):
        self.assertIn("[DRY-RUN]", self.wrap)
        self.assertIn("çalıştırılacak", self.wrap)

    def test_dry_run_precheck_anchor(self):
        self.assertIn("publish_precheck.sh", self.wrap)
        self.assertIn("--allow-remote", self.wrap)

    def test_dry_run_ci_watch_anchor(self):
        # Dry-run'da CI izleme komutları önizlenir (gh run list + watch).
        self.assertIn("gh run list", self.wrap)
        self.assertIn("gh run watch", self.wrap)
        self.assertIn("--exit-status", self.wrap)

    def test_dry_run_artifact_anchor(self):
        self.assertIn("--json artifacts", self.wrap)

    def test_run_wrapper_prints_command(self):
        # run() dry-run'da komutu log'lar (komut fiili kaybolmaz).
        m = re.search(
            r"run\(\)\s*\{.*?DRY-RUN.*?çalıştırılacak",
            self.wrap, re.S)
        self.assertIsNotNone(
            m, "run() dry-run komut önizlemesi bulunamadı")


if __name__ == "__main__":
    unittest.main()
