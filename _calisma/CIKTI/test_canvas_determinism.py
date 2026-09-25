#!/usr/bin/env python3
"""test_canvas_determinism.py — canvas_determinism_test.sh sözleşme kapısı.

canvas (Incidental Proof) TeX kaynağının determinizm deneyi stub-tectonic ile
sabitlenir (gerçek TeX derlemesi yapılmaz):

  1) PASS sözleşmesi: iki koşum birebir aynı bayt → verdict=PASS,
     residual=none, rc=0; rapor key=value makine-okur.
  2) Kanonik /ID fallback: yalnız /ID farklıysa kanonik hash eşitliği
     verdict=PASS verir (residual=/ID) — motorun rastgele belge-kimliği
     determinizm ihlali sayılmaz (texlive zinciri sözleşmesi).
  3) Tamper fail-closed: içerik farkı kanonik fallback'i atlatabilmez →
     residual=content, verdict=FAIL, rc=1.
  4) SKIP sözleşmesi (K3): tectonic yok → exit 0 + SKIP satırı (cron job'ı
     runner araçlarıyla uyumlu; sessiz kanıt kaybı yok).
  5) SDE env-sızdırma: SOURCE_DATE_EPOCH alt-sürece exportlanır (stub bunu
     görmüyorsa exit 9 → deney rc=1; motor güncel zamanı gömer diyen ölçülmüş
     sapmaya karşı fail-closed).
  6) --outdir güvenlik: tectonic HER çağrıda --outdir alır (almazsa stub
     exit 9 → deney rc=1); kaynak dizinine yazma yolu yok.

stdlib-only, OFFLINE.
"""
import os
import re
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE / "canvas_determinism_test.sh"
TEX = "\\documentclass{article}\\begin{document}x\\end{document}\n"
ID1 = "A" * 32
ID2 = "B" * 32


def _write_exec(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


_ARGPARSE = (
    "#!/bin/sh\n"
    'outdir=""; src=""; saw_outdir=0; prev=0\n'
    'for arg in "$@"; do\n'
    '  if [ "$prev" = "1" ]; then outdir="$arg"; saw_outdir=1; prev=0; continue; fi\n'
    '  case "$arg" in\n'
    '    --outdir) prev=1;;\n'
    '    --outdir=*) outdir="${arg#--outdir=}"; saw_outdir=1;;\n'
    '    *.tex) src="$arg";;\n'
    '  esac\n'
    'done\n'
    'if [ "$saw_outdir" = "0" ]; then echo "OUTDIR-GUARD: --outdir yok" >&2; exit 9; fi\n'
    'base=$(basename -- "${src:-sample.tex}" .tex)\n'
    # Gerçek-motor semantiği: PDF, --outdir'e yazılır (stub CWD'ye DEĞİL).
    'pdf="${outdir:-$PWD}/$base.pdf"\n'
    'if [ -n "$CANV_STUB_SRCFILE" ]; then printf "%s" "$src" > "$CANV_STUB_SRCFILE"; fi\n'
)
# outdir_next kalıntısı yok: --outdir sonraki-arg biçemi (script'in kullandığı
# `--outdir "$PWD"` biçemi) ayrışır; ayrı case-kolu yeterli değilse test
# kırmızıdır — bu yüzden guard her stub'ta.

def _stub(body1, body2=None, sde=None, same_id=False) -> str:
    """Stub tectonic: run1 → body1 + /ID ID1, run2 → body2 (varsayılan body1)
    + /ID ID2. same_id=True ise her iki koşum birebir aynı baytı üretir
    (residual=none yolu). CANV_STUB_CNT ile koşum sayısı tutulur. sde
    verilirse stub SOURCE_DATE_EPOCH'un o değere exportlandığını doğrular
    (değilse exit 9)."""
    sde_guard = ""
    if sde is not None:
        sde_guard = (
            'if [ "${SOURCE_DATE_EPOCH:-UNSET}" != "%s" ]; then '
            'echo "SDE-GUARD: beklenen %s, gelen ${SOURCE_DATE_EPOCH:-UNSET}" '
            '>&2; exit 9; fi\n' % (sde, sde)
        )
    return (
        _ARGPARSE + sde_guard +
        'cnt="$CANV_STUB_CNT"; '
        'n=$(( $(cat "$cnt" 2>/dev/null || echo 0) + 1 )); echo "$n" > "$cnt"\n'
        'if [ "$n" = "1" ]; then b="%s"; id="%s"; else b="%s"; id="%s"; fi\n'
        'printf "%%s\\n/ID [<%%s><%%s>]\\n" "$b" "$id" "$id" > "$pdf"\n'
        % (body1, ID1, body2 if body2 is not None else body1,
           ID1 if same_id else ID2)
    )


def run_experiment(env_extra, tectonic_stub=None, provide_tectonic=True):
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        tex = td / "sample.tex"
        tex.write_text(TEX, encoding="utf-8")
        out = td / "report.txt"
        env = dict(os.environ, TEX_SOURCE=str(tex), DETERMINISM_OUT=str(out),
                   **env_extra)
        if provide_tectonic:
            tools = td / "tools"
            tools.mkdir()
            _write_exec(tools / "tectonic",
                        tectonic_stub if tectonic_stub is not None
                        else _stub("PDF-stub"))
            cnt = td / "cnt"
            env["CANV_STUB_CNT"] = str(cnt)
            env["PATH"] = f"{tools}:{os.environ.get('PATH', '')}"
        r = subprocess.run(["bash", str(SCRIPT)], capture_output=True,
                           text=True, env=env, cwd=td, timeout=60)
        report = out.read_text(encoding="utf-8") if out.is_file() else None
        return {"rc": r.returncode, "out": r.stdout + r.stderr,
                "report": report}


def kv(report, key):
    m = re.search(rf"^{re.escape(key)}=(.*)$", report or "", re.M)
    return m.group(1) if m else None


class TestCanvasDeterminism(unittest.TestCase):
    def test_identical_bytes_pass_residual_none(self):
        res = run_experiment({"SOURCE_DATE_EPOCH": "1700000000"},
                             tectonic_stub=_stub("PDF-stub", same_id=True))
        self.assertEqual(res["rc"], 0, res["out"])
        self.assertEqual(kv(res["report"], "verdict"), "PASS")
        self.assertEqual(kv(res["report"], "residual"), "none")
        self.assertEqual(kv(res["report"], "source_date_epoch"), "1700000000")

    def test_id_only_difference_canonical_pass(self):
        # Yalnız /ID farklı (A…A vs B…B), gövde aynı → kanonik fallback PASS.
        res = run_experiment({"SOURCE_DATE_EPOCH": "1700000000"},
                             tectonic_stub=_stub("PDF-stub"))
        self.assertEqual(res["rc"], 0, res["out"])
        self.assertEqual(kv(res["report"], "verdict"), "PASS")
        self.assertTrue(
            kv(res["report"], "residual").startswith("/ID"),
            "yalnız-/ID sapması residual=/ID olmalı",
        )
        self.assertEqual(kv(res["report"], "tectonic_canonical_run1_sha256"),
                         kv(res["report"], "tectonic_canonical_run2_sha256"),
                         "yalnız /ID farklı: kanonik hash'ler eşit olmalı")
        self.assertNotEqual(kv(res["report"], "tectonic_run1_id"),
                            kv(res["report"], "tectonic_run2_id"))

    def test_content_difference_fails_closed(self):
        # run2 gövdesi farklı → kanonik fallback kurtaramaz → FAIL rc=1.
        res = run_experiment({"SOURCE_DATE_EPOCH": "1700000000"},
                             tectonic_stub=_stub("PDF-stub", "PDF-TAMPERED"))
        self.assertEqual(res["rc"], 1, res["out"])
        self.assertEqual(kv(res["report"], "verdict"), "FAIL")
        self.assertEqual(kv(res["report"], "residual"), "content")

    def test_missing_tectonic_skips(self):
        # K3 SKIP sözleşmesi: tectonic yok → exit 0, SKIP görünür. PATH
        # daraltılır (homebrew'daki gerçek tectonic görünmesin; SKIP yolu
        # sha256sum'a varmadan biter).
        res = run_experiment({"SOURCE_DATE_EPOCH": "1700000000",
                              "PATH": "/usr/bin:/bin"},
                             provide_tectonic=False)
        self.assertEqual(res["rc"], 0, res["out"])
        self.assertIn("SKIP", res["out"])

    def test_sde_exported_to_subprocess(self):
        # SDE env-sızdırma: stub SDE=1700000000 görmüyorsa exit 9 → deney
        # rc=1. rc=0 kanıtı: motor alt-sürece SDE exportlanıyor.
        res = run_experiment({"SOURCE_DATE_EPOCH": "1700000000"},
                             tectonic_stub=_stub("PDF-stub",
                                                 sde="1700000000"))
        self.assertEqual(res["rc"], 0, res["out"])

    def test_sde_missing_fails_loudly(self):
        # Kontrpvaryant: SDE guard'lı stub + script SDE'yi exportlamıyorsa
        # guard patlar → rc != 0 (sessiz sapma yok). Script SDE'yi her zaman
        # export ettiği için rc=0 beklenir; guard'ın çalıştığı ayrı kanıt:
        # stub'u doğrudan yanlış SDE ile çağırıp exit 9 almak.
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            tools = td / "tools"
            tools.mkdir()
            _write_exec(tools / "tectonic", _stub("PDF-stub",
                                                  sde="1700000000"))
            stub = tools / "tectonic"
            r = subprocess.run([str(stub), "--outdir", str(td)],
                               capture_output=True, text=True,
                               env={"PATH": "/usr/bin:/bin"},
                               timeout=10)
            self.assertEqual(r.returncode, 9, r.stdout + r.stderr)
            self.assertIn("SDE-GUARD", r.stderr)

    def test_outdir_always_passed_and_sandboxed(self):
        # --outdir sözleşmesi: stub outdir-guard'lı (yoksa exit 9 → rc=1);
        # koşum kaynak-dizininde PDF bırakmaz.
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            srcdir = td / "src"
            srcdir.mkdir()
            tex = srcdir / "sample.tex"
            tex.write_text(TEX, encoding="utf-8")
            out = td / "report.txt"
            tools = td / "tools"
            tools.mkdir()
            _write_exec(tools / "tectonic", _stub("PDF-stub"))
            env = dict(os.environ, TECTONIC_BIN=str(tools / "tectonic"),
                       TEX_SOURCE=str(tex), DETERMINISM_OUT=str(out),
                       CANV_STUB_CNT=str(td / "cnt"),
                       PATH=f"{tools}:{os.environ.get('PATH', '')}",
                       SOURCE_DATE_EPOCH="1700000000")
            r = subprocess.run(["bash", str(SCRIPT)], capture_output=True,
                               text=True, env=env, cwd=td, timeout=60)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertFalse((srcdir / "sample.pdf").exists(),
                             "kaynak dizinine yazma YASAK")


if __name__ == "__main__":
    unittest.main()
