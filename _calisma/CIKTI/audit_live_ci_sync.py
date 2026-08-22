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
PR-only job'lar push run'ında `skipped` görünür ama YİNE de run job listesinde
yer alır — o yüzden isim eşleşmesi event'ten bağımsız çalışır.

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
import re
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
DEFAULT_DOC = REPO_ROOT / "docs" / "PUBLISH_SCENARIO.md"

# Bu job'ın KENDİ adı/artifact'ı karşılaştırmadan hariç tutulur — meta-denetçi
# olarak run'ın içinde koşar; kendi artifact'ı denetim ADIMINDAN SONRA yüklenir
# (her run'da "fazla job/eksik artifact" yanlış-pozitif üretir). Doc tablosu
# bu job'ı içermez (advisory meta-araçtır, teslim pipeline'ı değil).
SELF_JOB = "Live CI doc↔GitHub sync audit (advisory)"
SELF_ARTIFACT = "audit-live-ci"

# ── Doc parse ────────────────────────────────────────────────────────────
# Job tablosu satırları: "| 1 | A | Delivery verification — K1-K14 (...) | ✅ ... |"
_JOB_ROW_RE = re.compile(
    r"^\|\s*\d+\s*\|\s*([A-D])\s*\|\s*(.+?)\s*\|")
# Artifact satırları: "- `unit-tests` (...)" veya "- `budget-verify` + `budget` (...)"
_ARTIFACT_BULLET_RE = re.compile(r"^\s*-\s*(.+)$")


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


def exclude_self(live_jobs, live_artifacts):
    """Denetçi job'ının kendi adını/artifact'ını canlı listeden çıkarır."""
    return ([n for n in live_jobs if n != SELF_JOB],
            [n for n in live_artifacts if n != SELF_ARTIFACT])


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--doc", default=str(DEFAULT_DOC),
                    help="PUBLISH_SCENARIO.md yolu (varsayılan: docs/)")
    ap.add_argument("--run-id", default=None, help="run ID (varsayılan: son run)")
    ap.add_argument("--json", action="store_true", help="makine-okur JSON")
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
    except RuntimeError as e:
        print(f"HATA: canlı veri çekilemedi ({e})", file=sys.stderr)
        return 2

    # Meta-denetçi kendini karşılaştırmaz (bkz. SELF_JOB/SELF_ARTIFACT).
    live_jobs, live_artifacts = exclude_self(live_jobs, live_artifacts)

    doc_job_names = [name for (_cat, name) in doc_jobs]
    job_cmp = compare(doc_job_names, live_jobs, "jobs")
    art_cmp = compare(doc_artifacts, live_artifacts, "artifacts")
    ok = job_cmp["ok"] and art_cmp["ok"]
    verdict = "PASS" if ok else "FAIL"

    if args.json:
        print(json.dumps({
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
            },
        }, indent=2, ensure_ascii=False))
    else:
        print(f"Canlı CI denetimi — {repo} (run {run_id})")
        print(f"doc: {doc_path}")
        print(f"\n── JOB senkronu ──")
        print(f"  doc: {len(doc_job_names)} job | canlı: {len(live_jobs)} job")
        for n in job_cmp["missing"]:
            print(f"  [FAIL] doc'ta var, canlıda YOK: {n}")
        for n in job_cmp["extra"]:
            print(f"  [FAIL] canlıda var, doc'ta YOK: {n}")
        if not job_cmp["missing"] and not job_cmp["extra"]:
            print("  birebir eşleşiyor")
        print(f"\n── ARTIFACT senkronu ──")
        print(f"  doc: {len(doc_artifacts)} artifact | canlı: {len(live_artifacts)} artifact")
        for n in art_cmp["missing"]:
            print(f"  [FAIL] doc'ta var, canlıda YOK: {n}")
        for n in art_cmp["extra"]:
            print(f"  [FAIL] canlıda var, doc'ta YOK: {n}")
        if not art_cmp["missing"] and not art_cmp["extra"]:
            print("  birebir eşleşiyor")
        print(f"\nSONUÇ: {verdict} — {'doc ↔ GitHub senkron' if ok else 'DRIFT: doc bayat (yukarıdaki [FAIL] satırları)'}")

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
