#!/usr/bin/env python3
"""run_summary_k0.py — K0 bayat zip bulgularını GITHUB_STEP_SUMMARY'ye yaz.

verify.yml'deki 'K0 findings — run summary' adımının inline Python mantığının
standalone hali. k0_findings.json (verify_delivery.py --k0-out) sidecar'ından
okur ve run summary'ye ayrı bir bölüm yazar.

GITHUB_STEP_SUMMARY env'i yoksa (yerel test) çıktı stdout'a yazılır.
"""
import contextlib
import json
import os
import sys

SUMMARY_PATH = os.environ.get("GITHUB_STEP_SUMMARY")


@contextlib.contextmanager
def summary_sink():
    if SUMMARY_PATH:
        with open(SUMMARY_PATH, "a", encoding="utf-8") as f:
            yield f
    else:
        yield sys.stdout


def _load(path="k0_findings.json"):
    """K0 sidecar'ı — yoksa None (tek kaynak okuma)."""
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def status(path="k0_findings.json"):
    """'PASS' | 'FAIL' | 'MISSING' — durum panosu için tek satır özet."""
    data = _load(path)
    if data is None:
        return "MISSING"
    return "FAIL" if data.get("count", 0) else "PASS"


def render(sink, path="k0_findings.json"):
    """K0 bölümünü sink'e yaz (sidecar yoksa advisory not). Döndürür bulgu sayısı."""
    data = _load(path)
    if data is None:
        sink.write("## 🔍 K0 bayat zip: sidecar bulunamadı\n\n"
                   "> `verify_delivery.py` `--k0-out` üretmedi "
                   "(verify job'u çalışmadı?).\n")
        return 0
    count = data.get("count", 0)
    findings = data.get("findings", [])
    if count:
        sink.write(f"## 🔴 K0 bayat zip: {count} bulgu\n\n")
        for f in findings:
            sink.write(f"- `{f['rel']}`  (`{f['sha256'][:16]}…`)\n")
        sink.write("\n> Fail-closed: P1 bulgusu olarak işaretlendi. "
                   "Kanonik kopya yalnızca `_calisma/CIKTI/` altında "
                   "olmalıdır.\n")
    else:
        sink.write("## ✅ K0 bayat zip: temiz (bulgu yok)\n\n"
                   "> CIKTI dışında zip bulunamadı.\n")
    return count


def main() -> None:
    with summary_sink() as s:
        count = render(s)
    print(f"K0 summary written ({count} findings).")


if __name__ == "__main__":
    main()
