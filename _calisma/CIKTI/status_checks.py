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

Advisory kontratı (her modda koşar): tüm job adları ↔ required set farkı
raporlanır — plist-check (macOS advisory) required sette DEĞİLSE, exclude
bayat kaldıysa veya isim çakışması varsa exit 1 (fail-closed).

Çıkış kodları:
  0 — liste üretildi; veya --gh'de birebir eşleşme; veya koruma kurulu değil
      (publish öncesi normal — UYARI basılır, bloke etmez).
  1 — advisory kontratı ihlali VEYA --gh'de eksik/fazla check VEYA merge
      engeli smoke FAIL (fail-closed).
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
# Required check OLMAYAN job'lar: PR-only/advisory (banner kapı olmasın).
GATE_EXCLUDE = {
    "manifest-comment",    # PR-only: yorum düşürme
    "precheck",             # AŞAMA 0 advisory
    "label-gate-p1",        # PR-only: P1 etiket opsiyonel blokaj (required DEĞİL)
    "plist-check",          # macOS-advisory: push'ta çalışmaz
    "mirror-check",         # macOS: sync sonrası K17 fail-closed (advisory)
    "daemon-http",          # advisory: daemon-modu HTTP 200 smoke (advisory)
    "audit-live-ci",        # advisory: doc↔GitHub senkron denetimi
    "audit-refs-trend",     # advisory: refs-trend satırları ↔ kaynak denetimi
    "override-trend",       # advisory: CLI override zaman serisi
}
# Not: "label-gate" (Pre-commit P0 label gate) BİLEREK required check'tir —
# precommit-p0 etiketi varken FAIL verip merge'i bloke eder; bu yüzden
# GATE_EXCLUDE'da DEĞİL. 12'li required liste (2026-08-23): 9 eski gate +
# commit-msg-gate (commit-msg ihlal blokajı — PR-only ama required),
# config-sync (config snapshot ↔ CONFIG_BASENAMES üçlü senkron),
# ci-simulate (yerel CI simülasyonu — full K1-K14 replay).
# commit-msg-gate (commit-msg ihlal blokajı — PR-only ama required),
# config-sync (config snapshot ↔ CONFIG_BASENAMES üçlü senkron),
# ci-simulate (yerel CI simülasyonu — full K1-K14 replay).


def gate_jobs():
    """workflow'daki job id → name eşlemesi (required check adayları)."""
    with open(WORKFLOW, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    jobs = data["jobs"]
    return {jid: j["name"] for jid, j in jobs.items() if jid not in GATE_EXCLUDE}


def all_jobs(data=None):
    """workflow'daki TÜM job id → name eşlemesi (required + advisory + PR-only).

    data verilirse mock/parçalı workflow üzerinde çalışır (testler için);
    verilmezse WORKFLOW dosyasını okur.
    """
    if data is None:
        with open(WORKFLOW, encoding="utf-8") as f:
            data = yaml.safe_load(f)
    jobs = data.get("jobs") or {}
    return {jid: (j.get("name") if isinstance(j, dict) else str(j))
            for jid, j in jobs.items()}


def advisory_contract(data=None):
    """Advisory kontratı: tüm job adları ↔ required set farkını denetler.

    Fail-closed invariantlar:
      1. GATE_EXCLUDE'daki her job id workflow'da VAR olmalı (bayat exclude
         = o kapı sessizce düşmüş demektir).
      2. Exclude edilen hiçbir job adı required sette OLAMAZ (isim çakışması
         = required olmaması gereken bir job kapıya girmiş).
      3. plist-check (macOS advisory) özel olarak required DEĞİL olmalı.

    Döndürür: {ok, all_jobs, required, advisory, plist_check, issues}.
    advisory = tüm adlar − required adlar (advisory/PR-only farkı).
    """
    if data is None:
        with open(WORKFLOW, encoding="utf-8") as f:
            data = yaml.safe_load(f)
    allj = all_jobs(data)
    req_names = {nm for jid, nm in allj.items() if jid not in GATE_EXCLUDE}
    issues = []
    for jid in sorted(GATE_EXCLUDE):
        nm = allj.get(jid)
        if nm is None:
            issues.append(f"GATE_EXCLUDE '{jid}' workflow'da yok (bayat exclude)")
        elif nm in req_names:
            issues.append(
                f"'{jid}' ({nm}) exclude edilmiş ama required sette "
                "(isim çakışması)")
    pc_name = allj.get("plist-check")
    plist = {
        "job_id": "plist-check",
        "name": pc_name,
        "required": pc_name in req_names if pc_name else False,
        "ok": pc_name is not None and pc_name not in req_names,
    }
    if pc_name is None:
        issues.append(
            "'plist-check' job'ı workflow'da yok (advisory denetimi kayıp)")
    elif pc_name in req_names:
        issues.append(
            f"'plist-check' required sette — advisory olmalı: {pc_name}")
    return {
        "ok": not issues and plist["ok"],
        "all_jobs": allj,
        "required": sorted(req_names),
        "advisory": sorted(set(allj.values()) - req_names),
        "plist_check": plist,
        "issues": issues,
    }


def format_contract(contract):
    """Advisory kontratı bölümünü insan-okur metne çevirir."""
    lines = ["\n── Advisory kontratı (tüm job'lar ↔ required farkı) ──"]
    pc = contract["plist_check"]
    if pc["ok"]:
        lines.append(f"  [PASS] plist-check: \"{pc['name']}\" advisory — "
                     "required sette DEĞİL")
    else:
        lines.append(f"  [FAIL] plist-check advisory olmalı: {pc}")
    lines.append(
        f"  Tüm adlar ({len(contract['all_jobs'])}) − required "
        f"({len(contract['required'])}) = advisory/PR-only "
        f"({len(contract['advisory'])}):")
    for nm in contract["advisory"]:
        lines.append(f"    • {nm}")
    for issue in contract["issues"]:
        lines.append(f"  [FAIL] {issue}")
    lines.append(f"  Durum: {'PASS' if contract['ok'] else 'FAIL'}")
    return "\n".join(lines)


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
        ("required_status_checks.strict",
         sc.get("strict") is not None,
         "strict tanımlı değil — up-to-date zorunluluğu ayarlanmamış"),
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
    contract = advisory_contract()
    payload = {
        "workflow": WORKFLOW,
        "gate_jobs": list(gates.keys()),
        "excluded": sorted(GATE_EXCLUDE),
        "checks": expected,
        "all_jobs": contract["all_jobs"],
        "advisory": contract["advisory"],
        "advisory_contract": {
            k: v for k, v in contract.items() if k != "all_jobs"},
    }

    if not contract["ok"]:
        # Fail-closed: advisory kontratı ihlali (örn. plist-check required'a
        # girmiş, bayat exclude, isim çakışması) — TÜM modlarda exit 1.
        if args.json:
            out = dict(payload)
            out.update({"verdict": "FAIL", "issues": contract["issues"]})
            print(json.dumps(out, indent=2, ensure_ascii=False))
        else:
            print(format_contract(contract))
        sys.exit(1)

    if args.json and not args.gh:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return

    if not args.json:
        print(f"Beklenen status check adları ({len(expected)}) — kaynak: {WORKFLOW}")
        print(f"  (required aday job'lar: {', '.join(gates)}; "
              f"hariç: {', '.join(sorted(GATE_EXCLUDE))})")
        for i, n in enumerate(expected, 1):
            print(f"  {i:2d}. {n}")
        print(format_contract(contract))

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
        # 404 = koruma GERÇEKTEN kurulu değil (NOT_SET_UP). Diğer hatalar
        # (403 yetki yok, ağ) koruma olabilir ama okunamadı — UYARI aynı
        # kalır ama mesaj ayırt edilir: "erişilemedi" ≠ "kurulu değil".
        # GITHUB_TOKEN'da administration scope'u olmadığından CI'da 403/404
        # oluşur; gerçek doğrulama yerelde gh auth ile yapılır (fail-closed
        # exit 1 — yanlış-PASS vermez).
        err = str(e)
        is_404 = "404" in err or "Not Found" in err
        gh_result["warning"] = err
        gh_result["verdict"] = "NOT_SET_UP" if is_404 else "UNREADABLE"
        if args.json:
            print(json.dumps(gh_result, indent=2, ensure_ascii=False))
        else:
            label = "kurulu değil" if is_404 else "erişilemedi (yetki/ağ)"
            print(f"HATA: branch protection {label} — {e}", file=sys.stderr)
            print("  --gh modu fail-closed: doğrulanamıyorsa exit 1.",
                  file=sys.stderr)
            print(f"\nUYARI: branch protection {label} — {e}")
            print("  Kurulum: gh api -X PUT repos/.../branches/main/protection")
        sys.exit(1)

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
