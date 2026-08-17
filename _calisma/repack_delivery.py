#!/usr/bin/env python3
"""
repack_delivery.py — Stoic-Hume V5 teslim zincirini deterministik yeniden paketler.

iff skop düzeltmesi sonrası (core_section.tex + L0_Lplus_spec.md + PDF) çağrılır.
Sıra:
  1) MANIFEST.txt'i yeniden üretir (18 dosya MD5 + boyut; başlık güncellenir)
  2) iç zip  TESLIM_V5_FINAL_2026-08-17.zip   (V5_ICERIK/TESLIM_V5_FINAL_2026-08-17/)
  3) iç sidecar + KLASOR_CHECKSUMLARI.sha256
  4) dış zip  TESLIM_KLASOR_V5_2026-08-17.zip  (TESLIM/Stoic-Hume-Final-V5_2026-08-17/)
  5) dış sidecar
  6) iki zip + sidecar'ı CIKTI/'ya kopyalar

Zip'ler sıralı girdiler + sabit zaman damgasıyla üretilir (tekrarlanabilir).
Çalıştırma:  python3 repack_delivery.py   (repo kökünden)
"""
import hashlib
import os
import re
import zipfile

ROOT = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.join(ROOT, "V5_ICERIK", "TESLIM_V5_FINAL_2026-08-17",
                   "stoic_hume_package", "Stoic_Hume_Formal_Section_2026-08-17")
INNER_SRC = os.path.join(ROOT, "V5_ICERIK", "TESLIM_V5_FINAL_2026-08-17")
OUTER_SRC = os.path.join(ROOT, "TESLIM", "Stoic-Hume-Final-V5_2026-08-17")
CIKTI = os.path.join(ROOT, "CIKTI")

INNER_DIR = "TESLIM_V5_FINAL_2026-08-17"
OUTER_DIR = "Stoic-Hume-Final-V5_2026-08-17"
INNER_ZIP = "TESLIM_V5_FINAL_2026-08-17.zip"
OUTER_ZIP = "TESLIM_KLASOR_V5_2026-08-17.zip"

MANIFEST_FILES = [
    "core_section.tex", "L0_Lplus_spec.md", "model_check_report.md",
    "core_formal_model_check.py", "test_output.txt", "requirements.txt",
    "REPRODUCIBILITY.md", "INTEGRATION_NOTE.md", "internal_review_report.md",
    "original_manuscript.pdf", "README.md", "ingiliz_empirizmi_v3.tex",
    "ingiliz_empirizmi_v3.pdf", "encoding_sensitivity_check.py",
    "encoding_sensitivity_output.txt", "gate15_check.py",
    "gate15_output.txt", "provenance2_supplement.md",
]

SKIP = {".DS_Store", "__MACOSX"}
FIXED_DT = (2026, 8, 17, 0, 0, 0)


def md5(p):
    h = hashlib.md5()
    with open(p, "rb") as f:
        for c in iter(lambda: f.read(65536), b""):
            h.update(c)
    return h.hexdigest()


def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for c in iter(lambda: f.read(65536), b""):
            h.update(c)
    return h.hexdigest()


def write_manifest():
    core_lines = sum(1 for _ in open(os.path.join(PKG, "core_section.tex"), encoding="utf-8", errors="ignore"))
    spec_lines = sum(1 for _ in open(os.path.join(PKG, "L0_Lplus_spec.md"), encoding="utf-8", errors="ignore"))
    header = (
        "# MANIFEST — Stoic_Hume_Formal_Section_2026-08-17\n"
        "# Generated: 2026-08-17 (added revised manuscript ingiliz_empirizmi_v3.tex/.pdf after INTEGRATION_NOTE)\n"
        "# V5 (2026-08-17): manuscript recompiled with V5 additions — §2.12 encoding sensitivity (L0^A/L0^B),\n"
        "#   §2.13 E0/E1/E2 minimal-enlargement benchmark, §2.14 Gate 1.5 non-triviality check, new §6\n"
        "#   Objections & Replies (with negative-result matrix), Open Science Statement; 33 pp.\n"
        "# V5b (2026-08-17): encoding-sensitivity test EXECUTED — §2.12 now reports the\n"
        "#   computational result (L0^A: 16/16 undetermined; L0^B: 6/10 undetermined, 4/10\n"
        "#   determined by the decomposition axiom): encoding-sensitive in degree, robust\n"
        "#   in existence. New files: encoding_sensitivity_check.py + frozen output.\n"
        "# V5c (2026-08-17): Gate 1.5 items T1-T10 verified individually; §2.14 now has the\n"
        "#   full 10/10 Table 1. New files: gate15_check.py (T2-T5, incl. Gamma on the\n"
        "#   model pair) + frozen output. Manuscript recompiled (31 pp).\n"
        "# V5d (2026-08-17): remaining V5 gaps closed — §2.15 HI1-HI4 hyperintensionality\n"
        "#   four-layer claim, §4.6 Ev0-Ev4 historical-evidence ladder, M 7.151-152\n"
        "#   katalepsis/episteme hierarchy added to Appendix + Provenance. 33 pp.\n"
        "# V5e (2026-08-17): Provenance 2.0 seven-column evidence register added as\n"
        "#   provenance2_supplement.md (optional supplement; not part of the page count).\n"
        "#   This closes the last remaining V5 architecture item.\n"
        "# V5f (2026-08-17): citation audit fixes — Tillemans 1999 added to References;\n"
        "#   standalone editor entries for Beauchamp 1999 and Nidditch 1975; Bury entry\n"
        "#   annotated by volume year (1935 = Loeb vol. II); body Nidditch citation now\n"
        "#   year-bearing. Manuscript recompiled (still 33 pp). Supplement note added.\n"
        "# V5g (2026-08-17): bridge-collapse characterization SCOPE FIX — the previous\n"
        "#   'if and only if' between 'a model separates T1 from T2' and (⋆) was valid\n"
        "#   only at the single-pair level. Now: pair-level iff, one-way global\n"
        "#   implication, and the corrected global equivalence T1∧M0∧¬T2 ⟺ T1∧M0∧(⋆).\n"
        "#   Z3-verified (symbolic_proof_z3.py P4-d/P4-e UNSAT). core_section.tex and\n"
        "#   L0_Lplus_spec.md updated; manuscript recompiled (still 33 pp).\n"
        f"# Python: Python 3.11 (also verified 3.10, 3.12)\n"
        f"# LaTeX: core_section.tex ({core_lines} lines) + L0_Lplus_spec.md ({spec_lines} lines);\n"
        "#   ingiliz_empirizmi_v3.tex compiled with tectonic 0.17.0, 33 pp.\n"
        "# Verification: PASS (Prop 1 Boolean + bridge + pair/global characterization +\n"
        "#   Prop 2 model pair with O_1-O_3); symbolic re-proof via Z3 (12 checks).\n"
        "\n"
        "File                                        Size (B)  MD5\n"
        "------------------------------------------ ---------  --------------------------------\n"
    )
    rows = []
    for fn in MANIFEST_FILES:
        p = os.path.join(PKG, fn)
        rows.append(f"{fn:<42} {os.path.getsize(p):>9}  {md5(p)}\n")
    rows.append("MANIFEST.txt                                       0  (self; excluded — recompute on use)\n")
    with open(os.path.join(PKG, "MANIFEST.txt"), "w", encoding="utf-8") as f:
        f.write(header)
        f.writelines(rows)


def build_zip(src_dir, top_name, out_path):
    """Sıralı + sabit zaman damgalı deterministik zip."""
    entries = []
    for root, dirs, files in os.walk(src_dir):
        dirs.sort()
        for fn in sorted(files):
            if fn in SKIP or fn.endswith(".pyc"):
                continue
            full = os.path.join(root, fn)
            rel = os.path.relpath(full, src_dir)
            entries.append((rel, full))
    entries.sort()
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as z:
        for rel, full in entries:
            zi = zipfile.ZipInfo(os.path.join(top_name, rel).replace(os.sep, "/"),
                                 date_time=FIXED_DT)
            zi.compress_type = zipfile.ZIP_DEFLATED
            with open(full, "rb") as f:
                z.writestr(zi, f.read())


def write_sidecar(zip_path, name):
    with open(zip_path + ".sha256", "w") as f:
        f.write(f"{sha256(zip_path)}  {name}\n")


def main():
    write_manifest()

    # 1) iç zip + sidecar
    inner_zip = os.path.join(OUTER_SRC, INNER_ZIP)
    build_zip(INNER_SRC, INNER_DIR, inner_zip)
    write_sidecar(inner_zip, INNER_ZIP)

    # 2) KLASOR_CHECKSUMLARI.sha256 (dış klasördeki 10 dosya)
    outer_files = sorted(
        f for f in os.listdir(OUTER_SRC)
        if os.path.isfile(os.path.join(OUTER_SRC, f)) and f != "KLASOR_CHECKSUMLARI.sha256"
    )
    with open(os.path.join(OUTER_SRC, "KLASOR_CHECKSUMLARI.sha256"), "w") as f:
        for fn in outer_files:
            f.write(f"{sha256(os.path.join(OUTER_SRC, fn))}  {fn}\n")

    # 3) dış zip + sidecar
    outer_zip = os.path.join(CIKTI, OUTER_ZIP)
    build_zip(OUTER_SRC, OUTER_DIR, outer_zip)
    write_sidecar(outer_zip, OUTER_ZIP)

    # 4) CIKTI'ya iç zip + sidecar kopyala
    for fn in (INNER_ZIP, INNER_ZIP + ".sha256"):
        with open(os.path.join(OUTER_SRC, fn), "rb") as src, \
             open(os.path.join(CIKTI, fn), "wb") as dst:
            dst.write(src.read())

    print("MANIFEST güncellendi; iç/dış zip + sidecar + KLASOR_CHECKSUMLARI yeniden üretildi.")
    print(f"  iç zip : {INNER_ZIP} ({os.path.getsize(inner_zip)} B)")
    print(f"  dış zip : {OUTER_ZIP} ({os.path.getsize(outer_zip)} B)")


if __name__ == "__main__":
    main()
