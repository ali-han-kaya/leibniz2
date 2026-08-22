#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""summary_pattern_drift.py — reproducibility merge pattern drift'i GITHUB_STEP_SUMMARY'ye yazar.

Kullanım:
  python3 summary_pattern_drift.py [--summary-path PATH]

CI'da GITHUB_STEP_SUMMARY ortam değişkeni ayarlıysa otomatik kullanılır.
Sonuç: PASS (tüm artifact'lar kapsamda) veya DRIFT (eksik/fazla artifact).
"""
import os
import re
import sys

# ── Konum ──────────────────────────────────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
WORKFLOW = os.path.join(SCRIPT_DIR, "..", "..", ".github", "workflows", "verify.yml")

# ARTIFACT_JOBS'u gen_repro_manifest.py'den içe aktar
sys.path.insert(0, SCRIPT_DIR)
import gen_repro_manifest as gm

# EXCLUDED: prefix ile indirilenler + çıktı (merge pattern'e girmez)
EXCLUDED = {
    "precommit-logs", "refs-trend", "override-trend", "precheck-report",
    "python3-shell", "plist-check", "reproducibility",
}


def _read_pattern():
    """verify.yml'den merge pattern'i oku (brace format)."""
    with open(WORKFLOW, encoding="utf-8") as f:
        text = f.read()
    m = re.search(
        r"merge-multiple:\s*true\s*\n\s*pattern:\s*'\{([^}]+)\}'\s*\n",
        text,
    )
    if not m:
        return None
    return {s.strip() for s in m.group(1).split(",")}


def _summary_md(pattern, expected):
    """Markdown tablosu üret."""
    missing = expected - pattern
    extra = pattern - expected
    ok = not missing and not extra

    lines = []
    if ok:
        lines.append("### ✅ Reproducibility merge pattern — PASS")
    else:
        lines.append("### 🔴 Reproducibility merge pattern — DRIFT")
    lines.append("")
    lines.append("| Durum | Artifact |")
    lines.append("|-------|----------|")

    for name in sorted(expected):
        if name in pattern:
            lines.append(f"| ✅ | `{name}` |")
        else:
            lines.append(f"| 🔴 **EKSIK** | `{name}` |")

    for name in sorted(extra):
        lines.append(f"| ⚠️ **FAZLA** | `{name}` |")

    lines.append("")
    lines.append(f"**Pattern'de:** {len(pattern)} artifact · **Beklenen:** {len(expected)} artifact")
    if missing:
        lines.append(f"**Eksik:** {', '.join(sorted(missing))}")
    if extra:
        lines.append(f"**Fazla:** {', '.join(sorted(extra))}")

    return "\n".join(lines)


def main():
    summary_path = None
    for i, arg in enumerate(sys.argv[1:], 1):
        if arg == "--summary-path" and i < len(sys.argv) - 1:
            summary_path = sys.argv[i + 1]

    pattern = _read_pattern()
    if pattern is None:
        print("HATA: verify.yml'de merge pattern bulunamadı")
        return 1

    expected = set(gm.ARTIFACT_JOBS) - EXCLUDED
    md = _summary_md(pattern, expected)

    # Summary yaz
    dest = summary_path or os.environ.get("GITHUB_STEP_SUMMARY")
    if dest:
        with open(dest, "a", encoding="utf-8") as f:
            f.write("\n" + md + "\n")
        print(f"Summary yazıldı: {dest}")
    else:
        print(md)

    ok = pattern == expected
    print(f"Sonuç: {'PASS' if ok else 'DRIFT'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
