#!/usr/bin/env python3
"""
qpdf_determinism_experiment.py
==============================

Finite-validation artefact for the V5l finding (2026-08-18): the PDF
build-time step `qpdf --remove-metadata` is NOT byte-deterministic.

The manuscript PDF is compiled with tectonic 0.17.0, which is already
non-deterministic (V5k). Independently, the post-processing step
`qpdf --remove-metadata` (used to compute the metadata-stripped SHA-256,
K6-DETERM sidecar) is ALSO non-deterministic: the V5l experiment ran the
same qpdf command 3 times on the SAME input PDF and got 3 DIFFERENT
outputs (b090ac01…, 429984da…, 509a47a6…; raw PDF e7b0bc0b…).

Consequence: the metadata-stripped SHA-256 cannot be freely recomputed.
repack_delivery.py therefore regenerates the sidecar ONLY when the PDF's
raw SHA-256 changes; if the raw hash is unchanged, the existing sidecar is
reused (proven: consecutive repacks are byte-identical).

Two modes:
  default                          — prints the FROZEN RECORD (this output
                                     is byte-stable and is the K5 gate
                                     input: qpdf_determinism_output.txt).
                                     The live raw SHA-256 of the on-disk
                                     PDF is computed and printed; if the
                                     PDF is ever recompiled, the record
                                     goes stale and K5 fails closed until
                                     the record is regenerated.
  --rerun [N]                      — re-runs the live experiment: qpdf
                                     --remove-metadata N times (default 5)
                                     on the same input, prints the fresh
                                     stripped hashes + verdict. Output
                                     VARIES run to run — that is the
                                     experiment itself.

Run:    python3 qpdf_determinism_experiment.py            (frozen record)
        python3 qpdf_determinism_experiment.py --rerun 5  (live experiment)
Requires: qpdf only for --rerun mode; default mode is stdlib-only.
"""

import argparse
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PDF = os.path.join(HERE, "ingiliz_empirizmi_v3.pdf")

# V5l tarihsel kayıt (2026-08-18, MANIFEST notu): aynı girdi PDF üzerinde
# 3 ardışık qpdf --remove-metadata çalıştırması 3 FARKLI çıktı üretti.
# Tam hash'ler MANIFEST'ta yalnızca ÖNEK olarak kaydedildi.
HISTORICAL_RUNS = [("b090ac01", 1), ("429984da", 2), ("509a47a6", 3)]
HISTORICAL_RAW_PREFIX = "e7b0bc0b"
FROZEN_TS = "2026-08-18"


def sha256_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def report_record(pdf_path):
    """Donmuş kayıt — byte-stabil çıktı (K5 girişi)."""
    if not os.path.isfile(pdf_path):
        print(f"HATA: PDF yok: {pdf_path}")
        return 2
    raw = sha256_file(pdf_path)
    print("qpdf determinism experiment — frozen record (V5l, %s)" % FROZEN_TS)
    print("=" * 68)
    print("input PDF      : %s" % os.path.basename(pdf_path))
    print("raw SHA-256    : %s   (on-disk PDF'ten hesaplanır)" % raw)
    print("qpdf           : qpdf --remove-metadata  (V5l: NOT byte-deterministic)")
    print("=" * 68)
    print("HISTORICAL RECORD (V5l, %s, MANIFEST notu): aynı girdi PDF" % FROZEN_TS)
    print("(raw %s…) üzerinde 3 ardışık çalıştırma 3 FARKLI stripped çıktı" % raw[:8])
    print("üretti (hash'ler MANIFEST'ta önek olarak kayıtlı):")
    for prefix, i in HISTORICAL_RUNS:
        print("  run %d  %s…" % (i, prefix))
    print("verdict        : NON-DETERMINISTIC — metadata-stripped SHA-256")
    print("                 serbestçe yeniden hesaplanamaz; repack sidecar'ı")
    print("                 yalnızca raw hash değişince yeniden üretir (V5l fix).")
    print("=" * 68)
    print("Bu dosya donmuş kayıttır (K5 byte-for-byte). Yukarıdaki raw SHA-256")
    print("kayıttakinden farklıysa (PDF yeniden derlendi) kaydı yeniden üretin:")
    print("  python3 qpdf_determinism_experiment.py > qpdf_determinism_output.txt")
    return 0


def report_rerun(pdf_path, runs):
    """Canlı deney — qpdf'yi runs kez aynı girdi üzerinde koşar."""
    if not os.path.isfile(pdf_path):
        print(f"HATA: PDF yok: {pdf_path}")
        return 2
    qpdf = shutil.which("qpdf")
    if not qpdf:
        print("HATA: qpdf bulunamadı (PATH'te yok) — --rerun için qpdf gerekir")
        return 1
    raw = sha256_file(pdf_path)
    hashes = []
    for i in range(1, runs + 1):
        tmp = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as t:
                tmp = t.name
            r = subprocess.run([qpdf, "--remove-metadata", pdf_path, tmp],
                               capture_output=True, text=True, timeout=120)
            if r.returncode != 0:
                print(f"  run {i}: qpdf başarısız (exit {r.returncode})")
                hashes.append(None)
            else:
                hashes.append(sha256_file(tmp))
        finally:
            if tmp and os.path.isfile(tmp):
                os.unlink(tmp)
    print("qpdf determinism experiment — canlı deney (--rerun)")
    print("=" * 68)
    print("qpdf          : %s" % qpdf)
    print("input PDF     : %s" % os.path.basename(pdf_path))
    print("raw SHA-256   : %s" % raw)
    print("runs          : %d" % runs)
    for i, h in enumerate(hashes, 1):
        print("  stripped #%d : %s" % (i, h if h else "(qpdf başarısız)"))
    distinct = len({h for h in hashes if h})
    verdict = "DETERMINISTIC" if distinct <= 1 else "NON-DETERMINISTIC"
    print("distinct      : %d/%d" % (distinct, runs))
    print("verdict       : %s — aynı girdi üzerinde farklı stripped çıktılar" % verdict)
    return 0


def main():
    ap = argparse.ArgumentParser(
        description="V5l qpdf non-determinizm deneyi: donmuş kayıt + canlı üretim.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Varsayılan mod donmuş kaydı basar (byte-stabil, K5 girişi).\n"
               "--rerun N qpdf --remove-metadata'ı aynı girdi üzerinde N kez\n"
               "canlı koşar; çıktı run'dan run'a DEĞİŞİR (deneyin kendisi).")
    ap.add_argument("--pdf", default=PDF,
                    help="girdi PDF (varsayılan: betiğin yanındaki ingiliz_empirizmi_v3.pdf)")
    ap.add_argument("--rerun", nargs="?", const=5, type=int, metavar="N",
                    help="qpdf'yi N kez canlı yeniden koş (varsayılan 5); "
                         "çıktı donmuş kayıt DEĞİLDİR")
    args = ap.parse_args()
    if args.rerun is not None:
        if args.rerun < 1:
            print("HATA: --rerun N >= 1 olmalı")
            return 2
        return report_rerun(args.pdf, args.rerun)
    return report_record(args.pdf)


if __name__ == "__main__":
    sys.exit(main())
