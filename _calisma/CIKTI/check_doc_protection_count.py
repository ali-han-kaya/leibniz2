#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_doc_protection_count.py — PUBLISH_SCENARIO.md'deki required-check
sayılarını CANLI branch protection API'siyle karşılaştıran kapı.

NEDEN AYRI KAPI: `check_status_check_doc_sync.py` dokümanı verify.yml
TÜRETİMİNE bağlar (offline, token'sız). Ama GitHub'daki koruma ayrı bir
gerçektir: workflow'a required job eklenip protection güncellenmezse doküman
"14 required" derken API 12 context döner. Operatör dokümanı doğru sanıp eksik
seçimle merge engelini kaybeder. Bu kapı iki gerçeği karşılaştırır ve yalnızca
SAYIYI denetler — ad kümesinin eşleşmesi `status_checks.py --gh`'nin işidir.

SÖZLEŞME (fail-closed):
  1. Doküman beyanları TEK kaynaktan okunur: `check_status_check_doc_sync.SITES`
     (yalnız PUBLISH + `required` alanı). Regex burada KOPYALANMAZ — çapa
     değişirse kapı sessizce körleşmesin.
  2. API context sayısı `required_status_checks.contexts` (PUT şeması) ya da
     `required_status_checks.checks[].context` (GET şeması) üzerinden sayılır.
     `required_status_checks: null` = kural yok → 0 (gerçek bir cevap, hata
     değil); alan hiç yoksa/bozuksa OKUNAMAZ → rc 2 (temiz sayılmaz).
  3. Token yok / gh yok / JSON bozuk → rc 2. Burada SKIP YOKTUR: çağrılan bir
     kapının sessiz yeşili, kapının hiç var olmamasıyla aynıdır.
  4. Sayı uyuşmazlığı → rc 1; her beyan için `doküman ↔ API` değeri yazılır.

SALT-OKUNUR: API'ye hiçbir şey YAZMAZ (yalnızca GET).

Kullanım:
  PROTECTION_PAT=<pat> python3 _calisma/CIKTI/check_doc_protection_count.py
  ... --repo owner/name --branch main --json
  ... --protection-file protection.json     # offline/CI artefaktı (GET çıktısı)

Exit: 0 = sayılar eşit; 1 = uyuşmazlık; 2 = ölçüm imkânsız.
"""

import argparse
import json
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import check_protection_drift as cpd      # noqa: E402  (token + gh GET, tek kaynak)
import check_status_check_doc_sync as docs  # noqa: E402  (beyan çapaları, tek kaynak)

REPO = HERE.parent.parent
BRANCH = "main"


class MeasurementError(RuntimeError):
    """Ölçüm imkânsız (token/gh/JSON/çapa) — rc 2, sessiz PASS yok."""


def doc_claims(root=REPO, text=None):
    """PUBLISH_SCENARIO.md'deki `required` sayı beyanları — [{site, doc}].

    Çapalar `check_status_check_doc_sync.SITES`'ten gelir; her çapa TAM OLARAK
    bir kez eşleşmelidir (0 eşleşme = beyan kayboldu, >1 = belirsiz).
    """
    if text is None:
        path = pathlib.Path(root) / docs.PUBLISH
        if not path.is_file():
            raise MeasurementError(f"beyan dosyası yok: {path}")
        text = path.read_text(encoding="utf-8")
    claims = []
    for site in docs.SITES:
        if site["file"] != docs.PUBLISH or "required" not in site["fields"]:
            continue
        matches = list(re.finditer(site["pattern"], text, re.M))
        if len(matches) != 1:
            raise MeasurementError(
                f"{site['id']}: {len(matches)} eşleşme (tam olarak 1 olmalı) — "
                "beyan kayboldu ya da belirsizleşti")
        idx = site["fields"].index("required")
        claims.append({"site": site["id"], "doc": int(matches[0].group(idx + 1))})
    if not claims:
        raise MeasurementError(
            "PUBLISH_SCENARIO.md'de hiç `required` sayı beyanı bulunamadı — "
            "kapı kör kalır")
    return claims


def api_required_count(protection):
    """Koruma nesnesindeki required context sayısı.

    GET şeması `checks[].context`, PUT şeması `contexts[]` döner; ikisi de
    aynı kümeyi anlatır, biri varsa o sayılır.
    """
    if not isinstance(protection, dict):
        raise MeasurementError("koruma nesnesi dict değil — okunamadı")
    if "required_status_checks" not in protection:
        raise MeasurementError(
            "required_status_checks alanı yok — context sayısı okunamadı")
    sc = protection["required_status_checks"]
    if sc is None:
        # GitHub: kural kurulu değil. Gerçek cevap → 0; doküman 14 diyorsa
        # uyuşmazlık olarak raporlanır (hata değil, bulgu).
        return 0
    if not isinstance(sc, dict):
        raise MeasurementError(
            f"required_status_checks beklenmeyen tip: {type(sc).__name__}")
    for key in ("contexts", "checks"):
        value = sc.get(key)
        if isinstance(value, list):
            return len(value)
    raise MeasurementError(
        "required_status_checks.contexts/checks yok — context sayısı okunamadı")


def compare(claims, api_count):
    """Beyan ↔ API uyuşmazlıkları — [{site, doc, api}]."""
    return [{"site": c["site"], "doc": c["doc"], "api": api_count}
            for c in claims if c["doc"] != api_count]


def load_protection_file(path):
    """`--protection-file`: GET çıktısının JSON kopyası (offline/CI artefaktı)."""
    try:
        data = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    except OSError as exc:
        raise MeasurementError(f"koruma dosyası okunamadı ({path}): {exc}")
    except json.JSONDecodeError as exc:
        raise MeasurementError(f"koruma dosyası JSON değil ({path}): {exc}")
    if not isinstance(data, dict):
        raise MeasurementError(f"koruma dosyası nesne değil ({path})")
    return data


def format_report(claims, api_count, findings, branch):
    lines = [f"check-doc-protection-count: branch={branch}", "",
             f"  doküman beyanı: {len(claims)} çapa · "
             f"beklenen required: {sorted({c['doc'] for c in claims})}",
             f"  API required context: {api_count}"]
    if findings:
        lines.append("FAIL — doküman ↔ koruma API uyuşmazlığı:")
        for f in findings:
            lines.append(f"  • {f['site']}: doküman {f['doc']} ↔ API {f['api']}")
        lines.append("  Remediy: korumayı workflow ile eşitle "
                     "(_calisma/CIKTI/setup_branch_protection.py) ya da dokümanı "
                     "yeniden türet "
                     "(check_status_check_doc_sync.py --write --file "
                     "docs/PUBLISH_SCENARIO.md).")
    else:
        lines.append("PASS — beyan edilen required sayısı canlı koruma ile aynı")
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=str(REPO),
                    help="repo kökü (varsayılan: script konumu)")
    ap.add_argument("--repo", default=None, help="owner/name")
    ap.add_argument("--branch", default=BRANCH, help=f"varsayılan: {BRANCH}")
    ap.add_argument("--protection-file", default=None,
                    help="GET /protection çıktısı (JSON) — API'ye gitmeden ölç")
    ap.add_argument("--json", action="store_true", help="makine-okur çıktı")
    args = ap.parse_args(argv)

    def fail(msg, payload):
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(f"check-doc-protection-count: {msg}", file=sys.stderr)
        return 2

    try:
        claims = doc_claims(pathlib.Path(args.root))
    except MeasurementError as exc:
        return fail(f"ÖLÇÜM İMKÂNSIZ — {exc}",
                    {"verdict": "ERROR", "error": str(exc)})

    if args.protection_file:
        try:
            protection = load_protection_file(args.protection_file)
        except MeasurementError as exc:
            return fail(f"ÖLÇÜM İMKÂNSIZ — {exc}",
                        {"verdict": "ERROR", "error": str(exc)})
        repo = args.repo or "(protection-file)"
    else:
        token = cpd.token_from_env()
        if not token:
            msg = ("token yok (%s) — branch protection okunamaz; "
                   "`--protection-file` ile offline ölçün"
                   % "/".join(cpd.TOKEN_ENVS))
            return fail(f"ÖLÇÜM İMKÂNSIZ — {msg}",
                        {"verdict": "ERROR", "error": msg})
        repo, err = cpd.repo_slug(args.repo)
        if not repo:
            return fail(f"ÖLÇÜM İMKÂNSIZ — repo belirlenemedi: {err}",
                        {"verdict": "ERROR", "error": err or "repo yok"})
        protection, err = cpd.fetch_protection(repo, token, args.branch)
        if protection is None:
            msg = f"{repo} koruması okunamadı: {err}"
            return fail(f"ÖLÇÜM İMKÂNSIZ — {msg}",
                        {"verdict": "ERROR", "error": msg})

    try:
        api_count = api_required_count(protection)
    except MeasurementError as exc:
        return fail(f"ÖLÇÜM İMKÂNSIZ — {exc}",
                    {"verdict": "ERROR", "error": str(exc)})

    findings = compare(claims, api_count)
    if args.json:
        print(json.dumps({
            "verdict": "FAIL" if findings else "PASS",
            "branch": args.branch,
            "repo": repo,
            "api_required": api_count,
            "sites": len(claims),
            "findings": findings,
        }, ensure_ascii=False, indent=2))
    else:
        print(format_report(claims, api_count, findings, args.branch))
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
