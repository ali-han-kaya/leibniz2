#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_doc_artifact_sync.py — PUBLISH_SCENARIO artifact listesi ↔ ARTIFACT_JOBS senkron kapısı.

docs/PUBLISH_SCENARIO.md'deki "Artifact listesi (N):" bölümü, run'ın
yüklediği TÜM artifact'ları belgeler. gen_repro_manifest.ARTIFACT_JOBS ise
reproducibility manifest'inin kapsadığı artifact → job kaynağı eşlemesidir
(TEK KAYNAK kuralı: ARTIFACT_JOBS + verify.yml birlikte değiştirilir).

Invariantlar (fail-closed):
  1. ARTIFACT_JOBS'taki HER artifact doc listesinde VAR olmalı — manifest
     kapsamındaki bir artifact belgelenmezse denetim izi eksik kalır.
  2. Doc'taki fazlalıklar (ARTIFACT_JOBS'da olmayanlar) TAM OLARAK
     {mirror-check, daemon-http, ci-simulate, audit-refs-trend,
     audit-live-ci, changelog-drift} olmalı — reproducibility job'ı bu
     advisory artifact'ları indirmez; başka bir fazlalık =
     doc/ARTIFACT_JOBS drift'i.
  3. "Artifact listesi (N)" başlığındaki N sayısı ayrıştırılan ad
     sayısıyla birebir olmalı (bayat sayı = liste güncellenmemiş).

Reuse: doc ayrıştırması audit_live_ci_sync.parse_doc_artifacts (canlı CI
denetiminin aynı parser'ı — iki kapı aynı doc sözleşmesini kullanır).

stdlib unittest — ek bağımlılık yok.
"""
import pathlib
import re
import sys
import unittest

CIKTI = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(CIKTI))

import audit_live_ci_sync as als  # noqa: E402
import gen_repro_manifest as gen_manifest  # noqa: E402

# Reproducibility download kapsamı DIŞINDA kalan doc artifact'ları (advisory
# job'ların çıktıları). ARTIFACT_JOBS'a girmemeleri BİLEREK — merge pattern'e
# girmezler, manifest'e girmezler; doc'ta görünmeleri doğrudur.
DOC_ONLY_ADVISORY = frozenset({
    "mirror-check",     # macOS fail-closed (K17) — job output
    "daemon-http",      # advisory smoke — job output
    "ci-simulate",      # advisory yerel CI simülasyonu — job output
    "audit-refs-trend", # advisory denetim — job output
    "audit-live-ci",    # advisory meta-denetçi — job output
    "changelog-drift",  # advisory: gen_changelog --check drift logu — job output
})

DOC = pathlib.Path("docs/PUBLISH_SCENARIO.md")

_HEADER_RE = re.compile(r"^\*\*Artifact listesi\s*\((\d+)\):\*\*\s*$")


def _doc_text():
    return DOC.read_text(encoding="utf-8")


def _header_count(doc_text):
    for ln in doc_text.splitlines():
        m = _HEADER_RE.match(ln.strip())
        if m:
            return int(m.group(1))
    return None


class TestDocArtifactSync(unittest.TestCase):
    """Gerçek doc ↔ ARTIFACT_JOBS çapraz doğrulaması (repo kökünden koşulur)."""

    @classmethod
    def setUpClass(cls):
        if not DOC.is_file():
            raise unittest.SkipTest(f"{DOC} yok — repo kökünden koşulmalı")
        cls.doc_names = als.parse_doc_artifacts(_doc_text())

    def test_doc_has_artifact_section(self):
        self.assertTrue(self.doc_names, "doc'ta 'Artifact listesi' bölümü yok")

    def test_header_count_matches_parsed_names(self):
        n = _header_count(_doc_text())
        self.assertIsNotNone(n, "'Artifact listesi (N):' başlığı bulunamadı")
        self.assertEqual(n, len(self.doc_names),
                         f"başlık {n} diyor, liste {len(self.doc_names)} ad içeriyor")

    def test_every_artifact_jobs_key_documented(self):
        # Invariant 1: manifest kapsamındaki her artifact doc'ta var.
        missing = sorted(set(gen_manifest.ARTIFACT_JOBS) - set(self.doc_names))
        self.assertEqual(missing, [],
                         "ARTIFACT_JOBS'ta olup doc listesinde OLMAYAN artifact'lar: "
                         f"{missing} — doc'a ekleyin veya ARTIFACT_JOBS'tan çıkarın")

    def test_doc_extras_are_exactly_known_advisory(self):
        # Invariant 2: doc fazlalıkları tam olarak bilinen advisory set.
        extras = sorted(set(self.doc_names) - set(gen_manifest.ARTIFACT_JOBS))
        self.assertEqual(extras, sorted(DOC_ONLY_ADVISORY),
                         "doc'ta ARTIFACT_JOBS'da olmayan beklenmedik artifact'lar: "
                         f"{extras} — beklenen advisory set: {sorted(DOC_ONLY_ADVISORY)}")

    def test_reproducibility_artifact_documented(self):
        # Manifest'in kendisi de listede olmalı (kapsayıcı artifact).
        self.assertIn("reproducibility", self.doc_names)


class TestDocParsing(unittest.TestCase):
    """Parser'ın doc sözleşmesine duyarlılığı (mock metinler, OFFLINE)."""

    def test_splits_plus_artifacts(self):
        doc = ("**Artifact listesi (2):**\n"
               "- `budget-verify` + `budget` (bütçe sidecar + aggregator)\n")
        self.assertEqual(als.parse_doc_artifacts(doc), ["budget-verify", "budget"])

    def test_stops_at_next_heading(self):
        doc = ("**Artifact listesi (1):**\n"
               "- `unit-tests` (log)\n"
               "**Not:** Kapı ...\n"
               "- `reports` (sonraki başlık altında — YAKALANMAMALI)\n")
        self.assertEqual(als.parse_doc_artifacts(doc), ["unit-tests"])

    def test_ignores_backticks_in_description(self):
        doc = ("**Artifact listesi (1):**\n"
               "- `verify-report` (tek log: K1-K14 + `--full` bölümü)\n")
        self.assertEqual(als.parse_doc_artifacts(doc), ["verify-report"])

    def test_no_section_returns_empty(self):
        self.assertEqual(als.parse_doc_artifacts("başlık yok\n"), [])

    def test_header_count_regex(self):
        self.assertEqual(_header_count("**Artifact listesi (24):**\n"), 24)
        self.assertIsNone(_header_count("**Artifact listesi:**\n"))
        self.assertIsNone(_header_count("başka metin\n"))


if __name__ == "__main__":
    unittest.main()
