#!/usr/bin/env python3
"""run_summary_klayers.py — K1-K10 katman durumlarını run summary'ye yaz.

verify.yml'deki 'K layers — run summary' adımının standalone hali.
klayers.json (verify_delivery.py --klayers-out) sidecar'ından okur ve
GITHUB_STEP_SUMMARY'ye her K katmanı için ayrı bir bölüm yazar (K0 deseni).

Kapsam: K1-K10 (K0 ayrı run_summary_k0.py'de; K11-K14 istenirse aynı
sidecar'dan RENDER_LAYERS'a eklenir). GITHUB_STEP_SUMMARY env'i yoksa
(yerel test) çıktı stdout'a yazılır.
"""
import contextlib
import json
import os
import sys


# Bu script'in run summary'de gösterdiği katmanlar (sıralı).
RENDER_LAYERS = ["K1", "K2", "K3", "K4", "K5", "K6", "K7", "K8", "K9", "K10", "K11", "K12", "K13", "K14", "K16", "K17"]


@contextlib.contextmanager
def summary_sink():
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as f:
            yield f
    else:
        yield sys.stdout


def status(path="klayers.json"):
    """'PASS' | 'FAIL' | 'MISSING' — durum panosu için tek satır özet."""
    if not os.path.isfile(path):
        return "MISSING"
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return "FAIL"
    layers = data.get("layers", {})
    for key in RENDER_LAYERS:
        lyr = layers.get(key)
        if lyr and lyr.get("status") == "FAIL":
            return "FAIL"
    return "PASS"


def render(sink, path="klayers.json"):
    """K1-K10 bölümlerini sink'e yaz (sidecar yoksa advisory not)."""
    if not os.path.isfile(path):
        sink.write("## ⚠️ K katmanları: sidecar bulunamadı\n\n"
                   "> `verify_delivery.py` `--klayers-out` üretmedi "
                   "(verify job'u çalışmadı?).\n")
        return

    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    layers = data.get("layers", {})

    for key in RENDER_LAYERS:
        lyr = layers.get(key)
        if not lyr:
            sink.write(f"## ⏭️ {key}: sidecar'da yok\n\n")
            continue
        label = lyr.get("label", "?")
        status = lyr.get("status", "SKIP")
        fl = lyr.get("findings", [])
        if status == "SKIP":
            sink.write(f"## ⏭️ {key} {label}: bu job'da koşmadı (N/A)\n\n")
        elif status == "FAIL":
            sink.write(f"## 🔴 {key} {label}: {len(fl)} bulgu\n\n")
            for f in fl:
                ev = f" ({f.get('evidence')})" if f.get("evidence") else ""
                sink.write(f"- [{f.get('priority', '?')}] {f.get('check', '?')}: "
                           f"{f.get('issue', '?')}{ev}\n")
            sink.write("\n")
        else:  # PASS
            sink.write(f"## ✅ {key} {label}: PASS\n\n")


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    path = argv[0] if argv else "klayers.json"
    with summary_sink() as s:
        render(s, path)
    print(f"K layers summary written ({len(RENDER_LAYERS)} layers).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
