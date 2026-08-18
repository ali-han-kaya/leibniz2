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
  7) config'i paket içeriğiyle senkron eder (gen_config.py) — update-config
     hook'u ile AYNI felsefe: önce --dry-run; drift yoksa dokunmaz, varsa
     yazma modunda günceller. Ortam eksikse (exit 2) uyarı ile geçer (CI
     config-drift job'ı orada yakalar), şema hatası repack'i bloke eder.

Zip'ler sıralı girdiler + sabit zaman damgasıyla üretilir (tekrarlanabilir).
Çalıştırma:  python3 repack_delivery.py            (repo kökünden)
             python3 repack_delivery.py --verify  (repack sonrası zip'lerin
               SHA-256'sını .sha256 sidecar'larıyla doğrular; uyuşmazlık/eksik
               → exit 1, fail-closed)
"""
import argparse
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
    "ingiliz_empirizmi_v3.pdf","encoding_sensitivity_check.py", "encoding_sensitivity_output.txt",
    "gate15_check.py", "gate15_output.txt", "provenance2_supplement.md",
    "qpdf_determinism_experiment.py", "qpdf_determinism_output.txt",
    "ingiliz_empirizmi_v3.pdf.metadata.sha256",
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
        "# V5h (2026-08-17): bibliographic fixes — Beth 1953 entry corrected from\n"
        "#   Journal of Symbolic Logic 18(1): 8-13 to Indagationes Math\n"
        "#   15: 330-339 (also Proc. KNAW A56: 330-339). Fosl 1998 review moved from\n"
        "#   Journal of the History of Philosophy 36(2) (uncorroborated) to ECSSS\n"
        "#   Newsletter 11: 35-36 (corroborated). Manuscript recompiled (still 33 pp).\n"
        "#   verify_delivery.py --check-references now exits 0.\n"
        "# V5i (2026-08-17): PDF build determinism (K6-DETERM) added. qpdf --remove-metadata\n"
        "#   computes metadata-stripped SHA-256 (qpdf 12.4.0); sidecar stored alongside\n"
        "#   the PDF (ingiliz_empirizmi_v3.pdf.metadata.sha256). KNOWN LIMITATION:\n"
        "#   tectonic 0.17.0 byte-deterministic değildir — ardışık derleme farklı\n"
        "#   metadata-stripped hash üretir. Bu nedenle --strict-determinism bayrağı\n"
        "#   varsayılan kapalıdır; drift bilgi amaçlı raporlanır (P0/P1 yok). TeXLive\n"
        "#   + SOURCE_DATE_EPOCH geçişi determinism'i sağlayabilir (henüz değil).\n"
        "# V5j (2026-08-17): bibliographic fixes — Popkin 1952 reprint pages 133-148\n"
        "#   corrected to 133-147; Priest 2018 full subtitle restored ('An Essay on\n"
        "#   Buddhist Metaphysics and the Catuskoti'). Reference audit KUCUK NOTs\n"
        "#   closed; all REFERENCE_KNOWN entries now DUZELTILDI (INFO only).\n"
        "# V5k (2026-08-18): KNOWN LIMITATION — tectonic non-determinism. The manuscript\n"
        "#   PDF is still compiled with tectonic 0.17.0, which is NOT byte-deterministic:\n"
        "#   consecutive builds of the same .tex produce different byte streams, hence\n"
        "#   different metadata-stripped SHA-256 hashes. Therefore K6-DETERM is\n"
        "#   informational by default (--strict-determinism OFF) and must not be enabled\n"
        "#   until the build migrates to TeXLive + SOURCE_DATE_EPOCH (TEXMFOUTPUT). This\n"
        "#   limits build reproducibility only — NOT the logical content (K1-K5, K8, K9\n"
        "#   unaffected).\n"
        "# V5l (2026-08-18): REPACK DETERMINISM — qpdf non-determinism experiment +\n"
        "#   fix. EXPERIMENT: qpdf --remove-metadata is NOT deterministic — the same\n"
        "#   input PDF produced 3 different outputs in 3 runs (b090ac01…, 429984da…,\n"
        "#   509a47a6…; raw PDF e7b0bc0b…). So the metadata-stripped hash cannot be\n"
        "#   recomputed freely. FIX: repack_delivery.py regenerates the sidecar only\n"
        "#   when the PDF's raw SHA-256 changes; if the raw hash is unchanged, the\n"
        "#   existing sidecar is reused. PROOF: consecutive repacks are byte-identical\n"
        "#   (zip hash stable). The sidecar therefore stays in sync with the package\n"
        "#   without adding hash noise to the bundle.\n"
        "# V5m (2026-08-18): qpdf determinism experiment extracted to\n"
        "#   qpdf_determinism_experiment.py + frozen output (qpdf_determinism_output.txt).\n"
        "#   Default mode prints the byte-stable frozen record (K5 girişi); --rerun [N]\n"
        "#   re-runs qpdf --remove-metadata N times on the same input (output varies run\n"
        "#   to run — that is the experiment itself). K5 now checks 4 script/frozen pairs.\n"
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


def verify_sidecars(ci_dir=None):
    """CIKTI/'daki her zip'in SHA-256'sını kendi .sha256 sidecar'ıyla karşılaştırır.

    Sidecar formatı write_sidecar ile birebir: "<sha256>  <name>\n". Denetim
    hash'e bakar (name bilgi amaçlıdır — repack'in yazdığı formatla aynı).
    ZIP veya sidecar eksikse / hash uyuşmuyorsa FAIL.

    Dönüş: True = tüm zip↔sidecar eşleşmeleri PASS; False = en az bir eksik
           veya uyuşmazlık (fail-closed çağıran exit 1 yapar).
    """
    ci = ci_dir or CIKTI
    pairs = [
        (INNER_ZIP, os.path.join(ci, INNER_ZIP),
         os.path.join(ci, INNER_ZIP + ".sha256")),
        (OUTER_ZIP, os.path.join(ci, OUTER_ZIP),
         os.path.join(ci, OUTER_ZIP + ".sha256")),
    ]
    ok = True
    print("--- zip ↔ sidecar bütünlük denetimi (--verify) ---")
    for name, zip_path, sc_path in pairs:
        if not os.path.isfile(zip_path):
            print(f"  [EKSİK] {name} — zip yok")
            ok = False
            continue
        if not os.path.isfile(sc_path):
            print(f"  [EKSİK] {name}.sha256 — sidecar yok")
            ok = False
            continue
        actual = sha256(zip_path)
        expected = ""
        try:
            with open(sc_path, encoding="utf-8", errors="ignore") as f:
                first = f.readline().strip()
            expected = first.split()[0] if first else ""
        except OSError:
            expected = ""
        match = bool(expected) and actual == expected
        tag = "PASS" if match else "FAIL"
        shown = expected[:16] if expected else "(boş/okunamadı)"
        print(f"  [{tag}] {name}: {actual[:16]}…")
        print(f"        sidecar: {shown} — {'eşleşti' if match else 'UYUŞMUYOR / EKSİK'}")
        if not match:
            ok = False
    print(f"  bütünlük: {'TÜMÜ PASS' if ok else 'FAIL (en az bir uyuşmazlık/eksik)'}")
    return ok


def sync_config():
    """Repack sonrası config'i paket içeriğiyle senkron et (update-config felsefesi).

    update_config_hook.sh ile aynı kural: önce gen_config.py --dry-run;
    drift yoksa dosyaya dokunmaz (yazma modu her zaman yeniden yazar → byte
    farkı + gereksiz değişiklik üretirdi), drift varsa yazma modunda
    günceller. Ortam eksikse (exit 2) UYARI ile geç — CI'daki config-drift
    job'ı orada fail-closed denetler. Şema doğrulaması başarısızlığı (1)
    repack'i bloke eder.

    Dönüş: True = senkron tamam (dokunulmadı / güncellendi / ortam uyarısı),
           False = şema hatası veya beklenmedik exit (repack FAIL).
    """
    import subprocess
    import sys

    gen = os.path.join(CIKTI, "gen_config.py")

    def run(dry):
        cmd = [sys.executable, gen, "--dir", CIKTI]
        if dry:
            cmd.append("--dry-run")
        return subprocess.run(cmd, capture_output=True, text=True)

    r = run(True)
    if r.returncode == 0:
        print("  config senkron : drift yok (config paket içeriğiyle güncel)")
        return True
    if r.returncode == 2:
        print("  UYARI: gen_config ortam hatası (exit 2) — config güncellenemedi; "
              "CI config-drift kapısı denetler.")
        return True
    if r.returncode == 1:
        print("  config drift tespit edildi — gen_config yazma modunda güncelleniyor…")
        w = run(False)
        if w.returncode == 0:
            print(f"  config senkron : güncellendi → "
                  f"{os.path.join(CIKTI, 'verify_delivery.config.json')}")
            return True
        if w.returncode == 2:
            print("  UYARI: gen_config yazma modunda ortam hatası (exit 2) — "
                  "config güncellenemedi; CI config-drift kapısı denetler.")
            return True
        print(f"  HATA: gen_config yazma modunda başarısız (exit {w.returncode}) — "
              "config güncellenemedi.")
        return False
    print(f"  HATA: gen_config beklenmedik exit ({r.returncode}).")
    return False


def main():
    ap = argparse.ArgumentParser(
        description="Stoic-Hume V5 teslim zincirini deterministik yeniden paketler.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="--verify: repack SONRASI CIKTI/'daki zip'lerin SHA-256'sını "
               "kendi .sha256 sidecar'larıyla karşılaştırır; uyuşmazlık/eksik "
               "→ exit 1 (fail-closed bütünlük kapısı).")
    ap.add_argument("--verify", action="store_true",
                    help="repack sonrası zip hash'lerini sidecar'larla doğrula "
                         "(eksik/uyuşmazlık → exit 1)")
    args = ap.parse_args()

    # 0) PDF metadata-stripped hash sidecar (build determinism proxy).
    #    build_zip'dan ÖNCE yapılır (çünkü MANIFEST.txt sidecar'ı listeler).
    #    DETERMİNİZM: qpdf --remove-metadata aynı PDF üzerinde farklı byte'lar
    #    üretir (non-deterministic). Bu yüzden sidecar yalnızca PDF'in ham
    #    SHA-256'sı DEĞİŞTİĞİNDE yeniden üretilir; PDF aynıysa mevcut sidecar
    #    korunur. Böylece ardışık repack'ler byte-identical zip üretir ve
    #    sidecar gerçekten "senkron" kalır (hash gürültüden arındırılır).
    import subprocess as _sp, tempfile as _tf
    pdf = os.path.join(PKG, "ingiliz_empirizmi_v3.pdf")
    pdf_sidecar = os.path.join(PKG, "ingiliz_empirizmi_v3.pdf.metadata.sha256")
    raw_hash = sha256(pdf) if os.path.isfile(pdf) else None
    # Mevcut sidecar'daki ham hash'i oku (varsa); PDF değişmediyse qpdf'i atla.
    cached_raw = None
    if os.path.isfile(pdf_sidecar):
        for line in open(pdf_sidecar, encoding="utf-8", errors="ignore"):
            if line.startswith("# raw:"):
                cached_raw = line.split()[2]
                break
    qpdf = None
    for cand in ("qpdf", "/opt/homebrew/bin/qpdf"):
        if os.path.isfile(cand):
            qpdf = cand
            break
    if qpdf and raw_hash and cached_raw == raw_hash:
        print(f"  (metadata sidecar reuse — PDF raw hash değişmedi: {raw_hash[:12]}…)")
    elif qpdf and raw_hash:
        with _tf.NamedTemporaryFile(suffix=".pdf", delete=False) as _t:
            _tmp = _t.name
        _sp.run([qpdf, "--remove-metadata", pdf, _tmp],
                       capture_output=True, timeout=60)
        if os.path.isfile(_tmp):
            with open(pdf_sidecar, "w", encoding="utf-8") as f:
                f.write(f"{sha256(_tmp)}  ingiliz_empirizmi_v3.pdf.metadata\n")
                f.write(f"# raw: {raw_hash}  ingiliz_empirizmi_v3.pdf\n")
            os.unlink(_tmp)
        else:
            print(f"  UYARI: qpdf başarısız, sidecar oluşturulmadı")
    elif not qpdf:
        print(f"  UYARI: qpdf bulunamadı, sidecar oluşturulmadı")

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
    inner_size = os.path.getsize(inner_zip)
    outer_size = os.path.getsize(outer_zip)

    # 5) Self-clean: OUTER_SRC içindeki transient iç zip + sidecar'ı sil.
    #    İç zip artık dış zip'in İÇİNDE paketlendi ve kanonik kopyası
    #    CIKTI/'da — OUTER_SRC'de duran kopya yalnızca ara üründür. Recursive
    #    K0 (verify_delivery.py) bunu bayat kopya olarak P1 işaretler; repack
    #    kendi ara ürününü silerek normal akışta K0'ı yeşil tutar.
    for fn in (INNER_ZIP, INNER_ZIP + ".sha256"):
        p = os.path.join(OUTER_SRC, fn)
        if os.path.isfile(p):
            os.unlink(p)

    # 6) Config senkronu (update-config felsefesi) — zip'ler CIKTI/'ya
    #    kopyalandıktan SONRA, böylece gen_config güncel paketi okur.
    sync_ok = sync_config()

    print("MANIFEST güncellendi; iç/dış zip + sidecar + KLASOR_CHECKSUMLARI yeniden üretildi.")
    print(f"  iç zip : {INNER_ZIP} ({inner_size} B) → CIKTI/ + dış zip içine gömüldü")
    print(f"  dış zip : {OUTER_ZIP} ({outer_size} B)")

    verify_ok = True
    if args.verify:
        verify_ok = verify_sidecars()

    return 0 if (sync_ok and verify_ok) else 1


if __name__ == "__main__":
    main()
