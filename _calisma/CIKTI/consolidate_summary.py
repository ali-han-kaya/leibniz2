#!/usr/bin/env python3
"""consolidate_summary.py — verify job run summary'sini TEK kaynaktan üret.

verify.yml'deki 5 ayrı "— run summary" adımının yerine tek giriş noktası:
pre-commit + K0 + bütçe + soy hattı + K katmanları bölümlerini AYNI
GITHUB_STEP_SUMMARY'ye sırayla yazar. Her bölümün render mantığı ilgili
run_summary_*.py modülündedir (tek kaynak — bu script yalnızca sıralar ve
tek bir sink açar).

Varsayılan sidecar yolları (verify job çalışma dizini = repo kökü):
  logs/PRECOMMIT_RAPORU.md, k0_findings.json, budget_verify.json,
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
import run_summary_klayers as _klayers
import run_summary_lineage as _lineage
import run_summary_precommit as _precommit

SUMMARY_PATH = os.environ.get("GITHUB_STEP_SUMMARY")

# Bölüm → varsayılan sidecar yolu (verify job'uyla birebir).
DEFAULT_PATHS = {
    "precommit": "logs/PRECOMMIT_RAPORU.md",
    "k0": "k0_findings.json",
    "budget": "budget_verify.json",
    "lineage": "lineage_findings.json",
    "klayers": "klayers.json",
}

# Bölüm → render fonksiyonu (sıra, run summary'deki bölüm sırasıdır).
SECTIONS = [
    ("precommit", _precommit.render),
    ("k0", _k0.render),
    ("budget", _budget.render),
    ("lineage", _lineage.render),
    ("klayers", _klayers.render),
]


@contextlib.contextmanager
def summary_sink():
    if SUMMARY_PATH:
        with open(SUMMARY_PATH, "a", encoding="utf-8") as f:
            yield f
    else:
        yield sys.stdout


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    paths = dict(DEFAULT_PATHS)

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
        for name, render in SECTIONS:
            render(s, paths[name])
    print("Consolidated summary written "
          "(pre-commit + K0 + bütçe + soy hattı + K katmanları).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
