#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_surface_cwv_report.py — üç yüzeyin CWV (Core Web Vitals) raporu.

İDDİA: repodaki ÜÇ kullanıcı-yüzeyi de yüklenirken CWV bütçelerinin altında
kalır — dashboard (`_calisma/CIKTI/preview.html`), landing
(`_calisma/landing/landing.html`) ve `apps/dashboard-next` (Next 15 panosu).

Neden bu dosya var: `test_dashboard_cls_budget.py` CLS'i yalnız dashboard için
ölçer. Landing ve dashboard-next için "sayfa zıplamıyor / geç boyanmıyor"
iddiasını ölçen hiçbir şey yoktu. Bu dosya AYNI ölçüm çekirdeğini
(`test_dashboard_cls_budget.CLS_RECORDER` + session-window matematiği) üç
yüzeye koşturup tek deterministik raporda birleştirir; ölçüm hatları
kopyalanmaz, import edilir (drift kapısı: `test_cls_math_is_shared_with_
dashboard_gate`).

Ölçüm yöntemi (dashboard kapısıyla birebir aynı çekirdek):
  * CLS — `layout-shift` PerformanceObserver sayfa yüklenmeden önce
    `add_init_script` ile kurulur; `hadRecentInput` atlanır; girdiler
    "session window" kuralıyla (komşu < 1 sn, pencere < 5 sn) toplanır ve
    EN BÜYÜK pencere CLS olur. Python tarafı aynı kuralı girdilerden
    yeniden hesaplar ve JS değeriyle karşılaştırır (iki uygulama = tek kural).
  * LCP — `largest-contentful-paint` observer'ın son girdisi (ms).
  * FCP — `paint` girdilerinden `first-contentful-paint` (ms).
  * TTFB — `navigation` girdisinden responseStart - startTime (ms).
  Bu üç metrik Web Vitals eşikleriyle KAPIDIR: "observer kuruldu ama değer
  hiç gelmedi" durumu PASS değil FAIL'dir (ölü ölçüm = yeşil değil).

INP neden yok: Event Timing (INP) bu ortamda ÖLÇÜLEMİYOR — başsız
Chromium'da gerçek `page.click` + `page.keyboard.press` sonrası
`performance.getEntriesByType('event')` BOŞ dönüyor (probe: interactionId
taşıyan 0 girdi). Uydurma bir sayı üretmek yerine kapsam dışı bırakıldı;
raporda yalnız `interaction_entries` GÖZLEMİ taşınır (kapı değil) — Chromium
bir gün girdi yayınlarsa bu sayaç sıfırdan büyük görünür ve INP eklenebilir.

Yüzeyler ve sunum (§ CI ile aynı staging kuralı):
  1. dashboard      → `/preview.html?theme=<dark|light>` (preview_server)
  2. landing        → `/landing.html` + `/landing/assets/*.png` (preview_server;
     dosyalar geçici bir staging dizinine kopyalanır — CI'da
     `build_landing.py --output _calisma/CIKTI/landing.html` ile mirror'a
     stage edilen düzenin eşdeğeri)
  3. dashboard-next → `/` (`next start`, mevcut `.next` derlemesi,
     `PREVIEW_API=<preview_server>` + `TREND_SOURCE=preview`)

Fail-closed guard'lar:
  * Layout-shift desteklenmiyor / observer kurulamadı → FAIL.
  * Yüzey panelleri ya da yüzeye özgü metin yoksa → FAIL (boş/hatalı sayfa
    ölçmek anlamsızdır; Next hata sayfası da buraya düşer). Canlı sunucuya
    işaret edildiğinde beklenen VERİ de zorunludur; sunucuyu kendimiz
    açtığımızda boş-mirror iskeleti geçerli sayılır (mirror durumu
    versiyonlanmaz, taze klonda history.jsonl yoktur).
  * Metrik yok / sayısal değil / NaN / sonsuz / negatif → FAIL.
  * Canlı sunucu (`DASHBOARD_BASE_URL`, `CWV_DASHBOARD_NEXT_BASE_URL`)
    erişilemezse → FAIL (açıkça istendi, sessizce geçilmez).
  * `landing.html` ya da `.next/BUILD_ID` yoksa → FAIL (taze artefakt yok).
  * Negatif kontrol: statik yüzeye SONRADAN 400 px yapay kaydırma enjekte
    edilir; ölçüm hattının onu GÖRDÜĞÜ ve bütçeyi AŞTIĞI doğrulanır.

Env override'ları:
  CWV_SURFACES               virgülle ayrılmış yüzey listesi
                             (varsayılan: dashboard,landing,dashboard-next)
  DASHBOARD_BASE_URL         canlı preview_server tabanı (dashboard + landing);
                             verilmezse taze preview_server başlatılır
  CWV_DASHBOARD_NEXT_BASE_URL canlı Next sunucusu tabanı; verilmezse
                             `next start` ile kendisi başlatılır
  DASHBOARD_THEME            dark | light (varsayılan: dark) — dashboard URL'i
  CLS_BUDGET                 CLS bütçesi (varsayılan 0.1; paylaşılan env)
  CWV_LCP_BUDGET_MS          LCP bütçesi (varsayılan 2500)
  CWV_FCP_BUDGET_MS          FCP bütçesi (varsayılan 1800)
  CWV_TTFB_BUDGET_MS         TTFB bütçesi (varsayılan 800)
  CWV_REPORT_PATH            verilirse deterministik JSON rapor yazılır

Çalıştırma:
  python3 _calisma/CIKTI/test_surface_cwv_report.py            # üç yüzey
  CWV_SURFACES=landing python3 _calisma/CIKTI/test_surface_cwv_report.py
"""

import hashlib
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(HERE))

# Ölçüm çekirdeği TEK kaynaktan: CLS recorder'ı, session-window matematiği,
# bütçe kararı ve sunucu yardımcıları dashboard kapısından import edilir.
sys.path.insert(0, HERE)
import test_dashboard_cls_budget as cwv_core  # noqa: E402

try:
    from playwright.sync_api import sync_playwright
except ImportError:  # CI runner'da playwright kurulu değilse SKIP (fail değil)
    sync_playwright = None

SERVER_SCRIPT = os.path.join(HERE, "preview_server.py")
LANDING_DIR = os.path.join(REPO_ROOT, "_calisma", "landing")
NEXT_DIR = os.path.join(REPO_ROOT, "apps", "dashboard-next")
NEXT_BUILD_ID = os.path.join(NEXT_DIR, ".next", "BUILD_ID")

# Web Vitals "good" eşikleri (web.dev). CLS eşiği paylaşılan çekirdekten
# gelir; diğerleri burada sabittir ve env ile geçici override edilebilir.
BUDGETS_DEFAULT = {
    "cls": cwv_core.BUDGET_DEFAULT,
    "fcp_ms": 1800.0,
    "lcp_ms": 2500.0,
    "ttfb_ms": 800.0,
}
BUDGET_ENV = {
    "cls": "CLS_BUDGET",
    "fcp_ms": "CWV_FCP_BUDGET_MS",
    "lcp_ms": "CWV_LCP_BUDGET_MS",
    "ttfb_ms": "CWV_TTFB_BUDGET_MS",
}

VALID_THEMES = cwv_core.VALID_THEMES
SETTLE_MS = cwv_core.SETTLE_MS
READY_TIMEOUT_MS = 20000
# Yapay kaydırma bütçesi: çekirdeğin negatif kontrolüyle aynı büyüklük.
ARTIFICIAL_SHIFT_PX = cwv_core.ARTIFICIAL_SHIFT_PX

# Yüzey kayıt defteri — SIRA kanoniktir (rapor da bu sırayla yazılır).
SURFACE_ORDER = ("dashboard", "landing", "dashboard-next")

SURFACE_SPECS = {
    "dashboard": {
        "url_path": "/preview.html?theme={theme}",
        "server": "preview",
        "theme_scoped": True,
        "ready": "#m-verdict",
        "panels": ("#m-verdict", "#status-board", "#badges"),
        "content": ("Verdict",),
        "content_any": ("PASS", "FAIL"),
        # Sunucuyu BİZ açtığımızda mirror'ın koşum geçmişi (history.jsonl +
        # runs/) klonda YOKTUR; o durumda "no run yet" iskeleti sayfanın
        # gerçek durumudur ve CLS ölçümü yine anlamlıdır. Ama canlı bir
        # sunucuya işaret edildiğinde (DASHBOARD_BASE_URL) veri GERÇEKTEN
        # gelmiş olmalı — gevşetme o iddiayı düşürürdü (CI bu yüzden strict).
        "content_any_offline": ("PASS", "FAIL", "no run yet"),
        "inp_target": "#status-board",
        "artifacts": ("_calisma/CIKTI/preview.html", "_calisma/CIKTI/preview.js"),
    },
    "landing": {
        "url_path": "/landing.html",
        "server": "preview",
        "theme_scoped": False,
        "ready": "#chain",
        "panels": ("#chain", "#proof", "#cta"),
        "content": ("teslim anına kadar.",),
        "content_any": (),
        "inp_target": "#chain h2",
        "artifacts": ("_calisma/landing/landing.html",),
    },
    "dashboard-next": {
        "url_path": "/",
        "server": "next",
        "theme_scoped": False,
        # Paneller artık shadcn `Card` (div[data-slot="card"]) — `<section>`
        # kalktı. data-slot shadcn'ın kararli kancası (registry'den gelir ve
        # `has-data-[slot=…]` varyantlari onu anahtarlar), yol ise markupsiz
        # bir `h2` bulamaz. Ölçüm sözleşmesi GERÇEK markup'ı izlemeli:
        # eski `main section` seçicisi sessizce "panel yok" sanıp FAIL eder.
        "ready": 'main [data-slot="card"]',
        "panels": ('main [data-slot="card"]', 'main [data-slot="card"] h2',
                   "header nav"),
        "content": ("Son Koşum",),
        # Trend paneli veriyle doldu mu: satır varsa tablo, yoksa boş-durum
        # metni. Panelin hiç gelmemesi (Suspense'te takılı kalması) FAIL.
        "content_any": ("ZAMAN", "henüz veri yok"),
        "inp_target": 'main [data-slot="card"] h2',
        # `.next` gitignore'lu bir derleme çıktısı: BUILD_ID derlemeyi,
        # build-manifest chunk listesini kilitler — rapor "hangi derleme
        # ölçüldü" sorusunu yanıtlar.
        "artifacts": ("apps/dashboard-next/.next/BUILD_ID",
                      "apps/dashboard-next/.next/build-manifest.json"),
    },
}

ENV_SURFACES = "CWV_SURFACES"
ENV_REPORT_PATH = "CWV_REPORT_PATH"
ENV_LIVE_PREVIEW = "DASHBOARD_BASE_URL"
ENV_LIVE_NEXT = "CWV_DASHBOARD_NEXT_BASE_URL"


# --------------------------------------------------------------- ölçüm JS
# Çekirdek CLS recorder'ının ÜSTÜNE CWV probe'u eklenir; tek `add_init_script`
# ile ikisi de sayfa yüklenmeden kurulur.
CWV_PROBE = r"""
window.__cwvProbe = {
  lcp: null, fcp: null, ttfb: null, observers: {}, errors: [],
  interactionEntries: 0,
};
(function () {
  var probe = window.__cwvProbe;
  function observe(type, cb) {
    try {
      var observer = new PerformanceObserver(cb);
      observer.observe({ type: type, buffered: true });
      probe.observers[type] = true;
    } catch (e) {
      probe.observers[type] = false;
      probe.errors.push(type + ': ' + e);
    }
  }
  observe('largest-contentful-paint', function (list) {
    var entries = list.getEntries();
    var last = entries[entries.length - 1];
    if (last) probe.lcp = { startTime: last.startTime, size: last.size };
  });
  observe('paint', function (list) {
    for (var entry of list.getEntries()) {
      if (entry.name === 'first-contentful-paint') probe.fcp = entry.startTime;
    }
  });
  observe('event', function (list) {
    for (var entry of list.getEntries()) {
      if (entry.interactionId) probe.interactionEntries += 1;
    }
  });
  function readNavigation() {
    var nav = performance.getEntriesByType('navigation')[0];
    if (nav) probe.ttfb = nav.responseStart - nav.startTime;
  }
  if (document.readyState === 'complete') readNavigation();
  else window.addEventListener('load', readNavigation);
})();
"""

CWV_RECORDER = cwv_core.CLS_RECORDER + "\n" + CWV_PROBE


# --------------------------------------------------------- saf karar (browser'sız)
def evaluate_metric(value, budget, label="metrik"):
    """(ok, reason) — `evaluate_budget` ile AYNI fail-closed sözleşme.

    Ölçülemeyen bir metrik PASS sayılamaz: aksi halde "observer kuruldu ama hiç
    girdi gelmedi" durumu sessizce yeşil görünürdü.
    """
    if value is None:
        return False, "%s ölçülemedi (değer yok) — fail-closed" % label
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False, "%s sayısal değil: %r" % (label, value)
    if math.isnan(value):
        return False, "%s NaN" % label
    if math.isinf(value):
        return False, "%s sonsuz" % label
    if value < 0:
        return False, "%s negatif: %s" % (label, value)
    if value < budget:
        return True, "%s %.3f < bütçe %s" % (label, value, budget)
    return False, "%s %.3f >= bütçe %s" % (label, value, budget)


def resolve_budgets(env=None):
    """Bütçe tablosunu env override'larıyla kurar; geçersiz değer → ValueError.

    CLS bütçesi paylaşılan `CLS_BUDGET` env'ini çekirdeğin kendi doğrulayıcısıyla
    okur (aynı sözleşme: pozitif sonlu sayı).
    """
    env = os.environ if env is None else env
    budgets = {"cls": cwv_core.resolve_budget(env.get("CLS_BUDGET", ""))}
    for key in ("fcp_ms", "lcp_ms", "ttfb_ms"):
        raw = (env.get(BUDGET_ENV[key]) or "").strip()
        if not raw:
            budgets[key] = BUDGETS_DEFAULT[key]
            continue
        try:
            value = float(raw)
        except ValueError:
            raise ValueError("%s sayısal değil: %r" % (BUDGET_ENV[key], raw))
        if not math.isfinite(value) or value <= 0:
            raise ValueError(
                "%s pozitif sonlu sayı olmalı: %r" % (BUDGET_ENV[key], raw))
        budgets[key] = value
    return budgets


def resolve_surfaces(env=None):
    """CWV_SURFACES env'ini kanonik sıralı tuple'a çevirir (fail-closed).

    Boş/verilmemiş → tüm yüzeyler. Bilinmeyen ad → ValueError: sessizce
    atlamak, istenen yüzeyin hiç ölçülmemesini gizlerdi.
    """
    env = os.environ if env is None else env
    raw = (env.get(ENV_SURFACES) or "").strip()
    if not raw:
        return SURFACE_ORDER
    requested = [token.strip() for token in raw.split(",") if token.strip()]
    if not requested:
        return SURFACE_ORDER
    unknown = sorted(set(requested) - set(SURFACE_ORDER))
    if unknown:
        raise ValueError("%s bilinmeyen yüzey içeriyor: %s (geçerli: %s)" % (
            ENV_SURFACES, ", ".join(unknown), ", ".join(SURFACE_ORDER)))
    selected = set(requested)
    return tuple(name for name in SURFACE_ORDER if name in selected)


def explicit_surface_request(env=None):
    """CWV_SURFACES'te AÇIKÇA istenen yüzeyler (boşsa boş küme)."""
    env = os.environ if env is None else env
    raw = (env.get(ENV_SURFACES) or "").strip()
    return {token.strip() for token in raw.split(",") if token.strip()}


def drop_unavailable_surfaces(surfaces, env=None, build_id_path=None):
    """(kalan yüzeyler, düşürüldü_mü) — derleme yoksa next yüzeyi düşer.

    Varsayılan koşum her yerde çalışabilmeli (tam süit keşfi dahil):
    `apps/dashboard-next/.next` taze bir checkout'ta YOKTUR ve orada ölçüm
    yapılamaz. Ama yüzey AÇIKÇA istenmişse (CWV_SURFACES=dashboard-next)
    sessizce atlamak yanlış olurdu — o durumda fail-closed kalır ve
    `artifacts_for` derleme istisnasını yükseltir.
    """
    build_id_path = NEXT_BUILD_ID if build_id_path is None else build_id_path
    if ("dashboard-next" in surfaces and not os.path.isfile(build_id_path)
            and "dashboard-next" not in explicit_surface_request(env)):
        return tuple(s for s in surfaces if s != "dashboard-next"), True
    return tuple(surfaces), False


def resolve_theme(env=None):
    """DASHBOARD_THEME'i çekirdeğin doğrulayıcısıyla okur (dark|light)."""
    env = os.environ if env is None else env
    return cwv_core.resolve_theme(env.get("DASHBOARD_THEME", ""))


def surface_url_path(name, theme):
    path = SURFACE_SPECS[name]["url_path"]
    return path.format(theme=theme) if SURFACE_SPECS[name]["theme_scoped"] else path


def surface_theme(name, theme):
    """Raporda yüzeyin hangi temada ölçüldüğü (landing/next tema-dışı)."""
    return theme if SURFACE_SPECS[name]["theme_scoped"] else "default"


def content_present(spec, text, live=False):
    """(yüzey gerçekten render oldu mu) — içerik metni + veri kaynağı şartı.

    `live=True` (base env ile verildi): beklenen veri durumları zorunludur.
    `live=False` (sunucuyu biz açtık): yüzeyin boş-mirror iskelet hâli de
    geçerlidir (`content_any_offline`), çünkü mirror durumu versiyonlanmaz.
    """
    haystack = text.lower()
    if not all(s.lower() in haystack for s in spec["content"]):
        return False
    allowed = (spec["content_any"] if live
               else spec.get("content_any_offline", spec["content_any"]))
    return not allowed or any(s.lower() in haystack for s in allowed)


def checks_for(metrics, panels_present, content_present, supported,
               observer_installed, budgets):
    """Yüzey başına deterministik check tablosu (fail-closed)."""
    ok, reason = cwv_core.evaluate_budget(metrics.get("cls"), budgets["cls"])
    checks = {"cls": {"verdict": "PASS" if ok else "FAIL", "reason": reason}}
    for key, label in (("fcp_ms", "FCP"), ("lcp_ms", "LCP"), ("ttfb_ms", "TTFB")):
        ok, reason = evaluate_metric(metrics.get(key), budgets[key], label)
        checks[key] = {"verdict": "PASS" if ok else "FAIL", "reason": reason}
    return checks


def surface_verdict(checks, panels_present, content_present, supported,
                    observer_installed):
    """Yüzey PASS'ı: ölçüm canlı + içerik gerçek + tüm metrikler bütçe altı."""
    if not (supported and observer_installed and panels_present and content_present):
        return "FAIL"
    if not checks:
        return "FAIL"
    return "PASS" if all(c["verdict"] == "PASS" for c in checks.values()) else "FAIL"


def aggregate_verdict(surfaces):
    """Tüm yüzeyler PASS ise PASS; eksik/FAIL varsa FAIL (fail-closed)."""
    if not surfaces:
        return "FAIL"
    for name in SURFACE_ORDER:
        if name in surfaces and surfaces[name].get("verdict") != "PASS":
            return "FAIL"
    return "PASS"


def build_report(surfaces, budgets):
    """Deterministik JSON raporu — port/zaman damgası YOK (sıralı anahtarlar).

    URL'ler port taşır ve her koşumda değişir; raporda yalnız yüzeyin
    `url_path`'i tutulur (`/preview.html?theme=dark` gibi), böylece iki koşumun
    raporu bayt-bayt karşılaştırılabilir kalır.
    """
    return {
        "budgets": budgets,
        "surfaces": surfaces,
        "verdict": aggregate_verdict(surfaces),
    }


def write_report(path, report):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, sort_keys=True, ensure_ascii=False)
        f.write("\n")


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def artifacts_for(name):
    """Ölçülen artefaktların içerik imzası + (next için) derleme kimliği.

    Rapor "neyi ölçtük" sorusunu yanıtlamalı: landing.html yeniden üretilirse
    hash değişir ve iki rapor arasındaki fark ölçüm gürültüsü değil artefakt
    farkıdır.
    """
    files = {}
    for rel in SURFACE_SPECS[name]["artifacts"]:
        full = os.path.join(REPO_ROOT, rel)
        if not os.path.isfile(full):
            raise RuntimeError(
                "%s artefaktı yok: %s — ölçülecek yüzey diskte değil" % (name, rel))
        files[rel] = sha256_file(full)
    extra = {}
    if name == "dashboard-next":
        if not os.path.isfile(NEXT_BUILD_ID):
            raise RuntimeError(
                "apps/dashboard-next/.next/BUILD_ID yok — derleme gerekli: "
                "npm run build --prefix apps/dashboard-next")
        with open(NEXT_BUILD_ID, encoding="utf-8") as f:
            extra["build_id"] = f.read().strip()
    return files, extra


# ------------------------------------------------------------------ sunucular
def stage_preview_dir(names, dest):
    """preview_server'ın beklediği staging dizinini kurar (CI mirror eşdeğeri).

    Mirror dizininin TAMAMI symlink'lenir: `/api/latest` ve `/api/trend`
    verisini `PREVIEW_DIR` altında arar (`history.jsonl`, `runs/`), ayrıca
    preview.html + preview.js oradan servis edilir. Yalnız kopyalasaydık
    sunucu BOŞ bir mirror görür, dashboard "no run yet" diye ölçülürdü —
    yani ölçüm gerçek sayfa değil iskelet olurdu.

    Landing ise KOPYALANIR (symlink değil): `serve_landing_assets` gerçekpath
    guard'ı ağacı `PREVIEW_DIR/landing/assets` altında tutmak ister; kopya
    CI'nın `build_landing.py --output _calisma/CIKTI/landing.html` staging'iyle
    aynı düzendir.
    """
    os.makedirs(dest, exist_ok=True)
    for entry in sorted(os.listdir(HERE)):
        if entry in ("landing.html", "landing"):
            continue  # landing bu koşumda staging'den serve edilir
        src = os.path.join(HERE, entry)
        link = os.path.join(dest, entry)
        if os.path.lexists(link):
            continue
        try:
            os.symlink(src, link)
        except OSError:  # symlink desteklenmiyorsa kopyala (davranış aynı)
            if os.path.isdir(src):
                shutil.copytree(src, link, symlinks=True)
            else:
                shutil.copy2(src, link)
    if "dashboard" in names:
        for fname in ("preview.html", "preview.js"):
            if not os.path.exists(os.path.join(dest, fname)):
                raise RuntimeError("preview mirror dosyası yok: %s" % fname)
    if "landing" in names:
        src = os.path.join(LANDING_DIR, "landing.html")
        if not os.path.isfile(src):
            raise RuntimeError(
                "landing.html yok: %s — önce build_landing.py ile üret "
                "(python3 _calisma/landing/build_landing.py)" % src)
        shutil.copyfile(src, os.path.join(dest, "landing.html"))
        assets_src = os.path.join(LANDING_DIR, "assets")
        assets_dest = os.path.join(dest, "landing", "assets")
        os.makedirs(assets_dest, exist_ok=True)
        pngs = sorted(n for n in os.listdir(assets_src)
                      if n.lower().endswith(".png"))
        if not pngs:
            raise RuntimeError("landing asset PNG yok: %s" % assets_src)
        for name in pngs:
            shutil.copyfile(os.path.join(assets_src, name),
                            os.path.join(assets_dest, name))
    return dest


def read_log_tail(path, limit=1500):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read()[-limit:]
    except OSError:
        return "<log okunamadı>"


def spawn_preview_server(preview_dir, port, log_path):
    """Yüzeyleri sunan preview_server'ı ücretsiz portta başlatır (fail-closed)."""
    log = open(log_path, "w", encoding="utf-8")
    try:
        proc = subprocess.Popen(
            [sys.executable, SERVER_SCRIPT,
             "--dir", HERE,
             "--preview-dir", preview_dir,
             "--port", str(port),
             "--bind", "127.0.0.1",
             "--interval", "3600"],
            cwd=HERE, stdout=log, stderr=subprocess.STDOUT)
    finally:
        # Çocuk kendi fd kopyasını aldı; parent'ın handle'ı burada kapanır
        # (aksi halde ResourceWarning + log dosyası açık kalır).
        log.close()
    if not cwv_core.wait_for_port("127.0.0.1", port, timeout=20):
        proc.terminate()
        proc.wait(timeout=5)
        raise RuntimeError(
            "preview_server 127.0.0.1:%s üzerinde başlamadı:\n%s" % (
                port, read_log_tail(log_path)))
    return proc


def spawn_next_server(port, preview_api, log_path):
    """`next start` ile dashboard-next yüzeyini ayağa kaldırır (fail-closed)."""
    build_id = artifacts_for("dashboard-next")[1]["build_id"]
    binary = os.path.join(NEXT_DIR, "node_modules", ".bin", "next")
    if not os.path.isfile(binary):
        raise RuntimeError(
            "apps/dashboard-next/node_modules/.bin/next yok — "
            "npm ci --prefix apps/dashboard-next gerekli")
    env = dict(os.environ)
    # Server Component fetch'i runtime env'den okunur (NEXT_PUBLIC_ değil):
    # `next start` sonrası override çalışır. Trend kaynağı açıkça `preview`
    # seçilir → DB parolası olmayan makinede de aynı ölçüm.
    env["PREVIEW_API"] = preview_api
    env["TREND_SOURCE"] = "preview"
    log = open(log_path, "w", encoding="utf-8")
    try:
        proc = subprocess.Popen(
            [binary, "start", "-H", "127.0.0.1", "-p", str(port)],
            cwd=NEXT_DIR, env=env, stdout=log, stderr=subprocess.STDOUT)
    finally:
        log.close()
    if not cwv_core.wait_for_port("127.0.0.1", port, timeout=45):
        proc.terminate()
        proc.wait(timeout=5)
        raise RuntimeError(
            "next start 127.0.0.1:%s üzerinde başlamadı (build %s):\n%s" % (
                port, build_id, read_log_tail(log_path)))
    return proc


def http_get(url, timeout=20):
    """Isınma isteği: ilk isteğin soğuk-yol gecikmesini ölçüme karıştırma."""
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return resp.status, resp.read()


def terminate(proc):
    if proc is None:
        return
    try:
        proc.terminate()
        try:
            proc.wait(timeout=8)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=8)
    except OSError:
        pass


# ------------------------------------------------------------- saf süit
class SurfaceCwvReportContractTest(unittest.TestCase):
    """Browser'sız: bütçe kararı, yüzey kayıt defteri, rapor determinizmi."""

    def test_metric_verdict_is_fail_closed(self):
        self.assertTrue(evaluate_metric(10.0, 20.0, "LCP")[0])
        self.assertFalse(evaluate_metric(20.0, 20.0, "LCP")[0],
                         "tam bütçe değeri FAIL olmalı (iddia kesin küçüktür)")
        self.assertFalse(evaluate_metric(None, 20.0, "LCP")[0])
        self.assertFalse(evaluate_metric(float("nan"), 20.0, "LCP")[0])
        self.assertFalse(evaluate_metric(float("inf"), 20.0, "LCP")[0])
        self.assertFalse(evaluate_metric(-1.0, 20.0, "LCP")[0])
        self.assertFalse(evaluate_metric("10", 20.0, "LCP")[0])
        self.assertFalse(evaluate_metric(True, 20.0, "LCP")[0])

    def test_thresholds_match_web_vitals_good_limits(self):
        self.assertEqual(BUDGETS_DEFAULT["cls"], 0.1)
        self.assertEqual(BUDGETS_DEFAULT["lcp_ms"], 2500.0)
        self.assertEqual(BUDGETS_DEFAULT["fcp_ms"], 1800.0)
        self.assertEqual(BUDGETS_DEFAULT["ttfb_ms"], 800.0)

    def test_budget_env_overrides_validate(self):
        budgets = resolve_budgets({"CLS_BUDGET": "0.25",
                                   "CWV_LCP_BUDGET_MS": "3000"})
        self.assertEqual(budgets["cls"], 0.25)
        self.assertEqual(budgets["lcp_ms"], 3000.0)
        self.assertEqual(budgets["fcp_ms"], 1800.0)
        for env in ({"CWV_LCP_BUDGET_MS": "abc"},
                    {"CWV_TTFB_BUDGET_MS": "0"},
                    {"CWV_FCP_BUDGET_MS": "-5"},
                    {"CWV_LCP_BUDGET_MS": "nan"},
                    {"CLS_BUDGET": "-1"}):
            with self.assertRaises(ValueError):
                resolve_budgets(env)

    def test_cls_math_is_shared_with_dashboard_gate(self):
        """Drift kapısı: CWV recorder'ı çekirdek CLS recorder'ını taşır."""
        self.assertTrue(CWV_RECORDER.startswith(cwv_core.CLS_RECORDER))
        self.assertIn("__clsBudget", CWV_RECORDER)
        self.assertIs(cwv_core.cls_from_session_windows,
                      sys.modules["test_dashboard_cls_budget"].cls_from_session_windows)
        # Çekirdeğin kendi matematiğiyle aynı sonucu vermeli (tek kural).
        entries = [(0.0, 0.01), (900.0, 0.02), (3000.0, 0.05)]
        self.assertAlmostEqual(cwv_core.cls_from_session_windows(entries), 0.05)

    def test_surface_registry_is_complete(self):
        self.assertEqual(SURFACE_ORDER, ("dashboard", "landing", "dashboard-next"))
        for name in SURFACE_ORDER:
            spec = SURFACE_SPECS[name]
            for key in ("url_path", "server", "ready", "panels", "content",
                        "content_any", "artifacts", "theme_scoped"):
                self.assertIn(key, spec, "%s: %s eksik" % (name, key))
            self.assertTrue(spec["url_path"].startswith("/"))
            self.assertTrue(spec["panels"])
            self.assertTrue(spec["content"])
            self.assertIn(spec["server"], ("preview", "next"))
        # Her yüzey bir sunucu yoluyla sunulabilmeli.
        self.assertEqual(
            sorted({SURFACE_SPECS[n]["server"] for n in SURFACE_ORDER}),
            ["next", "preview"])

    def test_surface_selection_defaults_and_validates(self):
        self.assertEqual(resolve_surfaces({}), SURFACE_ORDER)
        self.assertEqual(resolve_surfaces({ENV_SURFACES: "  "}), SURFACE_ORDER)
        self.assertEqual(resolve_surfaces({ENV_SURFACES: "landing"}), ("landing",))
        # Kanonik sıra: env'deki sıra raporu değiştirmez.
        self.assertEqual(resolve_surfaces({ENV_SURFACES: "landing,dashboard"}),
                         ("dashboard", "landing"))
        self.assertEqual(resolve_surfaces({ENV_SURFACES: "landing,landing"}),
                         ("landing",))
        with self.assertRaises(ValueError):
            resolve_surfaces({ENV_SURFACES: "dashboard,blog"})

    def test_next_surface_is_dropped_without_build_unless_explicit(self):
        no_build = os.path.join(tempfile.gettempdir(), "cwv_no_such_build_id")
        kept, dropped = drop_unavailable_surfaces(
            SURFACE_ORDER, env={}, build_id_path=no_build)
        self.assertTrue(dropped)
        self.assertEqual(kept, ("dashboard", "landing"))
        # Açık istek → düşürülmez (fail-closed kalsın: derleme istisnası yükselir)
        kept, dropped = drop_unavailable_surfaces(
            SURFACE_ORDER, env={ENV_SURFACES: "dashboard-next"},
            build_id_path=no_build)
        self.assertFalse(dropped)
        self.assertIn("dashboard-next", kept)
        # Derleme varsa hiçbir şey düşmez.
        with tempfile.NamedTemporaryFile("w", suffix="BUILD_ID") as f:
            f.write("test-build")
            f.flush()
            kept, dropped = drop_unavailable_surfaces(
                SURFACE_ORDER, env={}, build_id_path=f.name)
        self.assertFalse(dropped)
        self.assertEqual(kept, SURFACE_ORDER)

    def test_offline_fallback_only_relaxes_our_own_server(self):
        spec = SURFACE_SPECS["dashboard"]
        self.assertTrue(set(spec["content_any"]) <=
                        set(spec["content_any_offline"]))
        skeleton = "VERDICT — no run yet"
        self.assertFalse(
            content_present(spec, skeleton, live=True),
            "canlı sunucuda veri gelmeden yüzey PASS sayılamaz")
        self.assertTrue(
            content_present(spec, skeleton, live=False),
            "kendi açtığımız sunucuda boş-mirror iskeleti geçerli durumdur")
        self.assertFalse(content_present(spec, "boş sayfa", live=False))
        self.assertTrue(content_present(spec, "VERDICT PASS", live=True))
        for name in ("landing", "dashboard-next"):
            self.assertNotIn("content_any_offline", SURFACE_SPECS[name],
                             "%s: gevşetme yalnız dashboard'da tanımlı olmalı" % name)

    def test_surface_urls_and_theme(self):
        self.assertEqual(surface_url_path("dashboard", "light"),
                         "/preview.html?theme=light")
        self.assertEqual(surface_url_path("landing", "light"), "/landing.html")
        self.assertEqual(surface_url_path("dashboard-next", "light"), "/")
        self.assertEqual(surface_theme("landing", "light"), "default")
        self.assertEqual(surface_theme("dashboard", "light"), "light")
        self.assertEqual(resolve_theme({}), "dark")
        with self.assertRaises(ValueError):
            resolve_theme({"DASHBOARD_THEME": "blue"})

    def test_staging_produces_preview_server_layout(self):
        tmp = tempfile.mkdtemp(prefix="cwv_stage_")
        try:
            if not os.path.isfile(os.path.join(LANDING_DIR, "landing.html")):
                self.skipTest("landing.html üretilmemiş")
            stage_preview_dir(("dashboard", "landing"), tmp)
            for rel in ("preview.html", "preview.js", "landing.html",
                        "landing/assets/P1-a.png"):
                self.assertTrue(os.path.isfile(os.path.join(tmp, rel)),
                                "stage eksik: %s" % rel)
            # Mirror verisi (history.jsonl + runs) staging'de görünmeli;
            # yoksa dashboard "no run yet" iskeleti ölçülürdü.
            self.assertTrue(os.path.isfile(os.path.join(tmp, "history.jsonl")))
            self.assertTrue(os.path.isdir(os.path.join(tmp, "runs")))
            # Landing KOPYA, symlink DEĞİL (gerçekpath guard'ı + CI düzeni).
            self.assertFalse(os.path.islink(os.path.join(tmp, "landing.html")))
            bundled = os.path.join(tmp, "landing", "assets")
            self.assertTrue(all(n.lower().endswith(".png")
                                for n in os.listdir(bundled)))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_surface_verdict_is_fail_closed(self):
        budgets = dict(BUDGETS_DEFAULT)
        good = {"cls": 0.0, "fcp_ms": 100.0, "lcp_ms": 200.0, "ttfb_ms": 5.0}
        checks = checks_for(good, True, True, True, True, budgets)
        self.assertEqual(surface_verdict(checks, True, True, True, True), "PASS")
        # Metrik eksik → FAIL
        checks = checks_for({"cls": 0.0, "fcp_ms": 100.0, "lcp_ms": None,
                             "ttfb_ms": 5.0}, True, True, True, True, budgets)
        self.assertEqual(checks["lcp_ms"]["verdict"], "FAIL")
        self.assertEqual(surface_verdict(checks, True, True, True, True), "FAIL")
        # Panel/metin/destek yok → FAIL (metrikler iyi olsa bile)
        for args in ((False, True, True, True), (True, False, True, True),
                     (True, True, False, True), (True, True, True, False)):
            self.assertEqual(
                surface_verdict(checks_for(good, True, True, True, True, budgets),
                                *args),
                "FAIL")

    def test_report_is_deterministic_and_port_independent(self):
        def surface(value):
            return {
                "url_path": "/landing.html",
                "theme": "default",
                "metrics": {"cls": value, "fcp_ms": 100.0, "lcp_ms": 200.0,
                            "ttfb_ms": 5.0, "interaction_entries": 0},
                "checks": checks_for(
                    {"cls": value, "fcp_ms": 100.0, "lcp_ms": 200.0,
                     "ttfb_ms": 5.0}, True, True, True, True, BUDGETS_DEFAULT),
                "verdict": "PASS",
            }
        first = build_report(
            {"landing": surface(0.001), "dashboard": surface(0.002)},
            dict(BUDGETS_DEFAULT))
        second = build_report(
            {"dashboard": surface(0.002), "landing": surface(0.001)},
            dict(reversed(list(BUDGETS_DEFAULT.items()))))
        self.assertEqual(
            json.dumps(first, sort_keys=True, ensure_ascii=False),
            json.dumps(second, sort_keys=True, ensure_ascii=False),
            "rapor anahtar sırasına duyarsız olmalı")
        self.assertNotIn("http://", json.dumps(first))
        self.assertEqual(first["verdict"], "PASS")
        # Tek yüzey FAIL → agregat FAIL; eksik yüzey PASS'ı bozmaz ama
        # boş rapor FAIL.
        broken = surface(0.5)
        broken["verdict"] = "FAIL"
        self.assertEqual(
            build_report({"landing": broken}, dict(BUDGETS_DEFAULT))["verdict"],
            "FAIL")
        self.assertEqual(build_report({}, dict(BUDGETS_DEFAULT))["verdict"], "FAIL")

    def test_aggregate_ignores_unrequested_surfaces_but_requires_measured(self):
        ok = {"verdict": "PASS"}
        self.assertEqual(aggregate_verdict({"landing": ok}), "PASS")
        self.assertEqual(aggregate_verdict({"dashboard-next": {"verdict": "FAIL"}}),
                         "FAIL")


# ------------------------------------------------------ canlı ölçüm süiti
@unittest.skipIf(sync_playwright is None,
                 "playwright kurulu değil (pip install playwright + chromium)")
class SurfaceCwvReportTest(unittest.TestCase):
    """Üç yüzeye karşı gerçek CWV ölçümü + bütçe iddiası."""

    base_preview = None
    base_next = None
    preview_proc = None
    next_proc = None
    stage_dir = None
    _cache = {}
    _errors = {}

    @classmethod
    def setUpClass(cls):
        cls.surfaces = resolve_surfaces()
        cls.live = set()  # env ile verilen CANLI base'e sahip yüzeyler
        cls.surfaces, dropped = drop_unavailable_surfaces(cls.surfaces)
        if dropped:
            print(
                "NOT: dashboard-next yüzeyi atlandı — "
                "apps/dashboard-next/.next derlemesi yok "
                "(npm run build --prefix apps/dashboard-next). Zorlamak "
                "için: CWV_SURFACES=dashboard-next", flush=True)
        cls.budgets = resolve_budgets()
        cls.theme = resolve_theme()
        cls.artifacts = {}
        cls.build_ids = {}
        cls._tmp = tempfile.mkdtemp(prefix="cwv_report_")
        cls._logs = os.path.join(cls._tmp, "logs")
        os.makedirs(cls._logs, exist_ok=True)

        # 1) preview_server: dashboard + landing aynı staging dizininden.
        need_preview = any(SURFACE_SPECS[n]["server"] == "preview"
                           for n in cls.surfaces)
        live_preview = (os.environ.get(ENV_LIVE_PREVIEW) or "").strip() or None
        if live_preview:
            host, port = cwv_core.split_base(live_preview)
            cls.base_preview = live_preview.rstrip("/")
            cls.live.update(n for n in cls.surfaces
                            if SURFACE_SPECS[n]["server"] == "preview")
            if not cwv_core.wait_for_port(host, port, timeout=10):
                raise RuntimeError(
                    "%s=%s erişilemedi (%s:%s dinlemiyor)" % (
                        ENV_LIVE_PREVIEW, live_preview, host, port))
        elif need_preview:
            cls.stage_dir = stage_preview_dir(cls.surfaces,
                                              os.path.join(cls._tmp, "preview"))
            port = cwv_core.free_port()
            cls.preview_proc = spawn_preview_server(
                cls.stage_dir, port, os.path.join(cls._logs, "preview_server.log"))
            cls.base_preview = "http://127.0.0.1:%s" % port

        # 2) dashboard-next: mevcut `.next` derlemesi üzerinden `next start`.
        live_next = (os.environ.get(ENV_LIVE_NEXT) or "").strip() or None
        if "dashboard-next" in cls.surfaces:
            if live_next:
                host, port = cwv_core.split_base(live_next)
                cls.base_next = live_next.rstrip("/")
                cls.live.add("dashboard-next")
                if not cwv_core.wait_for_port(host, port, timeout=10):
                    raise RuntimeError(
                        "%s=%s erişilemedi (%s:%s dinlemiyor)" % (
                            ENV_LIVE_NEXT, live_next, host, port))
            else:
                port = cwv_core.free_port()
                cls.next_proc = spawn_next_server(
                    port, cls.base_preview or "http://127.0.0.1:8000",
                    os.path.join(cls._logs, "next_start.log"))
                cls.base_next = "http://127.0.0.1:%s" % port
            _, cls.build_ids["dashboard-next"] = artifacts_for("dashboard-next")

        # 3) Artefakt imzaları + yüzey erişim kontrolü.
        #    Isınma isteği aynı zamanda fail-closed bir kapıdır: yüzey 200
        #    dönmüyorsa (örn. landing.html mirror'a stage edilmemiş → 404)
        #    ölçüm 20 sn selector timeout'uyla değil, NET bir mesajla düşer.
        for name in cls.surfaces:
            files, extra = artifacts_for(name)
            cls.artifacts[name] = files
            if extra:
                cls.build_ids.update(extra)
            url = cls.base(name) + surface_url_path(name, cls.theme)
            try:
                status, _ = http_get(url)
            except urllib.error.HTTPError as exc:
                raise RuntimeError(
                    "%s yüzeyi %s → HTTP %s: artefakt sunulmuyor "
                    "(landing için build_landing.py çıktısı stage edilmeli)" % (
                        name, surface_url_path(name, cls.theme), exc.code)) from exc
            except (urllib.error.URLError, OSError) as exc:
                raise RuntimeError(
                    "%s yüzeyi %s → erişilemedi: %s" % (
                        name, surface_url_path(name, cls.theme), exc)) from exc
            if status != 200:
                raise RuntimeError("%s yüzeyi %s → HTTP %s (200 beklenirdi)" % (
                    name, surface_url_path(name, cls.theme), status))

    @classmethod
    def base(cls, name):
        return (cls.base_next if SURFACE_SPECS[name]["server"] == "next"
                else cls.base_preview)

    @classmethod
    def tearDownClass(cls):
        try:
            if cls._cache:
                report = cls.build_live_report()
                for name in cls.surfaces:
                    data = report["surfaces"].get(name) or {}
                    metrics = data.get("metrics") or {}
                    detail = " ".join(
                        "%s=%s" % (key, "n/a" if metrics.get(key) is None
                                   else "%.4f" % metrics[key])
                        for key in ("cls", "fcp_ms", "lcp_ms", "ttfb_ms")
                        if key in metrics)
                    print("CWV yüzeyi %s: %s · %s (%s)" % (
                        name, detail, data.get("url_path"),
                        data.get("verdict")), flush=True)
                print("CWV üç yüzey raporu: %s · karar=%s" % (
                    " · ".join(sorted(cls.surfaces)), report["verdict"]),
                    flush=True)
                path = (os.environ.get(ENV_REPORT_PATH) or "").strip()
                if path:
                    write_report(path, report)
        finally:
            terminate(cls.next_proc)
            terminate(cls.preview_proc)
            cls.next_proc = None
            cls.preview_proc = None
            if cls._tmp:
                shutil.rmtree(cls._tmp, ignore_errors=True)

    # ------------------------------------------------------------- ölçüm
    @classmethod
    def measure(cls, name):
        """(yüzey başına 1 kez) gerçek CWV ölçümü döndürür."""
        if name in cls._cache:
            return cls._cache[name]
        if name in cls._errors:
            # Başarısız ölçüm ÖNBELLEKLENİR: aksi halde her test aynı
            # timeout'u baştan beklerdi (6 test × 20 sn = 2 dk boşa bekleme).
            raise cls._errors[name]
        spec = SURFACE_SPECS[name]
        url = cls.base(name) + surface_url_path(name, cls.theme)
        try:
            data = cls._measure_once(name, spec, url)
        except Exception as exc:  # noqa: BLE001 — önbelleğe alıp yeniden fırlat
            cls._errors[name] = exc
            raise
        cls._cache[name] = data
        return data

    @classmethod
    def _measure_once(cls, name, spec, url):
        """Tek sayfa yüklemesiyle ölçüm; hata mesajları yüzey adını taşır."""
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                page = browser.new_page()
                page.route("/sw.js", lambda route: route.fulfill(body=""))
                page.add_init_script(CWV_RECORDER)
                page.goto(url, wait_until="domcontentloaded")
                try:
                    page.wait_for_selector(spec["ready"],
                                           timeout=READY_TIMEOUT_MS)
                except Exception as exc:  # noqa: BLE001
                    raise RuntimeError(
                        "%s yüzeyi yüklenmedi: `%s` %ss içinde görünmedi "
                        "(%s) — sayfa iskeleti mi servis edildi?" % (
                            name, spec["ready"], READY_TIMEOUT_MS // 1000,
                            surface_url_path(name, cls.theme))) from exc
                page.wait_for_timeout(SETTLE_MS)
                # Gerçek etkileşim: Event Timing girdilerini sayar (INP bu
                # ortamda yayınlanmıyor — bkz. modül başlığı). Hedefler
                # navigasyon yapmayan elemanlar.
                target = spec.get("inp_target")
                if target:
                    try:
                        page.click(target, timeout=5000)
                        page.wait_for_timeout(500)
                    except Exception:  # noqa: BLE001 — gözlem, kapı değil
                        pass
                data = page.evaluate(
                    "() => ({cls: window.__clsBudget, cwv: window.__cwvProbe})")
                panel_flags = page.evaluate(
                    "(sels) => sels.map((s) => !!document.querySelector(s))",
                    list(spec["panels"]))
                text = page.evaluate(
                    "() => ((document.body.innerText || '') + ' ' + "
                    "(document.body.textContent || ''))")
            finally:
                browser.close()
        data["panelsPresent"] = all(panel_flags)
        # Metin karşılaştırması büyük/küçük harf DUYARSIZ ve innerText +
        # textContent BİRLEŞİMİ üzerinden: `innerText` layout-aware'dır — CSS
        # `text-transform`'u yansıtır ("Verdict" → "VERDICT") ve gizli
        # bölümleri dışlar; `textContent` ise daraltılmış panelleri de kapsar.
        # İkisinin birleşimi "bu sayfa gerçekten render oldu mu" sorusunu
        # yanıtlar. Veri-şartı sunucu kaynağına bağlıdır (bkz. content_present).
        data["contentPresent"] = content_present(spec, text,
                                                 live=name in cls.live)
        return data

    @classmethod
    def metrics_of(cls, data):
        cls_block = data.get("cls") or {}
        probe = data.get("cwv") or {}
        lcp = probe.get("lcp") or {}
        return {
            "cls": cls_block.get("value"),
            "fcp_ms": probe.get("fcp"),
            "lcp_ms": lcp.get("startTime"),
            "ttfb_ms": probe.get("ttfb"),
            "interaction_entries": probe.get("interactionEntries"),
        }

    @classmethod
    def build_live_report(cls):
        surfaces = {}
        for name in cls.surfaces:
            data = cls.measure(name)
            metrics = cls.metrics_of(data)
            cls_block = data.get("cls") or {}
            probe = data.get("cwv") or {}
            supported = bool(cls_block.get("supported"))
            observer = bool(cls_block.get("observerInstalled") and
                            all(probe.get("observers", {}).values()))
            checks = checks_for(metrics, data["panelsPresent"],
                                data["contentPresent"], supported, observer,
                                cls.budgets)
            surfaces[name] = {
                "url_path": surface_url_path(name, cls.theme),
                "theme": surface_theme(name, cls.theme),
                "metrics": metrics,
                "checks": checks,
                "panels_present": bool(data["panelsPresent"]),
                "content_present": bool(data["contentPresent"]),
                "cls_supported": supported,
                "cls_observer_installed": bool(cls_block.get("observerInstalled")),
                "cls_entries": len(cls_block.get("entries") or []),
                "cls_python_value": cwv_core.cls_from_session_windows(
                    [(e.get("startTime"), e.get("value"))
                     for e in (cls_block.get("entries") or [])]),
                "observer_errors": list(probe.get("errors") or []),
                "artifacts": cls.artifacts.get(name) or {},
                "verdict": surface_verdict(checks, data["panelsPresent"],
                                           data["contentPresent"], supported,
                                           observer),
            }
        if cls.build_ids:
            for name in cls.surfaces:
                if name in cls.build_ids:
                    surfaces[name]["build_id"] = cls.build_ids[name]
        return build_report(surfaces, dict(cls.budgets))

    # ------------------------------------------------------------- testler
    def test_1_every_surface_renders_real_content(self):
        for name in self.surfaces:
            data = self.measure(name)
            spec = SURFACE_SPECS[name]
            self.assertTrue(
                data["panelsPresent"],
                "%s: paneller eksik (%s) — boş/hatalı sayfa ölçüldü" % (
                    name, ", ".join(spec["panels"])))
            self.assertTrue(
                data["contentPresent"],
                "%s: beklenen içerik yok (%s%s)" % (
                    name, ", ".join(spec["content"]),
                    " / biri: " + ", ".join(spec["content_any"])
                    if spec["content_any"] else ""))

    def test_2_measurement_environment_is_live_on_every_surface(self):
        for name in self.surfaces:
            data = self.measure(name)
            self.assertTrue(
                (data.get("cls") or {}).get("supported"),
                "%s: tarayıcı `layout-shift` desteklemiyor — CLS ölçülemez" % name)
            self.assertTrue(
                (data.get("cls") or {}).get("observerInstalled"),
                "%s: layout-shift observer kurulamadı: %r" % (
                    name, (data.get("cls") or {}).get("observeError")))
            probe = data.get("cwv") or {}
            for entry_type in ("largest-contentful-paint", "paint", "event"):
                self.assertTrue(
                    probe.get("observers", {}).get(entry_type),
                    "%s: %s observer kurulamadı: %r" % (
                        name, entry_type, probe.get("errors")))
            metrics = self.metrics_of(data)
            for key in ("fcp_ms", "lcp_ms", "ttfb_ms"):
                self.assertIsInstance(
                    metrics[key], (int, float),
                    "%s: %s sayısal dönmedi: %r" % (name, key, metrics[key]))

    def test_3_cls_js_and_python_agree_on_every_surface(self):
        """Recorder'ın session-window toplamı Python kuralıyla aynı olmalı."""
        for name in self.surfaces:
            data = self.measure(name)
            js_value = (data.get("cls") or {}).get("value")
            py_value = cwv_core.cls_from_session_windows(
                [(e.get("startTime"), e.get("value"))
                 for e in ((data.get("cls") or {}).get("entries") or [])])
            self.assertAlmostEqual(
                js_value, py_value, places=6,
                msg="%s: JS=%r Python=%r — iki uygulama ayrıştı" % (
                    name, js_value, py_value))

    def test_4_every_surface_within_cwv_budget(self):
        report = self.build_live_report()
        for name in self.surfaces:
            data = report["surfaces"][name]
            failed = [(key, check["reason"])
                      for key, check in sorted(data["checks"].items())
                      if check["verdict"] != "PASS"]
            self.assertEqual(
                failed, [],
                "%s: CWV bütçesi aşıldı (%s) — ölçüm: %s" % (
                    name, "; ".join(r for _, r in failed), data["metrics"]))
            self.assertEqual(data["verdict"], "PASS")

    def test_5_report_is_complete_and_deterministic(self):
        first = self.build_live_report()
        second = self.build_live_report()
        self.assertEqual(json.dumps(first, sort_keys=True),
                         json.dumps(second, sort_keys=True),
                         "aynı koşumda rapor deterministik olmalı")
        self.assertEqual(set(first["surfaces"]), set(self.surfaces))
        self.assertEqual(first["budgets"]["cls"], self.budgets["cls"])
        for name in self.surfaces:
            data = first["surfaces"][name]
            self.assertTrue(data["artifacts"],
                            "%s: artefakt imzası yok" % name)
            for rel, digest in data["artifacts"].items():
                self.assertEqual(len(digest), 64, "%s: sha256 değil" % rel)
        self.assertEqual(first["verdict"],
                         "PASS" if self.surfaces else "FAIL")

    def test_6_artificial_shift_is_detected_and_over_budget(self):
        """Negatif kontrol: statik yüzeyde ölçüm hattı gerçekten çalışıyor."""
        name = "landing" if "landing" in self.surfaces else "dashboard"
        spec = SURFACE_SPECS[name]
        url = self.base(name) + surface_url_path(name, self.theme)
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                page = browser.new_page()
                page.route("/sw.js", lambda route: route.fulfill(body=""))
                page.add_init_script(CWV_RECORDER)
                page.goto(url, wait_until="domcontentloaded")
                page.wait_for_selector(spec["ready"], timeout=READY_TIMEOUT_MS)
                page.wait_for_timeout(SETTLE_MS)
                before = page.evaluate("() => window.__clsBudget.value")
                page.evaluate(cwv_core.INJECT_SHIFT, ARTIFICIAL_SHIFT_PX)
                page.wait_for_timeout(800)
                after = page.evaluate("() => window.__clsBudget.value")
            finally:
                browser.close()
        self.assertGreater(
            after, before,
            "yapay %s px kaydırma ölçülmedi (before=%s after=%s) — %s "
            "ölçüm hattı ölü, test-4'teki PASS güvenilmez" % (
                ARTIFICIAL_SHIFT_PX, before, after, name))
        ok, reason = cwv_core.evaluate_budget(after, budget=self.budgets["cls"])
        self.assertFalse(
            ok, "yapay kaydırma CLS bütçesini AŞMADI (%s) — eşik uygulanmıyor" % reason)


if __name__ == "__main__":
    unittest.main(verbosity=2)
