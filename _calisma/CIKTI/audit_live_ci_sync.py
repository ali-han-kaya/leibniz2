#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""audit_live_ci_sync.py — canlı CI denetimi: doc ↔ GitHub senkronunu doğrular.

PUBLISH_SCENARIO.md'deki Job kategorileri tablosu ve Artifact listesi, canlı
GitHub Actions run'ının GERÇEK job ve artifact adlarıyla karşılaştırılır.
Amaç: "doc ile pipeline sürüklendi" durumunu tekrar edilebilir biçimde yakala
(manuel `gh run view` + doc okuma yerine).

Karşılaştırılan iki eksen:
  1) JOB senkronu — doc tablosundaki her job adı canlı run'da olmalı; canlıda
     doc'ta OLMAYAN job varsa o da drift (doc bayat).
  2) ARTIFACT senkronu — doc artifact listesindeki her ad canlı run'da olmalı;
     canlıda doc'ta olmayan artifact varsa drift.

Fail-closed: herhangi bir eksik/fazla → exit 1 (JSON'da verdict: FAIL).
Ayrıca `REQUIRED_ARTIFACTS` (sabitlenmiş artifact'ler) doc'ta VE canlıda
mevcut olmalı — `python3-shell` her run'da beklenir (varlık/yokluk kapısı).

ARTIFACT ayrıcalığı (advisory, upstream-skipped): `needs: [verify]` ile
verify'e bağlı bir job `skipped` olduğunda (kırmızı verify → downstream
atlandı) onun artifact'ları canlıda yok diye drift sayılmaz —
`upstream_skipped` olarak raporlanır ve verdict'i bozmaz. Bu, kırmızı verify
çift cezalandırmasını (verify + advisory audit) önler. Producer'ı success
iken eksik artifact hâlâ gerçek drift'tir (FAIL).

PR-only job'lar push run'ında `skipped` görünür ama YİNE de job listesinde
yer alır — bu yüzden isim eşleşmesi event'ten bağımsız çalışır.

Kullanım:
  python3 _calisma/CIKTI/audit_live_ci_sync.py                 # son run (main)
  python3 _calisma/CIKTI/audit_live_ci_sync.py --run-id 32498… # belirli run
  python3 _calisma/CIKTI/audit_live_ci_sync.py --json          # makine-okur

Çıkış kodları:
  0 — senkron (tüm doc job/artifact canlıda, fazla yok)
  1 — drift (eksik/fazla job VEYA artifact) — fail-closed
  2 — çalışma hatası (doc yok, gh yok, run bulunamadı)
"""
import argparse
import json
import pathlib

import ci_failure_pattern
import re
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
DEFAULT_DOC = REPO_ROOT / "docs" / "PUBLISH_SCENARIO.md"

# Bu job'ın KENDİ adı/artifact'ı karşıdırmadan hariç tutulur — meta-denetçi
# olarak run'ın içinde koşar; artifact'ı denetim ADIMINDAN SONRA yüklenir.
# Doc kendi job'ını/artifact'ını LİSTEYEBİLİR (job tablosu + artifact listesi
# güncel hâlde içerir) — bu yüzden dışlama İKİ TARAFTA da uygulanır: canlı ve
# doc tarafından çıkarılıp KALAN kümeler karşılaştırılır. Tek taraflı dışlama
# "missing: <kendi adı>" ile her run'da yanlış FAIL üretir (2026-08-24, e2e
# testiyle yakalandı).
SELF_JOB = "Live CI doc↔GitHub sync audit (advisory)"
SELF_ARTIFACT = "audit-live-ci"

# SABİTLENMIŞ (pinned) artifact'ler — genel küme karşılaştırmasından BAĞIMSIZ
# olarak her run'da doc'ta VE canlıda var olmalı (fail-closed). Yeni eklenen
# kritik artifact'leri buraya ekleyin; küme karşılaştırması yalnızca "doc bayat"
# yakalar, bu liste ise "artifact düşürüldü / doc'tan çıkarıldı"yı da net
# bulgu olarak raporlar.
REQUIRED_ARTIFACTS = ["python3-shell"]


def check_required_presence(doc_artifacts, live_artifacts):
    """Sabitlenmiş artifact'lerin varlığını iki yanda da denetler.

    Döndürür: [(artifact, taraf)] — tarafta yoksa kayıt (taraf: 'doc' | 'live').
    Boş liste = hepsi her iki yanda da mevcut.
    """
    doc = set(doc_artifacts)
    liv = set(live_artifacts)
    missing = []
    for art in REQUIRED_ARTIFACTS:
        if art not in doc:
            missing.append((art, "doc"))
        if art not in liv:
            missing.append((art, "live"))
    return missing

# ── Doc parse ────────────────────────────────────────────────────────────
# Job tablosu satırları: "| 1 | A | Delivery verification — K1-K14 (...) | ✅ ... |"
_JOB_ROW_RE = re.compile(
    r"^\|\s*\d+\s*\|\s*([A-D])\s*\|\s*(.+?)\s*\|")
# Artifact satırları: "- `unit-tests` (...)" veya "- `budget-verify` + `budget` (...)"
_ARTIFACT_BULLET_RE = re.compile(r"^\s*-\s*(.+)$")

# upload-artifact bloğu: `uses:` → `with:` → `name:` (yalnızca yatay boşluk;
# \s* değil — `with:` ile `name:` arasına başka anahtar giremez).
_UPLOAD_ARTIFACT_RE = re.compile(
    r"^[ \t]*uses:[ \t]*actions/upload-artifact@\S+[ \t]*\n"
    r"[ \t]*with:[ \t]*\n"
    r"[ \t]*name:[ \t]*(\S+)[ \t]*$",
    re.M)


def extract_workflow_upload_names(wf_text):
    """Workflow metnindeki TÜM `actions/upload-artifact` `name:` değerlerini
    çıkarır (sıralı, tekil). Bu, canlı run'ın artifact kümesinin OFFLINE
    eşdeğeridir: `--doc` karşılaştırmasında canlı tarafı temsil eder ve
    yeni eklenen artifact'ları otomatik yakalar (python3-shell drift
    regression'ı — `845206a`)."""
    names = []
    for m in _UPLOAD_ARTIFACT_RE.finditer(wf_text):
        n = m.group(1).strip()
        if n and n not in names:
            names.append(n)
    return names


def parse_doc_jobs(doc_text):
    """doc'taki job tablosundan (kategori, ad) çiftlerini çıkarır.

    Yalnızca "| N | X | Ad |" biçimli satırlar (tablo başlığı/ayırıcı hariç —
    başlık "| # | Kategori | Job |" biçimindedir, eşleşmez). Kategori
    sütunundaki açıklama (ör. "A — Required ...") adla karışmaz: ikinci
    hücre yalnızca tek harftir.
    """
    jobs = []
    for line in doc_text.splitlines():
        m = _JOB_ROW_RE.match(line.strip())
        if not m:
            continue
        cat = m.group(1)
        name = m.group(2).strip()
        # Beklenen sonuç hücresi başlıyorsa (| ✅) adı kes.
        name = re.split(r"\s*\|\s*[✅❌]", name)[0].strip()
        if name and name not in (",", ""):
            jobs.append((cat, name))
    return jobs


def parse_doc_artifacts(doc_text):
    """doc'taki YALNIZCA 'Artifact listesi' bölümünden adları çıkarır.

    Bölüm "**Artifact listesi (N):**" başlığıyla başlar ve bir sonraki
    "**...:**" başlığına kadar sürer — tüm dokümandaki backtick'leri
    toplamak yanlış pozitif üretir (komut örnekleri, commit hash'leri).
    Aynı satırda + ile birden çok olabilir: "- `a` + `b` (...)".
    """
    lines = doc_text.splitlines()
    start = next((i for i, ln in enumerate(lines)
                  if ln.strip().startswith("**Artifact listesi")), None)
    if start is None:
        return []
    artifacts = []
    for ln in lines[start + 1:]:
        if ln.strip().startswith("**") and ln.strip() != lines[start].strip():
            break  # sonraki başlık — bölüm bitti
        m = _ARTIFACT_BULLET_RE.match(ln)
        if not m:
            continue
        # Yalnızca ilk açıklama parantezine KADAR olan backtick'leri al
        # ("- `unit-tests` (… `test_*.py` glob'u)" → yalnızca unit-tests;
        # açıklamadaki backtick'ler artifact adı değildir).
        head = m.group(1).split("(", 1)[0]
        names = re.findall(r"`([^`]+)`", head)
        for n in names:
            n = n.strip()
            if n and n not in artifacts:
                artifacts.append(n)
    return artifacts


# ── Artifact → producer job (ARTIFACT_JOBS) ─────────────────────────────
# gen_repro_manifest.ARTIFACT_JOBS: artifact → üreten job id. Workflow
# job id → job name + conclusion ile birleşince eksik artifact'ın
# upstream-skipped mi yoksa gerçek drift mi olduğu sınıflanır.

# ── Canlı GitHub ─────────────────────────────────────────────────────────
def run_gh(args):
    r = subprocess.run(args, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout).strip())
    return r.stdout.strip()


def get_repo():
    return run_gh(["gh", "repo", "view", "--json", "nameWithOwner",
                   "-q", ".nameWithOwner"])


def get_latest_run(repo):
    out = run_gh(["gh", "run", "list", "--repo", repo, "--branch", "main",
                  "--limit", "1", "--json", "databaseId,headSha",
                  "-q", ".[0]"])
    if not out or out == "null":
        raise RuntimeError("main branch'te run bulunamadı")
    return json.loads(out)


def get_run_jobs(repo, run_id):
    """Run'daki TÜM job adları (skipped PR-only dahil — isim eşleşmesi için
    yeterli; sonuç değil ad denetlenir)."""
    out = run_gh(["gh", "run", "view", str(run_id), "--repo", repo,
                  "--json", "jobs", "-q", ".jobs[].name"])
    return [n for n in (line.strip() for line in out.splitlines()) if n]


def get_run_artifacts(repo, run_id):
    out = run_gh(["gh", "api",
                  f"repos/{repo}/actions/runs/{run_id}/artifacts",
                  "-q", ".artifacts[].name"])
    return [n for n in (line.strip() for line in out.splitlines()) if n]


def get_run_job_conclusions(repo, run_id):
    """Run'daki job ad → conclusion eşlemesi (skipped vs failure ayrımı için).

    `skipped` (needs: yüzünden atlandı) ile `failure` ayrımı, eksik
    artifact'ın upstream-skipped mi yoksa gerçek drift mi olduğunu
    sınıflamak için gerekir — kırmızı verify → downstream skipped
    artifact'ları advisory audit'i double-punish etmemeli.
    """
    out = run_gh(["gh", "run", "view", str(run_id), "--repo", repo,
                  "--json", "jobs", "-q", ".jobs"])
    try:
        jobs = json.loads(out or "[]")
    except json.JSONDecodeError:
        jobs = []
    return {j.get("name"): j.get("conclusion") for j in jobs if j.get("name")}


# ── Karşılaştırma ────────────────────────────────────────────────────────
def compare(expected, live, label):
    exp = set(expected)
    liv = set(live)
    missing = sorted(exp - liv)   # doc'ta var, canlıda yok
    extra = sorted(liv - exp)     # canlıda var, doc'ta yok
    return {
        "label": label,
        "ok": not missing and not extra,
        "missing": missing,
        "extra": extra,
    }


# ── Artifact drift sınıflaması (skipped upstream vs gerçek drift) ───────────
_ARTIFACT_PRODUCER_CACHE = None


def _workflow_job_names():
    """verify.yml job id → job name eşlemesi (TEK KAYNAK: workflow)."""
    wf_path = REPO_ROOT / ".github" / "workflows" / "verify.yml"
    try:
        import yaml  # type: ignore
        data = yaml.safe_load(wf_path.read_text(encoding="utf-8"))
        jobs = (data or {}).get("jobs") or {}
        return {jid: (j.get("name") if isinstance(j, dict) else str(j))
                for jid, j in jobs.items()}
    except Exception:
        # Fallback: basit regex (yaml yoksa/offline)
        text = wf_path.read_text(encoding="utf-8")
        id_pat = re.compile(r"^  ([a-z0-9-]+):\s*$", re.M)
        name_pat = re.compile(r"^\s+name:\s*(.+)$", re.M)
        ids = list(id_pat.finditer(text))
        out = {}
        for idx, m in enumerate(ids):
            jid = m.group(1)
            seg_start = m.end()
            seg_end = ids[idx + 1].start() if idx + 1 < len(ids) else len(text)
            seg = text[seg_start:seg_end]
            nm = name_pat.search(seg)
            if nm:
                out[jid] = nm.group(1).strip().strip('"').strip("'")
        return out


def _artifact_producer_map():
    """Artifact → üreten job name eşlemesi (ARTIFACT_JOBS + workflow)."""
    global _ARTIFACT_PRODUCER_CACHE
    if _ARTIFACT_PRODUCER_CACHE is not None:
        return _ARTIFACT_PRODUCER_CACHE
    try:
        from gen_repro_manifest import ARTIFACT_JOBS as AJ  # noqa: WPS433
    except Exception:
        AJ = {}
    job_names = _workflow_job_names()
    m = {}
    for art, jid in AJ.items():
        name = job_names.get(jid)
        if name:
            m[art] = name
    # ARTIFACT_JOBS'de olmayan ama doc'ta olabilen artifact'lar için
    # job id == artifact id fallback (örn. pattern-drift, preview-reload-smoke)
    for art in ["pattern-drift", "preview-reload-smoke", "audit-live-ci",
                "changelog-drift", "ci-simulate"]:
        if art not in m and art in job_names:
            m[art] = job_names[art]
        elif art not in m:
            # job id tireli, name ayrı — dene: artifact → job id varsayımı
            for jid, name in job_names.items():
                if art == jid or art.replace("-", "_") == jid.replace("-", "_"):
                    m[art] = name
                    break
    _ARTIFACT_PRODUCER_CACHE = m
    return m


def classify_artifact_drift(expected, live, conclusions=None):
    """Eksik artifact'ları upstream-skipped vs gerçek drift olarak ayırır.

    conclusions: {job name → conclusion} ("skipped", "failure", "success" …).
    Producer'ı `skipped` olan eksik artifact'lar `upstream_skipped`'e gider
    ve `ok`'u bozmaz — kırmızı verify → downstream skipped double-punish
    etmez. Diğer tüm eksik/fazla gerçek drift'tir (fail-closed).
    """
    conclusions = conclusions or {}
    exp = set(expected)
    liv = set(live)
    missing_raw = sorted(exp - liv)
    extra = sorted(liv - exp)
    producer_map = _artifact_producer_map()
    missing = []
    upstream_skipped = []
    for art in missing_raw:
        producer = producer_map.get(art)
        if producer and conclusions.get(producer) == "skipped":
            upstream_skipped.append(art)
        else:
            # Fallback: conclusion bilinmiyor ama artifact zaten biliniyor —
            # üretici skipped değilse gerçek drift.
            missing.append(art)
    upstream_skipped = sorted(upstream_skipped)
    ok = not missing and not extra
    return {
        "label": "artifacts",
        "ok": ok,
        "missing": missing,
        "extra": extra,
        "upstream_skipped": upstream_skipped,
    }


def exclude_self(live_jobs, live_artifacts):
    """Denetçinin kendi job/artifact adını listeden çıkarır.

    Dönüş değeri (temizlenmiş jobs, temizlenmiş artifacts) — çağıran doc
    tarafına da aynı dışlamayı uygulamalıdır (bkz. main)."""
    return ([n for n in live_jobs if n != SELF_JOB],
            [n for n in live_artifacts if n != SELF_ARTIFACT])


def build_combined_report(doc_result, failure_result):
    """Tek artifact için doc/live drift ve CI failure sınıflarını birleştir."""
    return {
        "schema": "audit-live-ci/v2",
        "doc_live_sync": doc_result,
        "failure_pattern": failure_result,
        "verdict": ("FAIL" if doc_result.get("verdict") == "FAIL"
                     or (failure_result and failure_result.get("categories", {}).get("deterministic"))
                     else "PASS"),
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--doc", default=str(DEFAULT_DOC),
                    help="PUBLISH_SCENARIO.md yolu (varsayılan: docs/)")
    ap.add_argument("--run-id", default=None, help="run ID (varsayılan: son run)")
    ap.add_argument("--json", action="store_true", help="makine-okur JSON")
    ap.add_argument("--with-failure-pattern", action="store_true",
                    help="aynı JSON'a son CI run failure sınıflandırmasını ekle")
    args = ap.parse_args(argv)

    doc_path = pathlib.Path(args.doc)
    if not doc_path.is_file():
        print(f"HATA: doc bulunamadı ({doc_path})", file=sys.stderr)
        return 2
    doc_text = doc_path.read_text(encoding="utf-8")

    doc_jobs = parse_doc_jobs(doc_text)
    doc_artifacts = parse_doc_artifacts(doc_text)
    if not doc_jobs:
        print(f"HATA: doc'ta job tablosu satırı bulunamadı ({doc_path})",
              file=sys.stderr)
        return 2

    try:
        repo = get_repo()
    except RuntimeError as e:
        print(f"HATA: repo belirlenemedi ({e})", file=sys.stderr)
        return 2

    try:
        if args.run_id:
            run_id = args.run_id
        else:
            run_id = str(get_latest_run(repo)["databaseId"])
    except RuntimeError as e:
        print(f"HATA: run bulunamadı ({e})", file=sys.stderr)
        return 2

    try:
        live_jobs = get_run_jobs(repo, run_id)
        live_artifacts = get_run_artifacts(repo, run_id)
        try:
            conclusions = get_run_job_conclusions(repo, run_id)
        except RuntimeError:
            conclusions = {}
    except RuntimeError as e:
        print(f"HATA: canlı veri çekilemedi ({e})", file=sys.stderr)
        return 2

    # Meta-deneteyi kendini iki taraftan da çıkarır (bkz. SELF_JOB/SELF_ARTIFACT)
    # — doc kendi satırını/listesini içerse bile denetim "kalan gerçek küme"yi
    # karşılaştırmalı; aksi halde her run'da kendini missing olarak raporlar.
    live_jobs, live_artifacts = exclude_self(live_jobs, live_artifacts)
    doc_jobs = [(c, n) for (c, n) in doc_jobs if n != SELF_JOB]
    doc_artifacts = [n for n in doc_artifacts if n != SELF_ARTIFACT]

    doc_job_names = [n for (_cat, n) in doc_jobs]
    job_cmp = compare(doc_job_names, live_jobs, "jobs")
    art_cmp = classify_artifact_drift(doc_artifacts, live_artifacts, conclusions)

    # Sabitlenmiş artifact varlığı (doc + live) — fail-closed kapı.
    # Advisory için upstream-skipped durumu true missing sayılmaz: kırmızı
    # verify → needs:[verify] artifact'ları skipped → python3-shell canlıda
    # yoksa bile double-punish olmamalı. Pinned kapı yalnızca producer
    # skipped değilken eksikse FAIL verir.
    _req_doc_missing = check_required_presence(doc_artifacts, doc_artifacts)
    _req_live_raw = check_required_presence(live_artifacts, live_artifacts)
    # Her pinned için producer conclusion'a bak
    producer_map = _artifact_producer_map()
    req_missing = []
    for art, side in _req_doc_missing:
        req_missing.append((art, side))
    for art, side in _req_live_raw:
        # side her zaman "live" burada (live_raw doc==live)
        prod = producer_map.get(art)
        if prod and conclusions.get(prod) == "skipped":
            continue
        req_missing.append((art, side))

    art_ok = art_cmp["ok"]
    ok = job_cmp["ok"] and art_ok and not req_missing
    verdict = "PASS" if ok else "FAIL"
    doc_result = {
        "verdict": verdict,
        "repo": repo,
        "run_id": run_id,
        "doc": str(doc_path),
        "jobs": {
            "doc": doc_job_names,
            "live": sorted(live_jobs),
            "missing": job_cmp["missing"],
            "extra": job_cmp["extra"],
        },
        "artifacts": {
            "doc": doc_artifacts,
            "live": sorted(live_artifacts),
            "missing": art_cmp["missing"],
            "extra": art_cmp["extra"],
            "upstream_skipped": art_cmp.get("upstream_skipped", []),
            "required_presence": {
                "ok": not req_missing,
                "missing": [f"{art} ({side})" for art, side in req_missing],
                "artifacts": REQUIRED_ARTIFACTS,
            },
        },
    }
    failure_result = None
    if args.with_failure_pattern:
        try:
            runs = ci_failure_pattern.list_runs(repo, None, ci_failure_pattern.DEFAULT_LIMIT)
            timeline, jobs = ci_failure_pattern.analyze(runs)
            failure_result = ci_failure_pattern.summarize(timeline, jobs)
            failure_result["flaky_count"] = len(failure_result["categories"]["flaky"])
            failure_result["deterministic_count"] = len(failure_result["categories"]["deterministic"])
        except (RuntimeError, ValueError, TypeError) as e:
            failure_result = {"verdict": "ERROR", "error": str(e)}

    if args.json:
        report = (build_combined_report(doc_result, failure_result)
                  if args.with_failure_pattern else doc_result)
        print(json.dumps(report,
            indent=2, ensure_ascii=False))
        hard_fail = (not ok or
                     bool(failure_result and failure_result.get("categories", {}).get("deterministic")))
        return 0 if not hard_fail else 1

    if args.with_failure_pattern and failure_result:
        print("\n── FAILURE PATTERN ──")
        print(json.dumps(failure_result, indent=2, ensure_ascii=False))

    print(f"Canlı CI denetimi — {repo} (run {run_id})")
    print(f"doc: {doc_path}")
    print(f"\nSONUÇ: {verdict} — {'doc ↔ GitHub senkron' if ok else 'DRIFT'}")
    hard_fail = (not ok or
                 bool(failure_result and failure_result.get("categories", {}).get("deterministic")))
    return 0 if not hard_fail else 1


if __name__ == "__main__":
    sys.exit(main())
