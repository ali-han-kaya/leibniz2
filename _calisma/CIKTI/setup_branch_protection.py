#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""setup_branch_protection.py — branch protection'ı TEK KOMUTLA kurar.

status_checks.py'den beklenen required check adlarını (workflow job
`name:`'leri — TEK KAYNAK) okur ve `gh api --method PUT` ile main branch'e
kurar:

  - required_status_checks: strict=true + beklenen adlar (birebir)
  - enforce_admins: true  (admin bypass kapalı — merge engeli smoke gereği)
  - allow_force_pushes / allow_deletions: false
  - mevcut review (dismissal_restrictions vb.) + restrictions ayarları
    KORUNUR → idempotent re-run (tekrar koşmak mevcut ayarları bozmaz)

Kurulum sonrası status_checks.py --gh ile birebir eşleşme doğrulanır
(fail-closed: kurulum sonrası hâlâ drift varsa exit 1).

Kullanım:
  python3 _calisma/CIKTI/setup_branch_protection.py                  # kur + doğrula
  python3 _calisma/CIKTI/setup_branch_protection.py --dry-run        # yalnızca önizle
  python3 _calisma/CIKTI/setup_branch_protection.py --repo owner/name
  python3 _calisma/CIKTI/setup_branch_protection.py --no-enforce-admins
  python3 _calisma/CIKTI/setup_branch_protection.py --no-verify

Çıkış kodları:
  0 — kuruldu + doğrulama PASS (veya --dry-run önizlemesi)
  1 — doğrulama FAIL (kurulum sonrası hâlâ drift) VEYA gh api PUT hatası
  2 — çalışma hatası (PyYAML yok, beklenen liste boş, repo belirlenemedi)

Not: admin izni gerekir — GITHUB_TOKEN'da yok; yerelde `gh auth login`
(admin scope) ile çalıştır.
"""
import argparse
import json
import pathlib
import subprocess
import sys

CIKTI = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(CIKTI))

import status_checks as sc  # noqa: E402


def gh_get(repo):
    """Mevcut korumayı oku (404 → RuntimeError)."""
    r = subprocess.run(
        ["gh", "api", f"repos/{repo}/branches/main/protection"],
        capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout).strip())
    return json.loads(r.stdout)


def gh_put(repo, body):
    """PUT ile korumayı uygula (başarısızlık → RuntimeError)."""
    r = subprocess.run(
        ["gh", "api", "--method", "PUT",
         f"repos/{repo}/branches/main/protection", "--input", "-"],
        input=json.dumps(body), capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout).strip())
    return r.stdout


def build_body(expected, current=None, enforce_admins=True):
    """PUT body'si: beklenen check'leri kurar, mevcut review/restrictions'ı korur.

    GET şeması ≠ PUT şeması: GET required_status_checks'te checks[] + url
    döner; PUT yalnızca strict + contexts (string listesi) kabul eder.
    """
    current = current or {}
    rpr = current.get("required_pull_request_reviews")
    if isinstance(rpr, dict):
        dr = rpr.get("dismissal_restrictions") or {}
        rpr_body = {
            "dismiss_stale_reviews": bool(rpr.get("dismiss_stale_reviews", False)),
            "require_code_owner_reviews": bool(
                rpr.get("require_code_owner_reviews", False)),
            "required_approving_review_count": int(
                rpr.get("required_approving_review_count", 1)),
            "dismissal_restrictions": {
                "users": [u.get("login") for u in (dr.get("users") or [])],
                "teams": [t.get("slug") for t in (dr.get("teams") or [])],
            } if dr else {},
        }
    else:
        rpr_body = None

    return {
        "required_status_checks": {"strict": True, "contexts": list(expected)},
        "enforce_admins": bool(enforce_admins),
        "required_pull_request_reviews": rpr_body,
        "restrictions": current.get("restrictions"),
        "allow_force_pushes": False,
        "allow_deletions": False,
    }


def verify_checks(repo):
    """Kurulum sonrası status_checks.py --gh (doğrulama alt süreci).

    Döner: (exit_code, stdout, stderr).
    """
    r = subprocess.run(
        [sys.executable, str(CIKTI / "status_checks.py"), "--gh", "--repo", repo],
        capture_output=True, text=True)
    return r.returncode, r.stdout, r.stderr


def main(argv=None):
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", default=None, help="owner/name (varsayılan: gh repo view)")
    ap.add_argument("--dry-run", action="store_true",
                    help="PUT body'yi yazdır, uygulama")
    ap.add_argument("--no-enforce-admins", action="store_true",
                    help="enforce_admins=false kur (varsayılan: true — admin bypass kapalı)")
    ap.add_argument("--no-verify", action="store_true",
                    help="kurulum sonrası status_checks.py --gh doğrulamasını atla")
    args = ap.parse_args(argv)

    expected = list(sc.gate_jobs().values())
    if not expected:
        print("HATA: beklenen check listesi boş — workflow job adları okunamadı",
              file=sys.stderr)
        return 2

    repo = args.repo
    if not repo:
        try:
            repo = sc.run_gh(["gh", "repo", "view", "--json", "nameWithOwner",
                              "-q", ".nameWithOwner"])
        except RuntimeError as e:
            print(f"HATA: repo belirlenemedi ({e}) — --repo owner/name verin",
                  file=sys.stderr)
            return 2

    print(f"Beklenen required check ({len(expected)}) — kaynak: {sc.WORKFLOW}")
    for c in expected:
        print(f"  • {c}")

    current = None
    try:
        current = gh_get(repo)
        print("\nMevcut koruma: VAR — review/restrictions korunacak (idempotent)")
    except RuntimeError:
        print("\nMevcut koruma: YOK — sıfırdan kurulacak")

    enforce_admins = not args.no_enforce_admins
    body = build_body(expected, current, enforce_admins=enforce_admins)

    if args.dry_run:
        print("\n[DRY-RUN] PUT body (uygulanmadı):")
        print(json.dumps(body, indent=2, ensure_ascii=False))
        return 0

    try:
        gh_put(repo, body)
    except RuntimeError as e:
        print(f"HATA: branch protection PUT başarısız — {e}", file=sys.stderr)
        return 1

    print(f"\nBranch protection kuruldu: {len(expected)} required check + strict "
          f"+ enforce_admins={enforce_admins} "
          "(force-push/deletions kapalı)")

    if args.no_verify:
        print("Doğrulama atlandı (--no-verify)")
        return 0

    print("\nDoğrulama (status_checks.py --gh):")
    rc, out, err = verify_checks(repo)
    if out:
        print(out.rstrip())
    if err:
        print(err.rstrip(), file=sys.stderr)
    if rc != 0:
        print("SONUÇ: FAIL — kurulum sonrası hâlâ drift (fail-closed)",
              file=sys.stderr)
        return 1
    print("SONUÇ: PASS ✓ — required check adları + merge engeli birebir eşleşiyor")
    return 0


if __name__ == "__main__":
    sys.exit(main())
