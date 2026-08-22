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
    "config", "precommit-logs", "refs-trend", "override-trend",
    "precheck-report", "python3-shell", "plist-check",
    "reproducibility",
})


def _read_merge_pattern(workflow_path: str):
    """verify.yml'den merge-multiple pattern'ini oku (brace format)."""
    with open(workflow_path, encoding="utf-8") as f:
        text = f.read()
    m = re.search(
        r"merge-multiple:\s*true\s*\n\s*pattern:\s*'\{([^}]+)\}'\s*\n",
        text,
    )
    if not m:
        return None
    return {s.strip() for s in m.group(1).split(",")}


def check(workflow_path: str = None):
    """Pattern tutarlılığını denetle. Hata listesi döndür."""
    wf = workflow_path or DEFAULT_WORKFLOW
    if not os.path.isfile(wf):
        return [f"Workflow dosyası bulunamadı: {wf}"]

    pattern = _read_merge_pattern(wf)
    if pattern is None:
        return ["verify.yml'de brace merge pattern bulunamadı"]

    expected = set(gm.ARTIFACT_JOBS) - EXCLUDED
    errors = []

    missing = expected - pattern
    extra = pattern - expected

    if missing:
        errors.append(f"Eksik (pattern'de yok ama ARTIFACT_JOBS'da var): {', '.join(sorted(missing))}")
    if extra:
        errors.append(f"Fazla (pattern'da var ama ARTIFACT_JOBS'da yok): {', '.join(sorted(extra))}")

    # Duplike kontrolü
    raw = ""
    with open(wf, encoding="utf-8") as f:
        text = f.read()
    m = re.search(r"pattern:\s*'\{([^}]+)\}'\s*\n", text)
    if m:
        items = [s.strip() for s in m.group(1).split(",")]
        dupes = [x for x in items if items.count(x) > 1]
        if dupes:
            errors.append(f"Duplike artifact'lar pattern'de: {', '.join(sorted(set(dupes)))}")

    return errors


def main():
    import argparse
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--workflow", default=None, help="Workflow dosya yolu")
    args = ap.parse_args()

    errors = check(args.workflow)
    if errors:
        print("PATTERN DRIFT TESPİT EDİLDİ:")
        for e in errors:
            print(f"  ✗ {e}")
        print("\nDüzeltme: verify.yml merge-multiple pattern'ini ARTIFACT_JOBS ile senkronlayın.")
        print("  Eksik artifact'ı pattern'e ekleyin veya ARTIFACT_JOBS'dan çıkarın.")
        return 1

    print("✓ merge pattern ↔ ARTIFACT_JOBS tutarlı")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
