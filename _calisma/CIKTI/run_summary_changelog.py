#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""run_summary_changelog.py — gen_changelog --check drift bulgularını run summary'ye yaz.

CI'daki advisory `changelog-drift` job'ı `gen_changelog.py --check`'i koşar
(çıktı `.freebuff/changelog_drift.txt`, exit kodu `.freebuff/changelog_drift.rc`).
Bu script o iki dosyayı okuyup GITHUB_STEP_SUMMARY'ye "Changelog drift"
bölümünü ekler. GITHUB_STEP_SUMMARY env'i yoksa (yerel test) çıktı stdout'a
yazılır — run_summary_budget.py deseninin birebir aynısı.

Durumlar:
  SENKRON  — rc 0: tablolar git log ile eşleşiyor
  DRIFT    — rc 1: tablolar git log'dan ayrık (tasarlanmış 1-commit gecikmesi
             dahil — her push'ta görünür kalması istenen advisory bilgi)
  HATA     — rc 2 veya rc dosyası bozuk: gen_changelog geçersiz girdi
  MISSING  — txt/rc dosyası yok: check çalışmadı

Kullanım:
  python3 _calisma/CIKTI/run_summary_changelog.py [TXT] [RC]
"""
from __future__ import annotations

import contextlib
import os
import sys


@contextlib.contextmanager
def summary_sink():
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as f:
            yield f
    else:
        yield sys.stdout


def status(txt_path: str, rc_path: str) -> str:
    """'SENKRON' | 'DRIFT' | 'HATA' | 'MISSING' — tek satır durum."""
    if not os.path.isfile(txt_path) or not os.path.isfile(rc_path):
        return "MISSING"
    with open(rc_path, encoding="utf-8") as f:
        raw = f.read().strip()
    try:
        rc = int(raw or "0")
    except ValueError:
        return "HATA"
    if rc == 0:
        return "SENKRON"
    if rc == 1:
        return "DRIFT"
    return "HATA"


def render(sink, txt_path: str, rc_path: str) -> None:
    st = status(txt_path, rc_path)
    sink.write("## 🔄 Changelog drift (gen_changelog --check, advisory)\n\n")
    if st == "MISSING":
        sink.write("> `gen_changelog --check` çalışmadı "
                   f"(`{txt_path}` / `{rc_path}` yok).\n")
        return
    if st == "SENKRON":
        sink.write("✅ SENKRON — changelog tabloları (README/PUBLISH_SCENARIO) "
                   "git log ile eşleşiyor.\n")
        return
    if st == "HATA":
        sink.write("⚠️ HATA — `gen_changelog --check` exit 2 (geçersiz girdi, "
                   "git log boş vb.).\n\n")
    else:  # DRIFT
        sink.write("⚠️ DRIFT — changelog tabloları git log'dan ayrık "
                   "(tasarlanmış 1-commit gecikmesi dahil):\n\n")
    sink.write("```text\n")
    with open(txt_path, encoding="utf-8") as f:
        body = f.read()
    sink.write(body)
    if body and not body.endswith("\n"):
        sink.write("\n")
    sink.write("```\n")


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    txt_path = argv[0] if len(argv) > 0 else "changelog_drift.txt"
    rc_path = argv[1] if len(argv) > 1 else "changelog_drift.rc"
    with summary_sink() as s:
        render(s, txt_path, rc_path)
    print("Changelog drift summary written to run summary.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
