#!/usr/bin/env python3
"""test_gen_commit_msg_evidence.py — gen_commit_msg_evidence.py regresyon kapısı.

COMMIT_MSG_BLOCK_EVIDENCE.md üretiminin deterministik olduğunu, doğru
formatı verdiğini ve tüm test senaryolarının çalıştığını doğrular.
"""
import pathlib
import subprocess
import sys
import tempfile
import unittest

CIKTI = pathlib.Path(__file__).resolve().parent
GEN = CIKTI / "gen_commit_msg_evidence.py"
HOOK = CIKTI / "commit_msg_hook.sh"


def _run_gen(out_path):
    r = subprocess.run(
        [sys.executable, str(GEN), "--out", str(out_path)],
        capture_output=True, text=True,
    )
    return r


class TestEvidenceGeneration(unittest.TestCase):
    def test_generates_markdown(self):
        with tempfile.TemporaryDirectory() as d:
            out = pathlib.Path(d) / "EVIDENCE.md"
            r = _run_gen(out)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertTrue(out.exists())
            txt = out.read_text(encoding="utf-8")
            self.assertIn("COMMIT_MSG_BLOCK_EVIDENCE.md", txt)
            self.assertIn("Test Sonuçları", txt)

    def test_deterministic_across_runs(self):
        """İki çalıştırma aynı çıktıyı üretmeli (zaman damgası hariç)."""
        with tempfile.TemporaryDirectory() as d:
            out1 = pathlib.Path(d) / "e1.md"
            out2 = pathlib.Path(d) / "e2.md"
            _run_gen(out1)
            _run_gen(out2)
            t1 = out1.read_text(encoding="utf-8")
            t2 = out2.read_text(encoding="utf-8")
            # Zaman damgası satırları hariç aynı olmalı
            def strip_timestamps(text):
                return "\n".join(
                    l for l in text.split("\n")
                    if "Üretim zamanı" not in l and "Son yenileme" not in l
                )
            self.assertEqual(strip_timestamps(t1), strip_timestamps(t2))

    def test_all_test_cases_produce_results(self):
        """28 test senaryosu raporda görünmeli."""
        with tempfile.TemporaryDirectory() as d:
            out = pathlib.Path(d) / "EVIDENCE.md"
            r = _run_gen(out)
            txt = out.read_text(encoding="utf-8")
            # Tabloda 28 satır olmalı (başlık hariç)
            rows = [l for l in txt.split("\n") if l.startswith("| ") and not l.startswith("| #")]
            self.assertEqual(len(rows), 28)

    def test_pass_when_all_correct(self):
        """Tüm testler doğruysa exit 0."""
        with tempfile.TemporaryDirectory() as d:
            out = pathlib.Path(d) / "EVIDENCE.md"
            r = _run_gen(out)
            self.assertEqual(r.returncode, 0)
            txt = out.read_text(encoding="utf-8")
            self.assertIn("SONUÇ: PASS", txt)

    def test_summary_section(self):
        """Özet bölümü mevcut ve tutarlı."""
        with tempfile.TemporaryDirectory() as d:
            out = pathlib.Path(d) / "EVIDENCE.md"
            _run_gen(out)
            txt = out.read_text(encoding="utf-8")
            self.assertIn("Toplam test:", txt)
            self.assertIn("Başarılı:", txt)
            self.assertIn("Başarısız:", txt)


class TestHookExists(unittest.TestCase):
    def test_hook_file_exists(self):
        self.assertTrue(HOOK.exists(), f"Hook bulunamadı: {HOOK}")


if __name__ == "__main__":
    unittest.main()
