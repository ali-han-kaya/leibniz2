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


def main() -> None:
    path = "k0_findings.json"
    if not os.path.isfile(path):
        with summary_sink() as s:
            s.write("## 🔍 K0 bayat zip: sidecar bulunamadı\n\n"
                    "> `verify_delivery.py` `--k0-out` üretmedi "
                    "(verify job'u çalışmadı?).\n")
        return
    data = json.load(open(path))
    count = data.get("count", 0)
    findings = data.get("findings", [])
    with summary_sink() as s:
        if count:
            s.write(f"## 🔴 K0 bayat zip: {count} bulgu\n\n")
            for f in findings:
                s.write(f"- `{f['rel']}`  (`{f['sha256'][:16]}…`)\n")
            s.write("\n> Fail-closed: P1 bulgusu olarak işaretlendi. "
                    "Kanonik kopya yalnızca `_calisma/CIKTI/` altında "
                    "olmalıdır.\n")
        else:
            s.write("## ✅ K0 bayat zip: temiz (bulgu yok)\n\n"
                    "> CIKTI dışında zip bulunamadı.\n")
    print(f"K0 summary written ({count} findings).")


if __name__ == "__main__":
    main()
