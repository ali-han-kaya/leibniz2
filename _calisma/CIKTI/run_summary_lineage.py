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



@contextlib.contextmanager
def summary_sink():
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as f:
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


def status(path="lineage_findings.json"):
    """'PASS' | 'FAIL' | 'MISSING' — durum panosu için tek satır özet."""
    if not os.path.isfile(path):
        return "MISSING"
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return "FAIL"
    return "PASS" if data.get("ok") else "FAIL"


def render(sink, path="lineage_findings.json"):
    """Soy hattı bölümünü sink'e yaz (sidecar yoksa advisory not)."""
    if not os.path.isfile(path):
        sink.write("## ⚠️ Soy hattı: sidecar bulunamadı\n\n"
                   "> `verify_delivery.py` `--lineage-out` üretmedi "
                   "(`--check-lineage` koşmadı?).\n")
        return

    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    gens = data.get("generations", [])
    ok = bool(data.get("ok", False))

    if ok:
        sink.write(f"## ✅ Soy hattı (zip_lineage.json): {len(gens)} nesil doğrulandı\n\n")
    else:
        sink.write(f"## 🔴 Soy hattı (zip_lineage.json): doğrulama başarısız ({len(gens)} nesil)\n\n")
    sink.write("| NESİL | NOTE | HASH | DURUM |\n")
    sink.write("|---|---|---|---|\n")
    for g in gens:
        h = (g.get("hash") or "?")[:16]
        note = (g.get("note") or "?").replace("|", "\\|")
        status = g.get("status") or "?"
        sink.write(f"| {g.get('gen', '?')} | {note} | `{h}…` | "
                   f"{_icon(status)} {status} |\n")
    if ok:
        sink.write("\n> Fail-closed: tüm commit'li nesiller `git show` ile, "
                   "`current` nesil canlı dosya ile doğrulandı.\n")
    else:
        sink.write("\n> Fail-closed: P0/P1 bulgusu olarak işaretlendi; "
                   "kanonik hash/soy hattı sapması var.\n")


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    path = argv[0] if argv else "lineage_findings.json"
    with summary_sink() as s:
        render(s, path)
    print("Lineage summary written.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
