#!/usr/bin/env python3
"""test_makefile_texlive.py — docs/Makefile.texlive (Faz 1) sözleşme kapısı.

docs/Makefile.tectonic'in TeXLive ikizi stub araçlarla sabitlenir (gerçek
TeX derlemesi yapılmaz):

  1) Yapısal: pdf/check/accept/clean target'ları, SOURCE_DATE_EPOCH ?=
     semantiği (geçmiş commit'i yeniden üretme), -output-directory
     (GÜVENLİK: kaynak dizinine asla yazma), PASSES ?= 3 (Faz 0: yeni
     target'lar tam 3 geçiş), son-geçiş 'Rerun to get' denetimi ve
     Makefile.tectonic'in paralel yaşamaya devam etmesi (geri dönüş yolu).
  2) pdf: tam PASSES geçiş koşar (stub sayaç == 3), PDF BUILD_DIR'de
     üretilip OUTPUT'a kopyalanır; son geçiş logunda 'Rerun to get' varsa
     fail-closed.
  3) check: deney betiğine delege eder — 2 bağımsız 3-geçişli koşum,
     verdict=PASS + rerun_left=0 x2 olmadan RC=0 YOK; stub pdflatex tam
     6 kez çağrılır.
  4) accept: Faz 3 kabul raporunun (docs/ID_RESIDUAL_ACCEPTANCE.md) hash
     geçiş defterini doğrular — önce check'i koşturur (taze kanıt), sonra
     kanonik hash'i defterde arar; defterde yoksa fail-closed (yeni
     bağlam → deftere bilinçli satır, Faz 6 çıkış yolu).

stdlib-only, OFFLINE.
"""
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
MAKEFILE = ROOT / "docs" / "Makefile.texlive"
TECTONIC_MAKEFILE = ROOT / "docs" / "Makefile.tectonic"

TEX = "\\documentclass{article}\\begin{document}x\\end{document}\n"


def _write(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")
    path.chmod(0o755)


def _stub_pdflatex(mode: str = "clean", counter: str = "") -> str:
    """stub pdflatex: PDF + log'u -output-directory'ye yazar (gerçek motor
    gibi); TEST_RUN_COUNT ile toplam çağrı sayısını tutar. mode=rerun son
    geçişte log'a 'Rerun to get' bırakır (fail-closed yolu). PDF, koşum-
    başına farklı /ID taşır — deney kanonik yolu hesaplar, accept defter-
    aramasına girer (Faz 3 sözleşmesi)."""
    counter_line = ""
    if counter:
        counter_line = (
            'cnt="%s"\n' % counter
            + 'mkdir -p "$(dirname "$cnt")"\n'
            + 'n=$(( $(cat "$cnt" 2>/dev/null || echo 0) + 1 )); echo "$n" > "$cnt"\n'
        )
    rerun_block = ""
    if mode == "rerun":
        rerun_block = (
            'if [ "${TEXLIVE_PASS_INDEX:-0}" = "${TEXLIVE_PASSES:-1}" ]; then\n'
            '  printf "Rerun to get cross-references.\\n" >> "$log"\n'
            "fi\n"
        )
    return (
        "#!/bin/sh\n"
        + counter_line
        + 'for arg in "$@"; do case "$arg" in *.tex) src="$arg";; '
          '-output-directory=*) outdir="${arg#-output-directory=}";; esac; done\n'
        'outdir="${outdir:-$PWD}"\n'
        'base=$(basename -- "${src:-sample.tex}" .tex)\n'
        'out="$outdir/$base.pdf"; log="$outdir/$base.log"\n'
        'printf "%s\\n/ID [<%032d> <%032d>]\\n" "%PDF-1.5" '
        '"${TEXLIVE_RUN_INDEX:-0}" "${TEXLIVE_RUN_INDEX:-0}" > "$out"\n'
        'printf "pass=%s/%s run=%s\\n" "${TEXLIVE_PASS_INDEX:-?}" '
        '"${TEXLIVE_PASSES:-?}" "${TEXLIVE_RUN_INDEX:-?}" > "$log"\n'
        + rerun_block
    )


STUB_TECTONIC = (
    "#!/bin/sh\n"
    'for arg in "$@"; do case "$arg" in *.tex) src="$arg";; esac; done\n'
    'out=$(basename -- "${src:-sample.tex}" .tex).pdf; '
    "printf 'tectonic-pdf' > \"$out\"\n"
)


class TestMakefileTexliveStructural(unittest.TestCase):
    def test_tectonic_twin_still_present(self):
        # Paralel yaşam: geri dönüş yolu (plan Faz 1).
        self.assertTrue(TECTONIC_MAKEFILE.is_file(),
                        "docs/Makefile.tectonic kalmalı")

    def test_structural_contract(self):
        text = MAKEFILE.read_text(encoding="utf-8")
        for marker in ("pdf:", "check:", "accept:", "clean:",
                       "SOURCE_DATE_EPOCH ?=", "-output-directory",
                       "PASSES ?= 3", "Rerun to get",
                       "TEXINPUTS", "TEXMFOUTPUT",
                       "ID_RESIDUAL_ACCEPTANCE.md"):
            self.assertIn(marker, text,
                          f"Makefile sözleşme işareti eksik: {marker}")


class TestMakefileTexliveBehavioral(unittest.TestCase):
    """Stub pdflatex/tectonic ile gerçek make koşumu (TeX derlemesi yok)."""

    def _make(self, target: str, mode: str = "clean", passes="3"):
        # Tempdir context'ten ÇIKMADAN tüm kanıtları oku (return sonrası dizin
        # silinir — ölçülen bulgu: kanıt yolları ölü dönüşüyordu).
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            src = td / "sample.tex"
            src.write_text(TEX, encoding="utf-8")
            tools = td / "tools"
            tools.mkdir()
            counter = td / "counter"
            _write(tools / "pdflatex", _stub_pdflatex(mode, str(counter)))
            _write(tools / "tectonic", STUB_TECTONIC)
            build = td / "build"
            (td / "out").mkdir()
            output = td / "out" / "sample.pdf"
            cmd = ["make", "-f", str(MAKEFILE), target,
                   f"SOURCE={src}", f"BUILD_DIR={build}", f"OUTPUT={output}",
                   f"PDFlatex={tools / 'pdflatex'}", "SOURCE_DATE_EPOCH=0"]
            if passes is not None:
                cmd.append(f"PASSES={passes}")
            env = dict(os.environ,
                       PATH=f"{tools}:{os.environ.get('PATH', '')}",
                       TEST_RUN_COUNT=str(counter))
            r = subprocess.run(cmd, capture_output=True, text=True,
                               env=env, cwd=td)
            report = build / "determinism_report.txt"
            return {
                "rc": r.returncode,
                "out": r.stdout + r.stderr,
                "build_pdf": (build / "sample.pdf").is_file(),
                "output_bytes": output.read_bytes() if output.is_file() else None,
                "counter": counter.read_text().strip() if counter.is_file() else None,
                "report": report.read_text(encoding="utf-8") if report.is_file() else None,
            }

    def test_pdf_runs_three_passes_and_copies_output(self):
        res = self._make("pdf", passes="3")
        self.assertEqual(res["rc"], 0, res["out"])
        self.assertEqual(res["counter"], "3",
                         "pdf target tam PASSES geçiş koşmalı (Faz 0)")
        self.assertTrue(res["build_pdf"], "PDF BUILD_DIR'de üretilmeli")
        self.assertIsNotNone(res["output_bytes"], "PDF OUTPUT'a kopyalanmalı")

    def test_pdf_fails_closed_when_rerun_left(self):
        # Faz 0: son geçiş logunda 'Rerun to get' varsa hizalama yok → fail-closed.
        res = self._make("pdf", mode="rerun", passes="3")
        self.assertNotEqual(res["rc"], 0, res["out"])
        self.assertIn("Rerun", res["out"])

    def test_check_delegates_experiment_and_pins_three_passes(self):
        # check = 2 bağımsız 3-geçişli koşum + kanonik karşılaştırma + Rerun=0
        # (deney betiğine delege; stub pdflatex tam 6 kez çağrılmalı).
        res = self._make("check", mode="clean", passes="3")
        self.assertEqual(res["rc"], 0, res["out"])
        self.assertEqual(res["counter"], "6", "3 geçiş × 2 koşum")
        report = res["report"] or ""
        self.assertIn("passes=3", report)
        self.assertIn("verdict=PASS", report)
        self.assertIn("texlive_run1_rerun_left=0", report)
        self.assertIn("texlive_run2_rerun_left=0", report)

    def test_check_fails_closed_on_unconverged_log(self):
        res = self._make("check", mode="rerun", passes="3")
        self.assertNotEqual(res["rc"], 0, res["out"])
        self.assertIsNotNone(res["report"], "başarısız deney bile rapor yazmalı")
        self.assertIn("residual=unconverged", res["report"])

    def test_accept_fails_closed_on_unrecorded_canonical(self):
        # Faz 3: accept = check + defter doğrulaması. Stub kanonik hash
        # defterde olmayacağı için fail-closed ve remedy göstermeli.
        res = self._make("accept", passes=None)
        self.assertNotEqual(res["rc"], 0, res["out"])
        self.assertIn("ID_RESIDUAL_ACCEPTANCE", res["out"])
        self.assertIn("defter", res["out"])


@unittest.skipUnless(
    shutil.which("pdflatex") and shutil.which("tectonic"),
    "gerçek motorlar yok (env-koşullu)",
)
class TestAcceptLedgerRealEngines(unittest.TestCase):
    """Faz 3 gerçek-yüzey: accept, check'in kanonik hash'ini kabul
    raporunun hash geçiş defterinde bulmalı (defter satırı 4: SDE=0,
    3-geçiş kanonik 544516b0…)."""

    def test_accept_pins_canonical_from_ledger(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            build = td / "build"
            cmd = ["make", "-f", str(MAKEFILE), "accept",
                   f"BUILD_DIR={build}",
                   f"OUTPUT={td / 'out.pdf'}",
                   "SOURCE_DATE_EPOCH=0"]
            r = subprocess.run(cmd, capture_output=True, text=True, cwd=td)
        out = r.stdout + r.stderr
        self.assertEqual(r.returncode, 0, out)
        self.assertIn("544516b0", out, "defter satırı 4'ün kanonik öneki")
        self.assertIn("KABUL", out)


if __name__ == "__main__":
    unittest.main()
