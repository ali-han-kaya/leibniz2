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

SUMMARY_PATH = os.environ.get("GITHUB_STEP_SUMMARY")

# Bu script'in run summary'de gösterdiği katmanlar (sıralı).
RENDER_LAYERS = ["K1", "K2", "K3", "K4", "K5", "K6", "K7", "K8", "K9", "K10"]


@contextlib.contextmanager
def summary_sink():
    if SUMMARY_PATH:
        with open(SUMMARY_PATH, "a", encoding="utf-8") as f:
            yield f
    else:
        yield sys.stdout


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    path = argv[0] if argv else "klayers.json"
    if not os.path.isfile(path):
        with summary_sink() as s:
            s.write("## ⚠️ K katmanları: sidecar bulunamadı\n\n"
                    "> `verify_delivery.py` `--klayers-out` üretmedi "
                    "(verify job'u çalışmadı?).\n")
        print("K layers summary written (missing sidecar).")
        return 0

    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    layers = data.get("layers", {})

    with summary_sink() as s:
        for key in RENDER_LAYERS:
            lyr = layers.get(key)
            if not lyr:
                s.write(f"## ⏭️ {key}: sidecar'da yok\n\n")
                continue
            label = lyr.get("label", "?")
            status = lyr.get("status", "SKIP")
            fl = lyr.get("findings", [])
            if status == "SKIP":
                s.write(f"## ⏭️ {key} {label}: bu job'da koşmadı (N/A)\n\n")
            elif status == "FAIL":
                s.write(f"## 🔴 {key} {label}: {len(fl)} bulgu\n\n")
                for f in fl:
                    ev = f" ({f.get('evidence')})" if f.get("evidence") else ""
                    s.write(f"- [{f.get('priority', '?')}] {f.get('check', '?')}: "
                            f"{f.get('issue', '?')}{ev}\n")
                s.write("\n")
            else:  # PASS
                s.write(f"## ✅ {key} {label}: PASS\n\n")
    print(f"K layers summary written ({len(RENDER_LAYERS)} layers).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
