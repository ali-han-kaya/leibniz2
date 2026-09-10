#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_config_drift_summary.py — config-drift artifact summary.txt sözleşmesi.

config_drift_comment.js ve tum_sapmalar_comment.js override bölümünü
config-drift/summary.txt 'cli_overrides=' satırından türetir (TEK KAYNAK).
summary.txt eksikse veya 'cli_overrides=' satırı yoksa her iki script
override bölümünü SESSİZCE atlar — tekrarlanabilirlik sapması PR yorumunda
görünmez kalır. Bu check, manifest-comment job'ının config-drift artifact'ını
indirdikten SONRA koşar: sözleşme bozuksa exit 1 (fail-closed) — yorum
override bölümü olmadan yayınlanmaz.

Sözleşme (Bundle config drift report adımının ürettiği):
  - config-drift/summary.txt MEVCUT olmalı
  - 'cli_overrides=' satırı içermeli
  - değer WARNING|OK|N/A ile başlamalı (battery/config_drift fixture'larıyla
    uyumlu: "WARNING 1 (override_count=1)" / "OK 0 (override_count=0)" /
    "N/A (denetim yok)")

Kullanım:
  python3 check_config_drift_summary.py [--dir config-drift]

Exit: 0 = PASS (sözleşme tam); 1 = FAIL (eksik/bozuk); 2 = kullanım hatası.
"""

import argparse
import os
import re
import sys

SUMMARY_NAME = "summary.txt"
OVERRIDE_LINE_RE = re.compile(r"^cli_overrides=(WARNING|OK|N/A)\b", re.M)


def check_summary(summary_dir):
    """summary.txt sözleşmesini denetle. (ok, findings, detail) döner."""
    findings = []
    summary_path = os.path.join(summary_dir, SUMMARY_NAME)

    if not os.path.isfile(summary_path):
        return False, [
            f"{summary_path} YOK — config-drift Bundle adımı summary.txt "
            "üretmedi; override bölümü sessiz atlanır (fail-closed)"
        ], "summary.txt eksik"

    try:
        with open(summary_path, encoding="utf-8") as f:
            text = f.read()
    except OSError as e:
        return False, [f"{summary_path} okunamadı: {e}"], "summary.txt okunamadı"

    if not OVERRIDE_LINE_RE.search(text):
        return False, [
            f"{summary_path} 'cli_overrides=' satırı içermiyor — script "
            "override bölümünü sessiz atlar (fail-closed)"
        ], "'cli_overrides=' satırı yok"

    m = OVERRIDE_LINE_RE.search(text)
    detail = f"cli_overrides={m.group(1)} bulundu"
    return True, [], detail


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dir", default="config-drift",
                    help="config-drift artifact dizini (varsayılan: config-drift)")
    args = ap.parse_args(argv)

    ok, findings, detail = check_summary(args.dir)
    if ok:
        print(f"SONUÇ: PASS — {detail} ({args.dir}/{SUMMARY_NAME})")
        return 0
    for f in findings:
        print(f"FAIL: {f}", file=sys.stderr)
    print(f"SONUÇ: FAIL — {detail} — {len(findings)} bulgu "
          f"({args.dir}/{SUMMARY_NAME})", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
