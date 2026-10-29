#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_check_id_residual_doc_sync.py — §4 defter satırı ↔ donmuş kayıt kapısı.

Kapsanan sözleşme
-----------------
`docs/ID_RESIDUAL_ACCEPTANCE.md` §4'teki teslim satırının **ham** ve
**metadata-stripped** hash'leri, `ingiliz_empirizmi_v3.pdf.metadata.sha256`
donmuş kaydındaki değerlerle birebir aynı olmalı. Kanonik hash, kayıtta
`# canonical:` satırı varsa eşleşmeli; yoksa NOT (bilgi) düzeyindedir.

Testler iki katmanlıdır:
  1. GERÇEK REPO — kapı bugünkü defter/kayıt üzerinde temiz dönmeli ve
     gerçek defterin kopyası üzerinde yapılan mutasyon yakalanmalı
     (kapının vakumlu olmadığının kanıtı).
  2. FIXTURE — her fail-closed dal (eksik satır/sütun/hücre, bozuk kayıt,
     ad uyuşmazlığı, belirsiz satır) ayrı ayrı kırmızıya çekilir.

stdlib-only, OFFLINE.
"""
import contextlib
import io
import json
import pathlib
import shutil
import sys
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import check_id_residual_doc_sync as gate  # noqa: E402

ROOT = HERE.parent.parent
REAL_DOC = ROOT / "docs" / "ID_RESIDUAL_ACCEPTANCE.md"
REAL_SIDECAR = (ROOT / gate.seal.PDF_REL).with_name(
    gate.seal.PDF_REL.name + gate.seal.SIDECAR_SUFFIX)
PDF_NAME = "ingiliz_empirizmi_v3.pdf"

H_RAW_A = "a" * 64
H_RAW_B = "b" * 64
H_STRIP_A = "c" * 64
H_STRIP_B = "d" * 64
H_CANON_A = "e" * 64
H_CANON_B = "f" * 64


def sidecar_text(raw=H_RAW_A, stripped=H_STRIP_A, canonical=None,
                 stripped_name=None):
    lines = [
        "%s  %s" % (stripped, stripped_name or (PDF_NAME + ".metadata")),
        "# raw: %s  %s" % (raw, PDF_NAME),
    ]
    if canonical is not None:
        lines.append("# canonical: %s  %s" % (canonical, PDF_NAME))
    return "\n".join(lines) + "\n"


def doc_text(raw=H_RAW_A, stripped=H_STRIP_A, canonical=H_CANON_A,
             columns=("Ham PDF (bilgi)", "Metadata-stripped",
                      "Kanonik `/ID`-nötr (referans)"),
             values=None, rows=1):
    """§4 alt-tablosunun küçük bir kopyasını üretir (sütun sırası verilebilir)."""
    values = values or {"Ham PDF (bilgi)": raw,
                        "Metadata-stripped": stripped,
                        "Kanonik `/ID`-nötr (referans)": canonical}
    header = "| Dönem | " + " | ".join(columns) + " | Durum |"
    sep = "|" + "---|" * (len(columns) + 2)
    cells = []
    for col in columns:
        val = values.get(col)
        cells.append("`%s`" % val if val else "—")
    body = ("| tectonic-era teslim (V5l; mevcut) | " + " | ".join(cells)
            + " | yanındaki sidecar |")
    extra = "| TeXLive-era teslim | — | — | — | beklemede |\n" if rows else ""
    return (
        "# /ID Kalıntısı Kabul Raporu\n\n"
        "## 4. Hash geçiş defteri\n\n"
        "### Teslim sidecar'ı geçiş kaydı\n\n"
        + header + "\n" + sep + "\n" + body + "\n" + extra + "\n"
    )


class FixtureCase(unittest.TestCase):
    """Temp dizinde defter + kayıt yazıp kapıyı koşturan taban sınıf."""

    def setUp(self):
        self.dir = pathlib.Path(tempfile.mkdtemp(prefix="idres-"))
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.doc = self.dir / "ID_RESIDUAL_ACCEPTANCE.md"
        self.sidecar = self.dir / (PDF_NAME + ".metadata.sha256")

    def write(self, doc=None, sidecar=None):
        if doc is not None:
            self.doc.write_text(doc, encoding="utf-8")
        if sidecar is not None:
            self.sidecar.write_text(sidecar, encoding="utf-8")

    def run_check(self):
        return gate.check(self.doc, self.sidecar, PDF_NAME)

    def kinds(self, findings):
        return sorted(f["kind"] for f in findings)


class TestRealRepo(FixtureCase):
    """Gerçek defter + gerçek kayıt: kapı bugün PASS, mutasyonda kırmızı."""

    def test_real_doc_matches_frozen_record(self):
        findings, notes, facts = gate.check(REAL_DOC, REAL_SIDECAR, PDF_NAME)
        self.assertEqual(findings, [],
                         "gerçek defter donmuş kayıtla senkron olmalı: %r"
                         % findings)
        self.assertEqual(facts["doc_hashes"]["raw"],
                         facts["record"]["raw"])
        self.assertEqual(facts["doc_hashes"]["stripped"],
                         facts["record"]["stripped"])
        # Kanonik bugün kayıtta yok → NOT, bloklayıcı bulgu değil.
        self.assertIsNone(facts["record"]["canonical"])
        self.assertEqual([n["kind"] for n in notes],
                         ["canonical_not_in_record"])

    def test_real_record_columns_are_distinct(self):
        """Kapının iki sütunu karıştırmadığının kanıtı: ham ≠ stripped."""
        _f, _n, facts = gate.check(REAL_DOC, REAL_SIDECAR, PDF_NAME)
        self.assertNotEqual(facts["record"]["raw"],
                            facts["record"]["stripped"])

    def test_real_doc_mutation_is_caught(self):
        """Gerçek defterin kopyasında tek hane değişirse kapı kırmızı olmalı."""
        text = REAL_DOC.read_text(encoding="utf-8")
        raw = gate.check(REAL_DOC, REAL_SIDECAR, PDF_NAME)[2]["record"]["raw"]
        self.assertIn(raw, text)
        # Mutasyon KORUNAN satıra uygulanır: aynı ham hash §4 ana tablosunda
        # (teslim satırı) da geçiyor; ilk eşleşmeyi değiştirmek kapının hiç
        # okumadığı bir tabloyu bozar ve testi vakumlu bırakırdı.
        match = gate.ROW_LABEL_RE.search(text)
        self.assertIsNotNone(match, "gerçek defterde teslim satırı yok")
        start = match.start()
        end = text.find("\n", start)
        row = text[start:end]
        self.assertIn(raw, row, "teslim satırında ham hash yok")
        mutated_row = row.replace(
            raw, ("0" if raw[0] != "0" else "1") + raw[1:], 1)
        mutated = text[:start] + mutated_row + text[end:]
        self.assertNotEqual(mutated, text, "gerçek defterde mutasyon uygulanamadı")
        self.write(doc=mutated)
        self.write(sidecar=REAL_SIDECAR.read_text(encoding="utf-8"))
        findings, _notes, _facts = self.run_check()
        self.assertEqual(self.kinds(findings), ["doc_value_mismatch"])
        self.assertEqual(findings[0]["column"], "raw")


class HookWiringTests(unittest.TestCase):
    """Kapı SUITE'A BAĞLI mı — yeşil ama hiç koşmayan kapı kanıt değildir."""

    def test_hook_is_declared_in_pre_commit(self):
        precommit = (ROOT / ".pre-commit-config.yaml").read_text(
            encoding="utf-8")
        self.assertIn("id: check-id-residual-doc-sync", precommit,
                      "kapı pre-commit zincirinde değil — drift serbest")
        self.assertIn("check_id_residual_doc_sync.py", precommit)

    def test_module_is_in_the_unit_battery(self):
        """Kapının KOŞTUĞU yer: main'de `gate_registry.yaml` yok (kaldırıldı),
        tek beyan `check-unit-tests` manifest'i. Manifestten düşen bir test
        "yeşil ama hiç koşmuyor" olurdu — bu test onu kırmızıya çevirir.
        """
        manifest = (HERE / "check_unit_tests.list").read_text(
            encoding="utf-8")
        self.assertIn("test_check_id_residual_doc_sync.py", manifest,
                      "kapı testi check-unit-tests manifest'inden düşmüş")


class TestDocDrift(FixtureCase):
    def test_doc_raw_mismatch(self):
        self.write(doc=doc_text(raw=H_RAW_B), sidecar=sidecar_text())
        findings, _n, _f = self.run_check()
        self.assertEqual(self.kinds(findings), ["doc_value_mismatch"])
        self.assertEqual(findings[0]["column"], "raw")

    def test_doc_stripped_mismatch(self):
        self.write(doc=doc_text(stripped=H_STRIP_B), sidecar=sidecar_text())
        findings, _n, _f = self.run_check()
        self.assertEqual(self.kinds(findings), ["doc_value_mismatch"])
        self.assertEqual(findings[0]["column"], "stripped")

    def test_both_columns_mutated_are_both_reported(self):
        self.write(doc=doc_text(raw=H_RAW_B, stripped=H_STRIP_B),
                   sidecar=sidecar_text())
        findings, _n, _f = self.run_check()
        self.assertEqual(sorted(f["column"] for f in findings),
                         ["raw", "stripped"])

    def test_missing_row(self):
        text = doc_text().replace("tectonic-era teslim", "başka bir teslim")
        self.write(doc=text, sidecar=sidecar_text())
        findings, _n, _f = self.run_check()
        self.assertIn("doc_row_missing", self.kinds(findings))

    def test_missing_table_header(self):
        self.write(doc="# rapor\n\n tablo yok\n", sidecar=sidecar_text())
        findings, _n, _f = self.run_check()
        self.assertIn("doc_table_missing", self.kinds(findings))

    def test_dash_cell_when_record_has_value(self):
        text = doc_text(values={
            "Ham PDF (bilgi)": None,
            "Metadata-stripped": H_STRIP_A,
            "Kanonik `/ID`-nötr (referans)": H_CANON_A,
        })
        self.write(doc=text, sidecar=sidecar_text())
        findings, _n, _f = self.run_check()
        self.assertEqual(self.kinds(findings), ["doc_hash_missing"])
        self.assertEqual(findings[0]["column"], "raw")

    def test_ambiguous_rows_fail_closed(self):
        text = doc_text()
        # Gerçek veri satırını (tectonic-era) ikinci kez ekle → hangisinin
        # yürürlükte olduğu belirsiz; kapı tahmin etmemeli.
        row = [line for line in text.splitlines()
               if line.startswith("| tectonic-era teslim")][0]
        self.write(doc=text + row + "\n", sidecar=sidecar_text())
        findings, _n, _f = self.run_check()
        self.assertIn("doc_row_ambiguous", self.kinds(findings))

    def test_column_order_is_read_from_header(self):
        """Sütunlar yeniden sıralanırsa sabit pozisyon varsayan kapı yanılır."""
        columns = ("Kanonik `/ID`-nötr (referans)", "Ham PDF (bilgi)",
                   "Metadata-stripped")
        self.write(doc=doc_text(columns=columns), sidecar=sidecar_text())
        findings, _n, facts = self.run_check()
        self.assertEqual(findings, [])
        self.assertEqual(facts["doc_hashes"]["raw"], H_RAW_A)
        self.assertEqual(facts["doc_hashes"]["stripped"], H_STRIP_A)
        self.assertEqual(facts["doc_hashes"]["canonical"], H_CANON_A)


class TestFrozenRecord(FixtureCase):
    def test_missing_sidecar(self):
        self.write(doc=doc_text())
        findings, _n, _f = self.run_check()
        self.assertEqual(self.kinds(findings), ["frozen_record_missing"])

    def test_missing_raw_line(self):
        self.write(doc=doc_text(),
                   sidecar="%s  %s.metadata\n" % (H_STRIP_A, PDF_NAME))
        findings, _n, _f = self.run_check()
        self.assertIn("frozen_record_malformed", self.kinds(findings))

    def test_malformed_stripped_line(self):
        self.write(doc=doc_text(),
                   sidecar="deadbeef  %s.metadata\n# raw: %s  %s\n"
                           % (PDF_NAME, H_RAW_A, PDF_NAME))
        findings, _n, _f = self.run_check()
        self.assertIn("stripped_malformed", self.kinds(findings))

    def test_stripped_names_another_pdf(self):
        self.write(doc=doc_text(),
                   sidecar=sidecar_text(stripped_name="other.pdf.metadata"))
        findings, _n, _f = self.run_check()
        self.assertIn("stripped_name_mismatch", self.kinds(findings))

    def test_raw_names_another_pdf(self):
        text = sidecar_text().replace("# raw: %s  %s" % (H_RAW_A, PDF_NAME),
                                      "# raw: %s  other.pdf" % H_RAW_A)
        self.write(doc=doc_text(), sidecar=text)
        findings, _n, _f = self.run_check()
        self.assertIn("frozen_record_name_mismatch", self.kinds(findings))


class TestCanonicalColumn(FixtureCase):
    def test_matching_canonical_is_clean(self):
        self.write(doc=doc_text(),
                   sidecar=sidecar_text(canonical=H_CANON_A))
        findings, notes, facts = self.run_check()
        self.assertEqual(findings, [])
        self.assertEqual(notes, [])
        self.assertEqual(facts["record"]["canonical"], H_CANON_A)

    def test_canonical_mismatch_is_blocking(self):
        self.write(doc=doc_text(),
                   sidecar=sidecar_text(canonical=H_CANON_B))
        findings, _n, _f = self.run_check()
        self.assertEqual(self.kinds(findings), ["doc_value_mismatch"])
        self.assertEqual(findings[0]["column"], "canonical")

    def test_canonical_missing_in_doc_but_in_record(self):
        text = doc_text(values={
            "Ham PDF (bilgi)": H_RAW_A,
            "Metadata-stripped": H_STRIP_A,
            "Kanonik `/ID`-nötr (referans)": None,
        })
        self.write(doc=text, sidecar=sidecar_text(canonical=H_CANON_A))
        findings, _n, _f = self.run_check()
        self.assertEqual(self.kinds(findings), ["doc_hash_missing"])
        self.assertEqual(findings[0]["column"], "canonical")

    def test_canonical_only_in_doc_is_note_not_failure(self):
        self.write(doc=doc_text(), sidecar=sidecar_text(canonical=None))
        findings, notes, _f = self.run_check()
        self.assertEqual(findings, [])
        self.assertEqual([n["kind"] for n in notes],
                         ["canonical_not_in_record"])


class TestCli(FixtureCase):
    def run_main(self, argv):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = gate.main(argv)
        return rc, buf.getvalue()

    def test_clean_fixture_returns_zero_and_json(self):
        self.write(doc=doc_text(), sidecar=sidecar_text())
        rc, out = self.run_main(["--doc", str(self.doc),
                                 "--sidecar", str(self.sidecar),
                                 "--json"])
        self.assertEqual(rc, 0)
        report = json.loads(out)
        self.assertTrue(report["ok"])
        self.assertEqual(report["findings"], [])

    def test_mutated_fixture_returns_one_and_json(self):
        self.write(doc=doc_text(raw=H_RAW_B), sidecar=sidecar_text())
        rc, out = self.run_main(["--doc", str(self.doc),
                                 "--sidecar", str(self.sidecar),
                                 "--json"])
        self.assertEqual(rc, 1)
        report = json.loads(out)
        self.assertFalse(report["ok"])
        self.assertEqual(report["findings"][0]["column"], "raw")

    def test_out_file_is_written(self):
        self.write(doc=doc_text(), sidecar=sidecar_text())
        out_path = self.dir / "reports" / "id_residual_doc_sync.json"
        rc, _out = self.run_main(["--doc", str(self.doc),
                                  "--sidecar", str(self.sidecar),
                                  "--json", "--out", str(out_path)])
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(out_path.read_text(encoding="utf-8"))["ok"],
                         True)

    def test_root_not_a_directory_returns_two(self):
        rc, _out = self.run_main(["--root", str(self.dir / "nope")])
        self.assertEqual(rc, 2)


if __name__ == "__main__":
    unittest.main()
