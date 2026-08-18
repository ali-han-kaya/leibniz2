#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
status_checks.py — branch protection status check adlarını TEK KAYNAKTAN
(workflow job `name:` alanları) türetir ve isteğe bağlı GitHub ile doğrular.

Neden: PUBLISH_SCENARIO AŞAMA 1'deki required check listesi elle yazılırsa
workflow değişince sürüklenir. Bu script her zaman workflow'un güncel job
adlarını üretir; --gh ile GitHub branch protection'daki gerçek listeyle
karşılaştırır (eksik/fazla check = drift).

Kullanım:
  python3 _calisma/CIKTI/status_checks.py                  # beklenen adlar
  python3 _calisma/CIKTI/status_checks.py --gh             # GitHub ile doğrula
  python3 _calisma/CIKTI/status_checks.py --gh --repo owner/name
  python3 _calisma/CIKTI/status_checks.py --json           # makine-okur çıktı

Çıkış kodları:
  0 — liste üretildi; veya --gh'de birebir eşleşme; veya koruma kurulu değil
      (publish öncesi normal — UYARI basılır, bloke etmez).
  1 — --gh'de eksik/fazla check (fail-closed: drift var).
  2 — çalışma hatası (PyYAML yok, repo belirlenemedi).

Not: CI'da değil yerel/publish aracıdır — branch protection okumak admin
izni gerektirir, GITHUB_TOKEN'da yoktur.
"""
import argparse
import json
import subprocess
import sys

try:
    import yaml
except ImportError:  # pragma: no cover
    sys.stderr.write(
        "HATA: PyYAML gerekli — pip install pyyaml "
        "(veya _calisma/.venv_z3/bin/python kullan)\n"
    )
    sys.exit(2)

WORKFLOW = ".github/workflows/verify.yml"
# Required check OLMAYAN job'lar: PR-only/advisory (yanlış kapı olmasın).
GATE_EXCLUDE = {"manifest-comment"}


def gate_jobs():
    """workflow'daki job id → name eşlemesi (required check adayları)."""
    with open(WORKFLOW, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    jobs = data["jobs"]
    return {jid: j["name"] for jid, j in jobs.items() if jid not in GATE_EXCLUDE}


def run_gh(args):
    r = subprocess.run(args, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout).strip())
    return r.stdout.strip()


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--gh", action="store_true",
                    help="GitHub branch protection ile doğrula (eksik/fazla = FAIL)")
    ap.add_argument("--repo", default=None, help="owner/name (varsayılan: gh repo view)")
    ap.add_argument("--json", action="store_true", help="makine-okur JSON çıktısı")
    args = ap.parse_args()

    gates = gate_jobs()
    expected = list(gates.values())
    payload = {
        "workflow": WORKFLOW,
        "gate_jobs": list(gates.keys()),
        "excluded": sorted(GATE_EXCLUDE),
        "checks": expected,
    }

    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return

    print(f"Beklenen status check adları ({len(expected)}) — kaynak: {WORKFLOW}")
    print(f"  (required aday job'lar: {', '.join(gates)}; "
          f"hariç: {', '.join(sorted(GATE_EXCLUDE))})")
    for i, n in enumerate(expected, 1):
        print(f"  {i:2d}. {n}")

    if not args.gh:
        print("\nGitHub ile doğrulamak için: --gh (branch protection kuruluysa)")
        return

    # ── GitHub karşılaştırması ────────────────────────────────────────────
    repo = args.repo
    if not repo:
        try:
            repo = run_gh(["gh", "repo", "view", "--json", "nameWithOwner",
                           "-q", ".nameWithOwner"])
        except RuntimeError as e:
            print(f"HATA: repo belirlenemedi ({e}) — --repo owner/name verin",
                  file=sys.stderr)
            sys.exit(2)

    print(f"\nGitHub karşılaştırması: {repo} (branch: main)")
    try:
        raw = run_gh(["gh", "api", f"repos/{repo}/branches/main/protection",
                      "--jq", ".required_status_checks.contexts"])
    except RuntimeError as e:
        print(f"UYARI: branch protection kurulu değil/erişilemedi — {e}")
        print("  (publish öncesi normaldir; AŞAMA 1 (b) web UI'dan kurulur — "
              "yukarıdaki listeyi yapıştır)")
        return

    try:
        configured = json.loads(raw)
        if not isinstance(configured, list):
            configured = []
    except json.JSONDecodeError:
        print("UYARI: gh api çıktısı ayrıştırılamadı — koruma yapısı farklı",
              file=sys.stderr)
        configured = []

    exp, conf = set(expected), set(configured)
    missing, extra = sorted(exp - conf), sorted(conf - exp)

    for c in sorted(conf):
        print(f"  [{'PASS' if c in exp else 'FAZLA'}] {c}")
    for c in missing:
        print(f"  [FAIL] workflow'da var ama GitHub'da yok: {c}")

    if not missing and not extra:
        print(f"\nSONUÇ: PASS — {len(conf)} check birebir eşleşiyor "
              "(workflow ↔ GitHub)")
    else:
        print(f"\nSONUÇ: FAIL — eksik: {missing}, fazla: {extra}")
        print("  Düzeltme: AŞAMA 1 (b) web UI'da required check listesini "
              "yukarıdaki adlarla eşitle (veya workflow'u güncelle)")
        sys.exit(1)


if __name__ == "__main__":
    main()
