#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_protection_drift.py — haftalık branch-protection drift kapısı (P1).

NEDEN AYRI SCRIPT: `status_checks.py --gh` aynı karşılaştırmayı yapar ama
CI'da KOŞAMAZ — branch protection okumak admin izni ister ve `administration`
scope'u Actions `permissions:` bloğunda GEÇERSİZDİR (ölçüldü 2026-09-30,
actionlint v1.7.7: "unknown permission scope administration"). Eklenirse
workflow PARSE HATASIYLA 0 JOB üretir. Bu yüzden okuma yetkisi
`PROTECTION_PAT` secret'ından gelir; GITHUB_TOKEN ile denenmez.

SÖZLEŞME (üç dal, üçü AYRI raporlanır):
  * token yok            → SKIP, rc=0, bulgu YOK (gürültü yapmaz; bu kasıtlı).
  * token var, okunamadı → rc=2 "DOĞRULANAMADI". Süresi geçmiş bir PAT'in
    sonsuza dek sessiz SKIP'e düşmesi, kapının hiç var olmamasıyla aynıdır —
    o yüzden bu dal YEŞİL değil.
  * okundu, drift var    → P1 bulguları (verify_delivery sözlüğü), rc=1.
  * okundu, temiz        → rc=0.

SALT-OKUNUR: API'ye hiçbir şey YAZMAZ (yalnızca GET).

Kullanım:
  PROTECTION_PAT=<pat> python3 _calisma/CIKTI/check_protection_drift.py
  PROTECTION_PAT=<pat> python3 _calisma/CIKTI/check_protection_drift.py --json
  python3 _calisma/CIKTI/check_protection_drift.py            # → SKIP rc=0
"""

import argparse
import json
import os
import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import status_checks as sc          # noqa: E402
import verify_delivery as vd        # noqa: E402

BRANCH = "main"
# Sırayla denenir. PROTECTION_PAT tercih edilir: fine-grained, yalnızca
# "Administration: read" yetkisi verilmiş bir token olmalıdır.
TOKEN_ENVS = ("PROTECTION_PAT", "GH_ADMIN_TOKEN")


def token_from_env(env=None):
    """Okuma yetkisi olan token'ı döndürür; yoksa None."""
    env = os.environ if env is None else env
    for name in TOKEN_ENVS:
        value = env.get(name)
        if value and value.strip():
            return value.strip()
    return None


def fetch_protection(repo, token, branch=BRANCH):
    """Koruma nesnesini okur. Döner: (protection|None, error|None).

    `gh` yoksa (OSError) veya çağrı başarısızsa hata DÖNER, yükseltmez:
    çağıran bunu "okunamadı" (rc=2) olarak raporlar. Yükseltseydi istisna
    traceback'i kapıyı rc=1 ile kırar ve "drift" ile "araç yok" ayırt
    edilemezdi.
    """
    try:
        r = subprocess.run(
            ["gh", "api", "repos/%s/branches/%s/protection" % (repo, branch)],
            capture_output=True, text=True,
            env={**os.environ, "GH_TOKEN": token})
    except OSError as exc:
        return None, "gh çalıştırılamadı: %s" % exc
    if r.returncode != 0:
        return None, (r.stderr or r.stdout).strip()
    try:
        data = json.loads(r.stdout)
    except json.JSONDecodeError as exc:
        return None, "gh api çıktısı ayrıştırılamadı: %s" % exc
    return (data if isinstance(data, dict) else {}), None


def repo_slug(explicit=None):
    """owner/name — verilmezse gh'den; olmazsa GITHUB_REPOSITORY."""
    if explicit:
        return explicit, None
    try:
        out = subprocess.run(["gh", "repo", "view", "--json", "nameWithOwner",
                              "-q", ".nameWithOwner"],
                             capture_output=True, text=True)
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip(), None
    except OSError as exc:
        return None, str(exc)
    slug = os.environ.get("GITHUB_REPOSITORY")
    if slug:
        return slug, None
    return None, "repo belirlenemedi"


def main(argv=None):
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", default=None, help="owner/name")
    ap.add_argument("--json", action="store_true", help="makine-okur çıktı")
    args = ap.parse_args(argv)

    token = token_from_env()
    if not token:
        # KASITLI SKIP: secret kurulmadıysa denetim yapılamaz. Bulgu üretmek
        # her hafta yanlış-P1 gürültüsü olurdu; sessiz kalmak yerine neyin
        # eksik olduğunu AÇIKÇA söyleriz.
        msg = ("SKIP — %s secret'ı yok; branch protection okunamaz "
               "(admin scope'u Actions'ta tanımlanamıyor). Kurulum: "
               "fine-grained token ('Administration: read') → repo secret "
               "'%s'" % (TOKEN_ENVS[0], TOKEN_ENVS[0]))
        if args.json:
            print(json.dumps({"status": "SKIP", "reason": "no-token",
                              "p1": [], "message": msg},
                             indent=2, ensure_ascii=False))
        else:
            print(msg)
        return 0

    repo, err = repo_slug(args.repo)
    if not repo:
        print("HATA: %s" % err, file=sys.stderr)
        return 2

    protection, err = fetch_protection(repo, token)
    if protection is None:
        # Token VAR ama okunamadı: süresi geçmiş olabilir. Sessiz SKIP
        # kapıyı ölü hâle getirirdi.
        msg = ("DOĞRULANAMADI — %s koruması okunamadı: %s "
               "(token geçersiz/süresi geçmiş ya da yetki yetersiz)"
               % (repo, err))
        if args.json:
            print(json.dumps({"status": "UNVERIFIABLE", "repo": repo,
                              "p1": [], "message": msg},
                             indent=2, ensure_ascii=False))
        else:
            print(msg, file=sys.stderr)
        return 2

    expected = list(sc.gate_jobs().values())
    findings = []
    ok, detail = vd.check_protection_drift(
        lambda pri, cid, check, issue, evidence="": findings.append(
            {"id": cid, "priority": pri, "check": check,
             "issue": issue, "evidence": evidence}),
        protection, expected)

    payload = {
        "status": "PASS" if ok else "FAIL",
        "repo": repo,
        "branch": BRANCH,
        "expected_checks": len(expected),
        "detail": detail,
        "p1": findings,
    }
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print("── branch protection drift (%s@%s) ──" % (repo, BRANCH))
        print("  beklenen required check: %d" % len(expected))
        print("  sonuç: %s — %s" % ("PASS" if ok else "FAIL", detail))
        for f in findings:
            print("  [%s] %s: %s\n        %s"
                  % (f["priority"], f["check"], f["issue"], f["evidence"]))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
