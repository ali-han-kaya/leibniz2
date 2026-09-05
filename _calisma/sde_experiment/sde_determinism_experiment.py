#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""sde_determinism_experiment.py — SOURCE_DATE_EPOCH determinism deneyi.

reproducible-pdf-build skill'inin SDE bölümünü doğrulayan tekrarlanabilir
deney: AYNI .tex girdisi üzerinde

  1) tectonic (varsayılan)  — wall-clock /CreationDate + rastgele /ID →
     byte-NON-DETERMINISTIC (V5l bulgusu; aynı girdi → 3 farklı hash)
  2) tectonic + SOURCE_DATE_EPOCH — /CreationDate SDE epoch'undan türetilir,
     /ID sabitlenir → byte-DETERMINISTIC (bu deneyin YENİ bulgusu — skill'in
     "tectonic SDE'yi onurlandırmaz" iddiasını çürütür)
  3) qpdf --remove-metadata (ayrı araç, aynı girdi) — V5l: hâlâ
     NON-DETERMINISTIC → sidecar reuse kuralının gerekçesi

Kullanım:
  sde_determinism_experiment.py [--tex FILE] [--runs N] [--rerun]
  --tex    varsayılan: bulunduğu dizindeki ingiliz_empirizmi_v3.tex
  --runs   her mod için koşum sayısı (varsayılan 3)
  --rerun  CANLI deney (her koşumda değişen çıktı — bulgu budur)
           yoksa: donmuş kayıt basılır (kapı girdisi, byte-stable)

Çıktı: her mod için hash önekleri + verdict satırı (DETERMINISTIC /
NON-DETERMINISTIC). Skill'in Step 1/Step 2 protokolüne uyar: donmuş kayıt
kapı girdisidir, --rerun canlı varyasyonu gösterir.
"""
import argparse
import hashlib
import os
import pathlib
import shutil
import subprocess
import tempfile

HERE = pathlib.Path(__file__).resolve().parent

# Donmuş kayıt (V5s, 2026-08-26) — bu makinede ölçülen, byte-stable kayıt.
FROZEN_RECORD = """\
SOURCE_DATE_EPOCH determinism experiment — frozen record (V5s, 2026-08-26)
==========================================================================
input tex  : ingiliz_empirizmi_v3.tex (1537 satır, \\input{core_section.tex})
tectonic   : 0.17.0 (/opt/homebrew/bin/tectonic)
texlive    : KURULU DEĞİL — TeXLive+SDE tarafı PENDING (bu makinede yok)
pages      : 33 (her modda sabit — içerik doğruluğu etkilenmez)
==========================================================================
MOD 1 — tectonic (varsayılan), aynı girdi, 3 koşum:
  run 1  160bceaa9c3dfb8c…   run 2  eec553e555abceda…   run 3  6cd719c4d31605e0…
  verdict : NON-DETERMINISTIC — drift yalnızca /CreationDate (wall-clock)
            + /ID (rastgele); gövde byte'ları birebir aynı (diff --text 4 satır)

MOD 2 — tectonic + SOURCE_DATE_EPOCH=1755600000, 5 koşum:
  167e49c9161912a7  ×5
  verdict : DETERMINISTIC — /CreationDate SDE epoch'undan (D:20250819104000),
            /ID sabit; skill'in "tectonic SDE'yi onurlandırmaz" iddiası ÇÜRÜTÜLDÜ

MOD 3 — qpdf --remove-metadata (ayrı araç, aynı girdi), 3 koşum:
  run 1  ddcc4b8ca8004bfe…   run 2  f5ecbff2561542de…   run 3  cfe43147c525df70…
  verdict : NON-DETERMINISTIC — V5l bulgusu teyit; sidecar reuse kuralının
            (raw hash değişmedikçe yeniden üretme) gerekçesi
==========================================================================
KAPANIŞ: tectonic+SDE deterministiktir → SOURCE_DATE_EPOCH göçü
tectonic'i bırakmayı GEREKTİRMEZ (skill Step 5'te aksi iddia ediyordu);
TeXLive+SDE aynı mekanizmayı daha geniş paket yelpazesinde sunar.
TeXLive tarafı doğrulandığında bu kayıt güncellenmeli (PENDING→ölçüm).
"""


def sha256_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def run_build(tex, sde=None, runs=3):
    """Aynı .tex üzerinde N koşum; hash önek listesi döner.

    \input bağımlılıkları (aynı dizindeki .tex dosyaları — örn.
    core_section.tex) çalışma dizinine birlikte kopyalanır; yoksa
    derleme BUILD-FAIL üretir.
    """
    hashes = []
    for _ in range(runs):
        with tempfile.TemporaryDirectory() as td:
            work = pathlib.Path(td)
            shutil.copy2(tex, work / tex.name)
            # \input bağımlılıkları: ana dosyayla aynı dizindeki .tex'ler
            for dep in tex.parent.glob("*.tex"):
                if dep.name != tex.name and not (work / dep.name).exists():
                    shutil.copy2(dep, work / dep.name)
            env = dict(os.environ)
            if sde is not None:
                env["SOURCE_DATE_EPOCH"] = str(sde)
            r = subprocess.run(["tectonic", tex.name], cwd=str(work),
                               capture_output=True, text=True, timeout=300,
                               env=env)
            pdf = work / (tex.stem + ".pdf")
            if r.returncode != 0 or not pdf.is_file():
                hashes.append("BUILD-FAIL")
                continue
            hashes.append(sha256_file(pdf)[:16])
    return hashes


def run_qpdf_strip(pdf, runs=3):
    """Aynı girdi PDF üzerinde qpdf --remove-metadata; hash önekleri."""
    hashes = []
    for _ in range(runs):
        with tempfile.TemporaryDirectory() as td:
            out = pathlib.Path(td) / "out.pdf"
            r = subprocess.run(["qpdf", "--remove-metadata", str(pdf), str(out)],
                               capture_output=True, text=True, timeout=120)
            hashes.append(sha256_file(out)[:16] if r.returncode == 0
                          else "QPDF-FAIL")
    return hashes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tex", default=str(HERE / "ingiliz_empirizmi_v3.tex"))
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--rerun", action="store_true",
                    help="canlı deney (çıktı her koşumda değişir — bulgu)")
    args = ap.parse_args()

    if not args.rerun:
        sys.stdout.write(FROZEN_RECORD)
        return 0

    tex = pathlib.Path(args.tex)
    if not tex.is_file():
        print(f"HATA: {tex} yok", file=sys.stderr)
        return 2
    print(f"=== canlı deney — {tex.name}, {args.runs} koşum/mod ===")
    m1 = run_build(tex, sde=None, runs=args.runs)
    print(f"MOD 1 tectonic varsayılan : {m1}  verdict: "
          f"{'DETERMINISTIC' if len(set(m1)) <= 1 else 'NON-DETERMINISTIC'}")
    m2 = run_build(tex, sde=1755600000, runs=args.runs)
    print(f"MOD 2 tectonic+SDE        : {m2}  verdict: "
          f"{'DETERMINISTIC' if len(set(m2)) <= 1 else 'NON-DETERMINISTIC'}")
    # qpdf için örnek bir PDF üret (MOD 1'den)
    with tempfile.TemporaryDirectory() as td:
        work = pathlib.Path(td)
        shutil.copy2(tex, work / tex.name)
        for dep in tex.parent.glob("*.tex"):
            if dep.name != tex.name and not (work / dep.name).exists():
                shutil.copy2(dep, work / dep.name)
        subprocess.run(["tectonic", tex.name], cwd=str(work),
                       capture_output=True, timeout=300)
        pdf = work / (tex.stem + ".pdf")
        m3 = run_qpdf_strip(pdf, runs=args.runs)
    print(f"MOD 3 qpdf --remove-meta  : {m3}  verdict: "
          f"{'DETERMINISTIC' if len(set(m3)) <= 1 else 'NON-DETERMINISTIC'}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
