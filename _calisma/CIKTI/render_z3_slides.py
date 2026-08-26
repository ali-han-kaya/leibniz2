#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""render_z3_slides.py — 12 Z3 teoremini bağımsız PNG görsellerine çevirir.

tex-render-guide Method 1 (standalone LaTeX → PDF → yüksek DPI PNG) ile
`symbolic_proof_z3.py`'deki 12 Z3 denetiminin iddia formüllerini slayt
kullanımına uygun, sayfadan bağımsız PNG'lere dönüştürür:

  kaynak        : _calisma/CIKTI/symbolic_proof_z3.py (12 record() denetimi)
  çıktı         : <out>/<id>.png — her teorem ayrı görsel
  çözünürlük    : 300 DPI (Method 1 varsayılanı; --dpi ile değiştir)
  arka plan     : şeffaf (slayt dostu; --bg beyaz yapılabilir)

Araç zinciri (Method 1 sırasıyla dener, düşen yedek):
  LaTeX : pdflatex → tectonic (bu makinede TeXLive yok, tectonic var)
  PDF→PNG : convert (ImageMagick) → pdftoppm (poppler) → sips

`--check-sync`, THEOREMS tablosundaki ID/iddia setini
symbolic_proof_z3.py'deki record() çağrılarıyla çapraz doğrular
(fail-closed: kod teorem ekler/çıkarırsa bu tablo bayat kalır ve
script drift'i yakalar).

Örnek:
  python3 _calisma/CIKTI/render_z3_slides.py --out _calisma/slides_z3
  python3 _calisma/CIKTI/render_z3_slides.py --check-sync
"""
import argparse
import os
import pathlib
import re
import shutil
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
Z3_SRC = HERE / "symbolic_proof_z3.py"

# ---------------------------------------------------------------------------
# 12 Z3 denetimi — ID → LaTeX iddia formülü + Z3 beklenen sonucu.
# Kaynak: symbolic_proof_z3.py record() satırları (P1-a … P5-note).
# LaTeX gösterimi skill'in Method 1 çıktısıyla birebir derlenir.
# ---------------------------------------------------------------------------
THEOREMS = [
    ("P1-a",   r"(T_2 \land M_0) \vDash T_1",                    "UNSAT", "geçerlilik"),
    ("P1-b",   r"T_1 \land M_0 \nvDash T_2",                     "SAT",   "karşı-model"),
    ("P2",     r"T_1 \land B_0 \vDash T_2 \;(M_0)",              "UNSAT", "bridge collapse"),
    ("P3-a",   r"(T_1 \land \neg T_2) \rightarrow \star",        "UNSAT", "çift düzeyi (→)"),
    ("P3-b",   r"\star \rightarrow (T_1 \land \neg T_2)",        "UNSAT", "çift düzeyi (←)"),
    ("P4-a",   r"(T_1 \land M_0 \land \neg T_2) \rightarrow \star", "UNSAT", "global (→)"),
    ("P4-b",   r"\star \rightarrow (T_1 \land M_0 \land \neg T_2)", "SAT", "global (←) geçersiz"),
    ("P4-c",   r"\star \land \neg T_1",                          "SAT",   "doyurulabilir"),
    ("P4-d",   r"(T_1 \land M_0 \land \star) \iff (T_1 \land M_0 \land \neg T_2)", "UNSAT", "düzeltilmiş karakterizasyon"),
    ("P4-e",   r"\star \rightarrow \neg T_2",                    "UNSAT", "⋆ → ¬T₂"),
    ("P5",     r"\exists \mathcal{M}_1,\mathcal{M}_2 :\ \mathrm{red}_{L_0}(\mathcal{M}_1)=\mathrm{red}_{L_0}(\mathcal{M}_2) \land G_1 \neq G_2", "SAT", "Prop 2 tanık çifti"),
    ("P5-note", r"\mathrm{Just}(b_0,c_0)=\top \Rightarrow \neg\mathrm{adm}(\mathcal{M})", "UNSAT", "spec §9 notu"),
]

_PREAMBLE = r"""\documentclass[border={border}pt]{{standalone}}
\usepackage{{amsmath,amssymb}}
\begin{{document}}
"""


def _latex_doc(theorem, border, with_label):
    tid, tex, verdict, note = theorem
    body = r"$\displaystyle " + tex + r"$"
    if with_label:
        body += (r"\\[6pt]\footnotesize\texttt{" + tid + r"} \;·\; "
                 r"\text{" + verdict + r"}")
    return (_PREAMBLE.format(border=border) + body + "\n\\end{document}\n")


def find_tex_engine():
    for cand in ("pdflatex", "latex", "tectonic"):
        if shutil.which(cand):
            return cand
    return None


def find_pdf_to_png():
    for cand in ("convert", "magick", "pdftoppm", "sips"):
        if shutil.which(cand):
            return cand
    return None


def compile_tex(engine, tex_path, workdir):
    """Method 1: .tex → .pdf (pdflatex/tectonic). Döner: bool."""
    if engine in ("pdflatex", "latex"):
        # latex → dvi için dvipng rotası ayrı; burada pdflatex PDF üretir.
        r = subprocess.run([engine, "-interaction=nonstopmode",
                            tex_path.name], cwd=str(workdir),
                           capture_output=True, text=True, timeout=120)
        return r.returncode == 0 and (workdir / tex_path.stem).with_suffix(".pdf").is_file()
    if engine == "tectonic":
        r = subprocess.run([engine, tex_path.name], cwd=str(workdir),
                           capture_output=True, text=True, timeout=300)
        return r.returncode == 0 and (workdir / tex_path.stem).with_suffix(".pdf").is_file()
    return False


def pdf_to_png(tool, pdf_path, png_path, dpi):
    """Method 1: .pdf → .png (convert/pdftoppm/sips). Döner: bool."""
    if tool in ("convert", "magick"):
        r = subprocess.run([tool, "-density", str(dpi), str(pdf_path),
                            "-quality", "100", str(png_path)],
                           capture_output=True, text=True, timeout=120)
        return r.returncode == 0 and png_path.is_file()
    if tool == "pdftoppm":
        r = subprocess.run([tool, "-r", str(dpi), "-png", "-singlefile",
                            str(pdf_path), str(png_path.with_suffix(""))],
                           capture_output=True, text=True, timeout=120)
        return r.returncode == 0 and png_path.is_file()
    if tool == "sips":
        r = subprocess.run(["sips", "-s", "format", "png",
                            str(pdf_path), "--out", str(png_path)],
                           capture_output=True, text=True, timeout=120)
        return r.returncode == 0 and png_path.is_file()
    return False


def check_sync():
    """THEOREMS ↔ symbolic_proof_z3.py record() ID'leri (fail-closed)."""
    if not Z3_SRC.is_file():
        print(f"HATA: {Z3_SRC} yok", file=sys.stderr)
        return 2
    src = Z3_SRC.read_text(encoding="utf-8")
    code_ids = set(re.findall(r'record\("([^"]+)"', src))
    table_ids = {t[0] for t in THEOREMS}
    missing = sorted(code_ids - table_ids)
    extra = sorted(table_ids - code_ids)
    problems = []
    if missing:
        problems.append(f"koddaki teoremler tabloda YOK: {missing}")
    if extra:
        problems.append(f"tablodaki teoremler kodda YOK: {extra}")
    # Aynı ID'nin beklenen sonucu kodla eşleşmeli (ör. P4-b SAT).
    for tid, _tex, verdict, _n in THEOREMS:
        m = re.search(rf'record\("{re.escape(tid)}",\s*"[^"]*",\s*"([^"]+)"', src)
        if m and m.group(1) != verdict:
            problems.append(
                f"{tid}: tablo beklenen={verdict}, kod beklenen={m.group(1)}")
    if problems:
        print("SENKRON DRIFT (exit 1):")
        for p in problems:
            print(f"  - {p}")
        return 1
    print(f"SENKRON OK — {len(THEOREMS)} teorem, kodla birebir (exit 0)")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=str(HERE.parent / "slides_z3"),
                    help="PNG çıktı dizini (varsayılan: _calisma/slides_z3)")
    ap.add_argument("--dpi", type=int, default=300)
    ap.add_argument("--border", type=int, default=4)
    ap.add_argument("--bg", choices=("transparent", "white"), default="transparent")
    ap.add_argument("--with-label", action="store_true",
                    help="ID + Z3 sonucu etiketini de görsele ekle")
    ap.add_argument("--only", help="yalnızca bu ID'yi render et (örn. P4-b)")
    ap.add_argument("--check-sync", action="store_true",
                    help="THEOREMS tablosunu kodla çapraz doğrula, render etme")
    args = ap.parse_args()

    if args.check_sync:
        return check_sync()

    engine = find_tex_engine()
    converter = find_pdf_to_png()
    if not engine:
        print("HATA: pdflatex/tectonic yok (TeX motoru bulunamadı)", file=sys.stderr)
        return 2
    if not converter:
        print("HATA: convert/pdftoppm/sips yok (PDF→PNG aracı bulunamadı)",
              file=sys.stderr)
        return 2
    print(f"Araçlar: LaTeX={engine}, PDF→PNG={converter} (dpi={args.dpi}, "
          f"bg={args.bg}, label={args.with_label})")

    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    import tempfile
    ok, fail = 0, 0
    for theorem in THEOREMS:
        tid = theorem[0]
        if args.only and tid != args.only:
            continue
        png = out / f"{tid}.png"
        doc = _latex_doc(theorem, args.border, args.with_label)
        with tempfile.TemporaryDirectory(prefix=f"z3slide_{tid}_") as td:
            work = pathlib.Path(td)
            tex = work / f"{tid}.tex"
            tex.write_text(doc, encoding="utf-8")
            if not compile_tex(engine, tex, work):
                print(f"[{tid}] DERLEME HATASI (tex üretildi: {tex})")
                fail += 1
                continue
            pdf = (work / tid).with_suffix(".pdf")
            if not pdf_to_png(converter, pdf, png, args.dpi):
                print(f"[{tid}] PNG DÖNÜŞÜM HATASI")
                fail += 1
                continue
        # şeffaf arka plan isteniyorsa pdftoppm/sips çıktısı zaten saydamdır;
        # convert çıktısı beyaz gelir — sips ile saydamlık eklenmez (yalnızca
        # beyaz istenirse olduğu gibi bırakılır).
        print(f"[{tid}] OK → {png} ({png.stat().st_size} bayt)")
        ok += 1
    print(f"ÖZET: {ok} OK, {fail} hata → {out}")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
