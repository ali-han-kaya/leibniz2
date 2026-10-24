#!/usr/bin/env python3
"""
repack_delivery.py — Stoic-Hume V5 teslim zincirini deterministik yeniden paketler.

iff skop düzeltmesi sonrası (core_section.tex + L0_Lplus_spec.md + PDF) çağrılır.
Sıra:
  0) sidecar (build determinism proxy) — V5l reuse kuralı + Faz 4: motor
     geçişinde yenileme KANONİK DEFTERE bağlıdır (defterde yoksa yazmaz, exit 1)
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
import shutil
import subprocess
import sys
import tempfile
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
    with open(os.path.join(PKG, "core_section.tex"),
              encoding="utf-8", errors="ignore") as f:
        core_lines = sum(1 for _ in f)
    with open(os.path.join(PKG, "L0_Lplus_spec.md"),
              encoding="utf-8", errors="ignore") as f:
        spec_lines = sum(1 for _ in f)
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
        "#   the PDF (ingiliz_empirizmi_v3.pdf.metadata.sha256).\n"
        "# V5j (2026-08-17): bibliographic fixes — Popkin 1952 reprint pages 133-148\n"
        "#   corrected to 133-147; Priest 2018 full subtitle restored ('An Essay on\n"
        "#   Buddhist Metaphysics and the Catuskoti'). Reference audit KUCUK NOTs\n"
        "#   closed; all REFERENCE_KNOWN entries now DUZELTILDI (INFO only).\n"
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
        "# V5n (2026-10-01, Faz 4): CORRECTION — the V5i/V5k KNOWN LIMITATION above is\n"
        "#   WRONG and is superseded by measurement (kept above as dated history, not as\n"
        "#   current guidance). MEASURED: the engine IS deterministic under\n"
        "#   SOURCE_DATE_EPOCH; the only byte difference between two builds is pdfTeX's\n"
        "#   random trailer /ID pair, which the /ID-canonical view neutralises. The real\n"
        "#   source of run-to-run hash noise is qpdf ITSELF: qpdf --remove-metadata\n"
        "#   produced 3 different hashes from the SAME delivery PDF (2042ba8b…/\n"
        "#   7f9125d0…/c9b9890d…), so strict must NEVER be applied to the\n"
        "#   metadata-stripped hash (that would be a false positive every run).\n"
        "#   K6-DETERM's determinism reference is the /ID-CANONICAL hash, compared\n"
        "#   against the acceptance ledger (docs/ID_RESIDUAL_ACCEPTANCE.md §4); strict is\n"
        "#   ON BY DEFAULT and a hash absent from the ledger is a P1 (fail-closed).\n"
        "#   This delivery PDF: canonical d4f67e39…\n"
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


# ---------------------------------------------------------------------------
# Faz 4 — motor geçişinde sidecar yenilemesi KANONİK DEFTERE BAĞLI (fail-closed)
#
# `docs/ID_RESIDUAL_ACCEPTANCE.md` §5 yenileme protokolü: PDF'in ham hash'i
# motor değişiminde değişir, bu yüzden sidecar TEK SEFERLİK bilinçli olarak
# yenilenir. Faz 4 o yenilemeyi deftere bağlar:
#
#   * yeni `/ID`-kanonik hash ÖLÇÜLÜR (tek uygulama: pdf_id_canonical.py),
#   * defterin "Kanonik (referans)" sütununda YOKSA sidecar YAZILMAZ ve repack
#     exit 1 verir — çıkış yolu `make -f docs/Makefile.texlive accept`,
#   * kabul edilirse sidecar üç satır olur: stripped + `# raw:` + `# canonical:`.
#
# Böylece "motor değişti" kaydı ile "defter kabul etti" kaydı AYNI anda
# oluşur; iki taraf tek taraflı kalamaz (repack determinizm kapısı).
LEDGER_ENV = "ID_RESIDUAL_LEDGER"
LEDGER_REL = os.path.join("..", "docs", "ID_RESIDUAL_ACCEPTANCE.md")
SIDECAR_CANONICAL = "# canonical:"


def _canonical_modules():
    """`(pdf_id_canonical, id_canonical)` — tembel import.

    Ağaç kopyalarında (test sandbox'ları, kısmi checkout) CIKTI modülleri
    bulunmayabilir; o zaman `(None, None)` döner ve çağıran fail-closed karar
    verir. Dosya varlığı sys.modules kirlenmesini de önler: yarım ağaçta
    `id_canonical` import edilip gerçek modülü gölgelemez.
    """
    pdf_mod = os.path.join(CIKTI, "pdf_id_canonical.py")
    id_mod = os.path.join(CIKTI, "id_canonical.py")
    if not (os.path.isfile(pdf_mod) and os.path.isfile(id_mod)):
        return None, None
    if CIKTI not in sys.path:
        sys.path.insert(0, CIKTI)
    import id_canonical  # noqa: PLC0415  (tembel: sandbox ağaçlarında yok)
    import pdf_id_canonical  # noqa: PLC0415
    return pdf_id_canonical, id_canonical


def ledger_candidates(ledger_paths=None):
    """Defter adayları: açık liste → env → repo docs (§4 tek kaynak)."""
    if ledger_paths is not None:
        return [str(p) for p in ledger_paths]
    out = []
    env = os.environ.get(LEDGER_ENV)
    if env:
        out.append(env)
    out.append(os.path.abspath(os.path.join(ROOT, LEDGER_REL)))
    return out


def resolve_ledger(ledger_paths=None):
    """İlk var olan defter yolu (yoksa None)."""
    for path in ledger_candidates(ledger_paths):
        if os.path.isfile(path):
            return path
    return None


def ledger_canonicals(ledger_path):
    """Defterin Kanonik sütunundaki TAM 64-hex küme (K6 ile aynı ayrıştırıcı)."""
    pdf_mod, _ic = _canonical_modules()
    if pdf_mod is None:
        raise RuntimeError("kanonik modül yok: _calisma/CIKTI/pdf_id_canonical.py")
    with open(ledger_path, encoding="utf-8", errors="replace") as fh:
        return pdf_mod.ledger_canonical_hashes(fh.read())


def measure_canonical(pdf_path):
    """`(canonical_sha256 | None, id_found)` — tek uygulama üzerinden."""
    pdf_mod, _ic = _canonical_modules()
    if pdf_mod is None:
        return None, False
    return pdf_mod.canonical_sha256_path(pdf_path)


def _cached_raw(sidecar_path):
    """Sidecar'daki `# raw:` hash'i (yoksa None)."""
    if not os.path.isfile(sidecar_path):
        return None
    with open(sidecar_path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if line.startswith("# raw:"):
                parts = line.split()
                return parts[2] if len(parts) >= 3 else None
    return None


def renew_sidecar(pdf_path, sidecar_path, stripped_sha, raw_sha,
                  ledger_paths=None):
    """Motor geçişi: sidecar'ı yenile VE kanonik deftere bağla (fail-closed).

    Döndürür `(ok, detail)`. `ok=False` iken sidecar'a HİÇ yazılmaz —
    yarım/bağsız kayıt bırakmak, kaydın defterle çelişmesine yol açardı.
    """
    pdf_mod, _ic = _canonical_modules()
    if pdf_mod is None:
        return False, ("kanonik çekirdek yok (_calisma/CIKTI/pdf_id_canonical.py) "
                       "— sidecar defter bağı kurulamaz")
    ledger = resolve_ledger(ledger_paths)
    if ledger is None:
        return False, ("kanonik kabul defteri yok (aranan: %s) — motor geçişi "
                       "defter satırı olmadan yenilenemez"
                       % ", ".join(ledger_candidates(ledger_paths)))
    canonical, id_found = pdf_mod.canonical_sha256_path(pdf_path)
    if not canonical:
        return False, "kanonik hash ölçülemedi: %s" % pdf_path
    accepted = ledger_canonicals(ledger)
    if not accepted:
        return False, "kanonik kabul defteri okunamadı/boş: %s" % ledger
    if canonical not in accepted:
        return False, ("yeni kanonik hash defterde YOK (strict): %s… — bilinçli "
                       "kabul için `make -f docs/Makefile.texlive accept` ile "
                       "deftere satır ekle (docs/ID_RESIDUAL_ACCEPTANCE.md "
                       "§4/§6)" % canonical[:16])
    name = os.path.basename(pdf_path)
    with open(sidecar_path, "w", encoding="utf-8") as fh:
        fh.write("%s  %s.metadata\n" % (stripped_sha, name))
        fh.write("# raw: %s  %s\n" % (raw_sha, name))
        fh.write("%s %s  %s\n" % (SIDECAR_CANONICAL, canonical, name))
    return True, ("sidecar yenilendi ve deftere bağlandı: canonical=%s… "
                  "id_found=%s" % (canonical[:16], id_found))


def sidecar_binding_problem(pdf_path, sidecar_path, ledger_paths=None):
    """Reuse yolunda mevcut kaydın PDF ve defterle tutarlılığı.

    `# canonical:` yoksa None döner: tectonic-era kayıt iki satırdır ve §6
    bunu bilgi düzeyi sayar. Defter yoksa da None (kısmi ağaç); yenileme
    yolunda eksik defter zaten fail-closed'dır.
    """
    _pdf_mod, ic_mod = _canonical_modules()
    if ic_mod is None:
        return None
    canonical = ic_mod.sidecar_canonical(str(sidecar_path))
    if not canonical:
        return None
    ledger = resolve_ledger(ledger_paths)
    if ledger is None:
        return None
    if canonical not in ledger_canonicals(ledger):
        return ("sidecar kanonik hash defterde yok: %s… (%s)"
                % (canonical[:16], ledger))
    measured, _found = measure_canonical(pdf_path)
    if measured and measured != canonical:
        return ("sidecar kanonik hash PDF ile uyuşmuyor: kayıt=%s… ölçülen=%s…"
                % (canonical[:16], measured[:16]))
    return None


def _find_qpdf():
    for cand in (shutil.which("qpdf"), "/opt/homebrew/bin/qpdf"):
        if cand and os.path.isfile(cand):
            return cand
    return None


def _strip_metadata(qpdf, src, dst):
    subprocess.run([qpdf, "--remove-metadata", src, dst],
                   capture_output=True, timeout=60)
    return os.path.isfile(dst)


def sync_metadata_sidecar(pdf_path, sidecar_path, ledger_paths=None, strip=None):
    """Adım 0: V5l reuse kuralı + Faz 4 defter bağı; `(ok, detail)` döner.

    `strip` yalnız test içindir: `(src, dst) -> bool`. Verilmezse qpdf
    `--remove-metadata` kullanılır; qpdf yoksa ve yenileme gerekiyorsa
    fail-closed (sidecar bayat kalamaz).
    """
    if not os.path.isfile(pdf_path):
        return True, "PDF yok — sidecar adımı atlandı"
    raw_hash = sha256(pdf_path)
    if _cached_raw(sidecar_path) == raw_hash:
        problem = sidecar_binding_problem(pdf_path, sidecar_path, ledger_paths)
        if problem:
            return False, problem
        return True, ("metadata sidecar reuse — PDF raw hash değişmedi: %s…"
                      % raw_hash[:12])
    if strip is None:
        qpdf = _find_qpdf()
        if qpdf is None:
            return False, ("PDF ham hash'i değişti ama qpdf yok — sidecar "
                           "yenilenemedi; kanonik defter bağı kurulamaz")
        strip = lambda src, dst, _q=qpdf: _strip_metadata(_q, src, dst)  # noqa: E731
    fd, tmp = tempfile.mkstemp(suffix=".pdf")
    os.close(fd)
    try:
        if not strip(pdf_path, tmp):
            return False, "metadata stripping başarısız — sidecar yenilenmedi"
        return renew_sidecar(pdf_path, sidecar_path, sha256(tmp), raw_hash,
                             ledger_paths)
    finally:
        if os.path.isfile(tmp):
            os.unlink(tmp)


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
    #    V5l kuralı: sidecar yalnızca PDF'in ham SHA-256'sı DEĞİŞTİĞİNDE
    #    (motor geçişi) yenilenir; qpdf'in kendi kararsızlığı pakete hash
    #    gürültüsü eklemesin. Faz 4: o yenileme KANONİK DEFTERE BAĞLIDIR —
    #    yeni `/ID`-kanonik hash defterde yoksa sidecar YAZILMAZ ve repack
    #    exit 1 verir (bkz. sync_metadata_sidecar / renew_sidecar).
    pdf = os.path.join(PKG, "ingiliz_empirizmi_v3.pdf")
    pdf_sidecar = os.path.join(PKG, "ingiliz_empirizmi_v3.pdf.metadata.sha256")
    ok_sidecar, sidecar_detail = sync_metadata_sidecar(pdf, pdf_sidecar)
    if not ok_sidecar:
        print(f"  HATA: {sidecar_detail}")
        print("  repack DURDURULDU — yarım paket/sidecar yazılmadı "
              "(fail-closed: motor geçişi defter kabulü olmadan ilerlemez)")
        return 1
    print(f"  {sidecar_detail}")

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
    raise SystemExit(main())
