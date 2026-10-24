#!/usr/bin/env python3
"""test_makefile_texlive.py — docs/Makefile.texlive (Faz 1) sözleşme kapısı.

docs/Makefile.tectonic'in TeXLive ikizi stub araçlarla sabitlenir (gerçek
TeX derlemesi yapılmaz):

  1) Yapısal: pdf/check/accept/clean target'ları, SOURCE_DATE_EPOCH ?=
     semantiği (geçmiş commit'i yeniden üretme), -output-directory
     (GÜVENLİK: kaynak dizinine asla yazma), PASSES ?= 3 (Faz 0: yeni
     target'lar tam 3 geçiş), son-geçiş 'Rerun to get' denetimi ve
     Makefile.tectonic'in paralel yaşamaya devam etmesi (geri dönüş yolu).
  2) pdf: tam PASSES geçiş koşar (stub sayaç == 3), PDF YALNIZ BUILD_DIR'de
     üretilir; son geçiş logunda 'Rerun to get' varsa fail-closed.
     Değişim-farkında yazım sınırı: tracked teslim OUTPUT'una dokunulmaz
     (içerik + mtime değişmez; olmayan OUTPUT yaratılmaz).
  3) check: deney betiğine delege eder — 2 bağımsız 3-geçişli koşum,
     verdict=PASS + rerun_left=0 x2 olmadan RC=0 YOK; stub pdflatex tam
     6 kez çağrılır.
  4) plate-book: canvas ailesi (Incidental Proof) hedefleri — el yazmasından
     AYRI SDE sabiti (PLATE_BOOK_EPOCH ?= 1700000000; SOURCE_DATE_EPOCH'tan
     türetilmez, aksi halde el yazması epoch'u canvas PDF'lerini sessizce
     yeniden damgalar), tectonic/XeTeX motor sözleşmesi, BUILD_DIR'a yazıp
     kanonik levha yoluna kopyalama ve plate-book-check'in kaynak-BAŞINA
     determinizm kapısı (2 bağımsız SDE koşumu; stub harness ile fail-closed
     yolları ölçülür — verdict=PASS yoksa ve drift varsa RC=0 YOK).
  5) accept: Faz 3 kabul raporunun (docs/ID_RESIDUAL_ACCEPTANCE.md) hash
     geçiş defterini doğrular — önce check'i koşturur (taze kanıt), sonra
     kanonik hash'i defterde arar; defterde yoksa fail-closed (yeni
     bağlam → deftere bilinçli satır, Faz 6 çıkış yolu) ve OUTPUT'a
     yazılmaz.
  5) accept yazım sınırı: tracked OUTPUT'un TEK yazım yolu accept'tir.
     Defter onayı + taze artefaktın kanonik hash eşleşmesi şart; yazım
     atomiktir (tmp+rename) ve öncesi/sonrası sha256 penceresi basılır.
     Taze derleme defterden kaymışsa yazım reddedilir (OUTPUT değişmez).

stdlib-only, OFFLINE.
"""
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
MAKEFILE = ROOT / "docs" / "Makefile.texlive"
TECTONIC_MAKEFILE = ROOT / "docs" / "Makefile.tectonic"
CANVAS_SCRIPT = ROOT / "_calisma" / "CIKTI" / "canvas_determinism_test.sh"
PLATE_STEMS = ("incidental_proof_canvas", "incidental_proof_plate02",
               "incidental_proof_plate03", "incidental_proof_plate04",
               "incidental_proof_book")

# Kanonik hash'in TEK uygulaması (Faz 4): ikinci bir kopya iki gerçeklik
# yaratırdı — yazım sınırı testi de aynı görünümü okur.
sys.path.insert(0, str(ROOT / "_calisma" / "CIKTI"))
import pdf_id_canonical  # noqa: E402

TEX = "\\documentclass{article}\\begin{document}x\\end{document}\n"

# Tracked teslim OUTPUT'unun sentinel'i + sabit geçmiş mtime: yazım olursa
# (aynı baytlar yeniden yazılsa bile) mtime penceresi kesin ayrışır.
SENTINEL_PDF = b"%PDF-1.5\nTRACKED-DELIVERY-SENTINEL\n"
# Önceki bir koşumdan BUILD_DIR'de kalmış bayat artefakt: onaysız bağlamda
# tracked OUTPUT'a kopyalanmamalı (yazım yolu defter kapısından geçer).
STALE_ARTIFACT_PDF = b"%PDF-1.5\nSTALE-BUILD-ARTIFACT\n"
PAST = 1_600_000_000
PAST_NS = PAST * 10 ** 9


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_bytes(data: bytes) -> str:
    return pdf_id_canonical.canonical_sha256_bytes(data)[0]


def _canonical(report_text: str) -> str:
    for line in report_text.splitlines():
        if line.startswith("texlive_canonical_run1_sha256="):
            return line.split("=", 1)[1].strip()
    return ""


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
    drift_block = ""
    if mode == "drift":
        # Yazım sınırı tatbikatı (gate 2): check koşumları TEXLIVE_RUN_INDEX
        # taşır (1/2) ve temiz PDF üretir; accept'in taze derlemesi pdf
        # hedefinden gelir ve RUN_INDEX VERMEZ → gövdeye fazladan bayt
        # eklenir, kanonik hash defterden kayar, yazım reddedilmeli.
        drift_block = (
            'if [ -z "${TEXLIVE_RUN_INDEX:-}" ]; then\n'
            '  printf "DRIFT\\n" >> "$out"\n'
            "fi\n"
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
        + drift_block
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


def _recipe(text: str, target: str) -> str:
    """Makefile'dan hedefin reçete bloğunu çıkarır (sekme-prefixli satırlar).

    Değişim-farkında pin: hangi hedefin tracked OUTPUT'a atıf yaptığı
    metinden değil, reçete sınırından okunur.
    """
    lines = text.splitlines()
    start = next((i for i, l in enumerate(lines)
                  if l.startswith(f"{target}:")), None)
    assert start is not None, f"{target} hedefi Makefile'da yok"
    block = []
    for line in lines[start + 1:]:
        if not line.startswith("\t"):
            break
        block.append(line)
    return "\n".join(block)


class _Sandbox:
    """Stub araçlı, izole make evreni (aynı dizinde iki faz koşulabilsin)."""

    def __init__(self, td, mode: str = "clean"):
        self.td = Path(td)
        self.src = self.td / "sample.tex"
        self.src.write_text(TEX, encoding="utf-8")
        self.tools = self.td / "tools"
        self.tools.mkdir()
        self.counter = self.td / "counter"
        _write(self.tools / "pdflatex", _stub_pdflatex(mode, str(self.counter)))
        _write(self.tools / "tectonic", STUB_TECTONIC)
        self.build = self.td / "build"
        (self.td / "out").mkdir()
        self.output = self.td / "out" / "sample.pdf"
        self.ledger = self.td / "acceptance_ledger.md"

    def write_output(self, body: bytes = SENTINEL_PDF) -> None:
        """Tracked OUTPUT'u sentinel baytlarla kur; mtime'ı GEÇMİŞE sabitle
        ki onaylı/onaysız her yazım pencere dışına düşsün."""
        self.output.write_bytes(body)
        os.utime(self.output, (PAST, PAST))

    def write_stale_artifact(self, body: bytes = STALE_ARTIFACT_PDF) -> None:
        """BUILD_DIR'de önceki koşumdan kalmış artefaktı taklit et."""
        self.build.mkdir(parents=True, exist_ok=True)
        (self.build / "sample.pdf").write_bytes(body)

    def snapshot(self) -> dict:
        if self.output.is_file():
            out = {
                "output_exists": True,
                "output_bytes": self.output.read_bytes(),
                "output_mtime_ns": self.output.stat().st_mtime_ns,
            }
        else:
            out = {"output_exists": False, "output_bytes": None,
                   "output_mtime_ns": None}
        report = self.build / "determinism_report.txt"
        artifact = self.build / "sample.pdf"
        return {
            "build_pdf": artifact.is_file(),
            "build_bytes": artifact.read_bytes() if artifact.is_file() else None,
            "counter": self.counter.read_text().strip()
            if self.counter.is_file() else None,
            "report": report.read_text(encoding="utf-8")
            if report.is_file() else None,
            **out,
        }

    def run(self, target: str, passes="3", accept_doc=None) -> dict:
        cmd = ["make", "-f", str(MAKEFILE), target,
               f"SOURCE={self.src}", f"BUILD_DIR={self.build}",
               f"OUTPUT={self.output}",
               f"PDFlatex={self.tools / 'pdflatex'}", "SOURCE_DATE_EPOCH=0"]
        if passes is not None:
            cmd.append(f"PASSES={passes}")
        if accept_doc is not None:
            cmd.append(f"ACCEPT_DOC={accept_doc}")
        env = dict(os.environ,
                   PATH=f"{self.tools}:{os.environ.get('PATH', '')}",
                   TEST_RUN_COUNT=str(self.counter))
        r = subprocess.run(cmd, capture_output=True, text=True, env=env,
                           cwd=self.td)
        return {"rc": r.returncode, "out": r.stdout + r.stderr,
                **self.snapshot()}


class TestMakefileTexliveBehavioral(unittest.TestCase):
    """Stub pdflatex/tectonic ile gerçek make koşumu (TeX derlemesi yok)."""

    def _make(self, target: str, mode: str = "clean", passes="3",
              accept_doc=None):
        # Tempdir context'ten ÇIKMADAN tüm kanıtları oku (return sonrası dizin
        # silinir — ölçülen bulgu: kanıt yolları ölü dönüşüyordu).
        with tempfile.TemporaryDirectory() as td:
            sb = _Sandbox(td, mode)
            sb.write_output()
            return sb.run(target, passes=passes, accept_doc=accept_doc)

    def test_pdf_writes_only_build_dir_and_leaves_tracked_output_untouched(self):
        # Değişim-farkında yazım sınırı: yerel derleme BUILD_DIR'a yazar;
        # tracked OUTPUT'un ne içeriği ne mtime'ı değişir (aynı baytları
        # yeniden yazmak bile yakalanır — sentinel mtime geçmişe sabit).
        res = self._make("pdf", passes="3")
        self.assertEqual(res["rc"], 0, res["out"])
        self.assertEqual(res["counter"], "3",
                         "pdf target tam PASSES geçiş koşmalı (Faz 0)")
        self.assertTrue(res["build_pdf"], "PDF BUILD_DIR'de üretilmeli")
        self.assertEqual(res["output_bytes"], SENTINEL_PDF,
                         "tracked teslim OUTPUT içeriği değişmemeli")
        self.assertEqual(res["output_mtime_ns"], PAST_NS,
                         "tracked OUTPUT'a yazım olmamalı (mtime sabit)")
        self.assertIn("output_write=deferred", res["out"])
        self.assertIn("build/sample.pdf", res["out"])

    def test_pdf_never_creates_a_missing_tracked_output(self):
        # Sınır pozitif yönü: "dokunma" yaratmayı da kapsar — pdf, olmayan
        # tracked OUTPUT dosyasını üretmemeli.
        with tempfile.TemporaryDirectory() as td:
            sb = _Sandbox(td)
            res = sb.run("pdf", passes="3")
            self.assertEqual(res["rc"], 0, res["out"])
            self.assertTrue(res["build_pdf"])
            self.assertFalse(res["output_exists"],
                             "pdf olmayan tracked OUTPUT'u yaratmamalı")

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
        # defterde olmayacağı için fail-closed ve remedy göstermeli; tracked
        # OUTPUT'a dokunulmaz — BUILD_DIR'de bayat artefakt DURSA BİLE (yazım
        # yalnız defter kapısından sonra, o da kanonik eşleşmeyle).
        with tempfile.TemporaryDirectory() as td:
            sb = _Sandbox(td)
            sb.write_output()
            sb.write_stale_artifact()
            res = sb.run("accept", passes=None)
        self.assertNotEqual(res["rc"], 0, res["out"])
        self.assertIn("ID_RESIDUAL_ACCEPTANCE", res["out"])
        self.assertIn("defter", res["out"])
        self.assertIn("YAZILMADI", res["out"])
        self.assertEqual(res["output_bytes"], SENTINEL_PDF,
                         "bayat artefakt tracked OUTPUT'a kopyalanmamalı")
        self.assertEqual(res["output_mtime_ns"], PAST_NS)
        self.assertEqual(res["counter"], "6",
                         "onaysız bağlamda taze derleme (pdf) koşmamalı")


class TestTexliveTrackedOutputWriteBoundary(unittest.TestCase):
    """Tracked teslim OUTPUT'unun yazım sınırı: yerel derleme (pdf) yalnız
    BUILD_DIR'a yazar; OUTPUT'un TEK yazım yolu accept'tir ve yazım yalnız
    defter onayı + taze artefaktın kanonik hash eşleşmesiyle olur.

    İki fazlı koşum şart: (1) check ile kanonik hash ölçülüp fixture deftere
    yazılır (onay ancak ölçülen hash ile kurulabilir), (2) accept aynı sanal
    evrende koşar.
    """

    def _structural(self, target: str) -> str:
        return _recipe(MAKEFILE.read_text(encoding="utf-8"), target)

    def test_only_accept_recipe_touches_tracked_output(self):
        # Değişim-farkında yapısal pin: pdf/check/clean/engineinfo tracked yola
        # ATIF bile etmez; kopyalama + atomik yazım yalnız accept reçetesinde.
        for target in ("pdf", "check", "clean", "engineinfo"):
            self.assertNotIn("$(OUTPUT)", self._structural(target),
                             f"{target} reçetesi tracked OUTPUT'a atıf yapmamalı")
        accept = self._structural("accept")
        self.assertIn("$(OUTPUT)", accept)
        self.assertIn('cp "$$ART" "$$TMP"', accept,
                      "accept onaylı yazımı kopyalamayla yapmalı")
        self.assertIn('mv -f "$$TMP"', accept,
                      "yazım atomik olmalı (tmp+rename)")
        self.assertIn("ART_CANON", accept,
                      "yazımdan önce kanonik eşleşme kapısı yok")
        self.assertIn("YAZILMADI", accept, "fail-closed mesajı yok")

    def _approved_two_phase(self, mode: str):
        """Faz 1: check → kanonik hash → fixture defter; Faz 2: accept."""
        td = tempfile.TemporaryDirectory()
        sb = _Sandbox(td.name, mode)
        sb.write_output()
        first = sb.run("check", passes="3")
        if first["rc"] != 0:
            td.cleanup()
            self.fail(f"hazırlık check'i geçmedi: {first['out']}")
        canon = _canonical(first["report"] or "")
        if not canon:
            td.cleanup()
            self.fail(f"rapor kanonik hash taşımıyor: {first['report']!r}")
        sb.ledger.write_text(
            "# fixture defter\n\n| Ölçüm | Kanonik (referans) |\n|---|---|\n"
            f"| stub 3-geçiş | {canon} |\n", encoding="utf-8")
        second = sb.run("accept", passes=None, accept_doc=sb.ledger)
        return td, sb, canon, second, first["counter"]

    def test_accept_writes_tracked_output_after_ledger_approval(self):
        td, sb, canon, res, before_counter = self._approved_two_phase("clean")
        try:
            self.assertEqual(res["rc"], 0, res["out"])
            self.assertIn("KABUL", res["out"])
            self.assertIn("tracked_output_written=true", res["out"])
            self.assertIn(f"output_sha256_before={_sha256(SENTINEL_PDF)}",
                          res["out"])
            self.assertIn(f"output_sha256_after={_sha256(res['build_bytes'])}",
                          res["out"])
            self.assertIn("tracked_output_note=", res["out"])
            self.assertEqual(res["output_bytes"], res["build_bytes"],
                             "tracked OUTPUT taze artefaktın baytlarını taşımalı")
            self.assertNotEqual(res["output_mtime_ns"], PAST_NS,
                                "onaylı yazım mtime'ı değiştirmeli")
            self.assertEqual(_canonical_bytes(res["output_bytes"]), canon,
                             "yazılan artefakt defterin kanonik hash'iyle eşleşmeli")
            self.assertEqual(int(res["counter"]) - int(before_counter), 9,
                             "accept fazı = check 6 + taze pdf 3 stub çağrısı")
        finally:
            td.cleanup()

    def test_accept_refuses_write_when_fresh_artifact_canonical_drifts(self):
        # Gate 2: defter onaylı kanonik hash'i taşır AMA accept'in taze
        # derlemesi kaymış → yazım reddedilir, tracked OUTPUT değişmez.
        td, sb, canon, res, _before = self._approved_two_phase("drift")
        try:
            self.assertNotEqual(res["rc"], 0, res["out"])
            self.assertIn("YAZILMADI", res["out"])
            self.assertIn("artefakt=", res["out"])
            self.assertEqual(res["output_bytes"], SENTINEL_PDF)
            self.assertEqual(res["output_mtime_ns"], PAST_NS,
                             "kanonik kaymada tracked OUTPUT'a yazılmaz")
            self.assertNotEqual(_canonical_bytes(res["build_bytes"]), canon,
                                "stub drift üretmedi — test kurulumu geçersiz")
        finally:
            td.cleanup()


@unittest.skipUnless(
    shutil.which("pdflatex") and shutil.which("tectonic"),
    "gerçek motorlar yok (env-koşullu)",
)
class TestAcceptLedgerRealEngines(unittest.TestCase):
    """Faz 3 gerçek-yüzey: accept, check'in kanonik hash'ini kabul
    raporunun hash geçiş defterinde bulmalı (defter satırı 9: SDE=0,
    3-geçiş kanonik 5899be5d…)."""

    def test_accept_pins_canonical_from_ledger_and_writes_delivery(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            build = td / "build"
            output = td / "out.pdf"
            cmd = ["make", "-f", str(MAKEFILE), "accept",
                   f"BUILD_DIR={build}", f"OUTPUT={output}",
                   "SOURCE_DATE_EPOCH=0"]
            r = subprocess.run(cmd, capture_output=True, text=True, cwd=td)
            out = r.stdout + r.stderr
            artifact = build / "ingiliz_empirizmi_v3.pdf"
            written = output.read_bytes() if output.is_file() else None
            artifact_bytes = (artifact.read_bytes()
                              if artifact.is_file() else None)
        self.assertEqual(r.returncode, 0, out)
        # Kanonik hash KAYNAK-TÜREVLİDİR: kaynak değişince satır 9'a geçilir
        # (defter satır 4 = kaynak öncesi ölçüm, kasıtlı olarak korunur).
        self.assertIn("5899be5d", out, "defter satırı 9'un kanonik öneki")
        self.assertIn("KABUL", out)
        self.assertIn("tracked_output_written=true", out)
        self.assertIsNotNone(written,
                             "accept defter onayından sonra tracked OUTPUT yazmalı")
        self.assertEqual(written, artifact_bytes,
                         "yazılan teslim PDF'i doğrulanmış artefaktın baytları olmalı")
        self.assertTrue(_canonical_bytes(written).startswith("544516b0"),
                        "yazılan PDF kanonik hash'i defter satırı 4 ile başlamalı")



def _stub_plate_tectonic(mode: str, counter: str, epoch_log: str,
                        order_log: str = "") -> str:
    """canvas ailesi için stub tectonic: PDF'i --outdir'e yazar.

    mode='drift' → her çağrıda içerik farklı: determinizm kapısının
    fail-closed yolunu ölçer. SDE her çağrıda log'a yazılır; hedefin hangi
    epoch'u ihraç ettiği iddiası ancak böyle kanıtlanır (iddia ile log
    ayrışırsa test kırmızı).

    Satırlar raw-string listesinden birleştirilir: printf biçimlerindeki
    `\n` tek katmanda kalır, kaçış katmanı birikmez."""
    lines = [
        r'#!/bin/sh',
        r'cnt="@CNT@"',
        r'if [ -n "$cnt" ]; then',
        r'  n=$(( $(cat "$cnt" 2>/dev/null || echo 0) + 1 )); echo "$n" > "$cnt"',
        r'fi',
        r'sdelog="@SDE@"',
        r'if [ -n "$sdelog" ]; then',
        r'  printf "sde=%s\n" "${SOURCE_DATE_EPOCH:-unset}" >> "$sdelog"',
        r'fi',
        r'prev=""; outdir="."; src=""',
        r'for arg in "$@"; do',
        r'  if [ "$prev" = "--outdir" ]; then outdir="$arg"; fi',
        r'  case "$arg" in *.tex) src="$arg";; esac',
        r'  prev="$arg"',
        r'done',
        r'base=$(basename -- "${src:-sample.tex}" .tex)',
        r'if [ "$base" = "incidental_proof_book" ]; then',
        r'  vis=0',
        r'  for p in incidental_proof_canvas incidental_proof_plate02 incidental_proof_plate03 incidental_proof_plate04; do',
        r'    [ -f "$(dirname "$src")/$p.pdf" ] && vis=$((vis + 1))',
        r'  done',
        r'  printf "plates_visible_to_book=%s\n" "$vis" >> "@ORD@"',
        r'fi',
        r'mkdir -p "$outdir"',
        r'{',
        r'  printf "%%PDF-1.5\n"',
        r'  printf "sde=%s\n" "${SOURCE_DATE_EPOCH:-unset}"',
        r'  printf "/ID [<%032d> <%032d>]\n" 0 0',
        r'} > "$outdir/$base.pdf"',
    ]
    if mode == "drift":
        lines.append(r'printf "call=%s\n" "${n:-0}" >> "$outdir/$base.pdf"')
    return ("\n".join(lines) + "\n").replace("@CNT@", counter) \
        .replace("@SDE@", epoch_log).replace("@ORD@", order_log)


# Makefile'ın dayandığı harness sözleşmesinin asgarisi: TEX_SOURCE +
# DETERMINISM_OUT okunur, TECTONIC_BIN iki bağımsız koşumla çağrılır,
# karar rapora (verdict=PASS|FAIL) yazılır. Gerçek harness
# (canvas_determinism_test.sh) aynı sözleşmeyi taşır — TestPlateBookRealSurface
# onu doğrudan koşar.
#
# Üç mod: 'clean' (dürüst), 'verdict_fail_exit_zero' (rapora FAIL yazar ama
# RC=0 — kararın RAPORA yazıldığını pinler), 'verdict_pass_exit_nonzero'
# (rapora PASS yazar ama kendi RC'si ≠0 — harness'ın çıkış durumunun da
# onurlandırıldığını pinler). Kapının iki bağımsız yolu böyle ayrı ayrı
# kanıtlanır; tek yol kaldırıldığında hangi testin kırmızıya döndüğü ölçüldü.
def _stub_harness(mode: str = "clean") -> str:
    lines = [
        r'#!/bin/sh',
        r'set -eu',
        r'out="${DETERMINISM_OUT:-./determinism_report.txt}"',
        r'mkdir -p "$(dirname "$out")"',
        r'd1="$(dirname "$out")/.stub-run1"; d2="$(dirname "$out")/.stub-run2"',
        r'rm -rf "$d1" "$d2"; mkdir -p "$d1" "$d2"',
        r'"$TECTONIC_BIN" --outdir "$d1" "$TEX_SOURCE" >/dev/null',
        r'"$TECTONIC_BIN" --outdir "$d2" "$TEX_SOURCE" >/dev/null',
        r'stem=$(basename "${TEX_SOURCE%.tex}")',
        r'h1=$(sha256sum "$d1/$stem.pdf" | awk "{print \$1}")',
        r'h2=$(sha256sum "$d2/$stem.pdf" | awk "{print \$1}")',
        r'printf "tectonic=stub\nsource_date_epoch=%s\n" "${SOURCE_DATE_EPOCH:-0}" > "$out"',
        r'printf "tectonic_run1_sha256=%s\ntectonic_run2_sha256=%s\n" "$h1" "$h2" >> "$out"',
        r'rm -rf "$d1" "$d2"',
    ]
    if mode == "clean":
        lines += [
            r'if [ "$h1" = "$h2" ]; then printf "residual=none\nverdict=PASS\n" >> "$out"; exit 0; fi',
            r'printf "residual=content\nverdict=FAIL\n" >> "$out"; exit 1',
        ]
    elif mode == "verdict_fail_exit_zero":
        lines += [r'printf "residual=content\nverdict=FAIL\n" >> "$out"', r'exit 0']
    elif mode == "verdict_pass_exit_nonzero":
        lines += [r'printf "residual=none\nverdict=PASS\n" >> "$out"', r'exit 3']
    else:
        raise ValueError(mode)
    return "\n".join(lines) + "\n"


STUB_CANVAS_HARNESS = _stub_harness("clean")


class TestMakefileTexlivePlateBook(unittest.TestCase):
    """Canvas ailesi (Incidental Proof) — tectonic/XeTeX + ayrı SDE sabiti."""

    def test_structural_contract(self):
        mk = MAKEFILE.read_text(encoding="utf-8")
        for marker in ("plate-book:", "plate-book-check:", "plate-book-clean:",
                       "PLATE_BOOK_EPOCH ?= 1700000000",
                       "PLATE_DETERMINISM_SCRIPT :=",
                       "canvas_determinism_test.sh",
                       "PLATE_BUILD_DIR", '--outdir "$(PLATE_BUILD_DIR)"',
                       "PLATE_DIR ?="):
            self.assertIn(marker, mk, f"plate-book sözleşme işareti eksik: {marker}")
        phony = [ln for ln in mk.splitlines() if ln.startswith(".PHONY:")][0]
        for tgt in ("plate-book", "plate-book-check", "plate-book-clean"):
            self.assertIn(tgt, phony, f"{tgt} .PHONY'de değil")

    def test_epoch_is_a_family_constant_not_derived(self):
        mk = MAKEFILE.read_text(encoding="utf-8")
        # Aile sabiti çivili ve el yazması epoch'undan TÜRETİLMEMİŞ olmalı.
        self.assertIn("PLATE_BOOK_EPOCH ?= 1700000000", mk)
        self.assertNotIn("PLATE_BOOK_EPOCH ?= $(SOURCE_DATE_EPOCH)", mk)
        # Her iki hedef de SDE'yi aile sabitinden ihraç eder.
        self.assertIn('SOURCE_DATE_EPOCH="$(PLATE_BOOK_EPOCH)"', mk)

    def test_readme_documents_plate_book(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("docs/Makefile.texlive plate-book", readme)
        self.assertIn("plate-book-check", readme)
        self.assertIn("PLATE_BOOK_EPOCH", readme)

    def _plate(self, target, mode="clean", harness="stub", script=None,
               tectonic=None, env_extra=None, harness_mode="clean"):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            canvas = td / "canvas"
            canvas.mkdir()
            for stem in PLATE_STEMS:
                (canvas / f"{stem}.tex").write_text(TEX, encoding="utf-8")
            tools = td / "tools"
            tools.mkdir()
            counter = td / "counter"
            epoch_log = td / "epochs"
            order_log = td / "order"
            stub_tex = tools / "tectonic"
            _write(stub_tex, _stub_plate_tectonic(
                mode, str(counter), str(epoch_log), str(order_log)))
            if harness == "stub":
                script = td / "canvas_determinism_test.sh"
                _write(script, _stub_harness(harness_mode))
            build = td / "build"
            cmd = ["make", "-f", str(MAKEFILE), target,
                   f"PLATE_DIR={canvas}", f"PLATE_BUILD_DIR={build}"]
            if script is not None:
                cmd.append(f"PLATE_DETERMINISM_SCRIPT={script}")
            cmd.append(f"PLATE_TECTONIC={tectonic or stub_tex}")
            env = dict(os.environ, TEST_RUN_COUNT=str(counter))
            env.pop("PLATE_BOOK_EPOCH", None)
            env.update(env_extra or {})
            r = subprocess.run(cmd, capture_output=True, text=True, env=env, cwd=td)
            reports = sorted((build / "determinism").glob("*.txt"))
            return {
                "rc": r.returncode,
                "out": r.stdout + r.stderr,
                "counter": counter.read_text().strip() if counter.is_file() else None,
                "epochs": sorted(set(epoch_log.read_text().split())) if epoch_log.is_file() else [],
                "order": order_log.read_text() if order_log.is_file() else "",
                "canonical": {st: (canvas / f"{st}.pdf").is_file() for st in PLATE_STEMS},
                "built": {st: (build / f"{st}.pdf").is_file() for st in PLATE_STEMS},
                "reports": {rp.name: rp.read_text(encoding="utf-8") for rp in reports},
            }

    def test_build_compiles_all_sources_and_copies_canonical(self):
        res = self._plate("plate-book")
        self.assertEqual(res["rc"], 0, res["out"])
        self.assertEqual(res["counter"], "5", "5 kaynak = 4 levha + kitap")
        self.assertTrue(all(res["built"].values()), f"BUILD_DIR eksik: {res['built']}")
        self.assertTrue(all(res["canonical"].values()),
                        f"kanonik levha yolu eksik: {res['canonical']}")
        self.assertIn("plates=4", res["out"])
        self.assertIn("source_date_epoch=1700000000", res["out"])
        self.assertIn("sha256=", res["out"])

    def test_book_is_compiled_after_plates_are_copied(self):
        # Kanonik dizinde onceden PDF YOKKEN (taze durum) kitap derlenirken
        # dort levhanin da kanonik yolda olmasi gerekir; aksi halde kitap
        # onceki nesil (ya da hic) levhayi gomer. Eski "derle-hepsini sonra
        # kopyala" sirasi bu testte vis=0 verir.
        res = self._plate("plate-book")
        self.assertEqual(res["rc"], 0, res["out"])
        self.assertIn("plates_visible_to_book=4", res["order"], res["order"])

    def test_build_fails_closed_without_tectonic(self):
        res = self._plate("plate-book", tectonic="/nonexistent/tectonic")
        self.assertEqual(res["rc"], 2, res["out"])
        self.assertIn("tectonic not found", res["out"])

    def test_check_runs_two_sde_runs_per_source_with_family_epoch(self):
        # Ortamda el yazması epoch'u olsa bile canvas ailesi kendi sabitini
        # ihraç etmeli: aksi halde (ölçülmüş hata sınıfı) kabul edilen
        # PDF ile üretilen PDF farklı epoch'ta derlenir.
        res = self._plate("plate-book-check", env_extra={"SOURCE_DATE_EPOCH": "999"})
        self.assertEqual(res["rc"], 0, res["out"])
        self.assertEqual(res["counter"], "10", "5 kaynak × 2 koşum")
        self.assertEqual(res["epochs"], ["sde=1700000000"],
                         f"aile sabiti ihraç edilmedi: {res['epochs']}")
        self.assertEqual(len(res["reports"]), 5, res["reports"].keys())
        for name, body in res["reports"].items():
            self.assertIn("verdict=PASS", body, name)
        self.assertIn("verdict=PASS", res["out"])

    def test_check_fails_closed_on_drift(self):
        # Mutasyon: tectonic her çağrıda farklı bayt üretirse kapı KIRMIZI
        # olmalı (yeşil, kanıt değildir).
        res = self._plate("plate-book-check", mode="drift")
        self.assertNotEqual(res["rc"], 0, res["out"])
        self.assertTrue(any("verdict=FAIL" in b for b in res["reports"].values()),
                        res["reports"])

    def test_check_fails_closed_when_report_says_fail_despite_exit_zero(self):
        # Karar rapora yazilir: harness RC=0 donse bile verdict=FAIL tasiyan
        # bir rapor yesil gecemez (M3 mutasyonunda bu yol tek basina ortaya
        # cikti — drift testi yalnizca harness RC'sini goruyordu).
        res = self._plate("plate-book-check", harness_mode="verdict_fail_exit_zero")
        self.assertNotEqual(res["rc"], 0, res["out"])
        self.assertIn("verdict PASS degil", res["out"])

    def test_check_fails_closed_when_harness_fails_despite_pass_report(self):
        # Ters yon: rapor PASS dese bile harness'in kendi cikis durumu
        # sifirdan farkliysa kapi duser (M6 mutasyonu).
        res = self._plate("plate-book-check", harness_mode="verdict_pass_exit_nonzero")
        self.assertNotEqual(res["rc"], 0, res["out"])

    def test_check_fails_closed_when_script_missing(self):
        # harness="none": stub yolu EZMESİN, hedef gerçekten eksik betiği görsün
        res = self._plate("plate-book-check", harness="none",
                          script="/nonexistent/canvas_determinism_test.sh")
        self.assertNotEqual(res["rc"], 0, res["out"])
        self.assertIn("fail-closed", res["out"])

    def test_check_fails_closed_without_tectonic(self):
        res = self._plate("plate-book-check", tectonic="/nonexistent/tectonic")
        self.assertEqual(res["rc"], 2, res["out"])


@unittest.skipUnless(
    CANVAS_SCRIPT.is_file() and shutil.which("tectonic"),
    "canvas deney betiği ya da tectonic yok (gerçek-yüzey koşumu atlandı)",
)
class TestPlateBookRealSurface(unittest.TestCase):
    """Gerçek harness + gerçek kaynak + gerçek tectonic: delegasyonun
    gerçekten uçtan uca çalıştığı tek koşum (tek levha; kitap değil — süre)."""

    def test_real_harness_on_real_plate(self):
        real = ROOT / "_calisma" / "CIKTI" / "canvas" / "incidental_proof_canvas.tex"
        self.assertTrue(real.is_file(), f"gerçek levha kaynağı yok: {real}")
        with tempfile.TemporaryDirectory() as td:
            build = Path(td) / "build"
            cmd = ["make", "-f", str(MAKEFILE), "plate-book-check",
                   f"PLATE_DIR={real.parent}", f"PLATE_BUILD_DIR={build}",
                   f"PLATE_SOURCES={real}", f"PLATE_BOOK={real}"]
            r = subprocess.run(cmd, capture_output=True, text=True, cwd=td)
        out = r.stdout + r.stderr
        self.assertEqual(r.returncode, 0, out)
        self.assertIn("verdict=PASS", out)

if __name__ == "__main__":
    unittest.main()
