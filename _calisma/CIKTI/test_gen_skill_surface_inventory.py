#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_gen_skill_surface_inventory.py — üretilen envanter dokümanının sözleşmesi.

Envanter dokümanı ELLE yazılmaz; `skill_surfaces.list` + `check_skill_surfaces.py`
canlı ölçümünden ÜRETİLİR. Üretilen bir dokümanın asıl riski çürümesidir:

  * `--check` bayaltsa exit 1 (kapı fail-closed) — sürükleyen cipler.
  * Kanıt bağlantıları (`EVIDENCE`, `UNREGISTERED_EVIDENCE`) findings.md'deki
    BÖLÜM BAŞLIKLARINA işaret eder. Başlık yeniden adlanırsa bu test kırılır;
    aksi halde doküman var olmayan bir kanıta atıf yapardı ve BİZE YANLIŞ
    güvence verirdi. Bu, "test var" diye geçmeye en kolay yolun kapatılması.

Bu dosya `check_unit_tests.list` içindedir (batarya koşar — üretici saf metin
üretir, Next/Chromium istemez).
"""

import io
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)

from _calisma.CIKTI import check_skill_surfaces as gate  # noqa: E402
from _calisma.CIKTI import gen_skill_surface_inventory as gen  # noqa: E402


class EvidenceAnchorTest(unittest.TestCase):
    """Kanıt bağlantıları canlı mı? (bölüm yeniden adlandıysa kırılır)"""

    def setUp(self):
        with open(gen.FINDINGS, encoding="utf-8") as fh:
            self.findings = fh.read()

    def test_every_zero_domain_has_a_live_evidence_section(self):
        for domain in gen.EVIDENCE:
            ev = gen.EVIDENCE[domain]
            section = ev.get("section")
            self.assertTrue(section, "%s: kanıt bölümü tanımsız" % domain)
            self.assertIn(section, self.findings,
                          "findings.md'de bölüm YOK: %r (%s alanı). Bölüm "
                          "yeniden adlandıysa EVIDENCE güncellenmeli."
                          % (section, domain))

    def test_every_unregistered_evidence_has_a_live_section(self):
        for domain, ev in gen.UNREGISTERED_EVIDENCE.items():
            self.assertIn(ev["section"], self.findings,
                          "findings.md'de bölüm YOK: %r (%s). Yeniden adlandıysa"
                          " UNREGISTERED_EVIDENCE güncellenmeli."
                          % (ev["section"], domain))

    def test_every_zero_domain_in_manifest_has_evidence(self):
        """Manifest'teki HER zero-surface alanının kanıt bağlantısı olmalı."""
        ok, _findings, report = gate.check(root=ROOT)
        self.assertTrue(ok, "kapı yeşil değil — önce onu düzelt")
        for domain in report["zero_domains"]:
            self.assertIn(domain, gen.EVIDENCE,
                          "manifest zero-surface alanı %s için kanıt bağlantısı "
                          "yok; doküman '—' basar" % domain)

    def test_every_evidence_domain_is_actually_zero_surface(self):
        """Kanıt haritası yalnız GERÇEKTEN sıfır-yüzey alanları için olmalı."""
        ok, _findings, report = gate.check(root=ROOT)
        self.assertTrue(ok)
        for domain in gen.EVIDENCE:
            self.assertIn(domain, report["zero_domains"],
                          "%s artık manifest'te zero-surface DEĞİL — kanıt "
                          "haritasından çıkarılmalı" % domain)


class GeneratedDocTest(unittest.TestCase):
    """Üretilen dokümanın yapısı ve drift davranışı."""

    @classmethod
    def setUpClass(cls):
        cls.text, cls.data = gen.build(ROOT)

    def test_gate_is_green_so_doc_is_authoritative(self):
        self.assertTrue(
            self.data["ok"],
            "kapı kırmızıyken doküman üretilmemeli/yenilenmemeli: %s"
            % self.data["findings"])

    def test_doc_declares_itself_generated(self):
        self.assertIn("ÜRETİLMİŞ DOSYA", self.text,
                      "doc 'elle düzenleme' damgası taşımıyor — birisi "
                      "elle düzenlemeye çalışır")

    def test_doc_shows_all_zero_surfaces(self):
        for domain in self.data["zero_domains"]:
            self.assertIn("`%s`" % domain, self.text,
                          "sıfır-yüzey alanı tabloda görünmüyor: %s" % domain)

    def test_doc_reports_zero_surface_via_measured_counts(self):
        """'İddia geçerli' hücresi ÖLÇÜMden gelmeli, elle yazılmış olmamalı."""
        _, _, report = gate.check(root=ROOT)
        self.assertIn("0/%d" % len(gate.ZERO_SIGNATURES["rn-expo"]), self.text,
                      "rn-expo ölçülmüş imza sayısı dokümanda yok")

    def test_unregistered_gap_is_surfaced(self):
        """Manifest dışı kanıt dokümanda GÖRÜNMEZSE boşluk çürür."""
        self.assertIn("Manifest'te olmayan kanıt", self.text)
        for domain in gen.UNREGISTERED_EVIDENCE:
            self.assertIn("`%s`" % domain, self.text,
                          "manifest dışı alan görünmüyor: %s" % domain)

    def test_gap_section_measures_rather_than_asserts(self):
        """Boşluk bölümü iddiada değil ÖLÇÜMDE dayanmalı ('= 0' rakamları)."""
        self.assertIn("git-tracked", self.text)
        self.assertIn("= 0", self.text,
                      "boşluk bölümü bağımsız ölçüm basmıyor")

    def test_identity_mirrors_are_labelled_not_packages(self):
        """Ayna satırları 'paket' diye sunulmamalı — kimliktir."""
        self.assertIn("Kimlik aynaları", self.text)
        for alias in gate.IDENTITY_ALIASES:
            self.assertIn("`%s`" % alias, self.text)

    def test_no_unmeasured_verdict_words(self):
        """'PASS' gibi ölçülmemiş bir verdict basılmamalı."""
        self.assertNotIn("PASS:", self.text)

    def test_check_mode_detects_drift(self):
        """Bayalma kırmızıya dönmeli — `--check` sözleşmesi."""
        import tempfile

        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False,
                                         encoding="utf-8") as fh:
            fh.write("# bayat sürüm\n")
            stale = fh.name
        self.addCleanup(os.unlink, stale)
        rc = gen.main(["--check", "--out", stale, "--root", ROOT])
        self.assertEqual(rc, 1, "bayat doküman exit 1 vermeli")

    def test_check_mode_passes_on_fresh_output(self):
        """Diskteki doküman bayatsa --check KIRMIZI olmalıdır.

        Bu, dokümanın diskte gerçekten senkron olduğunu da doğrular.
        """
        rc = gen.main(["--check", "--out", gen.OUT_PATH, "--root", ROOT])
        self.assertEqual(rc, 0,
                         "diskteki doküman bayat — yeniden üret: python3 "
                         "_calisma/CIKTI/gen_skill_surface_inventory.py")

    def test_json_mode_is_machine_readable(self):
        buf = io.StringIO()
        old, sys.stdout = sys.stdout, buf
        try:
            rc = gen.main(["--json", "--root", ROOT])
        finally:
            sys.stdout = old
        self.assertEqual(rc, 0)
        self.assertIn("zero_domains", buf.getvalue())


class TrackedCountTest(unittest.TestCase):
    """`git ls-files` ölçümü — vendor gürültüsünü elemeli."""

    def test_tracked_count_of_absent_pattern_is_zero(self):
        self.assertEqual(gen._tracked_count(["*.rs"], ROOT), 0,
                         "izlenen .rs dosyası 0 olmalı (rn-expo/rust "
                         "sıfır-yüzey iddiasının bağımsız doğrulaması)")

    def test_tracked_count_of_present_pattern_is_positive(self):
        self.assertGreater(gen._tracked_count(["*.py"], ROOT), 0)


if __name__ == "__main__":
    unittest.main()
