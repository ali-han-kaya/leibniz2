#!/usr/bin/env python3
"""run_summary_k13.py — K13 ayrı-step sonucunu GITHUB_STEP_SUMMARY'ye yaz.

verify.yml'deki 'Run verify-delivery-repro-manifest (K13, separate)' adımının
ürettiği logs/k13_repro_manifest.json sidecar'ından okur (advisory job —
continue-on-error; sonuç yine de denetim izine girer). Sidecar şeması:
  {layer: "K13", ok: bool, exit: int, detail: str,
   scenarios: [{name, status}]}   # K13 negatif senaryo sonuçları

status(): durum panosu için 'PASS' | 'FAIL' | 'MISSING'.
render(): durum panosu sonrası ayrı bölüm — ok + exit + scenarios tablosu
(negatif senaryo kapsamı görünür). Sidecar yoksa advisory not (MISSING).

GITHUB_STEP_SUMMARY env'i yoksa (yerel test) çıktı stdout'a yazılır.
"""
import contextlib
import json
import os
import pathlib
import sys


def _load(path="logs/k13_repro_manifest.json"):
    """JSON sidecar'dan yükle — tek kaynak. Yoksa/bozuksa None."""
    jp = pathlib.Path(path)
    if not jp.exists():
        return None
    try:
        with open(jp, encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return None
        return data
    except (json.JSONDecodeError, OSError):
        return None


def status(path="logs/k13_repro_manifest.json"):
    """'PASS' | 'FAIL' | 'MISSING' — durum panosu için tek satır özet."""
    data = _load(path)
    if data is None:
        return "MISSING"
    return "PASS" if data.get("ok") else "FAIL"


def render(sink, path="logs/k13_repro_manifest.json"):
    """K13 bölümünü sink'e yaz (sidecar yoksa advisory not)."""
    data = _load(path)
    if data is None:
        sink.write("## ⚠️ K13 repro-manifest: sidecar bulunamadı\n\n"
                   "> `logs/k13_repro_manifest.json` üretilmedi "
                   "(ayrı-step çalışmadı?).\n")
        return

    ok = bool(data.get("ok"))
    exit_code = data.get("exit")
    detail = data.get("detail") or ""
    scenarios = data.get("scenarios") or []

    if ok:
        sink.write("## ✅ K13 repro-manifest: PASS\n\n")
    else:
        sink.write("## 🔴 K13 repro-manifest: FAIL\n\n")
    parts = [f"exit={exit_code}"]
    if detail:
        # "[K13] repro manifest: ..." önekini kırp (önemsiz).
        d = detail
        for prefix in ("[K13] repro manifest: ", "[K13-SCENARIO] "):
            if d.startswith(prefix):
                d = d[len(prefix):]
        parts.append(d[:200])
    sink.write(f"> {(' · '.join(parts))}\n")
    if scenarios:
        rows = " | ".join(f"`{s.get('name')}` "
                          + (":white_check_mark:" if s.get("status") == "PASS"
                             else ":x:")
                          for s in scenarios)
        sink.write(f"> Negatif senaryolar: {rows}\n")
    sink.write("\n")


def main() -> None:
    with summary_sink() as s:
        render(s)
    print("K13 summary written.")


@contextlib.contextmanager
def summary_sink():
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as f:
            yield f
    else:
        yield sys.stdout


if __name__ == "__main__":
    main()
