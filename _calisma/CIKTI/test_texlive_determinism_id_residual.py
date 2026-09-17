#!/usr/bin/env python3
"""test_texlive_determinism_id_residual.py — iki aşamalı determinism verdict kapısı.

texlive_determinism_test.sh'in dürüst raporlama sözleşmesini stub araçlarla
deterministik doğrular (gerçek TeXLive derlemesi yapmaz):

  1) İki bağımsız pdflatex koşumu YALNIZCA trailer /ID'de farklıysa
     (pdfTeX'in bilinen rastgele belge kimliği) → verdict=PASS,
     residual=/ID, kanonik hash'ler EŞİT raporlanır.
  2) İçerik gerçekten farklıysa (canary bayt) → verdict=FAIL, exit 1
     (fail-closed: kanonik /ID nötrleme hiçbir içerik farkını gizlemez).
  3) Hash'ler baştan eşitse → residual=none (hızlı yol).

stdlib-only, OFFLINE.
"""
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT = ROOT / "_calisma" / "CIKTI" / "texlive_determinism_test.sh"

ID1 = "AA" * 16
ID2 = "BB" * 16


def _stub_pdflatex(first_id: str, second_id: str, first_tag: str, second_tag: str) -> str:
    """Koşum sayacına göre /ID (+isteğe bağlı içerik etiketi) değişen stub."""
    return (
        "#!/bin/sh\n"
        'for arg in "$@"; do case "$arg" in *.tex) src="$arg";; esac; done\n'
        'out=$(basename -- "${src:-sample.tex}" .tex).pdf\n'
        'cnt="${TEST_RUN_COUNT:?TEST_RUN_COUNT gerekli}"\n'
        'mkdir -p "$(dirname "$cnt")"\n'
        'n=$(( $(cat "$cnt" 2>/dev/null || echo 0) + 1 )); echo "$n" > "$cnt"\n'
        f'if [ "$n" -eq 1 ]; then id="{first_id}"; tag="{first_tag}"; '
        f'else id="{second_id}"; tag="{second_tag}"; fi\n'
        'printf "%s\\n" "%PDF-1.5" > "$out"\n'
        'printf "trailer\\n" >> "$out"\n'
        'printf "/ID [<%s> <%s>]\\n" "$id" "$id" >> "$out"\n'
        'printf "content-tag=%s\\n" "$tag" >> "$out"\n'
    )


class TestTexliveDeterminismIdResidual(unittest.TestCase):
    def _run_experiment(self, pdflatex_body: str) -> tuple[int, str]:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "sample.tex"
            source.write_text("\\documentclass{article}\n", encoding="utf-8")
            tools = root / "tools"
            tools.mkdir()
            tectonic = tools / "tectonic"
            tectonic.write_text(
                "#!/bin/sh\n"
                'for arg in "$@"; do case "$arg" in *.tex) src="$arg";; esac; done\n'
                'out=$(basename -- "${src:-sample.tex}" .tex).pdf; '
                'printf \'tectonic-pdf\' > "$out"\n',
                encoding="utf-8",
            )
            tectonic.chmod(0o755)
            pdflatex = tools / "pdflatex"
            pdflatex.write_text(pdflatex_body, encoding="utf-8")
            pdflatex.chmod(0o755)
            report = root / "report.txt"
            env = dict(os.environ, TEX_SOURCE=str(source),
                       TECTONIC_BIN=str(tectonic), TEXLIVE_BIN=str(tools),
                       DETERMINISM_OUT=str(report), SOURCE_DATE_EPOCH="0")
            result = subprocess.run(["bash", str(SCRIPT)], env=env, cwd=root,
                                    capture_output=True, text=True)
            return result.returncode, report.read_text(encoding="utf-8")

    def _run_with_counter(self, pdflatex_body: str) -> tuple[int, str]:
        with tempfile.TemporaryDirectory() as td:
            counter = str(Path(td) / "runs" / "n")
            body = pdflatex_body.replace("#!/bin/sh\n",
                                         f"#!/bin/sh\nTEST_RUN_COUNT={counter!r}\n")
            return self._run_experiment(body)

    def test_id_only_residual_is_reported_and_passes(self):
        # İki koşum: içerik aynı, /ID farklı → residual=/ID, kanonik hash eşit.
        rc, report = self._run_with_counter(_stub_pdflatex(ID1, ID2, "x", "x"))
        self.assertEqual(rc, 0, report)
        self.assertIn("residual=/ID", report)
        self.assertIn("verdict=PASS", report)
        lines = dict(ln.split("=", 1) for ln in report.splitlines() if "=" in ln)
        self.assertEqual(lines["texlive_canonical_run1_sha256"],
                         lines["texlive_canonical_run2_sha256"],
                         "kanonik hash'ler /ID nötrlenince eşit olmalı")

    def test_content_difference_still_fails_closed(self):
        # İçerik canary farkı + farklı /ID → kanonik karşılaştırma FAIL üretmeli.
        rc, report = self._run_with_counter(_stub_pdflatex(ID1, ID2, "x", "y"))
        self.assertEqual(rc, 1, report)
        self.assertIn("verdict=FAIL", report)
        self.assertIn("residual=content", report)

    def test_equal_hashes_report_no_residual(self):
        # Her iki koşum birebir aynı PDF → residual=none hızlı yolu.
        rc, report = self._run_with_counter(_stub_pdflatex(ID1, ID1, "same", "same"))
        self.assertEqual(rc, 0, report)
        self.assertIn("residual=none", report)
        self.assertIn("verdict=PASS", report)

    def test_sde_must_reach_engines_fail_closed(self):
        # Sözleşme: script SOURCE_DATE_EPOCH'u HER İKİ motora da export etmeli
        # (tectonic ayağı eksikti; ölçüldü: hash oturumlar arası kayıyordu).
        # SDE setken ölen stub → script fail-closed çıkmalı, PASS yazmamalı.
        die_on_sde = (
            "#!/bin/sh\n"
            'if [ -n "${SOURCE_DATE_EPOCH:-}" ]; then\n'
            '  echo "SDE LEAK detected" >&2; exit 42\n'
            "fi\n"
        )
        rc, report = self._run_experiment(die_on_sde)
        self.assertEqual(rc, 42, report)
        self.assertNotIn("verdict=PASS", report)


if __name__ == "__main__":
    unittest.main()
