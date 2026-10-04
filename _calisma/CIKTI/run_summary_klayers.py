#!/usr/bin/env python3
"""run_summary_klayers.py — K1-K10 katman durumlarını run summary'ye yaz.

verify.yml'deki 'K layers — run summary' adımının standalone hali.
klayers.json (verify_delivery.py --klayers-out) sidecar'ından okur ve
GITHUB_STEP_SUMMARY'ye her K katmanı için ayrı bir bölüm yazar (K0 deseni).
status() dosya seviyesindeki durumu (MISSING / okunamaz → FAIL) burada
çözülür; katman verdict'i sözleşmenin sahibinden gelir.

Bu modül YALNIZCA yazar. Hangi katmanların var olduğunu, adlarını ve
run summary'de hangi sırayla gösterileceğini klayers_contract.py söyler;
status()/render() aynı gezinti yolunu (presentation_order) kullanır, böylece
"hangi katmanlar önemli" sorusunun tek cevabı kalır. K0 ayrı modülde
(run_summary_k0.py) ve kayıt dışı P0/P1'ler "Other" başlığı altında en üstte
görünür. GITHUB_STEP_SUMMARY env'i yoksa (yerel test) çıktı stdout'a yazılır.
"""
import contextlib
import json
import os
import sys

import klayers_contract as kc


@contextlib.contextmanager
def summary_sink():
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as f:
            yield f
    else:
        yield sys.stdout


def _load(path):
    """Katman sözlüğü; okunamazsa (bozuk JSON, eksik/boş "layers") None."""
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f).get("layers") or {}
    except (json.JSONDecodeError, OSError):
        return None


def status(path="klayers.json"):
    """'PASS' | 'FAIL' | 'MISSING' — durum panosu için tek satır özet."""
    if not os.path.isfile(path):
        return "MISSING"
    layers = _load(path)
    if layers is None:
        return "FAIL"
    # Verdict sözleşmenin sahibinde (klayers_contract.run_verdict).
    return kc.run_verdict(layers)


def render(sink, path="klayers.json"):
    """K1-K14 bölümlerini sink'e yaz (sidecar yoksa advisory not)."""
    if not os.path.isfile(path):
        sink.write("## ⚠️ K katmanları: sidecar bulunamadı\n\n"
                   "> `verify_delivery.py` `--klayers-out` üretmedi "
                   "(verify job'u çalışmadı?).\n")
        return

    layers = _load(path)
    if layers is None:
        sink.write("## ⚠️ K katmanları: sidecar okunamadı\n\n"
                   "> `klayers.json` bozuk JSON içeriyor.\n")
        return

    for key, lyr in kc.presentation_order(layers):
        if key == kc.OTHER_KEY:
            # Other kovası tanımı gereği daima FAIL'dir — yalnız bloklayan
            # öncelikler buraya düşer — bu yüzden PASS/SKIP dalları yok.
            # NOT: bulgu satırı `evidence` göstermez, katman bölümleri
            # gösterir (docs/KLAYERS_PIPELINE.md, "bilinen ayrışmalar").
            findings = lyr.get("findings", [])
            sink.write(f"## 🔴 Other {lyr.get('label', kc.OTHER_LABEL)}: "
                       f"{len(findings)} bulgu\n\n")
            for finding in findings:
                sink.write(f"- [{finding.get('priority', '?')}] "
                           f"{finding.get('check', '?')}: "
                           f"{finding.get('issue', '?')}\n")
            sink.write("\n")
            continue

        if not lyr:
            sink.write(f"## ⏭️ {key}: sidecar'da yok\n\n")
            continue

        label = lyr.get("label", "?")
        status = lyr.get("status", "SKIP")
        findings = lyr.get("findings", [])
        if status == "SKIP":
            sink.write(f"## ⏭️ {key} {label}: bu job'da koşmadı (N/A)\n\n")
        elif status == "FAIL":
            sink.write(f"## 🔴 {key} {label}: {len(findings)} bulgu\n\n")
            for f in findings:
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
    # Yazılan bölüm sayısını DÖNÜŞTE say: sidecar okunamıyorsa render()
    # yalnız uyarı yazar, "16 layers written" demek yanlış olurdu.
    layers = _load(path)
    written = len(kc.presentation_order(layers)) if layers is not None else 0
    if written:
        print(f"K layers summary written ({written} layers).")
    else:
        print("K layers summary: sidecar okunamadı — bölüm yazılmadı.")
    return 0


if __name__ == "__main__":
    sys.exit(main())