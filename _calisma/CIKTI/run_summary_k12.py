#!/usr/bin/env python3
"""Render K12 plist sidecar results for the consolidated run summary."""
import json
import pathlib


def _load(path="logs/k12_repro_manifest.json"):
    try:
        data = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def status(path="logs/k12_repro_manifest.json"):
    data = _load(path)
    if data is None:
        return "MISSING"
    return "PASS" if data.get("ok") else "FAIL"


def render(sink, path="logs/k12_repro_manifest.json"):
    data = _load(path)
    if data is None:
        sink.write("## ⚠️ K12 plist: sidecar bulunamadı\n\n")
        return
    ok = bool(data.get("ok"))
    icon = "✅" if ok else "🔴"
    sink.write(f"## {icon} K12 plist: {'PASS' if ok else 'FAIL'}\n\n")
    sink.write(f"> exit={data.get('exit')}\n\n")
    scenarios = data.get("scenarios") or {}
    if isinstance(scenarios, dict):
        sink.write("| Negatif senaryo | Sonuç |\n|---|---|\n")
        for name, result in scenarios.items():
            mark = "✅ PASS" if result == "PASS" else "🔴 " + str(result)
            sink.write(f"| `{name}` | {mark} |\n")
        sink.write("\n")


if __name__ == "__main__":
    import os
    import sys
    with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") if os.environ.get("GITHUB_STEP_SUMMARY") else sys.stdout as sink:
        render(sink)
