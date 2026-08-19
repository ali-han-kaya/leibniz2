#!/usr/bin/env python3
"""run_summary_lineage.py — soy hattı (--check-lineage) sonucunu run summary'ye yaz.

verify.yml'deki 'Lineage — run summary' adımının standalone hali.
lineage_findings.json (verify_delivery.py --lineage-out) sidecar'ından okur
ve GITHUB_STEP_SUMMARY'ye ayrı bir bölüm yazar (k0_findings.json deseni).

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


def _icon(status):
    s = (status or "").upper()
    if "FAIL" in s:
        return "🔴"
    if "PASS" in s:
        return "✅"
    return "ℹ️"  # INFO / UNVERIFIED


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    path = argv[0] if argv else "lineage_findings.json"
    if not os.path.isfile(path):
        with summary_sink() as s:
            s.write("## ⚠️ Soy hattı: sidecar bulunamadı\n\n"
                    "> `verify_delivery.py` `--lineage-out` üretmedi "
                    "(`--check-lineage` koşmadı?).\n")
        print("Lineage summary written (missing sidecar).")
        return 0

    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    gens = data.get("generations", [])
    ok = bool(data.get("ok", False))

    with summary_sink() as s:
        if ok:
            s.write(f"## ✅ Soy hattı (zip_lineage.json): {len(gens)} nesil doğrulandı\n\n")
        else:
            s.write(f"## 🔴 Soy hattı (zip_lineage.json): doğrulama başarısız ({len(gens)} nesil)\n\n")
        s.write("| NESİL | NOTE | HASH | DURUM |\n")
        s.write("|---|---|---|---|\n")
        for g in gens:
            h = (g.get("hash") or "?")[:16]
            note = (g.get("note") or "?").replace("|", "\\|")
            status = g.get("status") or "?"
            s.write(f"| {g.get('gen', '?')} | {note} | `{h}…` | "
                    f"{_icon(status)} {status} |\n")
        if ok:
            s.write("\n> Fail-closed: tüm commit'li nesiller `git show` ile, "
                    "`current` nesil canlı dosya ile doğrulandı.\n")
        else:
            s.write("\n> Fail-closed: P0/P1 bulgusu olarak işaretlendi; "
                    "kanonik hash/soy hattı sapması var.\n")
    print(f"Lineage summary written ({len(gens)} generations, ok={ok}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
