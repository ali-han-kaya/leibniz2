#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_workflow_contract.py — workflow_contract.py tek-kaynak sözleşme kapısı.

workflow_contract.py, verify.yml sözleşme kümelerinin TEK kopyasını taşır.
Bu meta-test:
  1. Üretici modüllerin (summary_pattern_drift, check_pattern_consistency,
     check_workflow_artifact_docs) kendi EXCLUDED/muafiyet attr'larının
     fixture ile BİREBİR aynı olduğunu doğrular — biri kaçarsa drift FAIL.
  2. Lazy re-export'ların (ARTIFACT_JOBS, GATE_EXCLUDE) üretici
     attr'larıyla özdeş olduğunu doğrular.
  3. Küme içi tutarlılığı pin'ler (DOC_ONLY ⊆ UPLOAD_EXCEPTIONS,
     merge-excluded kümesi ARTIFACT_JOBS ile kesişir vb.).

Yeni bir job/artifact eklendiğinde GÜNCELLENECEK TEK dosya:
workflow_contract.py (gerekçe satırlarıyla). Kapılar ve testler onu
içe aktarır; bu test ayrışıyı commit anında yakalar.

stdlib unittest — import-only, hızlı (<0.5s).
"""
import pathlib
import sys
import unittest

CIKTI = pathlib.Path(__file__).resolve().parent
if str(CIKTI) not in sys.path:
    sys.path.insert(0, str(CIKTI))

import workflow_contract as wc  # noqa: E402


class TestProducersMatchFixture(unittest.TestCase):
    """Üretici attr'ları fixture ile birebir — drift anında FAIL."""

    def test_summary_pattern_drift_excluded(self):
        import summary_pattern_drift as spd
        self.assertEqual(set(spd.EXCLUDED), set(wc.MERGE_PATTERN_EXCLUDED),
                         "summary_pattern_drift.EXCLUDED fixture'dan "
                         "koptu — workflow_contract.py'i güncelleyin ve "
                         "üreticiyi ondan içe aktarın")

    def test_check_pattern_consistency_excluded(self):
        import check_pattern_consistency as cpc
        self.assertEqual(set(cpc.EXCLUDED), set(wc.MERGE_PATTERN_EXCLUDED),
                         "check_pattern_consistency.EXCLUDED fixture'dan "
                         "koptu — workflow_contract.py'i güncelleyin ve "
                         "üreticiyi ondan içe aktarın")

    def test_check_workflow_artifact_docs_upload_exceptions(self):
        import check_workflow_artifact_docs as cwad
        self.assertEqual(set(cwad.UPLOAD_EXCEPTIONS),
                         set(wc.UPLOAD_EXCEPTIONS),
                         "check_workflow_artifact_docs muafiyet kümesi "
                         "fixture'dan koptu")


class TestLazyReExports(unittest.TestCase):
    """ARTIFACT_JOBS / GATE_EXCLUDE re-export'ları üreticiyle özdeş."""

    def test_artifact_jobs_is_same_object(self):
        import gen_repro_manifest as grm
        self.assertIs(wc.ARTIFACT_JOBS, grm.ARTIFACT_JOBS)

    def test_gate_exclude_is_same_object(self):
        try:
            import status_checks as sc  # noqa: E402
            self.assertIs(wc.GATE_EXCLUDE, sc.GATE_EXCLUDE)
        except SystemExit as e:
            # yaml yoksa status_checks import'u exit(2) — CI bare python'da
            # test suite'in BÜTÜNÜ (errors=1) ölmesin: bu prodült bir
            # environment hatası, contract hatası değil. Kapı, yaml kurulu
            # ortamda (venv, pre-commit) başarısız olsun yeter.
            self.skipTest(f"status_checks import PyYAML yok (bare runner) — exit {e.code}")


class TestSetConsistency(unittest.TestCase):
    """Kümeler arası yapısal invariantlar."""

    def test_doc_only_advisory_subset_of_upload_exceptions(self):
        self.assertTrue(wc.DOC_ONLY_ADVISORY <= wc.UPLOAD_EXCEPTIONS,
                        "doc-only advisory bir gün upload muafiyetinden "
                        "düşerse check_workflow_artifact_docs Fazla "
                        "raporlamaya başlar")

    def test_merge_excluded_intersect_artifact_jobs(self):
        # Üyeler gerçek artifact adları olmalı (yazım hatası yakalayıcı).
        unknown = wc.MERGE_PATTERN_EXCLUDED - set(wc.ARTIFACT_JOBS)
        self.assertFalse(unknown,
                         f"ARTIFACT_JOBS'ta olmayan merge-excluded üyeleri: "
                         f"{sorted(unknown)}")

    def test_merge_excluded_frozen(self):
        # Yanlışlıkla mutasyona kapı açılmamalı — tek kaynak donuk kalır.
        self.assertIsInstance(wc.MERGE_PATTERN_EXCLUDED, frozenset)
        self.assertIsInstance(wc.DOC_ONLY_ADVISORY, frozenset)
        self.assertIsInstance(wc.UPLOAD_EXCEPTIONS, frozenset)

    def test_dir_includes_lazy_names(self):
        self.assertIn("ARTIFACT_JOBS", dir(wc))
        self.assertIn("GATE_EXCLUDE", dir(wc))

    def test_unknown_lazy_attr_raises(self):
        with self.assertRaises(AttributeError):
            wc.NO_SUCH_CONTRACT_ATTR


if __name__ == "__main__":
    unittest.main()
