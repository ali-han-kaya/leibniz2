#!/usr/bin/env python3
"""consolidate_summary.py — verify job run summary'sini TEK kaynaktan üret.

verify.yml'deki 5 ayrı "— run summary" adımının yerine tek giriş noktası:
önce tek satırlık bir durum panosu (5 ikon: pre-commit + K0 + bütçe + soy hattı + K katmanları ✅/🔴),
sonra pre-commit + K0 + bütçe + soy hattı + K katmanları bölümlerini AYNI
GITHUB_STEP_SUMMARY'ye sırayla yazar. Her bölümün render mantığı ve panoya
giren durum özeti ilgili run_summary_*.py modülündedir (tek kaynak — bu
script yalnızca sıralar ve tek bir sink açar).

Varsayılan sidecar yolları (verify job çalışma dizini = repo kökü):
  logs/PRECOMMIT_RAPORU.json, k0_findings.json, budget_verify.json,
  lineage_findings.json, klayers.json

Opsiyonel override (yerel test/alternatif dizinler için):
  consolidate_summary.py --budget budget/index.json --k0 /tmp/k0.json ...

GITHUB_STEP_SUMMARY env'i yoksa (yerel test) çıktı stdout'a yazılır.
"""
import contextlib
import os
import sys

import run_summary_budget as _budget
import run_summary_k0 as _k0
import run_summary_k13 as _k13
import run_summary_klayers as _klayers
import run_summary_lineage as _lineage
import run_summary_precommit as _precommit


# Bölüm → varsayılan sidecar yolu (verify job'uyla birebir).
DEFAULT_PATHS = {
    "precommit": "logs/PRECOMMIT_RAPORU.json",
    "k0": "k0_findings.json",
    "budget": "budget_verify.json",
    "lineage": "lineage_findings.json",
    "klayers": "klayers.json",
    "k13": "logs/k13_repro_manifest.json",
}

# Bölüm → (etiket, render fonksiyonu, durum-panosu fonksiyonu). Sıra, run
# summary'deki bölüm sırasıdır. Tüm bölümler durum panosuna girer.
SECTIONS = [
    ("precommit", "Pre-commit", _precommit.render, _precommit.status),
    ("k0", "K0", _k0.render, _k0.status),
    ("budget", "Bütçe", _budget.render, _budget.status),
    ("lineage", "Soy hattı", _lineage.render, _lineage.status),
    ("klayers", "K katmanları", _klayers.render, _klayers.status),
    ("k13", "K13 ayrı-step", _k13.render, _k13.status),
]

# Durum panosu tek satır ikonları (status() → ikon).
_STATUS_ICONS = {"PASS": "✅", "FAIL": "🔴", "MISSING": "⚠️"}


@contextlib.contextmanager
def summary_sink():
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as f:
            yield f
    else:
        yield sys.stdout


def render_dashboard(sink, paths):
    """En üstteki tek satırlık durum panosu (pre-commit + K0 + bütçe)."""
    parts = []
    for name, label, _render, status in SECTIONS:
        if status is None:
            continue
        st = status(paths[name])
        parts.append(f"{label} {_STATUS_ICONS.get(st, '❓')}")
    sink.write("## 📊 Durum panosu: " + " · ".join(parts) + "\n\n")


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    paths = dict(DEFAULT_PATHS)

    dashboard_only = "--dashboard-only" in argv
    skip_dashboard = "--skip-dashboard" in argv
    argv = [a for a in argv if a not in ("--dashboard-only", "--skip-dashboard")]

    # Opsiyonel --<section> <path> override'ları.
    i = 0
    while i < len(argv):
        key = argv[i][2:] if argv[i].startswith("--") else ""
        if key in paths and i + 1 < len(argv):
            paths[key] = argv[i + 1]
            i += 2
        else:
            i += 1

    with summary_sink() as s:
        if not skip_dashboard:
            render_dashboard(s, paths)
        if not dashboard_only:
            for name, _label, render, _status in SECTIONS:
                render(s, paths[name])
    mode = "dashboard-only" if dashboard_only else (
        "skip-dashboard" if skip_dashboard else "full")
    print(f"Consolidated summary written ({mode})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
