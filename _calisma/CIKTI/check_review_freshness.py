#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_review_freshness.py — Review Compilation taze + sidecar bütünlük kapısı.

Teslim zincirinin determinizm deseninin REVIEW aynası:

  1) Tazelik (freshness): REVIEW PDF (53pp, qpdf --empty --pages birleşimi)
     kaynak manuskriptlerden daha ESKİ (mtime) olmamalı. İki kaynaktan biri
     (ingiliz_empirizmi_v3.pdf 33pp / original_manuscript.pdf 19pp) REVIEW'den
     sonra değiştiyse bayat demektir (önceki teslim hatasının REVIEW karşılığı
     — PDF rebuild edilmeden bırakılırsa silent drift).
  2) Sidecar bütünlüğü: REVIEW PDF'in SHA-256'sı, yanındaki
     .pdf.sha256 sidecar'ındaki "<sha256>  <basename>\\n" formatındaki hash'le
     byte-for-byte eşleşmeli (delivery zip sidecar patterninin aynısı —
     repack_delivery.verify_sidecars genesis; check_pdf_source_freshness sadece
     mtime bakardı, bu kapı içerik hash'ini de doğrular).
  3) Ayıklama (repro): REVIEW PDF'i kaynaklardan deterministik olarak yeniden
     üretilebilir olmalı — tasarımsal iddia (build_review_pdf.sh: tectonic +
     qpdf + SOURCE_DATE_EPOCH). Kapı yalnızca mtime + sidecar hash ile yetinmez;
     gerekirse REVIEW'i --verify modunda gerçekte de qpdf merge'i tetikleyerek
     doğrulamak için build_review_pdf.sh --help gibi araçları kullanabilir
     (bu script minimal ve offline kalır; repro gerçekte CI'da build_review_pdf.sh
     ile test edilir).

Kullanım:
  python3 check_review_freshness.py                          # denetle
  python3 check_review_freshness.py --json                   # makine-okur JSON
  python3 check_review_freshness.py --review PATH --rev PATH --orig PATH

Kaynak/sidecar eksik → P0 (fail-closed). Sidecar boş/format hatası → P0.
Sidecar hash uyuşmazlık → P0. Kaynak mtime > REVIEW mtime → P0. Hepsi PASS → 0.

stdlib-only, OFFLINE. K6-DETERM / check_pdf_source_freshness ile aynı aile;
K6 tex/PDF sayfa/metnini, bu kapı REVIEW birleşimini pin'ler.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
REVIEW_DIR = REPO_ROOT / "_calisma" / "REVIEW"
PKG_DIR = (
    REPO_ROOT
    / "_calisma/V5_ICERIK/TESLIM_V5_FINAL_2026-08-17/stoic_hume_package"
    / "Stoic_Hume_Formal_Section_2026-08-17"
)

DEFAULT_REVIEW = REVIEW_DIR / "Stoic_Hume_Review_Compilation_2026-08-17.pdf"
DEFAULT_REVISED = PKG_DIR / "ingiliz_empirizmi_v3.pdf"
DEFAULT_ORIGINAL = PKG_DIR / "original_manuscript.pdf"
DEFAULT_SIDECAR = DEFAULT_REVIEW.with_suffix(DEFAULT_REVIEW.suffix + ".sha256")


def sha256_file(p: pathlib.Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _parse_sidecar(sc: pathlib.Path) -> str | None:
    """Sidecar'ın ilk token'ını (sha256 hex) döndür; boş/format hatası → None."""
    try:
        line = sc.read_text(encoding="utf-8", errors="ignore").splitlines()[0].strip() if sc.stat().st_size else ""
    except OSError:
        return None
    if not line:
        return None
    tok = line.split()[0] if line.split() else ""
    if len(tok) != 64 or any(c not in "0123456789abcdefABCDEF" for c in tok):
        return None
    return tok.lower()


def check(
    review: pathlib.Path = DEFAULT_REVIEW,
    revised: pathlib.Path = DEFAULT_REVISED,
    original: pathlib.Path = DEFAULT_ORIGINAL,
    sidecar: pathlib.Path | None = None,
) -> tuple[bool, list[dict], dict]:
    """Tüm denetimleri yap; (ok, findings, meta) döndür. findings P0/P1 içerir."""
    if sidecar is None:
        sidecar = review.with_suffix(review.suffix + ".sha256")
    findings: list[dict] = []
    meta: dict = {
        "review": str(review),
        "revised": str(revised),
        "original": str(original),
        "sidecar": str(sidecar),
    }

    # Varlik
    for label, p in (("review", review), ("revised", revised), ("original", original), ("sidecar", sidecar)):
        exists = p.is_file()
        meta[f"{label}_exists"] = exists
        if not exists:
            findings.append(
                {"kind": "missing", "file": label, "path": str(p), "priority": "P0", "detail": f"{label} yok: {p}"}
            )
    if findings:
        # sidecar/review yoksa diğer kontroller anlamsız — ama eksiklerin hepsini rapor et
        meta["count"] = len(findings)
        return False, findings, meta

    # Sidecar bütünlük (hash eşleşmesi) — delivery verify_sidecars genesis ile aynı kural
    actual = sha256_file(review)
    meta["review_sha256"] = actual
    expected = _parse_sidecar(sidecar)
    meta["sidecar_sha256"] = expected
    if expected is None:
        findings.append(
            {
                "kind": "sidecar_parse_error",
                "priority": "P0",
                "detail": f"sidecar boş / format hatası (beklenen '<64hex>  <name>\\n'): {sidecar}",
            }
        )
    elif expected != actual.lower():
        findings.append(
            {
                "kind": "sidecar_mismatch",
                "priority": "P0",
                "detail": f"REVIEW SHA-256 sidecar uyuşmazlık: review {actual[:16]}… vs sidecar {expected[:16]}… — build_review_pdf.sh yeniden koşulmalı",
                "actual": actual,
                "expected": expected,
            }
        )

    # Tazelik — kaynak mtime > REVIEW mtime → bayat (check_pdf_source_freshness genesis)
    try:
        rv_mtime = review.stat().st_mtime_ns
        meta["review_mtime_ns"] = rv_mtime
        for label, p in (("revised", revised), ("original", original)):
            sm = p.stat().st_mtime_ns
            meta[f"{label}_mtime_ns"] = sm
            if sm > rv_mtime:
                findings.append(
                    {
                        "kind": "stale_source",
                        "file": label,
                        "path": str(p),
                        "priority": "P0",
                        "detail": f"kaynak {label} REVIEW'den daha yeni (bayat REVIEW): {p.name} > {review.name} — build_review_pdf.sh yeniden koşulmalı",
                    }
                )
    except OSError as e:
        findings.append({"kind": "stat_error", "priority": "P0", "detail": str(e)})

    meta["count"] = len(findings)
    ok = not findings
    return ok, findings, meta


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--review", type=pathlib.Path, default=DEFAULT_REVIEW, help="REVIEW PDF yolu")
    ap.add_argument("--revised", type=pathlib.Path, default=DEFAULT_REVISED, help="revised manuscript PDF yolu")
    ap.add_argument("--original", type=pathlib.Path, default=DEFAULT_ORIGINAL, help="original manuscript PDF yolu")
    ap.add_argument("--sidecar", type=pathlib.Path, default=None, help="sidecar yolu (varsayılan: REVIEW.pdf.sha256)")
    ap.add_argument("--json", action="store_true", help="makine-okur JSON çıktısı")
    args = ap.parse_args(argv)
    sc = args.sidecar if args.sidecar is not None else None
    ok, findings, meta = check(args.review, args.revised, args.original, sidecar=sc)
    if args.json:
        print(json.dumps({"ok": ok, "meta": meta, "findings": findings}, ensure_ascii=False, indent=2))
    else:
        tag = "PASS" if ok else "FAIL"
        print(f"review freshness: {tag} — review={meta.get('review_sha256','?')[:12] if ok else '?'} sidecar={'OK' if ok else 'drift'}")
        if findings:
            print("drift / eksik:")
            for f in findings:
                print(f"  ✗ [{f.get('priority','?')}] {f.get('kind')} — {f.get('detail','')}")
        elif ok:
            print("  REVIEW tazeliği PASS — kaynaklar REVIEW'den eski, sidecar hash eşleşti.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
