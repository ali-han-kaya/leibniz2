#!/usr/bin/env python3
"""check_zip_lineage_drift.py — K14 soy hattı/kanonik hash drift kapısı (commit-time).

NEDEN: K14 kontrolleri yalnızca CI'daki `verify_delivery.py --full` içinde
koşar. `b69de33` zipleri repack etti ama zip_lineage.json/cleanup_log.json
kanonik kayıtları yeni nesle güncellenmedi → CI-SIMULATE ve K1-K19 CI'ya
hepten kırdı (P0=3). Bu kapı AYNI karşılaştırmayı commit anında yapar:
kayıt ile canlı dosya uyuşmazsa commit bloke edilir (fail-closed).

Kaynaklar (verify_delivery.py ile AYNI tek kaynaklar):
  - zip_lineage.json  → generations[].current=true hash ↔ canlı dış zip (P0,
    verify_delivery.check_zip_lineage / LINEAGE-CUR ile aynı eşik)
  - cleanup_log.json  → canonical[].hash ↔ canlı dosya (P0, K14-CANON-HASH
    ile aynı eşik)
  - teslim metadata sidecar'ı → `# canonical:` referansı ↔ kabul defteri
    (Faz 4 repack determinizm kapısı; referans defterde yoksa P0)

Yalnızca P0 sınıfı denetlenir: P1 geçmiş-nesil türetmeleri (git show)
ve expect_absent/moved kayıtları CI'ın --full akışına bırakılır — kapı
offline, stdlib-only (id_canonical yardımcı modülü dışında bağımlılıksız)
ve ~10ms'dir.

Eşleşmeyen zip/dosya YOKSA (yeni checkout): UNVERIFIED (INFO) — engellemez,
aynı manier verify_delivery.check_cleanup'in CI davranışıdır.

Exit: 0 = kayıt ↔ canlı uyuşum, 1 = en az bir P0 drift.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(HERE))

sys.path.insert(0, HERE)
import id_canonical  # noqa: E402  (defter/normalizasyon tek kaynak)

# Teslim paketi + metadata sidecar adı. SIDECAR_NAME verify_delivery.
# PDF_METADATA_SIDECAR ile BİREBİR aynı olmalıdır. PKG_REL ise verify_delivery.
# PKG_REL'in REPO-göreli biçimidir (verify_delivery onu ZIP çıkarma köküne göre
# çözer): PKG_REL == "_calisma/V5_ICERIK/" + verify_delivery.PKG_REL. Kapı
# stdlib-only kalsın diye import edilmez; ikisi de test_check_zip_lineage_drift.
# py'de fail-closed pinlenir.
PKG_REL = ("_calisma/V5_ICERIK/TESLIM_V5_FINAL_2026-08-17/stoic_hume_package/"
           "Stoic_Hume_Formal_Section_2026-08-17")
SIDECAR_NAME = "ingiliz_empirizmi_v3.pdf.metadata.sha256"


def sha256_file(path: str) -> str | None:
    if not os.path.isfile(path):
        return None
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def fail(msg: str) -> int:
    print(f"K14-DRIFT (P0): {msg}", file=sys.stderr)
    return 1


def check_lineage_current(lineage_path: str, repo_root: str, findings: list) -> bool:
    """generations[].current=true ↔ canlı dış zip (LINEAGE-CUR eşik)."""
    ok = True
    try:
        with open(lineage_path, encoding="utf-8") as lf:
            lineage = json.load(lf)
    except (json.JSONDecodeError, OSError) as e:
        findings.append(fail(f"zip_lineage.json okunamadı: {e}"))
        return False

    rel = lineage.get("path_in_repo") or lineage.get("file") or ""
    live = sha256_file(os.path.join(repo_root, rel)) if rel else None
    cur = [g for g in lineage.get("generations", []) if g.get("current")]
    if not cur:
        findings.append(fail(f"zip_lineage.json'da current=true nesil yok ({rel})"))
        return False
    for g in cur:
        want = g.get("hash")
        if live is None:
            # verify_delivery davranışı: canlı dosya yoksa UNVERIFIED (INFO).
            print(f"K14-DRIFT (INFO): canlı zip yok — UNVERIFIED: {rel}")
            continue
        if want and live == want:
            print(f"K14-DRIFT PASS: lineage current ↔ canlı uyuşum: {rel} ({want[:12]}…)")
        else:
            ok = False
            findings.append(fail(
                f"lineage current ↔ canlı uyuşmuyor: {rel} "
                f"(kayıt={want} canlı={live}) — repack Delivery/registry resync gerekli"))
    return ok


def check_cleanup_canonical(cleanup_path: str, repo_root: str, findings: list) -> bool:
    """cleanup_log.json canonical[].hash ↔ canlı dosya (K14-CANON-HASH eşik)."""
    ok = True
    try:
        with open(cleanup_path, encoding="utf-8") as cf:
            log = json.load(cf)
    except (json.JSONDecodeError, OSError) as e:
        findings.append(fail(f"cleanup_log.json okunamadı: {e}"))
        return False

    for rec in log.get("canonical", []):
        rel = rec.get("path", "")
        want = rec.get("hash")
        p = os.path.join(repo_root, rel)
        got = sha256_file(p)
        if got is None:
            print(f"K14-DRIFT (INFO): kanonik dosya yok — UNVERIFIED: {rel}")
            continue
        if want and got == want:
            print(f"K14-DRIFT PASS: canonical hash uyuşum: {rel} ({want[:12]}…)")
        else:
            ok = False
            findings.append(fail(
                f"kanonik hash uyuşmuyor: {rel} (kayıt={want} canlı={got}) "
                f"— cleanup_log.json güncellenmeli (repack Delivery)"))
    return ok


def check_delivery_sidecar_canonical(sidecar_path: str, findings: list) -> bool:
    """Sidecar `# canonical:` referansı ↔ kabul defteri (Faz 4, P0).

    repack motor geçişinde sidecar'ı bilinçli yenilerken kanonik referansı
    yazar ve yazma anında defterde arar (repack fail-closed). Bu kapı AYNI
    iki kaynağı commit anında karşılaştırır: sidecar'daki referans defterde
    kayıtlı değilse P0 — motor geçişi ya defter satırı olmadan yapılmış ya da
    sidecar yenilemesi eksik. `# canonical:` satırı YOKSA (henüz yenilenmemiş
    tectonic-era sidecar) INFO: engellemez, yenileme beklemede demektir.
    """
    canonical = id_canonical.sidecar_canonical(sidecar_path)
    if not canonical:
        print("K14-DRIFT (INFO): sidecar'da # canonical: referansı yok — "
              "motor-geçişi yenilemesi beklemede (engellemez)")
        return True
    tokens, error, source = id_canonical.ledger_tokens()
    if error:
        findings.append(fail(
            f"kabul defteri okunamadı: {error} (sidecar kanonik referansı "
            f"doğrulanamaz)"))
        return False
    if not id_canonical.has_canonical(canonical, tokens):
        findings.append(fail(
            f"sidecar kanonik referansı kabul defterinde yok: "
            f"{canonical[:16]}… — defter satırı üret "
            f"(make -f docs/Makefile.texlive accept LEDGER=update) ya da "
            f"sidecar yenilemesini ({SIDECAR_NAME}) geri al"))
        return False
    print(f"K14-DRIFT PASS: sidecar kanonik referansı defterde kayıtlı: "
          f"{canonical[:12]}… (defter: {source})")
    return True


def main(argv: list | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--repo-root", default=REPO_ROOT,
                    help="Depo kökü (varsayılan: script konumundan türetilir)")
    args = ap.parse_args(argv)

    findings: list[int] = []
    ok = True

    lineage_path = os.path.join(args.repo_root, "_calisma", "CIKTI", "zip_lineage.json")
    cleanup_path = os.path.join(args.repo_root, "_calisma", "CIKTI", "cleanup_log.json")

    if os.path.isfile(lineage_path):
        ok &= check_lineage_current(lineage_path, args.repo_root, findings)
    else:
        print("K14-DRIFT (INFO): zip_lineage.json yok — bölüm atlandı")

    if os.path.isfile(cleanup_path):
        ok &= check_cleanup_canonical(cleanup_path, args.repo_root, findings)
    else:
        print("K14-DRIFT (INFO): cleanup_log.json yok — bölüm atlandı")

    sidecar_path = os.path.join(args.repo_root, PKG_REL, SIDECAR_NAME)
    if os.path.isfile(sidecar_path):
        ok &= check_delivery_sidecar_canonical(sidecar_path, findings)
    else:
        print("K14-DRIFT (INFO): teslim metadata sidecar'ı yok — bölüm atlandı")

    if not findings:
        print("K14-DRIFT: PASS — kayıt ↔ canlı dosya bütünlüğü tamam")
        return 0

    print(f"\nSONUÇ: FAIL — {len(findings)} P0 bulgu. "
          "Kayıt ile canlı zip bütünlüğü bozuk: repack_delivery.py + registry "
          "resync koşmalı, sonra zip + zip_lineage.json + cleanup_log.json "
          "AYNI commit'te stage edilmeli.", file=sys.stderr)
    return 1 if not ok else 0


if __name__ == "__main__":
    sys.exit(main())
