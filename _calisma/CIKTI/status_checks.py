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

strict YALNIZCA PR akışında değer olarak zorunludur: `required_pull_request_
reviews` doluysa `strict=false` FAIL'dir (bayat PR dalı merge edilebilir).
Doğrudan-push depolarında PR dalı olmadığı için strict uygulanmaz — orada
`strict=false` (ya da alanın yokluğu) yanlış-kırmızı üretmez.

İkincil kapı: required set yalnız verify.yml'den türetilmez. `SECONDARY_
WORKFLOWS` (bugün `docker-security.yml`) beyan edilir ve onun job adları da
beklenen sete girer; böylece docker-security PR'larda required check
kurulabilir ve `--gh` onu "FAZLA" saymaz. Beyan edilen dosya ya da job adı
okunamazsa fail-closed (kapı sessizce required setten düşmez).

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
import os
import pathlib
import subprocess
import sys

try:
    import yaml  # type: ignore[import-not-found]
    _HAVE_YAML = True
except ImportError:  # pragma: no cover — stdlib-only runnerlarda yaml yok
    yaml = None  # type: ignore[assignment]
    _HAVE_YAML = False

# verify.yml — scriptin kendi konumundan çöz (cwd'den bağımsız; testler
# CIKTI'dan da repo kökünden de koşabilsin).
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
WORKFLOW = str(_REPO_ROOT / ".github" / "workflows" / "verify.yml")

# ── İkincil kapı workflow'ları ─────────────────────────────────────────────
# Ölçülen boşluk (2026-10-26): required set yalnız verify.yml'den türetildiği
# için docker-security kapısı GitHub'da required YAPILAMIYORDU — yapılsa
# `--gh` onu "FAZLA" sayıp FAIL ederdi. Sonuç: PR'lar Trivy gate kırmızıyken
# (#146, #147) ya da hiç koşum olmadan (#97) merge edildi. Bu yüzden ikincil
# workflow'lar burada BEYAN edilir; job adları yine YAML'dan okunur (elle
# kopyalanmaz → yeniden adlandırma sessizce kaymaz).
SECONDARY_WORKFLOWS = ("docker-security.yml",)


def _workflow_path(rel):
    """İkincil workflow dosyasının mutlak yolu (repo kökünden)."""
    return str(_REPO_ROOT / ".github" / "workflows" / rel)


def secondary_gate_jobs():
    """İkincil workflow'ların job adları: {rel: {job_id: name}}.

    Fail-closed: beyan edilen dosya yoksa, YAML ayrıştırılamıyorsa ya da
    adı boş job varsa RuntimeError — kapı sessizce required setten düşmesin.
    """
    _require_yaml()
    out = {}
    for rel in SECONDARY_WORKFLOWS:
        path = _workflow_path(rel)
        if not os.path.isfile(path):
            raise RuntimeError(f"beyan edilen ikincil workflow yok: {rel}")
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        jobs = data.get("jobs") or {}
        named = {jid: (j or {}).get("name")
                 for jid, j in jobs.items() if isinstance(j, dict)}
        if not named or any(not nm for nm in named.values()):
            raise RuntimeError(
                f"{rel}: job adları okunamadı (required check türetilemez)")
        out[rel] = named
    return out


def expected_checks():
    """Required check adları: verify.yml kapıları + ikincil workflow kapıları.

    Sıra deterministiktir (önce verify job sırası, sonra beyan sırası) —
    `--gh` karşılaştırması ve `setup_branch_protection.py` PUT gövdesi
    koşumdan koşuma değişmez. Aynı ad iki workflow'da yaşarsa fail-closed:
    required set hangi kapıyı işaret ettiği belirsiz kalırdı.
    """
    primary = list(gate_jobs().values())
    secondary = [nm for jobs in secondary_gate_jobs().values()
                 for nm in jobs.values()]
    dupes = sorted({nm for nm in primary if nm in secondary})
    if dupes:
        raise RuntimeError(
            "aynı check adı iki workflow'da tanımlı: %s — required set "
            "belirsiz (adları ayrıştırın)" % dupes)
    return primary + secondary
# Required check OLMAYAN job'lar: PR-only/advisory (banner kapı olmasın).
GATE_EXCLUDE = {
    "manifest-comment",    # PR-only: yorum düşürme
    "precheck",             # AŞAMA 0 advisory
    "label-gate-p1",        # PR-only: P1 etiket opsiyonel blokaj (required DEĞİL)
    "plist-check",          # macOS-advisory: push'ta çalışmaz
    "mirror-check",         # macOS: sync sonrası K17 fail-closed (advisory)
    "daemon-http",          # advisory: daemon-modu HTTP 200 smoke (advisory)
    "fresh-clone-http",      # advisory: temiz clone + preview HTTP smoke
    "audit-live-ci",        # advisory: doc↔GitHub senkron denetimi
    "audit-refs-trend",     # advisory: refs-trend satırları ↔ kaynak denetimi
    "override-trend",       # advisory: CLI override zaman serisi
    "changelog-drift",      # advisory: gen_changelog --check drift bulguları
    "pattern-drift",         # advisory: merge pattern ↔ ARTIFACT_JOBS drift
    "budget-comment",        # PR-only: bütçe + pre-commit PR yorumu (bütçe kapısı ayrı job)
    "preview-reload-smoke",  # advisory: job adı "Preview reload smoke (advisory, macOS)";
                             #   macOS-only tarayıcı smoke'u — canlı protected sette YOK.
    "webkit-smoke",          # advisory: job adı "WebKit smoke (advisory, Safari/safedriver)";
                             #   macOS safedriver smoke'u — canlı protected sette YOK.
    "lake-proof",            # ayrı-step K9 lake build (lean-toolchain v4.14.0);
                             #   GitHub required kontrollerinde DEĞİL (advisory) —
                             #   K9, verify job'unun --full içinde de koşar.
}
# NOT (2026-10-25): `dashboard-smoke` ("Dashboard interaction E2E (node sandbox
# + Chromium CDP)") EXCLUDE'dan ÇIKARILDI — canlı branch protection bu adı
# required olarak tutuyor ve job fail-closed koşar (node katmanı tarayıcısız
# her ortamda, Chromium katmanı CDP). `preview-reload-smoke` ve `webkit-smoke`
# ise adlarında "advisory" taşıyan macOS-only smoke'lar; canlı protected
# sette yoklar, bu yüzden artık EXCLUDE'dalar. `plist-p1` (P1 plist drift
# kapısı, Linux) ise canlı protected sette REQUIRED'dır — bu yüzden
# EXCLUDE'da DEĞİL. Böylece türetilen required küme canlı koruma ile
# birebir: 32 job − 16 exclude = 16 required.
# Not: "label-gate" (Pre-commit P0 label gate) BİLEREK required check'tir —
# precommit-p0 etiketi varken FAIL verip merge'i bloke eder; bu yüzden
# GATE_EXCLUDE'da DEĞİL. 12'li required liste (2026-08-23): 9 eski gate +
# commit-msg-gate (commit-msg ihlal blokajı — PR-only ama required),
# config-sync (config snapshot ↔ CONFIG_BASENAMES üçlü senkron),
# ci-simulate (yerel CI simülasyonu — full K1-K14 replay).
# 27 job − 14 hariç = 13 required (fresh-clone-http dahil advisory).
#
# 2026-09-04 denetimi (job-id → karar, kanıt verify.yml + GitHub required set):
#   reports          REQUIRED kalır — tüketilen precommit-logs artifact'ı
#                    job içinde indirilir (coe=True), bundle repo-kaynaklı;
#                    kriter: fail-open değil, tüketim bağlı.
#   reproducibility  REQUIRED kalır — K10 bütünlük adımı (--verify-manifest)
#                    set -e altında job'u düşürür (fail-closed uç); manifest
#                    bundle'ı merge-blok kapıdır.
#   refs-trend       REQUIRED kalır — koddan türeyen trend tablosu in-jobs
#                    üretilir (artifact bağımlılığı yok), K6 trend zinciri.
#   lake-proof       ADVISORY kalır (exclude'da) — ayrı-step K9 lake build;
#                    K9, verify --full içinde bağımsız koşar (e30f8ea).


def _require_yaml():
    """PyYAML yoksa import noktasındaki gibi exit 2 — test/CI bare-run toleransı."""
    if not _HAVE_YAML:
        sys.stderr.write(
            "HATA: PyYAML gerekli — pip install pyyaml "
            "(veya _calisma/.venv_z3/bin/python kullan)\n"
        )
        sys.exit(2)


def gate_jobs():
    """workflow'daki job id → name eşlemesi (required check adayları)."""
    _require_yaml()
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
        _require_yaml()
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


def pr_flow_enabled(protection, override=None):
    """Depo PR-akışlı mı? (strict yalnızca bu yolda anlam taşır)

    Sinyal `required_pull_request_reviews`: GitHub'da "Require a pull request
    before merging" AÇIKken boş olmayan bir nesne döner (0 onay bile olsa),
    KAPALIYKEN `null`. `override` (True/False) verilirse tahmin yerine o
    kullanılır — akışı bilen çağıran kararı sabitleyebilir.
    """
    if override is not None:
        return bool(override)
    return bool(protection.get("required_pull_request_reviews"))


def _strict_probe(protection, pr_flow=None):
    """strict satırı: PR-akışında DEĞER, direct-push'ta uygulanabilirlik.

    NEDEN KOŞULLU (ölçüldü 2026-08-21, düzeltildi 2026-10-23): `strict=False`
    doğrudan-push depolarında MEŞRUDUR — PR dalı yok, "base'in gerisinde"
    durumu doğmaz; required check'ler push anında denetlenir. Ama PR-akışlı
    bir depoda strict kapalıysa bayat dal yeşil check'lerle merge edilebilir;
    "alan var mı" ölçmek bunu kaçırıyordu. Bu yüzden değer yalnızca PR
    akışında zorunlu: `required_status_checks` hiç yoksa yine fail-closed.
    """
    if not protection.get("required_status_checks"):
        return (False,
                "required_status_checks yok — up-to-date kuralı "
                "doğrulanamaz")
    sc = protection.get("required_status_checks")
    strict = sc.get("strict")
    if not pr_flow_enabled(protection, pr_flow):
        return (True,
                "PR zorunlu değil (direct-push) — strict uygulanmaz; "
                "bayat-dal riski yok")
    if strict is True:
        return True, ""
    if strict is False:
        return (False,
                "strict kapalı — base'in gerisindeki PR dalı up-to-date "
                "kontrolü olmadan merge edilebilir")
    return (False,
            "strict tanımlı değil — up-to-date zorunluluğu ayarlanmamış")


def merge_block_smoke(protection, pr_flow=None):
    """Koruma nesnesinden PR-merge engeli enforcement alanlarını denetle.

    `required_status_checks.contexts` birebir doğru olsa bile aşağıdakiler
    kapalıysa merge butonu gerçekten BLOKE ETMEZ. Her alan için
    (label, ok, failure_note) döner; ok=False → o koruma eksik (fail-closed).

    `pr_flow`: None → `required_pull_request_reviews`'tan türetilir; True/False
    verilirse repo akışı hakkındaki bu bilgi tahmini ezer (direct-push
    depoları strict=False ile yanlış-kırmızıya düşmesin).
    """
    strict_ok, strict_note = _strict_probe(protection, pr_flow)
    admins = protection.get("enforce_admins") or {}
    fp = protection.get("allow_force_pushes") or {}
    dele = protection.get("allow_deletions") or {}
    return [
        ("required_status_checks.strict", strict_ok, strict_note),
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


def evaluate_protection(expected, protection, pr_flow=None):
    """expected (check adları) ile tam koruma nesnesini karşılaştır.

    Döndürür: {names_ok, missing, extra, configured, smoke, enforcement_ok,
    pr_flow}. names_ok (check adı eşleşmesi) ve enforcement_ok (merge engeli
    smoke) AYRI bayraklar — her ikisi de geçmeli (fail-closed).

    `pr_flow` smoke'a aynen geçer (None → koruma nesnesinden türetilir).
    """
    sc = protection.get("required_status_checks") or {}
    configured = sc.get("contexts") or []
    if not isinstance(configured, list):
        configured = []
    exp, conf = set(expected), set(configured)
    missing = sorted(exp - conf)
    extra = sorted(conf - exp)
    smoke = merge_block_smoke(protection, pr_flow=pr_flow)
    enforcement_ok = all(ok for (_label, ok, _note) in smoke)
    return {
        "names_ok": not missing and not extra,
        "missing": missing,
        "extra": extra,
        "configured": sorted(conf),
        "smoke": smoke,
        "enforcement_ok": enforcement_ok,
        "pr_flow": pr_flow_enabled(protection, pr_flow),
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
    secondary = secondary_gate_jobs()
    expected = expected_checks()
    contract = advisory_contract()
    payload = {
        "workflow": WORKFLOW,
        "gate_jobs": list(gates.keys()),
        "excluded": sorted(GATE_EXCLUDE),
        "secondary_workflows": {rel: sorted(jobs)
                                for rel, jobs in secondary.items()},
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
        for rel, jobs in secondary.items():
            print(f"  (ikincil workflow: {rel} — required job'lar: "
                  f"{', '.join(jobs)})")
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
        # Strict'in uygulanabilirliğini belirleyen akış (koruma okunamadıysa
        # bilinmiyor): True = PR zorunlu, False = direct-push.
        "pr_flow": None,
        "verdict": "ERROR",
        "warning": None,
        # Advisory kontratı OFFLINE hesaplanır (workflow YAML'ından) —
        # GitHub erişilemese bile (UNREADABLE/NOT_SET_UP) JSON'da taşınır;
        # precheck job'ı `advisory_contract.ok` alanını ayrıca denetler.
        "advisory_contract": {
            k: v for k, v in contract.items() if k != "all_jobs"},
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
        "pr_flow": result["pr_flow"],
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
    print(f"  akış: {'PR zorunlu (strict uygulanır)' if result['pr_flow'] else 'direct-push (strict uygulanmaz)'}")
    for label, ok, note in result["smoke"]:
        # Not PASS'te de basılır: direct-push'ta strict satırının neden
        # yeşil olduğu (uygulanmaz) görünür kalsın.
        print(f"  [{'PASS' if ok else 'FAIL'}] {label}"
              + (f" — {note}" if note else ""))

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
