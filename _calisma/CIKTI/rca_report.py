#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""rca_report.py — kırmızı koşum için "bu kırmızı ne anlama geliyor?" tablosu.

Neden var: kırmızı bir koşum tek başına yorum değildir. Aynı ekranda üç
şey birden görünür ve bunları ayırmak zordur:

  1) Advisory bir job kırmızı — PR'yi bloklamaz, merge edilebilir.
  2) Zorunlu (required) bir job kırmızı — merge'i fiilen durdurur.
  3) Desen: tutarlı kırmızı (deterministik) / aralıklı (flaky) /
     config-drift sinyali.

Bu araç her düşen job için (job, önem, desen, kök neden ipucu, RCA belgesi,
kanıt bağlantısı, önerilen adım) satırı üretir; github_scripts/rca_comment.js
bunu PR yorumuna markdown tablo olarak düşürür.

Sınıflandırma `ci_failure_pattern.classify_job` ile Aynı kuralı kullanır
(tek sınıflandırma kaynağı); önem ayrımı branch protection'ın gerçek
required-context listesinden gelir — "advisory" kelimesine güvenilmez
(INC-2'de olduğu gibi job adı yanıltıcı olabilir).

Kullanım:
  python3 rca_report.py --run-id 37327309166            # tablo (insan okur)
  python3 rca_report.py --run-id 37327309166 --json     # makine-okur

Çıkış kodları:
  0 — rapor üretildi (düşen job olmasa bile)
  1 — gh erişilemedi / run bulunamadı
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys

import ci_failure_pattern as cfp

# Job adı (küçük harf) → (kök neden ipucu, RCA/kanıt belgesi, önerilen adım).
# Bilinmeyen job'lar "bilinmeyen desen" satırına düşer — UYDURMA metin yok,
# çünkü bu tablo kanıttır; tahmin kanıt yerine geçmez.
#
# "belge" alanı HER ZAMAN ya depoda açılabilen bir dosya yoludur ya da
# "run artifact: <yol>" ile açıkça repoda olmadığı işaretlenir. Bölüm/başlık
# işaretleri ("(INC-4)") metinde "bkz." ile verilir — çünkü yorumdaki tablo
# kanıttır ve okur yolu açıp okuyabilmelidir; açılmayan bir yol kanıttan çok
# yanıltıcıdır.
RCA_TABLE = (
    (
        "live ci doc",
        "PUBLISH_SCENARIO.md'deki job/artifact listesi canlı run ile eşleşmiyor",
        "docs/PUBLISH_SCENARIO.md",
        "audit_live_ci_sync.py çıktısındaki eksik/fazla adı doc'a işle",
    ),
    (
        "repack determinism",
        "teslim zip'i kaynakla senkron değil (son repack'tan sonra kaynak değişmiş)",
        "docs/RCA_REPACK_SIDECAR_DRIFT.md",
        "repack + zip_lineage.json + cleanup_log.json TEK commit'te üret",
    ),
    (
        "commit-msg gate",
        "commit başlığı/format kapısı ihlali",
        "_calisma/CIKTI/check_commit_messages.py",
        "check_commit_messages.py --range ile ihlali bul, başlığı yeniden yaz",
    ),
    (
        "k1-k19",
        "K katmanı kırmızı (unit test / pre-commit / deliverable)",
        "run artifact: logs/unit_tests.log",
        "run log'unda 'FAIL: test_' satırlarını oku; test adı kök nedeni verir",
    ),
    (
        "build and scan docker image",
        "Trivy taramasında CRITICAL/HIGH bulgu (taban imaj/yama katmanı)",
        "docs/DOCKER_SECURITY_PATCHING.md",
        "CVE'yi SECURITY_PATCH_PACKAGES ile kapat ya da taban imajı yükselt",
    ),
    (
        "local security smoke",
        "yerel güvenlik smoke (script parity) kırmızı",
        "docs/DOCKER_SECURITY_PATCHING.md",
        "smoke log'undaki verdict/sağlık satırlarını oku",
    ),
    (
        "texlive acceptance",
        "TeXLive kabul koşulu tutmadı (paket/derleme farkı)",
        "docs/TEX_RENDER_PIPELINE.md",
        "run log'unda pdflatex sürümü ile beklenen pini karşılaştır",
    ),
    (
        "determinism experiment",
        "trend ölçümü kayıt/teslim adımında durdu (PR yetkisi, auto-merge, onay)",
        "docs/KNOWN_INCIDENTS.md",
        "bot dalındaki kaydı koru; kayıt yolunu düzeltmeden koşumu yeşile sayma (bkz. INC-4)",
    ),
)
UNKNOWN = ("bilinmeyen desen — job log'una bak", "", "log'da ilk FAIL satırını oku")


def rca_for(job_name: str):
    """Job adına göre (kök_neden, belge, önerilen_adım)."""
    low = job_name.lower()
    for key, cause, doc, action in RCA_TABLE:
        if key in low:
            return cause, doc, action
    return UNKNOWN


def required_contexts(repo: str):
    """Branch protection'ın gerçek required context listesi + KAYNAK.

    Neden iki kaynak: GitHub'da branch protection okumak `administration`
    izni ister ve GITHUB_TOKEN'a VERİLEMEZ. Yani bu kod CI'da (asıl
    kullanıldığı yer) canlı API'yi okuyamaz ve liste boş döner — tablo
    "required bilinmiyor" diye sessizce çöker. Bu ilk canlı koşuda görüldü
    (docker-security run'ı: zorunlu 0 / advisory 0).

    Bu yüzden: canlı API başarılıysa O esas kaynaktır; başarısızsa
    `status_checks.gate_jobs()` kullanılır — o repo'nun TEK kaynağıdır
    (verify.yml job `name:` alanlarından türetilir, admin istemez).
    Dönen liste ve kaynak etiketi birlikte verilir ki tablo, ayrımın
    nereden geldiğini de söylesin.
    """
    proc = subprocess.run(
        ["gh", "api",
         f"repos/{repo}/branches/main/protection/required_status_checks"],
        capture_output=True, text=True)
    contexts = []
    if proc.returncode == 0:
        try:
            data = json.loads(proc.stdout)
        except json.JSONDecodeError:
            data = {}
        # Bu uç nokta contexts'i DÜZ liste döner; bazı sürümlerde
        # required_status_checks.{checks[],contexts[]} içine sarar. İkisi de
        # desteklenir.
        rsc = data.get("required_status_checks") or {}
        contexts = [c for c in (data.get("contexts") or []) if c]
        contexts += [c.get("context") for c in (rsc.get("checks") or [])
                     if c.get("context")]
        contexts += [c for c in (rsc.get("contexts") or []) if c]
    if contexts:
        seen, uniq = set(), []
        for c in contexts:
            if c not in seen:
                seen.add(c)
                uniq.append(c)
        return uniq, "branch-protection"
    try:
        derived = _derived_required()
    except BaseException:
        # BaseException: status_checks._require_yaml() PyYAML yoksa
        # sys.exit(2) çağırır ve SystemExit Exception'ın ALTINDA değildir.
        # `except Exception` yalnızca hatayı yutar, CI'da yine patlardı.
        derived = []
    if derived:
        return derived, "verify.yml job adları (canlı koruma okunamadı)"
    return [], "bilinmiyor"


def _derived_required(data=None):
    """verify.yml job adlarından türetilen required listesi (admin istemez).

    `status_checks.gate_jobs()` DEĞİL: o fonksiyon PyYAML yoksa
    sys.exit(2) ile süreci öldürür, ve bu fallback tam olarak PyYAML'in
    olmadığı CI'da çalışmak zorunda. Aynı TEK kaynağı (WORKFLOW yolu,
    GATE_EXCLUDE listesi) kullanır; yalnız YAML okumayı burada, kontrollü
    yaparız. `data` verilirse dosya hiç okunmaz (testler için).
    """
    import status_checks as sc
    if data is None:
        import yaml
        with open(sc.WORKFLOW, encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
    jobs = sc.all_jobs(data)
    return sorted({name for jid, name in jobs.items()
                   if jid not in sc.GATE_EXCLUDE and name})


def run_window(repo: str, workflow: str, limit: int = 10):
    """Aynı workflow'ün son N koşumundan job penceresi (flaky/deterministic için)."""
    runs = []
    proc = subprocess.run(
        ["gh", "run", "list", "--repo", repo, "--workflow", workflow,
         "--limit", str(limit), "--json", "databaseId,conclusion,status"],
        capture_output=True, text=True)
    if proc.returncode != 0:
        return runs
    try:
        runs = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return []
    timeline, jobs = cfp.analyze(runs)
    return jobs


def build_rows(run_id: str, repo: str, workflow: str, required, jobs_window):
    """(rows, meta) — düşen job'lar için RCA satırları."""
    jobs = cfp.list_jobs(repo, run_id)
    rows = []
    required_hits = 0
    for job in jobs:
        conclusion = job.get("conclusion")
        if conclusion != "failure":
            continue
        name = job.get("name") or "?"
        is_required = name in set(required) if required else None
        if is_required:
            required_hits += 1
        pattern, detail = cfp.classify_job(
            name, jobs_window.get(name, {}).get("failures", 1),
            max(1, jobs_window.get(name, {}).get("window", 1)))
        cause, doc, action = rca_for(name)
        rows.append({
            "job": name,
            "conclusion": conclusion,
            "severity": ("required" if is_required else
                         ("advisory" if is_required is False else "unknown")),
            "pattern": pattern,
            "pattern_detail": detail,
            "root_cause": cause,
            "rca_doc": doc,
            "action": action,
            "evidence": "https://github.com/%s/actions/runs/%s" % (repo, run_id),
        })
    return rows, required_hits


def build_report(run_id: str, repo: str, workflow: str, required, jobs_window,
                 required_source: str = "bilinmiyor"):
    rows, required_hits = build_rows(run_id, repo, workflow, required, jobs_window)
    advisory = sum(1 for r in rows if r["severity"] == "advisory")
    unknown = sum(1 for r in rows if r["severity"] == "unknown")
    # Verdict SAYIMLARDAN türetilir, "satır var mı"dan değil. Aksi hâlde
    # branch protection okunamadığında (unknown) "advisory-only" yazıp aynı
    # satırda "advisory kırmızı: 0" diyebilirdi — kendi kendisiyle çelişen
    # bir kanıt tablosu, tablodan daha kötüdür.
    if required_hits:
        verdict = "blocking"
    elif advisory:
        verdict = "advisory-only"
    elif rows and unknown == len(rows):
        # Hiçbir job'un önemi belirlenemedi: "bloklar mı" SORUSU boşta.
        # Uydurma yerine okuru PR kontroller sekmesine yolla.
        verdict = "indeterminate"
    else:
        verdict = "clean"
    return {
        "run_id": run_id,
        "workflow": workflow,
        "repo": repo,
        "rows": rows,
        "required_failures": required_hits,
        "advisory_failures": advisory,
        "unknown_severity": unknown,
        "required_source": required_source,
        "verdict": verdict,
    }


def render(report) -> str:
    """İnsan okur tablo (yorum betiğinin girdisi de budur)."""
    out = ["RCA — run #%s (%s)" % (report["run_id"], report["workflow"]),
           "verdict: %s | zorunlu kırmızı: %d | advisory kırmızı: %d"
           % (report["verdict"], report["required_failures"],
              report["advisory_failures"]),
           "",
           "önem listesi kaynağı: %s" % report.get("required_source", "bilinmiyor")]
    if report["verdict"] == "indeterminate":
        out.append("> **Önem ayrımı yapılamadı** — branch protection listesi "
                   "okunamadı, bu yüzden bu koşumun merge'i durdurup durdurmayacağı "
                   "bilinmiyor. PR kontroller sekmesinden bak.")
        out.append("")
    if not report["rows"]:
        out.append("(düşen job yok)")
        return "\n".join(out)
    out.append("| job | önem | desen | kök neden | belge | adım |")
    out.append("|---|---|---|---|---|---|")
    for r in report["rows"]:
        out.append("| %s | %s | %s | %s | %s | %s |" % (
            r["job"], r["severity"], r["pattern"], r["root_cause"],
            r["rca_doc"] or "—", r["action"]))
    return "\n".join(out)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--workflow", default="", help="pencere için workflow adı")
    ap.add_argument("--repo", default=None)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--out", default=None, help="JSON'u dosyaya yaz (github_scripts girdisi)")
    args = ap.parse_args(argv)

    repo = args.repo or cfp.get_repo()
    workflow = args.workflow
    if not workflow:
        # Görünen workflow adı YALNIZ başlıktır; çözülemezse rapor üretimi
        # durmaz (iş satırları ad'dan bağımsız). gh çağrısı aralıklı hata
        # veriyordu — bu yüzden ölüm değil, düşük bilgiyle devam.
        proc = subprocess.run(
            ["gh", "run", "view", args.run_id, "--repo", repo,
             "--json", "workflowName"],
            capture_output=True, text=True)
        workflow = "?"
        if proc.returncode == 0:
            try:
                workflow = json.loads(proc.stdout).get("workflowName") or "?"
            except json.JSONDecodeError:
                pass
    try:
        required, required_source = required_contexts(repo)
        window = run_window(repo, workflow) if workflow not in ("?", "") else {}
        report = build_report(args.run_id, repo, workflow, required, window,
                              required_source)
    except (RuntimeError, subprocess.CalledProcessError) as exc:
        print("HATA: run/veri alınamadı: %s" % exc, file=sys.stderr)
        return 1

    payload = json.dumps(report, indent=2, ensure_ascii=False)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(payload + "\n")
    if args.json:
        print(payload)
    else:
        print(render(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
