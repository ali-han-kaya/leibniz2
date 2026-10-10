"""
_adapter.py — Live CI Dashboard'un Vercel serverless adaptör gövdesi.

Yerel daemon'un /api yüzeyini (preview_server.py) Vercel'in /api dizini
dosya-tabanlı Python-runtime'ına taşır. Kural: yerel-yüzeyi TAKLİT ETMEK
yerine repo'daki TEK-KAYNAK yardımcıları İMPORT edip aynı veri-
sözleşmelerini üretmek (dashboard JS'i şema-değişmeden çalışır).

Veri-gerçeği (ölçülmüş, 2026-09-23):
  - git'te yaşayan canlı-veri: docs/determinism_trend/determinism_trend.jsonl
    (bot haftalık commitler) → /api/determinism-trend GERÇEK-değerli çalışır.
  - git-dışı (yerel çalışma-ürünü, Vercel-checkout'unda YOK):
    _calisma/CIKTI/history.jsonl, runs/, refs_trend.json →
      /api/run-history → GitHub Actions API türetimi (public repo)
      /api/trend       → boş-durum fallback'leri (yerel dosya-yok dallarıyla
                         aynı şekil)
  - /api/health → 200 "ok" düz-metin (yerel birebir).

Handler-biçemi: Vercel 2026 dosya-tabanlı sözleşme — BaseHTTPRequestHandler
alt-sınıfı (api/*.py). JSON-uzmanlığı burada: compact + ensure_ascii=False
+ no-store (yerel _send'in JSON-bacağı); hata-şekli {"error": ...}
(api_error kardeşi). Detaylar: docs/VERCEL_DEPLOYMENT.md.
"""
import json
import os
import re
import sys
import urllib.request

# ── Import-yolu-bootstrap (tek-gerçek kaynak; handler'larda yalnız köprü) ───
# Vercel-runtime handler'ı DOSYA-YOLUNDAN exec eder: `api/` sys.path'de değil
# (log: ModuleNotFoundError: '_adapter'). Bu blok, adaptörün kendisi ilk
# import edilirken yolları kurar; handler'larda aynı bloğu çoğaltmamak için
# bilinçli tek-kaynak. CIKTI-yolu SONA append: repo-kökündeki modül-adları
# stdlib/kendi modüllerimizi gölgelemesin (index'ler: script-dir + CWD önce;
# yalnız gerçekten-eksik import'lar CIKTI'ya düşer; CIKTI'da stdlib-gölge
# adı yok — denetlendi 2026-09-23). Idempotent (çift-exec'e dayanıklı).
_HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (_HERE, os.path.join(os.path.dirname(_HERE), "_calisma", "CIKTI")):
    if _p not in sys.path:
        sys.path.append(_p)

# ── Repo-kaynak yardımcıları (tek-kaynak sözleşme) ─────────────────────────
# preview_server.py import-etkisi-yansız (main()'e dek modül-seviyesi çağrı
# yok — ölçüldü: tek __main__ guard'ı); kütüphane olarak import edilebilir.
from preview_server import _project_history_record, load_history  # noqa: E402

# ── Yol-çözümü ──────────────────────────────────────────────────────────────
# Vercel: CWD = proje-kökü (runtime-doc). Yerel test repo-kökünden koşar;
# aynı çözüm iki bağlamda da doğru. preview_server.py'nin _HERE tabanlı
# PREVIEW_DIR sabitine DOKUNULMAZ (mirror-layout sözleşmesi); adaptör
# veri-yollarını kendisi çözer.
# api/ → repo-kökü: dosya-çapası, Vercel-CWD'den bağımsız (yerel testte
# os.chdir gereksinimini de kaldırır; mirror-layout sözleşmesi bozulmaz).
REPO_ROOT = os.path.dirname(_HERE)

DET_TREND_REL = "docs/determinism_trend/determinism_trend.jsonl"
GH_API_RUNS = "https://api.github.com/repos/{slug}/actions/runs?per_page=15"
OWNER_REPO_DEFAULT = "ali-han-kaya/leibniz2"


def _repo_slug():
    """GitHub Actions'da GITHUB_REPOSITORY; lokalde git-remote'tan."""
    if os.environ.get("GITHUB_REPOSITORY"):
        return os.environ["GITHUB_REPOSITORY"]
    try:
        import subprocess
        out = subprocess.run(["git", "remote", "get-url", "origin"],
                             capture_output=True, text=True,
                             timeout=10).stdout
        m = re.search(r"[:/]([^/:]+/[^/:]+?)(?:\.git)?\s*$", out)
        if m:
            return m.group(1)
    except Exception:
        pass
    return OWNER_REPO_DEFAULT


def _det_trend_path():
    return os.path.join(REPO_ROOT, DET_TREND_REL)


def jbody(data, status=200):
    """Yerel _send'in JSON-bacağı: compact + ensure_ascii=False."""
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


def jresp(data, status=200):
    return {"statusCode": status, "body": jbody(data)}


def jerror(status, message):
    """api_error(status, msg) kardeşi: yerel {"error": ...} şekli."""
    return jresp({"error": message}, status)


def _fetch(url):
    headers = {"Accept": "application/vnd.github+json",
               "User-Agent": "leibniz2-dashboard-adapter"}
    if os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = "Bearer " + os.environ["GITHUB_TOKEN"]
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read().decode("utf-8"))


# ── /api/run-history: GitHub Actions API'sinden türetim ────────────────────
def run_history_from_github(limit=15):
    """Yerel serve_run_history'nin satır-şemasını Actions-API'den üretir.

    Yerel satır-şeması (preview_server.serve_run_history): {ts, verdict,
    p0, p1, budget_usd, budget_limit, budget_method, duration_s,
    refs_verified, refs_total, pdf_pages, z3_passed, z3_total, lean_ok,
    lean_detail}. CI'da metrikler log'larda yaşadığından None taşınır
    (dashboard "—" basar); verdict=conclusion, ts=created_at. +2 bilinçli
    ek: workflow (ad), url (html_url). Anlam-yitimi bilinçli
    (docs/VERCEL_DEPLOYMENT.md §Sınırlar).
    """
    data = _fetch(GH_API_RUNS.format(slug=_repo_slug()))
    rows = []
    for run in data.get("workflow_runs", [])[:limit]:
        conclusion = run.get("conclusion")
        rows.append({
            "ts": run.get("created_at"),
            "verdict": ("PASS" if conclusion == "success"
                        else "FAIL" if conclusion == "failure" else "?"),
            "p0": None, "p1": None,
            "budget_usd": None, "budget_limit": None, "budget_method": None,
            "duration_s": None,
            "refs_verified": None, "refs_total": None,
            "pdf_pages": None, "z3_passed": None, "z3_total": None,
            "lean_ok": None, "lean_detail": None,
            "workflow": run.get("name"),
            "url": run.get("html_url"),
        })
    return rows


def api_run_history():
    try:
        return jresp(run_history_from_github())
    except Exception as e:
        return jerror(502, "github actions unavailable: " + str(e))


def api_trend():
    """Yerel serve_trend birebir: history + refs_trend tek round-trip;
    git-dışı veri yokken yerel dosya-yok fallback'i (aynı şekil)."""
    history = [_project_history_record(rec) for rec in load_history()
               if isinstance(rec, dict)]
    refs_path = os.path.join(REPO_ROOT, "_calisma/CIKTI/refs_trend.json")
    if not os.path.isfile(refs_path):
        refs_trend = {"rows": [], "duration_budget": {"rows": []}}
    else:
        try:
            with open(refs_path, encoding="utf-8") as f:
                loaded = json.load(f)
            refs_trend = loaded if isinstance(loaded, dict) else {"rows": []}
        except (OSError, ValueError):
            refs_trend = {"error": "refs trend unavailable"}
    return jresp({"history": history, "refs_trend": refs_trend})


def api_determinism_trend():
    """Yerel serve_determinism_trend birebir: AYNI badge-yardımcısı,
    git'te yaşayan gerçek trend-dosyasından."""
    import determinism_trend_badge as dtb
    rows = dtb.rows_from(_det_trend_path()) or []
    enriched = [dict(r, badge=dtb.badge([r])) for r in rows]
    return jresp({"badge": dtb.badge(rows), "rows": enriched})
