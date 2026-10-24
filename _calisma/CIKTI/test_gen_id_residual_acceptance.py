#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_gen_id_residual_acceptance.py — Faz 3 kabul üreticisi sözleşmesi.

`gen_id_residual_acceptance.py` = `make -f docs/Makefile.texlive accept`'in
çağırdığı GERÇEK üretici: determinism raporunu (2× bağımsız 3-geçiş ölçümü)
okur, kanıtı doğrular ve kanonik hash'i kabul raporunun §4 hash geçiş
defterine bağlar. Sabitlenen sözleşme:

  1) Kanonik tanımı + fallback: residual=/ID → kanonik satırlar;
     residual=none → ham hash (kanonik satır yoksa haksız fail-closed OLMAMALI).
  2) Kanıt tutarlılığı fail-closed: verdict≠PASS, rerun_left≠0, run1≠run2,
     rapor eksik → rc=1 (asla sessiz kabul).
  3) Defter doğrulaması: kanonik hash defterde yoksa rc=1 + uygulanabilir
     remedy (defter yolu + --update komutu).
  4) `--update` satırı ÖLÇÜLEN alanlardan üretir ve §4 tablosunun İÇİNE
     ekler (başka bölüme düşmez); ikinci koşumda idempotent.
  5) Varsayılan mod defteri DEĞİŞTİRMEZ (yalnız okur).

stdlib-only, OFFLINE (gerçek motor/make gerekmez).
"""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import gen_id_residual_acceptance as g  # noqa: E402

PRODUCER = HERE / "gen_id_residual_acceptance.py"
REAL_DOC = HERE.parent.parent / "docs" / "ID_RESIDUAL_ACCEPTANCE.md"
REAL_CANON = "544516b0d9d2f4c12b05b512b79b31ad238e82d3ca3aff81166a6bac1914f597"

DOC_FIXTURE = """# Sahte kabul raporu

## 4. Hash geçiş defteri

| # | Motor | Geçiş | SDE | Ham | Kanonik | Ölçüm |
|---|---|---|---|---|---|---|
| 1 | tectonic | 1 | 0 | — | `babe0000` | eski satır |

## 5. Etki

Metin.
"""


def report_text(canon=None, raw1="1" * 64, raw2="2" * 64, passes="3",
                rerun1="0", rerun2="0", verdict="PASS", residual="/ID",
                canonical_pair=None):
    """Deney raporu üret (gerçek üreticinin `key=value` biçimi)."""
    lines = ["TeXLive determinism evidence",
             "source=/x/ingiliz_empirizmi_v3.tex",
             "pdflatex=/usr/local/bin/pdflatex",
             "source_date_epoch=0",
             f"passes={passes}",
             f"texlive_run1_sha256={raw1}",
             f"texlive_run2_sha256={raw2}"]
    if passes != "1":
        lines += [f"texlive_run1_rerun_left={rerun1}",
                  f"texlive_run2_rerun_left={rerun2}"]
    if canonical_pair is not None:
        lines += [f"texlive_canonical_run1_sha256={canonical_pair[0]}",
                  f"texlive_canonical_run2_sha256={canonical_pair[1]}"]
    lines += [f"residual={residual}", f"verdict={verdict}"]
    return "\n".join(lines) + "\n"


def run_cli(report, doc, extra=()):
    """Üreticiyi alt süreçte koş; (rc, stdout+stderr, doc_sonrası)."""
    td = Path(tempfile.mkdtemp(prefix="faz3-test-"))
    rp = td / "determinism_report.txt"
    rp.write_text(report, encoding="utf-8")
    dp = td / "ID_RESIDUAL_ACCEPTANCE.md"
    dp.write_text(doc, encoding="utf-8")
    r = subprocess.run([sys.executable, str(PRODUCER),
                        "--report", str(rp), "--doc", str(dp), *extra],
                       capture_output=True, text=True, timeout=60)
    return r.returncode, r.stdout + r.stderr, dp.read_text(encoding="utf-8")


class TestParseAndCanonical(unittest.TestCase):
    def test_parse_report_ignores_header_and_keeps_value_spaces(self):
        text = ("TeXLive determinism evidence\n"
                "passes=3\n"
                "residual=/ID (pdfTeX rastgele belge kimligi)\n"
                "verdict=PASS\n")
        rep = g.parse_report(text)
        self.assertNotIn("TeXLive determinism evidence", rep)
        self.assertEqual(rep["passes"], "3")
        self.assertEqual(rep["residual"], "/ID (pdfTeX rastgele belge kimligi)")
        self.assertEqual(rep["verdict"], "PASS")

    def test_parse_report_keeps_id_lines_with_spaces_in_value(self):
        rep = g.parse_report("a=/ID [<11> <11>]\nb=2\n")
        self.assertEqual(rep["a"], "/ID [<11> <11>]")
        self.assertEqual(rep["b"], "2")

    def test_canonical_uses_id_neutralized_hashes(self):
        rep = g.parse_report(report_text(
            canonical_pair=(REAL_CANON, REAL_CANON)))
        canon, mode, problems = g.canonical_of(rep)
        self.assertEqual(canon, REAL_CANON)
        self.assertEqual(mode, "id-canonical")
        self.assertEqual(problems, [])

    def test_canonical_falls_back_to_raw_when_residual_none(self):
        """residual=none: rapor kanonik satırı YAZMAZ → ham hash kanoniktir.

        Bu fallback olmadan deterministik bir motorda accept haksız
        fail-closed olurdu.
        """
        rep = g.parse_report(report_text(raw1="d" * 64, raw2="d" * 64,
                                         residual="none"))
        canon, mode, problems = g.canonical_of(rep)
        self.assertEqual(canon, "d" * 64)
        self.assertEqual(mode, "raw-equal")
        self.assertEqual(problems, [])

    def test_canonical_mismatch_is_reported(self):
        rep = g.parse_report(report_text(canonical_pair=("a" * 64, "b" * 64)))
        canon, mode, problems = g.canonical_of(rep)
        self.assertTrue(problems, "run1≠run2 sessiz geçemez")

    def test_canonical_missing_when_raw_differ_and_no_canonical(self):
        rep = g.parse_report(report_text(raw1="1" * 64, raw2="2" * 64))
        canon, mode, problems = g.canonical_of(rep)
        self.assertIsNone(canon)
        self.assertTrue(problems)


class TestEvidenceProblems(unittest.TestCase):
    def test_pass_evidence_is_clean(self):
        rep = g.parse_report(report_text(canonical_pair=(REAL_CANON, REAL_CANON)))
        self.assertEqual(g.evidence_problems(rep), [])

    def test_verdict_fail_is_problem(self):
        rep = g.parse_report(report_text(verdict="FAIL"))
        self.assertTrue(any("verdict" in p for p in g.evidence_problems(rep)))

    def test_rerun_left_is_problem_only_in_multipass(self):
        multi = g.parse_report(report_text(rerun2="2"))
        self.assertTrue(any("rerun_left" in p for p in g.evidence_problems(multi)))
        single = g.parse_report(report_text(passes="1", rerun1=None, rerun2=None))
        self.assertEqual(g.evidence_problems(single), [])

    def test_non_numeric_passes_is_problem(self):
        rep = g.parse_report(report_text(passes="uc"))
        self.assertTrue(any("passes" in p for p in g.evidence_problems(rep)))


class TestLedgerHelpers(unittest.TestCase):
    def test_real_doc_ledger_rows_numbered(self):
        # Satır SAYISI pinlenmez: `LEDGER=update` bilinçli olarak satır EKLER.
        # Pinlenen şey numaralandırma bütünlüğü + helper'ın §4'ü bulması.
        nums = g.ledger_row_numbers(REAL_DOC.read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(nums), 4, f"§4 veri satırları: {nums}")
        self.assertEqual(nums, list(range(1, len(nums) + 1)),
                         "defter numaralandırması boşluksuz olmalı")

    def test_insert_row_lands_inside_section_4(self):
        out = g.insert_row(DOC_FIXTURE, "| 2 | yeni | 3 | 0 | x | `c` | n |")
        self.assertLess(out.index("| 2 | yeni"), out.index("## 5."),
                        "yeni satır §4 tablosunun içine girmeli")
        self.assertEqual(g.ledger_row_numbers(out), [1, 2])

    def test_insert_row_without_section_raises(self):
        with self.assertRaises(ValueError):
            g.insert_row("# defter yok\n", "| 1 | x |")

    def test_build_row_from_measured_fields(self):
        rep = g.parse_report(report_text(canonical_pair=(REAL_CANON, REAL_CANON)))
        row = g.build_row(rep, REAL_CANON, "pdfTeX 9 (TeX Live)", "not", 5)
        self.assertTrue(row.startswith("| 5 | pdfTeX 9 (TeX Live) | 3 | 0 |"))
        self.assertIn(REAL_CANON, row)
        self.assertIn("`/ID`", row)

    def test_build_row_marks_raw_equal_case(self):
        rep = g.parse_report(report_text(raw1="d" * 64, raw2="d" * 64,
                                         residual="none", passes="1"))
        row = g.build_row(rep, "d" * 64, "pdfTeX", "not", 5)
        self.assertIn("residual=none", row)

    def test_build_row_engine_label_fallback(self):
        rep = g.parse_report(report_text(canonical_pair=(REAL_CANON, REAL_CANON)))
        row = g.build_row(rep, REAL_CANON, "", "not", 5)
        self.assertIn("pdflatex", row)
        self.assertIn("sürüm etiketi verilmedi", row)


class TestCliContract(unittest.TestCase):
    def test_accept_when_canonical_recorded(self):
        rc, out, _ = run_cli(report_text(canonical_pair=(REAL_CANON, REAL_CANON)),
                             DOC_FIXTURE.replace("`babe0000`", f"`{REAL_CANON}`"))
        self.assertEqual(rc, 0, out)
        self.assertIn("KABUL", out)
        self.assertIn(REAL_CANON, out)
        self.assertIn("Faz 3", out)

    def test_unrecorded_canonical_is_fail_closed_with_remedy(self):
        rc, out, doc_after = run_cli(
            report_text(canonical_pair=(REAL_CANON, REAL_CANON)), DOC_FIXTURE)
        self.assertEqual(rc, 1, out)
        self.assertIn("ID_RESIDUAL_ACCEPTANCE", out)
        self.assertIn("defter", out)
        self.assertIn("--update", out)
        # Varsayılan mod defteri DEĞİŞTİRMEZ (yalnız okur).
        self.assertEqual(doc_after, DOC_FIXTURE)

    def test_update_produces_row_from_evidence_and_is_idempotent(self):
        rep = report_text(canonical_pair=(REAL_CANON, REAL_CANON))
        rc, out, doc_after = run_cli(
            rep, DOC_FIXTURE, ["--update", "--engine-label", "pdfTeX 3 (TeX Live)"])
        self.assertEqual(rc, 0, out)
        self.assertIn("DEFTER GÜNCELLENDİ", out)
        self.assertIn(REAL_CANON, doc_after)
        self.assertEqual(g.ledger_row_numbers(doc_after), [1, 2])
        self.assertLess(doc_after.index("| 2 |"), doc_after.index("## 5."))
        # İkinci koşum: satır artık var → yalnız KABUL, kopya satır YOK.
        rc2, out2, doc_after2 = run_cli(rep, doc_after, ["--update"])
        self.assertEqual(rc2, 0, out2)
        self.assertNotIn("DEFTER GÜNCELLENDİ", out2)
        self.assertEqual(doc_after2, doc_after)
        self.assertEqual(g.ledger_row_numbers(doc_after2), [1, 2])

    def test_update_uses_raw_fallback_row_when_residual_none(self):
        rep = report_text(raw1="d" * 64, raw2="d" * 64, residual="none",
                          passes="1")
        rc, out, doc_after = run_cli(rep, DOC_FIXTURE, ["--update"])
        self.assertEqual(rc, 0, out)
        self.assertIn("d" * 64, doc_after)
        self.assertIn("residual=none", doc_after)

    def test_verdict_fail_is_rejected(self):
        rc, out, doc_after = run_cli(
            report_text(canonical_pair=(REAL_CANON, REAL_CANON), verdict="FAIL"),
            DOC_FIXTURE, ["--update"])
        self.assertEqual(rc, 1, out)
        self.assertIn("TUTARSIZ", out)
        self.assertEqual(doc_after, DOC_FIXTURE, "tutarsız kanıtla defter YAZILMAZ")

    def test_rerun_left_is_rejected(self):
        rc, out, _ = run_cli(
            report_text(canonical_pair=(REAL_CANON, REAL_CANON), rerun1="3"),
            DOC_FIXTURE)
        self.assertEqual(rc, 1, out)
        self.assertIn("rerun_left", out)

    def test_missing_report_is_error(self):
        td = Path(tempfile.mkdtemp(prefix="faz3-test-"))
        dp = td / "ID_RESIDUAL_ACCEPTANCE.md"
        dp.write_text(DOC_FIXTURE, encoding="utf-8")
        r = subprocess.run([sys.executable, str(PRODUCER),
                            "--report", str(td / "yok.txt"), "--doc", str(dp)],
                           capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("determinism raporu yok", r.stderr)

    def test_missing_doc_is_error(self):
        td = Path(tempfile.mkdtemp(prefix="faz3-test-"))
        rp = td / "r.txt"
        rp.write_text(report_text(canonical_pair=(REAL_CANON, REAL_CANON)),
                      encoding="utf-8")
        r = subprocess.run([sys.executable, str(PRODUCER),
                            "--report", str(rp), "--doc", str(td / "yok.md")],
                           capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
