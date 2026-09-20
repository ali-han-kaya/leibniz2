#!/usr/bin/env python3
"""test_texlive_determinism_id_residual.py — iki aşamalı determinism verdict kapısı.

texlive_determinism_test.sh'in dürüst raporlama sözleşmesini stub araçlarla
deterministik doğrular (gerçek TeXLive derlemesi yapmaz):

  1) Bağımsız pdflatex koşumları YALNIZCA trailer /ID'de farklıysa
     (pdfTeX'in bilinen rastgele belge kimliği) → verdict=PASS,
     residual=/ID, kanonik hash'ler EŞİT raporlanır.
  2) İçerik gerçekten farklıysa (canary bayt) → verdict=FAIL, exit 1
     (fail-closed: kanonik /ID nötrleme hiçbir içerik farkını gizlemez).
  3) Hash'ler baştan eşitse → residual=none (hızlı yol).
  4) 3-geçiş modu (DETERMINISM_PASSES — Faz 0/2 sözleşmesi): her koşum tam
     N geçiş koşar (stub sayaç N×2 çağrıyı kanıtlar), rapor passes=N taşır
     ve rerun_left=0 ×2 yazar; son geçiş logunda 'Rerun to get' kalan
     multi-pass koşum fail-closed FAIL üretir (K6 hizalama iddiası ancak
     Rerun=0 ile yapılır). Default 1 kalır — trend/hook sözleşmesi Faz 4'e
     dek korunur.
  5) SOURCE_DATE_EPOCH HER İKİ motora da export edilmeli (SDE-setken ölen
     stub → fail-closed, PASS yazılmaz).

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


def _stub_pdflatex(mode: str = "fresh-id", first_tag: str = "x", second_tag: str = "x") -> str:
    """stub pdflatex gövdesi — mode'a göre /ID ve log davranışı:

      fresh-id : her çağrıda TAZE /ID (gerçek pdfTeX davranışı; iki bağımsız
                 koşumun son geçiş PDF'leri farklı /ID taşır)
      fixed-id : /ID sabit → ham hash'ler eşit (residual=none yolu)
      rerun    : SON geçiş logunda 'Rerun to get' bırakır (multi-pass'ta
                 fail-closed FAIL yolu)

    İçerik etiketi TEXLIVE_RUN_INDEX'e göre first/second seçilir (canary);
    PDF ve log -output-directory'ye yazılır (gerçek pdflatex gibi).
    """
    first, second = first_tag, second_tag
    if mode == "fixed-id":
        id_line = 'id="%s"\n' % ID1
    else:
        id_line = 'id=$(printf \'%032x\' "$n")\n'
    rerun_block = ""
    if mode == "rerun":
        rerun_block = (
            'if [ "${TEXLIVE_PASS_INDEX:-0}" = "${TEXLIVE_PASSES:-1}" ]; then\n'
            '  printf "Rerun to get cross-references.\\n" >> "$log"\n'
            "fi\n"
        )
    return (
        "#!/bin/sh\n"
        'for arg in "$@"; do case "$arg" in *.tex) src="$arg";; '
        '-output-directory=*) outdir="${arg#-output-directory=}";; esac; done\n'
        'outdir="${outdir:-$PWD}"\n'
        'base=$(basename -- "${src:-sample.tex}" .tex)\n'
        'out="$outdir/$base.pdf"; log="$outdir/$base.log"\n'
        'cnt="${TEST_RUN_COUNT:?TEST_RUN_COUNT gerekli}"\n'
        'mkdir -p "$outdir" "$(dirname "$cnt")"\n'
        'n=$(( $(cat "$cnt" 2>/dev/null || echo 0) + 1 )); echo "$n" > "$cnt"\n'
        'case "${TEXLIVE_RUN_INDEX:-1}" in 1) tag="%s";; *) tag="%s";; esac\n'
        % (first, second)
        + id_line
        + 'printf "%s\\n" "%PDF-1.5" > "$out"\n'
        'printf "trailer\\n" >> "$out"\n'
        'printf "/ID [<%s> <%s>]\\n" "$id" "$id" >> "$out"\n'
        'printf "content-tag=%s\\n" "$tag" >> "$out"\n'
        'printf "pass=%s/%s run=%s\\n" "${TEXLIVE_PASS_INDEX:-?}" '
        '"${TEXLIVE_PASSES:-?}" "${TEXLIVE_RUN_INDEX:-?}" > "$log"\n'
        + rerun_block
    )


class TestTexliveDeterminismIdResidual(unittest.TestCase):
    def _run_experiment(self, pdflatex_body: str, passes=None) -> tuple[int, str]:
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
            if passes is not None:
                env["DETERMINISM_PASSES"] = str(passes)
            result = subprocess.run(["bash", str(SCRIPT)], env=env, cwd=root,
                                    capture_output=True, text=True)
            return result.returncode, report.read_text(encoding="utf-8")

    def _run_with_counter(self, pdflatex_body: str, passes=None) -> tuple[int, str, int]:
        with tempfile.TemporaryDirectory() as td:
            counter = str(Path(td) / "runs" / "n")
            body = pdflatex_body.replace("#!/bin/sh\n",
                                         f"#!/bin/sh\nTEST_RUN_COUNT={counter!r}\n")
            rc, report = self._run_experiment(body, passes=passes)
            try:
                n = int(Path(counter).read_text().strip())
            except OSError:
                n = -1
            return rc, report, n

    def test_id_only_residual_is_reported_and_passes(self):
        # Default (tek-geçiş): iki koşum içerik aynı, /ID farklı → residual=/ID.
        rc, report, n = self._run_with_counter(_stub_pdflatex("fresh-id", "x", "x"))
        self.assertEqual(rc, 0, report)
        self.assertEqual(n, 2, "default mod 2 bağımsız tek-geçiş koşumu (Faz 4'e dek)")
        self.assertIn("residual=/ID", report)
        self.assertIn("verdict=PASS", report)
        self.assertIn("passes=1", report)
        lines = dict(ln.split("=", 1) for ln in report.splitlines() if "=" in ln)
        self.assertEqual(lines["texlive_canonical_run1_sha256"],
                         lines["texlive_canonical_run2_sha256"],
                         "kanonik hash'ler /ID nötrlenince eşit olmalı")

    def test_three_pass_contract_runs_each_run_three_times(self):
        # Faz 0/2: DETERMINISM_PASSES=3 → her koşum 3 geçiş (sayaç 6), rapor
        # passes=3 + rerun_left=0 ×2 taşır; /ID kalıntısı yine dürüst raporlanır.
        rc, report, n = self._run_with_counter(_stub_pdflatex("fresh-id", "x", "x"),
                                               passes=3)
        self.assertEqual(rc, 0, report)
        self.assertEqual(n, 6, "3 geçiş × 2 bağımsız koşum = 6 çağrı")
        self.assertIn("passes=3", report)
        self.assertIn("texlive_run1_rerun_left=0", report)
        self.assertIn("texlive_run2_rerun_left=0", report)
        self.assertIn("residual=/ID", report)
        self.assertIn("verdict=PASS", report)
        lines = dict(ln.split("=", 1) for ln in report.splitlines() if "=" in ln)
        self.assertEqual(lines["texlive_canonical_run1_sha256"],
                         lines["texlive_canonical_run2_sha256"])

    def test_pass_count_is_env_driven(self):
        # Mod env ile sürülür: PASSES=2 → sayaç 4, rapor passes=2.
        rc, report, n = self._run_with_counter(_stub_pdflatex("fresh-id"), passes=2)
        self.assertEqual(rc, 0, report)
        self.assertEqual(n, 4, "2 geçiş × 2 koşum = 4 çağrı")
        self.assertIn("passes=2", report)

    def test_rerun_left_fails_closed_in_multi_pass(self):
        # Faz 0: son geçiş logunda 'Rerun to get' kaldıysa hizalama iddiası
        # ÜRETİLEMEZ — multi-pass mod fail-closed FAIL (exit 1) vermeli.
        rc, report, _ = self._run_with_counter(_stub_pdflatex("rerun"), passes=3)
        self.assertEqual(rc, 1, report)
        self.assertIn("verdict=FAIL", report)
        self.assertIn("residual=unconverged", report)
        self.assertIn("texlive_run1_rerun_left=1", report)

    def test_content_difference_still_fails_closed(self):
        # İçerik canary farkı + farklı /ID → kanonik karşılaştırma FAIL üretmeli.
        rc, report, _ = self._run_with_counter(_stub_pdflatex("fresh-id", "x", "y"))
        self.assertEqual(rc, 1, report)
        self.assertIn("verdict=FAIL", report)
        self.assertIn("residual=content", report)

    def test_equal_hashes_report_no_residual(self):
        # Her iki koşum birebir aynı PDF → residual=none hızlı yolu.
        rc, report, _ = self._run_with_counter(_stub_pdflatex("fixed-id", "same", "same"))
        self.assertEqual(rc, 0, report)
        self.assertIn("residual=none", report)
        self.assertIn("verdict=PASS", report)

    def test_sde_must_reach_engines_fail_closed(self):
        # Sözleşme: script SOURCE_DATE_EPOCH'u HER İKİ motora da export etmeli.
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
