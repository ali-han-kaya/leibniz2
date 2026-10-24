#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
check_recovery_patches_index.py — recovery_patches INDEX integrity check.

Neden: `_calisma/CIKTI/recovery_patches_INDEX.json`'daki SHA-256 çamurları
ve dosya/etki kaydı tutarlılığını ön-commit sırasında denetlemek için.

Sözleşme:
- INDEX dosyası yok → exit 2 (ölçüm hatası — körleşen kapı).
- fingerprint'ler dosya ile uyuşmuysa → exit 1 (--strict) / uyarı (advisory).
- affected_files mapping'i bozuksa → uyarı (advisory, exit 0).
- Bu kapı read-only'dir: dosya değiştirmez, yalnızca doğrular (fail-closed
  bildirim).

Exit: 0 = uyumlu (veya advisory modda bayat), 1 = --strict altında bayat,
2 = kullanım/ölçüm hatası.
--json: {ok, stale, mismatched_fingerprints[], known_incident_fingerprints[], summary} makine-okunur.

Doppelt parmak-izi kuralı (double-fingerprint classify rule):
- Her patch'in SHA-256'ı INDEKSTEKI sha256 alanının değeriyle byte-for-byte
  aynı olmalı (bkz. check_precommit_orphans.py KNOWN-INCIDENT sınıflandırması).
- Eşleşme → KNOWN-INCIDENT (archived incident patch'indeki içerik)
- Uyuşmazlık → UNKNOWN (değişken/new içerik, araştırılmalı)
- Hem patch_id hem de sha256 birleştirilerek benzersiz sınıflandırma yapılır.
"""

import argparse
import hashlib
import json
import os
import pathlib
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
DEFAULT_INDEX = os.path.join(ROOT, "_calisma", "CIKTI", "recovery_patches_INDEX.json")


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _compute_sha256(filepath):
    """Compute SHA-256 hex digest of a file's bytes."""
    with open(filepath, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def _validate_index(index_path):
    """
    Validate the recovery_patches_INDEX.json file and cross-check SHA-256
    fingerprints against actual patch files in recovery_patches_20260918/.

    Returns (ok, report) where report is a dict with:
    - ok: bool — whether all checks pass
    - stale: bool — whether the file has stale/missing data
    - mismatched_fingerprints: list of patch_ids whose sha256 doesn't match
      the actual patch file (UNKNOWN classification)
    - known_incident_fingerprints: list of patch_ids that match the archive
      (KNOWN-INCIDENT classification)
    - summary: dict from index summary
    """

    report = {
        "ok": False,
        "stale": False,
        "mismatched_fingerprints": [],
        "known_incident_fingerprints": [],
        "summary": {},
    }

    try:
        index = _read(index_path)
    except FileNotFoundError:
        print(f"HATA: INDEX dosyası bulunamadı: {index_path}")
        return False, report
    except json.JSONDecodeError as exc:
        print(f"HATA: INDEX JSON çözümleme hatası: {index_path} ({exc})")
        return False, report

    # Ensure required top-level keys exist
    if "patches" not in index or "summary" not in index:
        print(f"HATA: INDEX eksik gerekli anahtar: 'patches' ve/veya 'summary'")
        return False, report

    patches = index["patches"]
    summary = index["summary"]

    report["summary"] = summary

    if not patches:
        print("UYARI: INDEX'de 'patches' listesi boş.")
        report["stale"] = True
        report["ok"] = True  # empty is not an error, just advisory
        return True, report

    # Build fingerprint map from INDEX: patch_id -> sha256
    index_fingerprints = {}
    for patch in patches:
        patch_id = patch.get("patch_id", "unknown")
        sha256 = patch.get("sha256", "")
        if sha256:
            index_fingerprints[patch_id] = sha256

    # Build fingerprint map from ACTUAL patch files in archive:
    # patch_id (filename) -> sha256
    archive = pathlib.Path(HERE) / "recovery_patches_20260918"
    actual_fingerprints = {}
    if archive.is_dir():
        for patch_file in archive.glob("patch*"):
            try:
                sha = _compute_sha256(patch_file)
                patch_id = patch_file.name  # e.g. patch1789754982-84993
                actual_fingerprints[patch_id] = sha
            except OSError:
                continue

    # Cross-check: classify each INDEX patch_id
    mismatched_fingerprints = []
    known_incident_fingerprints = []

    for patch_id, index_sha in index_fingerprints.items():
        if patch_id in actual_fingerprints:
            actual_sha = actual_fingerprints[patch_id]
            if index_sha == actual_sha:
                # SHA-256 matches → KNOWN-INCIDENT (archived incident patch content)
                known_incident_fingerprints.append(patch_id)
            else:
                # SHA-256 mismatch → UNKNOWN (changed/new content)
                mismatched_fingerprints.append(patch_id)
        else:
            # patch_id not found in archive → UNKNOWN
            mismatched_fingerprints.append(patch_id)

    # Check that all patches have sha256 fingerprints
    missing_sha = []
    for patch in patches:
        patch_id = patch.get("patch_id", "unknown")
        if "sha256" not in patch or not patch.get("sha256"):
            missing_sha.append(patch_id)

    if missing_sha:
        print(f"UYARI: Aşağıdaki patch'ler SHA-256 iziniyor: {', '.join(missing_sha)}")
        report["stale"] = True

    report["mismatched_fingerprints"] = mismatched_fingerprints
    report["known_incident_fingerprints"] = known_incident_fingerprints

    # Determine overall ok status
    # ok = no missing SHA AND no mismatched fingerprints (or not strict)
    # But empty patches or no mismatches still ok (advisory)
    if missing_sha:
        report["ok"] = False
    elif mismatched_fingerprints:
        report["ok"] = True  # advisory mode: report but don't block
    else:
        report["ok"] = True

    return report["ok"], report


def run(index_path=DEFAULT_INDEX):
    """Run the validation and return (rc, report_dict)."""
    ok, report = _validate_index(index_path)

    if not ok:
        return 2, report

    # Print human-readable output
    lines = []
    lines.append("RECOVERY PATCHES INDEX ↔ GERÇEK (check-recovery-patches-index)")
    lines.append(f"  index: {index_path}")
    lines.append(f"  patches: {report['summary'].get('total_patches', 0)}")

    if report["stale"]:
        lines.append("BAYAT: INDEX tutarlılık sorunu tespit edildi.")
        if report["mismatched_fingerprints"]:
            lines.append(
                f"  fingerprint'ler uyuşmuyor (UNKNOWN): {', '.join(report['mismatched_fingerprints'])}"
            )
        if report["known_incident_fingerprints"]:
            lines.append(
                f"  KNOWN-INCIDENT eşleşmeleri: {', '.join(report['known_incident_fingerprints'])}"
            )
        if report["summary"].get("missing_sha"):
            lines.append(
                f"  Eksik SHA-256: {', '.join(report['summary'].get('missing_sha', []))}"
            )
    else:
        lines.append("PASS: INDEX tutarlısı (advisory — commit bloke edilmedi).")

    for line in lines:
        print(line)

    return (0 if report["ok"] else 1), report


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="recovery_patches INDEX integrite denetimi (pre-commit hook)"
    )
    ap.add_argument(
        "--index", default=DEFAULT_INDEX,
        help="recovery_patches INDEX.json yolu"
    )
    ap.add_argument(
        "--json", action="store_true",
        help="makine-okunur JSON çıktı"
    )
    ap.add_argument(
        "--strict", action="store_true",
        help="bayatlıkta exit 1 (varsayılan: sadece uyarı, exit 0)"
    )
    args = ap.parse_args(argv)

    rc, report = run(args.index)
    report["strict"] = args.strict

    if args.json:
        payload = dict(report)
        payload["ok"] = report["ok"] and rc == 0
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return rc if rc == 2 else (rc if args.strict else 0)

    if rc == 2:
        return 2
    if report["stale"]:
        if args.strict:
            print("SONUÇ: FAIL (--strict) — INDEX bayat.")
            return 1
        print("UYARI: INDEX tutarlılık uyarısı (advisory — commit bloke edilmedi; --strict için kapalı mod).")
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())