#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_check_hook_env_matrix.py — check_hook_env_matrix.py denetçisi testleri.

Skill fail-closed deseni: doc ↔ kod senkronu (araç kümesi iki yönlü, lean pin'i,
algılama komutu varlığı) bozulursa exit 1. Gerçek doc ile PASS; kurcalanmış
doc kopyalarıyla her drift türü bulgu üretmeli.
"""
import importlib.util
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent.parent
DOC = REPO / "docs" / "HOOK_ENV_MATRIX.md"

sys.path.insert(0, str(HERE))
import check_hook_env_matrix as chem  # noqa: E402
import verify_delivery as vd  # noqa: E402

# Gerçek doc + gerçek probe anahtar kümesi (tek kaynak).
REAL_TEXT = DOC.read_text(encoding="utf-8")
REAL_KEYS = sorted(vd.probe_tool_versions())


class TestParseTable(unittest.TestCase):
    def test_real_doc_parses_all_rows(self):
        rows = chem.parse_table(REAL_TEXT)
        self.assertEqual(sorted(rows), ["lean", "pdfinfo", "pre_commit",
                                        "python", "qpdf", "z3"])

    def test_digit_key_z3(self):
        # z3 anahtarı RAKAM içerir — karakter sınıfı [a-z0-9_]+ olmalı.
        rows = chem.parse_table(REAL_TEXT)
        self.assertIn("z3", rows)

    def test_each_row_has_7_cells(self):
        rows = chem.parse_table(REAL_TEXT)
        for k, cells in rows.items():
            self.assertEqual(len(cells), 7, f"{k}: hücre sayısı")

    def test_ignore_header_and_notes(self):
        text = ("| Anahtar | Araç | ... |\n|---|---|\n"
                "| `python` | Python | x | p | 1 | 2 | c |\n"
                "Not satırı, tablo değil.\n")
        rows = chem.parse_table(text)
        self.assertEqual(sorted(rows), ["python"])


class TestCheckDoc(unittest.TestCase):
    def test_real_doc_pass(self):
        ok, findings = chem.check_doc(REAL_TEXT, REAL_KEYS)
        self.assertTrue(ok, findings)

    def test_missing_row_detected(self):
        # Kodda var, doc'ta yok → drift.
        text = REAL_TEXT.replace("| `z3` | Z3", "| `zz` | Z3")
        ok, findings = chem.check_doc(text, REAL_KEYS)
        self.assertFalse(ok)
        self.assertTrue(any("z3" in f and "DOC'TA YOK" in f for f in findings))

    def test_extra_row_detected(self):
        # Doc'ta var, kodda yok (bayat) → drift.
        text = REAL_TEXT.replace("| `python` | Python |",
                                 "| `gcc` | GCC | | | | | |\n| `python` | Python |")
        ok, findings = chem.check_doc(text, REAL_KEYS)
        self.assertFalse(ok)
        self.assertTrue(any("gcc" in f and "KOD'DA YOK" in f for f in findings))

    def test_lean_pin_drift_detected(self):
        # LEAN_TOOLCHAIN sabitiyle uyumsuz pin → drift.
        text = REAL_TEXT.replace(vd.LEAN_TOOLCHAIN, "leanprover/lean4:v9.9.9")
        ok, findings = chem.check_doc(text, REAL_KEYS)
        self.assertFalse(ok)
        self.assertTrue(any("LEAN PIN DRIFT" in f for f in findings))

    def test_missing_detection_command_detected(self):
        text = REAL_TEXT.replace("`lean --version`", "`lean`")
        # lean komut hücresini boşaltmak yerine pin hücresiyle karışma —
        # gerçek boş komut hücresi üret:
        lines = []
        for line in text.splitlines():
            if line.startswith("| `lean`"):
                cells = [c.strip() for c in line.strip().strip("|").split("|")]
                cells[6] = ""
                line = "| " + " | ".join(cells) + " |"
            lines.append(line)
        ok, findings = chem.check_doc("\n".join(lines), REAL_KEYS)
        self.assertFalse(ok)
        self.assertTrue(any("ALGILAMA KOMUTU YOK" in f and "lean" in f
                            for f in findings))

    def test_extra_cell_row_ignored(self):
        # 7 hücreden fazla satır tabloya girmez (yanlış-çözüm yok).
        rows = chem.parse_table("| `a` | x | y | z | 1 | 2 | 3 | 4 |")
        self.assertNotIn("a", rows)


class TestMainExit(unittest.TestCase):
    def _run(self, doc_text, *extra):
        with tempfile.TemporaryDirectory() as td:
            p = pathlib.Path(td, "matrix.md")
            p.write_text(doc_text, encoding="utf-8")
            r = subprocess.run(
                [sys.executable, str(HERE / "check_hook_env_matrix.py"),
                 "--doc", str(p), *extra],
                capture_output=True, text=True)
            return r

    def test_real_doc_exit_0(self):
        r = self._run(REAL_TEXT)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_drift_exit_1(self):
        broken = REAL_TEXT.replace("| `z3` | Z3", "| `zz` | Z3")
        r = self._run(broken)
        self.assertEqual(r.returncode, 1)

    def test_json_schema(self):
        r = self._run(REAL_TEXT, "--json")
        self.assertEqual(r.returncode, 0)
        d = json.loads(r.stdout)
        self.assertEqual(d["verdict"], "PASS")
        self.assertEqual(sorted(d["observed"]), REAL_KEYS)
        self.assertEqual(d["ok"], True)

    def test_missing_doc_exit_2(self):
        r = self._run("", "--doc", "/nonexistent/matrix.md")
        # doc argümanı verildi → dosya yok → exit 2.
        self.assertEqual(r.returncode, 2)


class TestProbeKeySet(unittest.TestCase):
    def test_probe_has_exactly_six_tools(self):
        # Kodun prob ettiği araç kümesi sabit — doc buna göre yazılır.
        keys = set(vd.probe_tool_versions())
        self.assertEqual(keys, {"python", "z3", "lean", "pre_commit",
                                "pdfinfo", "qpdf"})


if __name__ == "__main__":
    unittest.main()
