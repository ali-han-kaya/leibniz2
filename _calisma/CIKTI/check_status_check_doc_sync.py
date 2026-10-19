#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_status_check_doc_sync.py — publish dokümanlarındaki ELLE yazılmış
check sayılarını status_checks.py türetimine bağlayan senkron kapısı.

Neden (ölçülen kök neden): branch protection required listesi workflow job
`name:` alanlarından türetilir (`status_checks.py` — tek kaynak), ama
PUBLISH_SCENARIO.md ve docs/branch-protection-guide/ içindeki sayılar ELLE
yazılıdır. Workflow'a required job eklenince (ör. dashboard-smoke, a11y-gate,
texlive-accept) doküman sürükleniyor: operatör GitHub'da eksik check seçiyor,
merge ya hiç bloke olmuyor ya da yanlış kapıya bağlanıyor. Bu kapı o sayıları
türetimden yeniden hesaplar ve birebir eşleşme arar.

Sözleşme (fail-closed):
  1. Türetim tek kaynaktan: `workflow_contract.GATE_EXCLUDE` + verify.yml job
     `name:`leri (status_checks.py API'si). Kapı workflow'u KENDİ ayrıştırmaz.
  2. `SITES`: her beyan yeri (dosya + regex) TAM OLARAK BİR kez eşleşmeli.
     0 eşleşme = beyan/metin kayboldu (sessiz kapsam kaybı) → FAIL;
     >1 eşleşme = belirsiz beyan (hangisi doğru?) → FAIL.
  3. Sayı beyanları türetilen değere BİREBİR eşit olmalı (total/required/
     advisory/pr_only).
  4. Liste beyanları KÜME olarak karşılaştırılır: required check adları
     listeleri türetilen ad kümesine, "required DEĞİL PR-only" job id listesi
     türetilen id kümesine eşit olmalı (sayı doğru ama liste eksikse — 15
     sayısı + 12 ad — operatör eksik seçer; ikisi birlikte denetlenir).
  5. Bazı sayı benzeri metinler BİLİNÇLİ olarak kapsam dışıdır (tarihli run
     kayıtları, K katman aralıkları, başka kapının sözleşmesi): EXCLUSIONS'da
     gerekçesiyle listelenir; testleri bu çapaların dosyada HÂLÂ var olduğunu
     denetler (gerekçe çürürse sessizce kapsam dışına kaymasın).

Türetilen kategori kuralı (docs'taki "N required + M advisory + K PR-only"):
  required       = GATE_EXCLUDE'da OLMAYAN job'lar (status_checks.gate_jobs)
  pr_only        = `if:` koşulunda `github.event_name == 'pull_request'` olan
                   ve required OLMAYAN job'lar (PR yorum/kapı işleri)
  advisory       = ne required ne pr_only olan job'lar
  total          = verify.yml'deki tüm job'lar
  NOT: required ∧ pr_only boş DEĞİLDİR (ör. label-gate, commit-msg-gate PR'da
  koşar ama BİLEREK required'dır) — bu yüzden split "required dışı" üzerinden
  yapılır, "PR-only = 3" beklentisi bu kurala dayanır.

Kullanım:
  python3 _calisma/CIKTI/check_status_check_doc_sync.py          # denetle
  python3 _calisma/CIKTI/check_status_check_doc_sync.py --json   # makine-okur

Exit: 0 = senkron; 1 = drift veya beyan kaybı; 2 = ölçüm imkânsız
(PyYAML yok / dosya yok / workflow okunamadı). Sessiz PASS yoktur.
"""
import argparse
import json
import pathlib
import re
import sys

_HERE = pathlib.Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import status_checks as sc  # noqa: E402  (tek kaynak türetim)

REPO = _HERE.parent.parent
PUBLISH = "docs/PUBLISH_SCENARIO.md"
GUIDE_README = "docs/branch-protection-guide/README.md"
GUIDE_HTML = "docs/branch-protection-guide/guide.html"

# ── Sayı beyanları ─────────────────────────────────────────────────────────
# fields: regex'teki yakalama gruplarının soldan sağa karşılık geldiği
# türetilmiş anahtarlar. Sıra DEĞİŞTİRİLEMEZ (regex grubu ↔ alan eşlemesi).
SITES = (
    # PUBLISH_SCENARIO.md
    {"id": "ps-job-table-intro", "file": PUBLISH,
     "pattern": r"\*\*(\d+) job\*\*'u 4 kategoride",
     "fields": ("total",)},
    {"id": "ps-ci-watch", "file": PUBLISH,
     "pattern": r"# 3\) CI'ı izle \((\d+) job — (\d+) required \+ (\d+) "
                r"advisory \+ (\d+) PR-only",
     "fields": ("total", "required", "advisory", "pr_only")},
    {"id": "ps-incremental-verify", "file": PUBLISH,
     "pattern": r"\((\d+) check \+ merge engeli smoke\)",
     "fields": ("required",)},
    {"id": "ps-status-checks-usage", "file": PUBLISH,
     "pattern": r"#\s+python3 _calisma/CIKTI/status_checks\.py\s+#\s+"
                r"(\d+) ad workflow'dan türetilir",
     "fields": ("required",)},
    {"id": "ps-webui-list-intro", "file": PUBLISH,
     "pattern": r"#\s+→ (\d+) check \(adlar = workflow job",
     "fields": ("required",)},
    {"id": "ps-verify-output", "file": PUBLISH,
     "pattern": r"# SONUÇ: PASS — (\d+) check birebir eşleşiyor",
     "fields": ("required",)},
    {"id": "ps-label-gate-total", "file": PUBLISH,
     "pattern": r"\(toplam (\d+) check\)",
     "fields": ("required",)},
    {"id": "ps-webui-heading", "file": PUBLISH,
     "pattern": r"### Branch protection — web UI adım adım "
                r"\((\d+) required check\)",
     "fields": ("required",)},
    {"id": "ps-webui-name-count", "file": PUBLISH,
     "pattern": r"Arama kutusuna şu \*\*(\d+) adı\*\*",
     "fields": ("required",)},
    {"id": "ps-merge-watch", "file": PUBLISH,
     "pattern": r"# required check'ler \((\d+) kapı\) TAMAMLANMADAN",
     "fields": ("required",)},
    {"id": "ps-job-categories", "file": PUBLISH,
     "pattern": r"\*\*Job kategorileri \((\d+) job = (\d+) required \+ "
                r"(\d+) advisory \+ (\d+) PR-only\):\*\*",
     "fields": ("total", "required", "advisory", "pr_only")},
    # branch-protection-guide/README.md
    {"id": "guide-readme-intro", "file": GUIDE_README,
     "pattern": r"sırayla gösterir \((\d+) required check için\)",
     "fields": ("required",)},
    {"id": "guide-readme-step4", "file": GUIDE_README,
     "pattern": r"Arama kutusuna (\d+) check adını tek tek yazıp seç",
     "fields": ("required",)},
    {"id": "guide-readme-step7", "file": GUIDE_README,
     "pattern": r'"(\d+) status checks · 1 approving review"',
     "fields": ("required",)},
    {"id": "guide-readme-step8", "file": GUIDE_README,
     "pattern": r"^(\d+) check \+ merge engeli smoke",
     "fields": ("required",)},
    # branch-protection-guide/guide.html (PNG'lerin kaynağı)
    {"id": "guide-html-comment", "file": GUIDE_HTML,
     "pattern": r"ADIM 4 — Status checks \((\d+) kapı\)",
     "fields": ("required",)},
    {"id": "guide-html-caption4", "file": GUIDE_HTML,
     "pattern": r"Require status checks — (\d+) check \+ up-to-date",
     "fields": ("required",)},
    # ADIM 6 ("Create" ekranı) — kural listesinde seçili check sayısı görünür.
    # Bu beyan bir kez atlanmıştı (9 kalmıştı): ekranın kendi "N status checks"
    # metni ADIM 4/7 kapsamına girmediği için kapı sessizce yeşil kalıyordu.
    {"id": "guide-html-step6-selected", "file": GUIDE_HTML,
     "pattern": r"(\d+) status checks selected · strict",
     "fields": ("required",)},
    {"id": "guide-html-caption7", "file": GUIDE_HTML,
     "pattern": r"Kural oluştu — liste: <code>main</code> "
                r'<span class="desc">(\d+) status checks',
     "fields": ("required",)},
    {"id": "guide-html-card7", "file": GUIDE_HTML,
     "pattern": r"(\d+) status checks · 1 approving review — All changes",
     "fields": ("required",)},
    {"id": "guide-html-term-header", "file": GUIDE_HTML,
     "pattern": r"Beklenen status check adları \((\d+)\)",
     "fields": ("required",)},
    {"id": "guide-html-term-ellipsis", "file": GUIDE_HTML,
     "pattern": r"… \((\d+) kapı\)",
     "fields": ("required",)},
    {"id": "guide-html-term-verdict", "file": GUIDE_HTML,
     "pattern": r"SONUÇ: PASS — (\d+) check birebir eşleşiyor",
     "fields": ("required",)},
)

# ── Liste beyanları ────────────────────────────────────────────────────────
# kind: "required_names" → türetilen required ad kümesine eşit olmalı
#       "pr_only_ids"    → türetilen (required OLMAYAN) PR-only job id kümesi
# bölge: start..end arası satırlar; item_re her öğeyi yakalar.
LIST_SITES = (
    {"id": "ps-required-names-bash", "file": PUBLISH, "kind": "required_names",
     "start": r"#\s+→ \d+ check \(adlar = workflow job",
     "end": r"#\s+→ ✓ \"Require branches",
     # Bash yorum bloğu: `#   <ad>`; ilk satır script çağrısı + `# Ad` biçiminde.
     "item": r"^#\s+(?:python3 \S+\s+#\s+)?(\S.*?)\s*$",
     "skip": (r"^#\s+→", r"^#\s+\(", r"^#\s+—")},
    {"id": "ps-required-names-numbered", "file": PUBLISH,
     "kind": "required_names",
     "start": r"Arama kutusuna şu \*\*\d+ adı\*\*",
     "end": r"^\s+> \*\*Not:",
     "item": r"^\s*\d+\.\s*`([^`]+)`\s*$",
     "skip": ()},
    {"id": "guide-html-checkboxes", "file": GUIDE_HTML,
     "kind": "required_names",
     "start": r'<div class="check-list">',
     "end": r'<div class="erow"',
     "item": r'aria-label="([^"]+)" checked',
     "skip": (r"Require branches to be up to date",)},
    {"id": "ps-pr-only-note", "file": PUBLISH, "kind": "pr_only_ids",
     "start": r"\(PR-only ama required DEĞİL:",
     "end": r"^#\s+— push'ta çalışmaz",
     # Job id deseni: küçük harfle başlar, en az bir tireli parça içerir
     # (`label-gate-p1`). "PR-only"/"only" gibi kelime parçalarını yakalamaz.
     "item": r"([a-z][a-z0-9]*(?:-[a-z0-9]+)+)",
     "skip": ()},
)

# ── Kapsam dışı (gerekçeli) ────────────────────────────────────────────────
# Bu metinler sayı gibi görünür ama BİZİM sözleşmemizin dışındadır. Testleri
# hâlâ dosyada olduklarını denetler: gerekçe çürürse (metin değişir/kaybolur)
# kapsam sessizce daralmış olmasın.
EXCLUSIONS = (
    {"file": PUBLISH, "anchor": "**18 job** çalışıldı (8 required",
     "reason": "2026-08-21 tarihli run kaydı (canlı doğrulama transcript'i) — "
               "o günün job sayısı; bugünkü sözleşme değil"},
    {"file": PUBLISH, "anchor": "43 step-level site, 16 job",
     "reason": "continue-on-error denetim kaydı — '16 job' coe yüzeyi sayısı, "
               "check kategorisi değil; sözleşmesi test_advisory_coe_surfacing"},
    {"file": PUBLISH, "anchor": "(0 job); GitHub Actions UI'ında run boş "
                                "görünüyordu",
     "reason": "tarihsel hata anlatısı (0 job'lık boş run vakası)"},
    {"file": PUBLISH, "anchor": "--full K1-K14 +",
     "reason": "K katman aralığı (verify_delivery katmanları) — status check "
               "sayısı değil; ayrı sözleşme (test_verify_k_layers)"},
)

DERIVED_KEYS = ("total", "required", "advisory", "pr_only")


class MeasurementError(RuntimeError):
    """Ölçüm imkânsız (workflow/dosya okunamadı, PyYAML yok) — exit 2."""


def _workflow_jobs(root):
    """verify.yml job'ları: {job_id: {"name":…, "if":…}} (PyYAML gerekir)."""
    import yaml  # yerel import: yoksa MeasurementError (yukarıda yakalanır)

    path = root / ".github" / "workflows" / "verify.yml"
    if not path.is_file():
        raise MeasurementError(f"verify.yml yok: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    jobs = data.get("jobs") or {}
    return {jid: {"name": (j or {}).get("name") if isinstance(j, dict) else None,
                  "if": str((j or {}).get("if", "")) if isinstance(j, dict) else ""}
            for jid, j in jobs.items()}


def derive(root=REPO):
    """Dokümanların beyan ettiği sayıları TEK KAYNAKTAN türet.

    required kümesi status_checks.gate_jobs() (GATE_EXCLUDE dışı) ile, PR-only
    kümesi job `if:` koşuluyla belirlenir; advisory = kalanlar. Döndürür:
    {total, required, advisory, pr_only, required_names, pr_only_ids,
     pr_only_required_ids}.
    """
    try:
        jobs = _workflow_jobs(root)
    except ImportError as exc:  # pragma: no cover — PyYAML'sız ortam
        raise MeasurementError(f"PyYAML yok ({exc}) — venv python kullanın")
    except MeasurementError:
        raise
    except Exception as exc:  # pragma: no cover — bozuk YAML
        raise MeasurementError(f"verify.yml ayrıştırılamadı: {exc}")

    required_ids = set(_gate_job_ids(root))
    if not required_ids:
        raise MeasurementError("required job kümesi boş — GATE_EXCLUDE/verify.yml "
                               "okunamadı")
    for jid in required_ids:
        if jid not in jobs:
            raise MeasurementError(
                f"required job id '{jid}' verify.yml'de yok (bayat exclude?)")
    pr_only_ids = {jid for jid, meta in jobs.items()
                   if "github.event_name == 'pull_request'" in meta["if"]}
    if not pr_only_ids:
        raise MeasurementError("hiç PR-only job bulunamadı — `if:` deseni "
                               "değişmiş olabilir (türetim kör)")
    nonreq_pr_only = pr_only_ids - required_ids
    advisory_ids = set(jobs) - required_ids - pr_only_ids
    names = {jid: jobs[jid]["name"] for jid in jobs}
    return {
        "total": len(jobs),
        "required": len(required_ids),
        "advisory": len(advisory_ids),
        "pr_only": len(nonreq_pr_only),
        "required_names": sorted(names[jid] for jid in required_ids),
        "pr_only_ids": sorted(nonreq_pr_only),
        "pr_only_required_ids": sorted(pr_only_ids & required_ids),
    }


def _gate_job_ids(root):
    """status_checks.gate_jobs() job id'leri (root farklıysa geçici yönlendir).

    status_checks WORKFLOW yolunu kendi konumundan çözer; testler/başka
    checkout'lar için `--root` verildiğinde o yolu kullanırız.
    """
    if pathlib.Path(root).resolve() == REPO.resolve():
        return list(sc.gate_jobs().keys())
    original = sc.WORKFLOW
    try:
        sc.WORKFLOW = str(pathlib.Path(root) / ".github" / "workflows"
                          / "verify.yml")
        return list(sc.gate_jobs().keys())
    finally:
        sc.WORKFLOW = original


def _read(root, rel):
    path = pathlib.Path(root) / rel
    if not path.is_file():
        raise MeasurementError(f"beyan dosyası yok: {rel}")
    return path.read_text(encoding="utf-8")


def check_counts(text, derived, site):
    """Tek sayı beyanını denetle — (findings, matches) döndür."""
    findings = []
    matches = list(re.finditer(site["pattern"], text, re.M))
    if len(matches) != 1:
        findings.append({
            "site": site["id"], "kind": "match-count",
            "detail": f"{len(matches)} eşleşme (tam olarak 1 olmalı) — "
                      f"beyan kayboldu ya da belirsizleşti",
        })
        return findings, matches
    groups = matches[0].groups()
    if len(groups) != len(site["fields"]):
        raise MeasurementError(
            f"{site['id']}: regex {len(groups)} grup, {len(site['fields'])} "
            "alan bekleniyor")
    for field, raw in zip(site["fields"], groups):
        if int(raw) != derived[field]:
            findings.append({
                "site": site["id"], "kind": "drift", "field": field,
                "doc": int(raw), "derived": derived[field],
            })
    return findings, matches


def check_list(text, derived, site):
    """Tek liste beyanını denetle — (findings, items) döndür.

    Bölge start..end arasındadır (start satırı dahil — item regex'i karar
    verir). Öğe kümesi türetilen kümeye eşit olmalı; eksik/fazla öğe FAIL.
    """
    findings = []
    start = re.search(site["start"], text, re.M)
    # end çapası start'tan SONRA aranır: aynı işaret başka bir ekranda
    # (zaten var olan bir `.erow` gibi) start'tan önce de geçebilir; ilk
    # eşleşmeyi almak bölgeyi ters çevirip beyanı sahte "kayıp" gösterirdi.
    end = re.search(site["end"], text[start.end():], re.M) if start else None
    if not start or not end:
        findings.append({
            "site": site["id"], "kind": "match-count",
            "detail": "bölge çapaları bulunamadı (start/end) — beyan kayboldu",
        })
        return findings, []
    region = text[start.end():start.end() + end.start()]
    items = []
    for line in region.splitlines():
        if any(re.search(skip, line) for skip in site["skip"]):
            continue
        # Satır başına BİRDEN FAZLA öğe olabilir (virgülle ayrılmış id listesi) —
        # tek `search` yalnız ilkini alır ve listeyi sessizce eksik okurdu.
        items.extend(m.group(1).strip() for m in re.finditer(site["item"], line))
    if site["kind"] == "required_names":
        expected = set(derived["required_names"])
    elif site["kind"] == "pr_only_ids":
        # Virgül/boşluk ayrımlı id listesi: bölgedeki tüm id benzeri
        # parçaları topla, türetilen kümeyle karşılaştır.
        items = sorted({i for i in items if not i[0].isdigit()})
        expected = set(derived["pr_only_ids"])
    else:
        raise MeasurementError(f"bilinmeyen liste türü: {site['kind']}")
    found = set(items)
    if found != expected:
        findings.append({
            "site": site["id"], "kind": "list-drift",
            "missing": sorted(expected - found),
            "extra": sorted(found - expected),
        })
    return findings, items


def check(root=REPO):
    """Tüm beyanları denetle — (derived, findings, texts) döndür."""
    derived = derive(root)
    texts = {rel: _read(root, rel) for rel in (PUBLISH, GUIDE_README, GUIDE_HTML)}
    findings = []
    for site in SITES:
        site_findings, _ = check_counts(texts[site["file"]], derived, site)
        findings.extend(site_findings)
    for site in LIST_SITES:
        site_findings, _ = check_list(texts[site["file"]], derived, site)
        findings.extend(site_findings)
    for excl in EXCLUSIONS:
        if excl["anchor"] not in texts[excl["file"]]:
            findings.append({
                "site": "exclusion-anchor", "kind": "stale-exclusion",
                "detail": f"kapsam dışı gerekçesi çürüdü ({excl['file']}): "
                          f"{excl['anchor']!r} artık dosyada yok",
            })
    return derived, findings, texts


def format_report(derived, findings, files=None):
    lines = ["check-status-check-doc-sync: türetim (status_checks ↔ verify.yml)",
             f"  required={derived['required']}  advisory={derived['advisory']}  "
             f"pr_only={derived['pr_only']}  total={derived['total']}"]
    if files:
        for rel, text in files.items():
            lines.append(f"  {rel}: {len(text.splitlines())} satır")
    if findings:
        lines.append("FAIL — beyan ↔ türetim drift'i:")
        for f in findings:
            if f["kind"] == "drift":
                lines.append(f"  • {f['site']}: doküman {f['doc']} ↔ türetim "
                             f"{f['derived']} (alan: {f['field']})")
            elif f["kind"] == "list-drift":
                if f.get("missing"):
                    lines.append(f"  • {f['site']}: eksik: {f['missing']}")
                if f.get("extra"):
                    lines.append(f"  • {f['site']}: fazla: {f['extra']}")
            else:
                lines.append(f"  • {f['site']}: {f['detail']}")
        lines.append("  Remediy: python3 _calisma/CIKTI/status_checks.py "
                     "(türetilen adlar) → doküman sayılarını/listelerini eşitle.")
    else:
        lines.append("PASS — tüm beyanlar türetimle birebir")
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=str(REPO),
                    help="repo kökü (varsayılan: script konumu)")
    ap.add_argument("--json", action="store_true", help="makine-okur çıktı")
    args = ap.parse_args(argv)

    try:
        derived, findings, texts = check(pathlib.Path(args.root))
    except MeasurementError as exc:
        if args.json:
            print(json.dumps({"verdict": "ERROR", "error": str(exc)},
                             ensure_ascii=False, indent=2))
        else:
            print(f"check-status-check-doc-sync: ÖLÇÜM İMKÂNSIZ — {exc}",
                  file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps({
            "verdict": "FAIL" if findings else "PASS",
            "derived": derived,
            "sites": [s["id"] for s in SITES],
            "list_sites": [s["id"] for s in LIST_SITES],
            "findings": findings,
        }, ensure_ascii=False, indent=2))
        return 1 if findings else 0

    print(format_report(derived, findings, texts))
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
