#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_pattern_consistency.py — verify.yml merge pattern ↔ ARTIFACT_JOBS tutarlılık denetimi.

Pre-commit hook'u tarafından koşulur: verify.yml'deki brace merge pattern'ini
gen_repro_manifest.py'nin ARTIFACT_JOBS sözlüğüyle karşılaştırır.

Eksik/fazla artifact varsa exit 1 ile commit'i bloke eder.

Kullanım:
  python3 check_pattern_consistency.py
  python3 check_pattern_consistency.py --workflow .github/workflows/verify.yml
"""
import os
import re
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_WORKFLOW = os.path.join(SCRIPT_DIR, "..", "..", ".github", "workflows", "verify.yml")

# ARTIFACT_JOBS'u gen_repro_manifest.py'den içe aktar
sys.path.insert(0, SCRIPT_DIR)
import gen_repro_manifest as gm

# merge-multiple ile indirilmeyenler (prefix ile ayrı indirilir veya çıkış artifact'ı)
EXCLUDED = frozenset({
    "precommit-logs", "refs-trend", "override-trend",
    "precheck-report", "python3-shell", "plist-check",
    "mirror-check", "daemon-http", "audit-refs-trend",
    "reproducibility",
})


def _read_merge_pattern(workflow_path: str):
    """verify.yml'den merge-multiple pattern'ini oku (brace format).

    Döndürür: (items: set, line_no: int) — line_no pattern'in bulunduğu satır.
    """
    with open(workflow_path, encoding="utf-8") as f:
        lines = f.readlines()
    for i, line in enumerate(lines, 1):
        m = re.search(r"pattern:\s*'\{([^}]+)\}'", line)
        if m:
            return {s.strip() for s in m.group(1).split(",")}, i
    return None, 0


def check(workflow_path: str = None):
    """Pattern tutarlılığını denetle. Hata listesi döndür."""
    wf = workflow_path or DEFAULT_WORKFLOW
    if not os.path.isfile(wf):
        return [f"Workflow dosyası bulunamadı: {wf}"]

    pattern, line_no = _read_merge_pattern(wf)
    if pattern is None:
        return ["verify.yml'de brace merge pattern bulunamadı"]

    expected = set(gm.ARTIFACT_JOBS) - EXCLUDED
    errors = []

    missing = expected - pattern
    extra = pattern - expected

    if missing:
        errors.append(f"Eksik (satır {line_no}): pattern'de yok ama ARTIFACT_JOBS'da var: {', '.join(sorted(missing))}")
    if extra:
        errors.append(f"Fazla (satır {line_no}): pattern'da var ama ARTIFACT_JOBS'da yok: {', '.join(sorted(extra))}")

    # Duplike kontrolü
    with open(wf, encoding="utf-8") as f:
        text = f.read()
    m = re.search(r"pattern:\s*'\{([^}]+)\}'\s*\n", text)
    if m:
        items = [s.strip() for s in m.group(1).split(",")]
        dupes = [x for x in items if items.count(x) > 1]
        if dupes:
            errors.append(f"Duplike artifact'lar pattern'de: {', '.join(sorted(set(dupes)))}")

    return errors


def fix(workflow_path: str = None):
    """Eksik artifact'ları pattern'e otomatik ekle (sıralı, deterministic).

    Döndürür (added: set, errors: list). added boş ama errors boşsa → zaten güncel.
    Dosya yalnızca DEĞİŞİKLİK VARSA yazılır (idempotent).
    """
    wf = workflow_path or DEFAULT_WORKFLOW
    if not os.path.isfile(wf):
        return set(), [f"Workflow dosyası bulunamadı: {wf}"]

    with open(wf, encoding="utf-8") as f:
        text = f.read()

    # Hedef pattern'i bul: merge-multiple + pattern ile aynı satır
    # (birden fazla merge-multiple olabilir — brace pattern'in olduğu doğru satır)
    pat_re = re.compile(
        r"(merge-multiple:\s*true\s*\n\s*pattern:\s*)'\{([^}]+)\}'"
        r"(\s*\n)"
    )
    m = pat_re.search(text)
    if not m:
        return set(), ["verify.yml'de merge-multiple brace pattern bulunamadı"]

    prefix, current_str, suffix = m.group(1), m.group(2), m.group(3)
    current_items = [s.strip() for s in current_str.split(",")]
    current_set = set(current_items)

    expected = set(gm.ARTIFACT_JOBS) - EXCLUDED
    missing = expected - current_set
    extra = current_set - expected

    if not missing and not extra:
        return set(), []  # zaten güncel

    # Yeni sıralı liste: mevcut + eksik - fazla (deterministic sorted)
    new_items = sorted(current_set | missing - extra)
    # Duplike temizliği: sıralanmış listede zaten sorun olmaz ama emin olalım
    seen = set()
    deduped = []
    for x in new_items:
        if x not in seen:
            seen.add(x)
            deduped.append(x)

    new_pattern = prefix + "'{" + ",".join(deduped) + "}'" + suffix
    text = pat_re.sub(new_pattern, text, count=1)

    with open(wf, "w", encoding="utf-8") as f:
        f.write(text)

    return missing, []


def main():
    import argparse
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--workflow", default=None, help="Workflow dosya yolu")
    ap.add_argument("--fix", action="store_true",
                    help="Eksik artifact'ları pattern'e otomatik ekle "
                         "(sıralı, idempotent)")
    args = ap.parse_args()

    if args.fix:
        added, errors = fix(args.workflow)
        if errors:
            print("HATA:")
            for e in errors:
                print(f"  ✗ {e}")
            return 1
        if not added:
            print("✓ pattern zaten güncel — değişiklik yok")
            return 0
        print(f"✓ pattern güncellendi — eklenen: {', '.join(sorted(added))}")
        # Fix sonrası tutarlılığı doğrula
        verify_errors = check(args.workflow)
        if verify_errors:
            print("UYARI: fix sonrası hâlâ tutarsızlık var:")
            for e in verify_errors:
                print(f"  ✗ {e}")
            return 1
        print("✓ fix sonrası doğrulama: PASS")
        return 0

    errors = check(args.workflow)
    if errors:
        print("PATTERN DRIFT TESPİT EDİLDİ:")
        for e in errors:
            print(f"  ✗ {e}")
        print("\nDüzeltme: verify.yml merge-multiple pattern'ini ARTIFACT_JOBS ile senkronlayın.")
        print("  Eksik artifact'ı pattern'e ekleyin veya ARTIFACT_JOBS'dan çıkarın.")
        print("  VEYA: --fix ile otomatik düzeltin.")
        return 1

    print("✓ merge pattern ↔ ARTIFACT_JOBS tutarlı")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
