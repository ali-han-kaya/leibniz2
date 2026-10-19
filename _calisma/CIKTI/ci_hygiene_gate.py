#!/usr/bin/env python3
"""ci_hygiene_gate.py — CI hijyen kapısı (fail-closed).

Tüm .github/workflows/*.yml için üç kural:

  K1  permissions: top-level `permissions:` haritası mevcut — yoksa GitHub
      default broad-GITHUB_TOKEN sessizce devreye girer (hijyen ihlali).
  K2  timeout-minutes: her job'da mevcut, 1..120 aralığında int. bool
      reddedilir (bool, int alt-tipidir; `timeout-minutes: true` geçmez).
  K3  concurrency: top-level, non-empty `group` — aynı ref'te üst üste
      binen koşumlar engellenir (verify.yml referans-standart).
  K4  artifact retention-days: HER `actions/upload-artifact` adımı
      `with.retention-days` BİLDİRİR (GitHub'ın 90 günlük varsayılanı
      sessizce uygulanır — depo maliyeti ve Gizlilik/kvKK yüzeyi büyür),
      değer 1..90 aralığında int olur, ve SINIF kuralına uyar:
        * kanıt sınıfı (`EVIDENCE_ARTIFACTS`) → tam 90 gün
          (yeniden-üretilebilirlik ve koruma-durumu kanıtları teslim
          sonrası da erişilebilir kalmalı),
        * diğer (tanı/log/rapor) → ≤ 30 gün (varsayılan 90'a düşmesin).
      Adımlar PyYAML ağacından gezer; eksik/aralık-dışı/bool değer bulgu.

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

# ── K4: artifact retention politikası ─────────────────────────────────────
RETENTION_MIN, RETENTION_MAX = 1, 90
RETENTION_DIAG_MAX = 30
UPLOAD_ACTION = "actions/upload-artifact"
# Kanıt sınıfı: teslim/koruma kanıtı — 90 gün (tanı sınıfının üstünde).
EVIDENCE_ARTIFACTS = {
    "reproducibility": "K21 yeniden-üretilebilirlik kanıtı (delivery evidence)",
    "protection-drift": "dal koruma durumu kanıtı (audit evidence)",
}


def retention_findings(name: str, step: dict) -> list[str]:
    """Bir upload adımının retention-days sözleşmesini denetler."""
    with_ = step.get("with") if isinstance(step.get("with"), dict) else {}
    artifact = with_.get("name")
    artifact = artifact if isinstance(artifact, str) else "<adsız>"
    value = with_.get("retention-days")
    if value is None:
        return [f"{name}: upload '{artifact}': retention-days yok "
                f"(GitHub varsayılanı {RETENTION_MAX} gün sessizce uygulanır)"]
    if isinstance(value, bool) or not isinstance(value, int):
        return [f"{name}: upload '{artifact}': retention-days int olmalı "
                f"({value!r})"]
    if not RETENTION_MIN <= value <= RETENTION_MAX:
        return [f"{name}: upload '{artifact}': retention-days aralık dışı "
                f"({value}; {RETENTION_MIN}..{RETENTION_MAX})"]
    if artifact in EVIDENCE_ARTIFACTS:
        if value != RETENTION_MAX:
            return [f"{name}: upload '{artifact}': kanıt artefaktı "
                    f"{RETENTION_MAX} gün olmalı ({value}) — "
                    f"{EVIDENCE_ARTIFACTS[artifact]}"]
        return []
    if value > RETENTION_DIAG_MAX:
        return [f"{name}: upload '{artifact}': tanı sınıfı "
                f"≤{RETENTION_DIAG_MAX} gün olmalı ({value}) — kanıt "
                f"sınıfına alınacaksa EVIDENCE_ARTIFACTS'a gerekçesiyle ekle"]
    return []


def counts_for(workflows_dir: pathlib.Path) -> dict:
    """Kapsam sayacı: kaç workflow, kaç upload adımı görüldü (kör kapı yok)."""
    out = {"workflows": 0, "uploads": 0}
    for p in sorted(workflows_dir.glob("*.yml")):
        out["workflows"] += 1
        try:
            doc = yaml.safe_load(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        for job in ((doc or {}).get("jobs") or {}).values():
            for step in ((job or {}).get("steps") or []):
                if isinstance(step, dict) and isinstance(step.get("uses"), str) \
                        and step["uses"].startswith(UPLOAD_ACTION):
                    out["uploads"] += 1
    return out


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
            for step in job.get("steps") or []:
                if not isinstance(step, dict):
                    continue
                uses = step.get("uses")
                if isinstance(uses, str) and uses.startswith(UPLOAD_ACTION):
                    findings.extend(retention_findings(p.name, step))
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
    counts = counts_for(d)
    if findings:
        print(f"SONUÇ: FAIL ({len(findings)} ihlal)")
        for f in findings:
            print(f"  - {f}")
        return 1
    print(f"SONUÇ: PASS ({n} workflow · {counts['uploads']} upload adımı; "
          f"retention politikası: 1..{RETENTION_MAX} gün, kanıt sınıfı "
          f"{RETENTION_MAX}, diğer ≤{RETENTION_DIAG_MAX})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
