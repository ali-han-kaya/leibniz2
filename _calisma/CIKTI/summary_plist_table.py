#!/usr/bin/env python3
"""plist_report.json → GITHUB_STEP_SUMMARY markdown tablosu."""
import json, sys

path = sys.argv[1] if len(sys.argv) > 1 else "plist_report.json"
try:
    d = json.load(open(path))
except (FileNotFoundError, json.JSONDecodeError):
    print("_(plist_report.json yok — K12 çalışmadı)_")
    sys.exit(0)

ok = "✅" if d.get("ok") else "❌"
exit_code = d.get("exit", "?")
detail = d.get("detail", "-")
print(f"{ok} **K12** — exit {exit_code} — {detail}")
print()
print("| Profil | Durum | Yol |")
print("|---|---|---|")
for p in d.get("profiles", []):
    icon = "✅" if p.get("status") == "GÜNCEL" else "❌"
    label = p.get("label", "-")
    status = p.get("status", "-")
    path_val = p.get("path", "-")
    print(f"| {label} | {icon} {status} | `{path_val}` |")
