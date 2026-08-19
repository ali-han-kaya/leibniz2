#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
status_checks.py — branch protection status check adlarını TEK KAYNAKTAN
(workflow job `name:` alanları) türetir ve isteğe bağlı GitHub ile doğrular.

Neden: PUBLISH_SCENARIO AŞAMA 1'deki required check listesi elle yazılırsa
workflow değişince sürüklenir. Bu script her zaman workflow'un güncel job
adlarını üretir; --gh ile GitHub branch protection'daki gerçek listeyle
karşılaştırır (eksik/fazla check = drift). Koruma kuruluyken --gh ayrıca
PR-merge engeli smoke koşar: required_status_checks.strict, enforce_admins,
allow_force_pushes/allow_deletions — bunlar eksikse merge gerçekten BLOKE
edilmez (fail-closed; doğru check adlarına rağmen kapı açık kalabilir).

Kullanım:
  python3 _calisma/CIKTI/status_checks.py                  # beklenen adlar
  python3 _calisma/CIKTI/status_checks.py --gh             # GitHub ile doğrula
  python3 _calisma/CIKTI/status_checks.py --gh --repo owner/name
  python3 _calisma/CIKTI/status_checks.py --json           # makine-okur çıktı
  python3 _calisma/CIKTI/status_checks.py --gh --json      # doğrulama (names+smoke) JSON

Çıkış kodları:
  0 — liste üretildi; veya --gh'de birebir eşleşme; veya koruma kurulu değil
      (publish öncesi normal — UYARI basılır, bloke etmez).
  1 — --gh'de eksik/fazla check VEYA merge engeli smoke FAIL (fail-closed).
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
GATE_EXCLUDE = {"manifest-comment", "precheck"}  # precheck: AŞAMA 0 advisory


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


def merge_block_smoke(protection):
    """Koruma nesnesinden PR-merge engeli enforcement alanlarını denetle.

    `required_status_checks.contexts` birebir doğru olsa bile aşağıdakiler
    kapalıysa merge butonu gerçekten BLOKE ETMEZ. Her alan için
    (label, ok, failure_note) döner; ok=False → o koruma eksik (fail-closed).
    """
    sc = protection.get("required_status_checks") or {}
    admins = protection.get("enforce_admins") or {}
    fp = protection.get("allow_force_pushes") or {}
    dele = protection.get("allow_deletions") or {}
    return [
        ("required_status_checks.strict (up-to-date zorunlu)",
         sc.get("strict") is True,
         "strict kapalı — main'in gerisindeki PR'lar bloke edilmez"),
        ("enforce_admins.enabled (admin bypass kapalı)",
         admins.get("enabled") is True,
         "admin bypass açık — koruma bypass edilebilir"),
        ("allow_force_pushes.enabled == false",
         fp.get("enabled") is False,
         "force push açık/doğrulanamadı — geçmiş değiştirilebilir"),
        ("allow_deletions.enabled == false",
         dele.get("enabled") is False,
         "deletion açık/doğrulanamadı — branch silinebilir"),
    ]


def evaluate_protection(expected, protection):
    """expected (check adları) ile tam koruma nesnesini karşılaştır.

    Döndürür: {names_ok, missing, extra, configured, smoke, enforcement_ok}.
    names_ok (check adı eşleşmesi) ve enforcement_ok (merge engeli smoke)
    AYRI bayraklar — her ikisi de geçmeli (fail-closed).
    """
    sc = protection.get("required_status_checks") or {}
    configured = sc.get("contexts") or []
    if not isinstance(configured, list):
        configured = []
    exp, conf = set(expected), set(configured)
    missing = sorted(exp - conf)
    extra = sorted(conf - exp)
    smoke = merge_block_smoke(protection)
    enforcement_ok = all(ok for (_label, ok, _note) in smoke)
    return {
        "names_ok": not missing and not extra,
        "missing": missing,
        "extra": extra,
        "configured": sorted(conf),
        "smoke": smoke,
        "enforcement_ok": enforcement_ok,
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--gh", action="store_true",
                    help="GitHub branch protection ile doğrula (eksik/fazla = FAIL)")
    ap.add_argument("--repo", default=None, help="owner/name (varsayılan: gh repo view)")
    ap.add_argument("--json", action="store_true", help="makine-okur JSON çıktısı")
    args = ap.parse_args(argv)

    gates = gate_jobs()
    expected = list(gates.values())
    payload = {
        "workflow": WORKFLOW,
        "gate_jobs": list(gates.keys()),
        "excluded": sorted(GATE_EXCLUDE),
        "checks": expected,
    }

    if args.json and not args.gh:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return

    if not args.json:
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
            if args.json:
                print(json.dumps({"error": f"repo belirlenemedi: {e}",
                                  "verdict": "ERROR"},
                                 indent=2, ensure_ascii=False))
            else:
                print(f"HATA: repo belirlenemedi ({e}) — --repo owner/name verin",
                      file=sys.stderr)
            sys.exit(2)

    gh_result = {
        "workflow": WORKFLOW,
        "repo": repo,
        "branch": "main",
        "checks": expected,
        "names_ok": None,
        "missing": [],
        "extra": [],
        "configured": [],
        "enforcement_ok": None,
        "smoke": [],
        "verdict": "ERROR",
        "warning": None,
    }

    if not args.json:
        print(f"\nGitHub karşılaştırması: {repo} (branch: main)")

    try:
        raw = run_gh(["gh", "api", f"repos/{repo}/branches/main/protection"])
    except RuntimeError as e:
        gh_result["warning"] = str(e)
        gh_result["verdict"] = "NOT_SET_UP"
        if args.json:
            print(json.dumps(gh_result, indent=2, ensure_ascii=False))
        else:
            print(f"UYARI: branch protection kurulu değil/erişilemedi — {e}")
            print("  (publish öncesi normaldir; AŞAMA 1 (b) web UI'dan kurulur — "
                  "yukarıdaki listeyi yapıştır)")
        return

    try:
        protection = json.loads(raw)
        if not isinstance(protection, dict):
            protection = {}
    except json.JSONDecodeError:
        protection = {}
        if not args.json:
            print("UYARI: gh api çıktısı ayrıştırılamadı — koruma yapısı farklı",
                  file=sys.stderr)

    result = evaluate_protection(expected, protection)
    smoke_json = [{"label": label, "ok": ok, "note": note}
                  for (label, ok, note) in result["smoke"]]
    verdict = "PASS" if (result["names_ok"] and result["enforcement_ok"]) \
        else "FAIL"
    gh_result.update({
        "names_ok": result["names_ok"],
        "missing": result["missing"],
        "extra": result["extra"],
        "configured": result["configured"],
        "enforcement_ok": result["enforcement_ok"],
        "smoke": smoke_json,
        "verdict": verdict,
    })

    if args.json:
        print(json.dumps(gh_result, indent=2, ensure_ascii=False))
        if verdict == "FAIL":
            sys.exit(1)
        return

    # ── insan-okur çıktı ──
    expected_set = set(expected)
    for c in result["configured"]:
        print(f"  [{'PASS' if c in expected_set else 'FAZLA'}] {c}")
    for c in result["missing"]:
        print(f"  [FAIL] workflow'da var ama GitHub'da yok: {c}")

    # ── PR-merge engeli smoke (koruma ayarları) ──
    print("\n── PR-merge engeli smoke (koruma ayarları) ──")
    for label, ok, note in result["smoke"]:
        print(f"  [{'PASS' if ok else 'FAIL'}] {label}"
              + ("" if ok else f" — {note}"))

    if result["names_ok"] and result["enforcement_ok"]:
        print(f"\nSONUÇ: PASS — {len(result['configured'])} check birebir "
              "eşleşiyor (workflow ↔ GitHub) ve merge engeli etkin")
    else:
        problems = []
        if not result["names_ok"]:
            problems.append(
                f"eksik: {result['missing']}, fazla: {result['extra']}")
        if not result["enforcement_ok"]:
            problems.append("merge engeli etkin değil (smoke FAIL)")
        print(f"\nSONUÇ: FAIL — " + "; ".join(problems))
        print("  Düzeltme: AŞAMA 1 (b) web UI'da required check listesini "
              "yukarıdaki adlarla eşitle VE smoke FAIL'lerini düzelt "
              "(strict / enforce_admins / disallow force-push+deletions)")
        sys.exit(1)


if __name__ == "__main__":
    main()
