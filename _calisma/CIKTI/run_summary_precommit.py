#!/usr/bin/env python3
"""run_summary_precommit.py — pre-commit bulgularını GITHUB_STEP_SUMMARY'ye yaz.

verify.yml'deki 'Pre-commit findings — run summary' adımının inline Python
mantığının standalone hali. logs/PRECOMMIT_RAPORU.md'deki P0/P1 bulgularını
+ hook durumlarını ayrıştırıp run summary'ye ayrı bir bölüm yazar.

GITHUB_STEP_SUMMARY env'i yoksa (yerel test) çıktı stdout'a yazılır.
"""
import contextlib
import os
import pathlib
import re
import sys

SUMMARY_PATH = os.environ.get("GITHUB_STEP_SUMMARY")


@contextlib.contextmanager
def summary_sink():
    if SUMMARY_PATH:
        with open(SUMMARY_PATH, "a", encoding="utf-8") as f:
            yield f
    else:
        yield sys.stdout


def _load(path="logs/PRECOMMIT_RAPORU.md"):
    """(findings, hooks, verdict) — rapor yoksa None (tek kaynak ayrıştırma)."""
    report = pathlib.Path(path)
    if not report.exists():
        return None
    text = report.read_text(encoding="utf-8")
    findings = re.findall(r"^\| (P0|P1) \| (.+) \|$", text, re.M)
    hooks = re.findall(r"^\| ([^|]+?) \| (Passed|Failed) \|$", text, re.M)
    m = re.search(r"^- \*\*Sonuç:\*\* (.+)$", text, re.M)
    verdict = m.group(1).strip() if m else "bilinmiyor"
    return findings, hooks, verdict


def status(path="logs/PRECOMMIT_RAPORU.md"):
    """'PASS' | 'FAIL' | 'MISSING' — durum panosu için tek satır özet."""
    loaded = _load(path)
    if loaded is None:
        return "MISSING"
    findings, _, _ = loaded
    return "FAIL" if findings else "PASS"


def render(sink, path="logs/PRECOMMIT_RAPORU.md"):
    """Pre-commit bölümünü sink'e yaz (rapor yoksa advisory not)."""
    loaded = _load(path)
    if loaded is None:
        sink.write("## 🔍 Pre-commit: rapor bulunamadı\n\n"
                   "> `logs/PRECOMMIT_RAPORU.md` üretilmedi "
                   "(pre-commit kurulumu başarısız?).\n")
        return

    findings, hooks, verdict = loaded

    if findings:
        sink.write(f"## 🔴 Pre-commit bulguları: {len(findings)} bulgu\n\n")
        for pri, msg in findings:
            sink.write(f"- **{pri}**: {msg}\n")
        sink.write("\n> Advisory — build'i bloke etmez; denetim içindir. "
                   "Detay: `precommit-logs` artifact'ındaki PRECOMMIT_RAPORU.md.\n")
    else:
        sink.write("## ✅ Pre-commit: bulgu yok (tüm hook'lar geçti)\n\n")
    sink.write(f"> Sonuç: {verdict}\n")
    if hooks:
        parts = " | ".join(
            f"`{h}` " + (":white_check_mark:" if st == "Passed" else ":x:")
            for h, st in hooks
        )
        sink.write(f"> Hook'lar: {parts}\n")


def main() -> None:
    with summary_sink() as s:
        render(s)
    print("Pre-commit summary written.")


if __name__ == "__main__":
    main()
