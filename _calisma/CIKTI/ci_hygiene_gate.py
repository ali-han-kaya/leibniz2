#!/usr/bin/env python3
"""ci_hygiene_gate.py — CI hijyen kapısı (fail-closed).

Tüm .github/workflows/*.yml için üç kural:

  K1  permissions: top-level `permissions:` haritası mevcut — yoksa GitHub
      default broad-GITHUB_TOKEN sessizce devreye girer (hijyen ihlali).
  K2  timeout-minutes: her job'da mevcut, 1..120 aralığında int. bool
      reddedilir (bool, int alt-tipidir; `timeout-minutes: true` geçmez).
  K3  concurrency: top-level, non-empty `group` — aynı ref'te üst üste
      binen koşumlar engellenir (verify.yml referans-standart).

Çıkış sözleşmesi: 0=PASS, 1=FAIL (≥1 ihlal), 2=kullanım/ortam hatası.
PyYAML yoksa 2 — dürüst ortam-hatası, sessiz-PASS yok.
"""
from __future__ import annotations

import argparse
import pathlib
import sys

try:
    import yaml
except ImportError:  # ortam-hatası: fail-closed (rc=2), sessiz-PASS yok
    print("ci_hygiene_gate: PyYAML yok — ortam hatası (rc=2)", file=sys.stderr)
    sys.exit(2)

TIMEOUT_MIN, TIMEOUT_MAX = 1, 120


def findings_for(workflows_dir: pathlib.Path) -> list[str]:
    findings: list[str] = []
    paths = sorted(workflows_dir.glob("*.yml"))
    if not paths:
        return [f"workflow yok: {workflows_dir}"]

    for p in paths:
        try:
            doc = yaml.safe_load(p.read_text(encoding="utf-8"))
        except Exception as exc:
            findings.append(f"{p.name}: YAML parse hatası: {exc}")
            continue
        if not isinstance(doc, dict):
            findings.append(f"{p.name}: belge eşlenik değil")
            continue

        if "permissions" not in doc or doc["permissions"] is None:
            findings.append(f"{p.name}: top-level permissions yok")
        conc = doc.get("concurrency")
        if not isinstance(conc, dict) or not str(conc.get("group") or "").strip():
            findings.append(f"{p.name}: concurrency.group yok/boş")

        jobs = doc.get("jobs")
        if not isinstance(jobs, dict) or not jobs:
            findings.append(f"{p.name}: jobs yok/boş")
            continue
        for jid, job in jobs.items():
            if not isinstance(job, dict):
                findings.append(f"{p.name}: job {jid}: eşlenik değil")
                continue
            to = job.get("timeout-minutes")
            if isinstance(to, bool) or not isinstance(to, int) or not (
                    TIMEOUT_MIN <= to <= TIMEOUT_MAX):
                findings.append(
                    f"{p.name}: job {jid}: timeout-minutes yok/geçersiz "
                    f"({to!r}; {TIMEOUT_MIN}..{TIMEOUT_MAX} int olmalı)")
    return findings


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="CI hijyen kapısı (fail-closed)")
    ap.add_argument("--workflow", default=".github/workflows",
                    help="workflow dizini (default: .github/workflows)")
    args = ap.parse_args(argv)

    d = pathlib.Path(args.workflow)
    if not d.is_dir():
        print(f"ci_hygiene_gate: workflow dizini yok: {d}", file=sys.stderr)
        return 2

    findings = findings_for(d)
    n = len(sorted(d.glob("*.yml")))
    if findings:
        print(f"SONUÇ: FAIL ({len(findings)} ihlal)")
        for f in findings:
            print(f"  - {f}")
        return 1
    print(f"SONUÇ: PASS ({n} workflow)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
