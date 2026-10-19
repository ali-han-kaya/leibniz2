#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_check_seal_hash.py — mühür-halkası kapısının testleri.

Kapsanan davranışlar:
  - gerçek repoda mühür ↔ committed PDF ↔ donmuş kayıt üçlüsü uyuşur (rc 0)
  - halka sapması, merkez sapması, halka↔merkez tutarsızlığı → bulgu
  - donmuş kayıt (sidecar) sapması / yanlış dosya adı / bozuk format → bulgu
  - derlenmemiş artifact (`{{SEAL_RING}}` placeholder) → bulgu
  - eksik landing / PDF / sidecar → bulgu (fail-closed, sessiz geçmez)
  - CLI exit kodları + --json/--out
  - kapının süite bağlı olduğu (pre-commit hook + koşu manifesti + coverage)
"""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
import pathlib
import sys
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import check_seal_hash as gate  # noqa: E402

PDF_BYTES = b"%PDF-1.4\n% fixture manuscript\n%%EOF\n"
PDF_SHA = hashlib.sha256(PDF_BYTES).hexdigest()

SEAL_HTML = (
    '<html><body><div class="aside">'
    '<svg class="seal-big" viewBox="0 0 132 132" aria-hidden="true">'
    '<defs><path id="ring1" d="M 66,66"/></defs>'
    '<textPath href="#ring1">VERIFIED • {ring} •</textPath>'
    '<text x="66" y="82" fill="var(--fg-dimmed)">{center}…</text>'
    "</svg></div></body></html>"
)


class Fixture:
    """Geçici bir kökte landing + PDF + sidecar üçlüsü kurar."""

    def __init__(self, root: pathlib.Path):
        self.root = root
        self.landing = root / "landing.html"
        self.pdf = root / "manuscript.pdf"
        self.sidecar = root / "manuscript.pdf.metadata.sha256"

    def write(self, ring=None, center=None, html=None, pdf_bytes=PDF_BYTES,
              frozen_raw=None, frozen_name=None, write_landing=True,
              write_pdf=True, write_sidecar=True):
        if write_landing:
            if html is None:
                html = SEAL_HTML.format(
                    ring=ring if ring is not None else PDF_SHA[:12].upper(),
                    center=center if center is not None else PDF_SHA[:6].upper())
            self.landing.write_text(html, encoding="utf-8")
        if write_pdf:
            self.pdf.write_bytes(pdf_bytes)
        if write_sidecar:
            raw = frozen_raw if frozen_raw is not None else PDF_SHA
            name = frozen_name if frozen_name is not None else self.pdf.name
            self.sidecar.write_text(
                "0" * 64 + "  manuscript.pdf.metadata\n"
                "# raw: %s  %s\n" % (raw, name),
                encoding="utf-8")
        return self

    def run(self):
        return gate.check(self.landing, self.pdf, self.sidecar)


class TestSealHashGate(unittest.TestCase):
    def test_clean_fixture_passes(self):
        with tempfile.TemporaryDirectory(prefix="seal-hash-") as td:
            fixture = Fixture(pathlib.Path(td)).write()
            findings, facts = fixture.run()
            self.assertEqual(findings, [])
            self.assertEqual(facts["pdf_sha256"], PDF_SHA)
            self.assertEqual(facts["seal"]["ring"], PDF_SHA[:12])
            self.assertEqual(facts["seal"]["center"], PDF_SHA[:6])
            self.assertEqual(facts["frozen_raw"], PDF_SHA)

    def test_ring_mismatch_is_finding(self):
        with tempfile.TemporaryDirectory(prefix="seal-hash-") as td:
            wrong = "f" * 12
            findings, _ = Fixture(pathlib.Path(td)).write(ring=wrong).run()
            kinds = [item["kind"] for item in findings]
            self.assertIn("seal_ring_mismatch", kinds)
            self.assertIn("seal_internal_inconsistency", kinds)

    def test_center_mismatch_is_finding(self):
        with tempfile.TemporaryDirectory(prefix="seal-hash-") as td:
            findings, _ = Fixture(pathlib.Path(td)).write(center="f" * 6).run()
            kinds = [item["kind"] for item in findings]
            self.assertIn("seal_center_mismatch", kinds)
            self.assertIn("seal_internal_inconsistency", kinds)

    def test_short_ring_prefix_is_not_evidence(self):
        # PDF'in gerçek öneki, ama kanıt sayılamayacak kadar kısa.
        with tempfile.TemporaryDirectory(prefix="seal-hash-") as td:
            findings, _ = Fixture(pathlib.Path(td)).write(
                ring=PDF_SHA[:8].upper(), center=PDF_SHA[:6].upper()).run()
            kinds = [item["kind"] for item in findings]
            self.assertIn("seal_ring_too_short", kinds)

    def test_unparseable_ring_is_reported_as_missing(self):
        # Desene hiç uymayan halka (ör. 4 hex) "eksik" sayılır — yine fail-closed.
        with tempfile.TemporaryDirectory(prefix="seal-hash-") as td:
            findings, _ = Fixture(pathlib.Path(td)).write(
                ring=PDF_SHA[:4].upper(), center=PDF_SHA[:6].upper()).run()
            self.assertIn("seal_ring_missing",
                          [item["kind"] for item in findings])

    def test_frozen_record_mismatch_is_finding(self):
        with tempfile.TemporaryDirectory(prefix="seal-hash-") as td:
            findings, _ = Fixture(pathlib.Path(td)).write(
                frozen_raw="a" * 64).run()
            kinds = [item["kind"] for item in findings]
            self.assertIn("frozen_record_mismatch", kinds)

    def test_frozen_record_naming_other_file_is_finding(self):
        with tempfile.TemporaryDirectory(prefix="seal-hash-") as td:
            findings, _ = Fixture(pathlib.Path(td)).write(
                frozen_name="other.pdf").run()
            kinds = [item["kind"] for item in findings]
            self.assertIn("frozen_record_name_mismatch", kinds)

    def test_malformed_frozen_record_is_finding(self):
        with tempfile.TemporaryDirectory(prefix="seal-hash-") as td:
            fixture = Fixture(pathlib.Path(td)).write()
            fixture.sidecar.write_text("0" * 64 + "  manuscript.pdf.metadata\n",
                                       encoding="utf-8")
            findings, _ = fixture.run()
            self.assertIn("frozen_record_malformed",
                          [item["kind"] for item in findings])

    def test_unbuilt_landing_placeholder_is_finding(self):
        with tempfile.TemporaryDirectory(prefix="seal-hash-") as td:
            html = SEAL_HTML.format(ring="{{SEAL_RING}}",
                                    center="{{SEAL_CENTER}}")
            findings, _ = Fixture(pathlib.Path(td)).write(html=html).run()
            kinds = [item["kind"] for item in findings]
            self.assertIn("seal_placeholder", kinds)
            self.assertIn("seal_ring_missing", kinds)

    def test_seal_svg_absent_is_finding(self):
        with tempfile.TemporaryDirectory(prefix="seal-hash-") as td:
            findings, _ = Fixture(pathlib.Path(td)).write(
                html="<html><body>no seal here</body></html>").run()
            self.assertIn("seal_svg_missing",
                          [item["kind"] for item in findings])

    def test_missing_artifacts_are_findings(self):
        with tempfile.TemporaryDirectory(prefix="seal-hash-") as td:
            fixture = Fixture(pathlib.Path(td)).write(
                write_landing=False, write_pdf=False, write_sidecar=False)
            kinds = [item["kind"] for item in fixture.run()[0]]
            self.assertEqual(
                sorted(kinds),
                ["frozen_record_missing", "landing_missing", "pdf_missing"])

    def test_cli_exit_codes_and_json_output(self):
        with tempfile.TemporaryDirectory(prefix="seal-hash-") as td:
            root = pathlib.Path(td)
            fixture = Fixture(root).write()
            report_path = root / "report.json"
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                rc = gate.main([
                    "--landing", str(fixture.landing),
                    "--pdf", str(fixture.pdf),
                    "--sidecar", str(fixture.sidecar),
                    "--json", "--out", str(report_path),
                ])
            self.assertEqual(rc, 0)
            data = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertTrue(data["ok"])
            self.assertEqual(data["hashes"]["pdf_sha256"], PDF_SHA)
            self.assertEqual(data["hashes"]["seal_ring"], PDF_SHA[:12])

            # Aynı üçlü, mühür sapmış: rc 1 olmalı (fail-closed).
            Fixture(root).write(ring="f" * 12)
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                rc = gate.main(["--landing", str(fixture.landing),
                                "--pdf", str(fixture.pdf),
                                "--sidecar", str(fixture.sidecar), "--json"])
            self.assertEqual(rc, 1)
            self.assertFalse(json.loads(output.getvalue())["ok"])

    def test_bad_root_is_usage_error(self):
        output = io.StringIO()
        with contextlib.redirect_stderr(output):
            rc = gate.main(["--root", "/nonexistent-root-for-seal-gate"])
        self.assertEqual(rc, 2)

    def test_real_repository_seal_matches_committed_pdf(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            rc = gate.main(["--root", str(gate.REPO_ROOT), "--json"])
        self.assertEqual(rc, 0, output.getvalue())
        data = json.loads(output.getvalue())
        hashes = data["hashes"]
        # Asıl iddia üç kaynağın aynı hash üzerinde uzlaşmasıdır.
        self.assertEqual(hashes["pdf_sha256"], hashes["frozen_raw"])
        self.assertTrue(hashes["pdf_sha256"].startswith(hashes["seal_ring"]))
        self.assertTrue(hashes["pdf_sha256"].startswith(hashes["seal_center"]))

    def test_gate_is_wired_into_the_suite(self):
        precommit = (gate.REPO_ROOT / ".pre-commit-config.yaml").read_text(
            encoding="utf-8")
        self.assertIn("id: check-seal-hash", precommit)
        self.assertIn("check_seal_hash.py", precommit)

        manifest = (HERE / "check_unit_tests.list").read_text(encoding="utf-8")
        self.assertIn("test_check_seal_hash.py", manifest)

        coverage = (HERE / "test_coverage_report.py").read_text(
            encoding="utf-8")
        self.assertIn('"check-seal-hash"', coverage)
        self.assertIn("test_check_seal_hash.py", coverage)


if __name__ == "__main__":
    unittest.main()
