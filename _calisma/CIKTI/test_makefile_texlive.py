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
     kanıtı GERÇEK ÜRETİCİYE (gen_id_residual_acceptance.py) delege eder:
     rapor ayrıştırılır (verdict=PASS + 2× rerun=0 + run1=run2), kanonik
     hash §4 defterinde aranır. Defterde yoksa fail-closed (yeni bağlam →
     bilinçli satır, Faz 6 çıkış yolu); `LEDGER=update` satırı ELLE değil
     ölçülen alanlardan üretir. Varsayılan `LEDGER=check` salt-okunurdur.

stdlib-only, OFFLINE.
"""
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
MAKEFILE = ROOT / "docs" / "Makefile.texlive"
TECTONIC_MAKEFILE = ROOT / "docs" / "Makefile.tectonic"
ACCEPT_DOC = ROOT / "docs" / "ID_RESIDUAL_ACCEPTANCE.md"

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


class TestMakefileTexlivePhase0(unittest.TestCase):
    """Faz 0 sözleşme sabitleri: motor-kilidi dokümantasyonu + paralel yaşam."""

    def test_engineinfo_target_contract(self):
        # Motor sürüm kilidi: `make engineinfo` pdfTeX/TeXLive sürümünü ve
        # sözleşme sabitlerini yazdırır (CI log'u için makine-okur satırlar).
        mk = MAKEFILE.read_text(encoding="utf-8")
        self.assertIn("engineinfo:", mk, "engineinfo target'ı yok")
        self.assertIn(".PHONY: all pdf check accept clean engineinfo", mk)
        self.assertIn("$(PDBIN) -version", mk)
        self.assertIn("pdtex_version=", mk)
        self.assertIn("texinputs_contract=", mk)
        self.assertIn("texmfoutput_contract=", mk)
        self.assertIn("output_dir_contract=-output-directory", mk)
        self.assertIn("engine_lock=pdfTeX 3.141592653-2.6", mk)

    def test_readme_documents_parallel_life(self):
        # Paralel yaşam dokümantasyonu (plan Faz 1): README'de her iki
        # Makefile yan yana — motor geçiş rotası + geri dönüş yolu.
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("docs/Makefile.texlive", readme)
        self.assertIn("docs/Makefile.tectonic", readme)
        self.assertIn("engineinfo", readme)


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

    def test_accept_delegates_to_producer(self):
        # Faz 3: accept kabul kanıtını elle sed/grep ile okumaz — tek üretici
        # gen_id_residual_acceptance.py raporu ayrıştırır ve defter satırını
        # ölçülen alanlardan üretir (LEDGER=update).
        text = MAKEFILE.read_text(encoding="utf-8")
        self.assertIn("gen_id_residual_acceptance.py", text)
        self.assertIn("ACCEPT_GEN", text)
        self.assertIn("LEDGER ?= check", text)
        self.assertIn("--update", text)
        self.assertNotIn("sed -n 's/^texlive_canonical_run1_sha256=", text,
                         "elle defter ayrıştırma geri gelmemeli (tek üretici)")


class TestMakefileTexliveBehavioral(unittest.TestCase):
    """Stub pdflatex/tectonic ile gerçek make koşumu (TeX derlemesi yok)."""

    def _make(self, target: str, mode: str = "clean", passes="3",
              ledger=None, doc=None):
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
            if ledger is not None:
                cmd.append(f"LEDGER={ledger}")
            if doc is not None:
                cmd.append(f"ACCEPT_DOC={doc}")
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
                "doc": (Path(doc).read_text(encoding="utf-8")
                        if doc is not None and Path(doc).is_file() else None),
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

    def test_accept_update_appends_measured_ledger_row(self):
        # Faz 6 çıkış yolu: LEDGER=update defter satırını ELLE yazmaz —
        # ölçülen kanıttan (kanonik hash + passes + SDE + motor etiketi)
        # üretip §4 tablosuna ekler ve yeniden doğrular.
        with tempfile.TemporaryDirectory() as td:
            doc = Path(td) / "ACCEPTANCE.md"
            shutil.copyfile(ACCEPT_DOC, doc)
            before = doc.read_text(encoding="utf-8")
            res = self._make("accept", passes=None, ledger="update", doc=doc)
            self.assertEqual(res["rc"], 0, res["out"])
            self.assertIn("DEFTER GÜNCELLENDİ", res["out"])
            self.assertIn("KABUL", res["out"])
            after = res["doc"] or ""
            # satır numarası defterdeki en büyük satırdan türetilir (5 → 6)
            self.assertIn("| 6 |", after)
            self.assertEqual(len(after.splitlines()),
                             len(before.splitlines()) + 1,
                             "update yalnız TEK satır eklemeli")
            canon = re.search(r"^texlive_canonical_run1_sha256=(\S+)$",
                              res["report"] or "", re.M)
            self.assertIsNotNone(canon, res["report"])
            row = [ln for ln in after.splitlines() if ln.startswith("| 6 |")][0]
            self.assertIn(canon.group(1), row,
                          "defter satırı ölçülen kanonik hash'i taşımalı")

    def test_accept_update_is_idempotent(self):
        # Aynı kanıt ikinci kez update edilirse satır eklenmez (defter şişmez).
        with tempfile.TemporaryDirectory() as td:
            doc = Path(td) / "ACCEPTANCE.md"
            shutil.copyfile(ACCEPT_DOC, doc)
            first = self._make("accept", passes=None, ledger="update", doc=doc)
            self.assertEqual(first["rc"], 0, first["out"])
            second = self._make("accept", passes=None, ledger="update", doc=doc)
            self.assertEqual(second["rc"], 0, second["out"])
            self.assertEqual(second["doc"], first["doc"],
                             "ikinci update yeni satır eklememeli")
            self.assertNotIn("DEFTER GÜNCELLENDİ", second["out"])
            self.assertIn("KABUL", second["out"])

    def test_accept_rejects_unknown_ledger_mode(self):
        # Bilinmeyen LEDGER değeri sessizce 'check'e düşmez — fail-closed.
        res = self._make("accept", passes=None, ledger="bogus")
        self.assertNotEqual(res["rc"], 0, res["out"])
        self.assertIn("LEDGER=check|update", res["out"])

    def test_accept_update_fails_closed_without_ledger_table(self):
        # §4 tablosu yoksa update satır üretemez: exit 2, defter değişmez.
        with tempfile.TemporaryDirectory() as td:
            doc = Path(td) / "EMPTY.md"
            doc.write_text("# bos\n", encoding="utf-8")
            res = self._make("accept", passes=None, ledger="update", doc=doc)
            self.assertEqual(res["rc"], 2, res["out"])
            self.assertIn("tablosu bulunamadı", res["out"])
            self.assertEqual(res["doc"], "# bos\n")


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
