#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_dashboard_cls_budget.py — dashboard CLS bütçe kapısı (Playwright, fail-closed).

İDDİA: dashboard'ın yüklenme Cumulative Layout Shift (CLS) değeri 0.1'in
ALTINDADIR (Web Vitals "good" eşiği: CLS < 0.1).

Neden bu dosya var: CLS bu repoda HİÇBİR yerde ölçülmüyordu. a11y-gate
job'ının Lighthouse koşumu `--only-categories=accessibility` ile çalışır, yani
layout-shift auditi rapora hiç girmez; hiçbir gate "sayfa zıplamıyor" demiyor.
Bu dosya o boşluğu ölçen ve kıran kalıcı bir kapıya çevirir.

Ölçüm yöntemi — Chrome/Lighthouse'un KENDİ algoritması:
  PerformanceObserver({type:"layout-shift"}) sayfa yüklenmeden ÖNCE
  `add_init_script` ile kurulur; `hadRecentInput` olmayan girdiler
  "session window" kuralıyla toplanır (komşu girdiler arası < 1 sn VE pencere
  genişliği < 5 sn) ve EN BÜYÜK pencere değeri CLS olur. Girdilerin düz
  toplamı DEĞİL: bu ayrım önemli, çünkü uzun sayfalarda aralıklı küçük
  kaydırmaları toplamak CLS'i olduğundan büyük gösterir.

Fail-closed guard'lar (boş bir "0.0 PASS" yanılsamasına karşı):
  * `layout-shift` desteklenmiyorsa FAIL — desteklenmeyen ortamda her sayfa
    koşulsuz 0 verir, yani kapı sessizce anlamsızlaşırdı.
  * Observer kurulamadıysa FAIL.
  * Dashboard panelleri yoksa FAIL — boş/yüklenmemiş sayfada shift olmaz.
  * Ölçülen değer yok / sayısal değil / NaN / negatifse FAIL.
  * Negatif kontrol: sayfaya SONRADAN yapay bir kaydırma enjekte edilir ve
    ölçüm hattının onu GÖRDÜĞÜ + bütçeyi AŞTIĞI doğrulanır. Bu olmadan
    "CLS < 0.1" iddiası, ölçümün ölü olmasından da gelebilirdi.

Hedef sunucu (`test_dashboard_csp_nonce.py` ile aynı sözleşme):
  - `DASHBOARD_BASE_URL` verilirse: o CANLI sunucu (örn. http://127.0.0.1:8010);
    erişilemezse test FAIL eder (açıkça istendi, sessizce geçilmez).
  - Verilmezse: taze bir `preview_server.py` ücretsiz portta başlatılır
    (kendi kendine yeterli, CI-güvenli).

Env override'ları:
  DASHBOARD_BASE_URL  canlı sunucu tabanı (varsayılan: kendi sunucusunu başlat)
  DASHBOARD_THEME     dark | light (varsayılan: dark) — query'ye eklenir
  CLS_BUDGET          bütçe (varsayılan: 0.1) — test/CI için geçici override
  CLS_REPORT_PATH     verilirse deterministik JSON rapor yazılır (CI artifact)

Çalıştırma:
  python3 _calisma/CIKTI/test_dashboard_cls_budget.py                  # spawn
  DASHBOARD_BASE_URL=http://127.0.0.1:8010 \\
    python3 _calisma/CIKTI/test_dashboard_cls_budget.py                # canlı
"""

import json
import math
import os
import re
import socket
import subprocess
import sys
import time
import unittest

try:
    from playwright.sync_api import sync_playwright
except ImportError:  # CI runner'da playwright kurulu değilse SKIP (fail değil)
    sync_playwright = None

HERE = os.path.dirname(os.path.abspath(__file__))
SERVER_SCRIPT = os.path.join(HERE, "preview_server.py")
LIVE_BASE = (os.environ.get("DASHBOARD_BASE_URL") or "").strip() or None

# Web Vitals "good" eşiği. İddia: CLS < BUDGET_DEFAULT (kesin küçüktür:
# tam 0.1 FAIL eder).
BUDGET_DEFAULT = 0.1
VALID_THEMES = ("dark", "light")
THEME_DEFAULT = "dark"

# Yükleme sonrası sayfanın yerleşmesi için tanınan süre: SSE snapshot'ı,
# /api/latest fetch'i ve geç reflow bu pencerede olur — CLS'in kaynağı
# tam olarak bu "veri gelince paneller dolar" anıdır.
SETTLE_MS = 2500
# Negatif kontrolün yapay kaydırması: 400 px, ölçülen ~0.29 CLS üretir
# (bütçenin ~3 katı) — bütçeyi aşması garanti, gerçekçi bir zıplama.
ARTIFICIAL_SHIFT_PX = 400

# ---------------------------------------------------------------- ölçüm JS
# Sayfa yüklenmeden ÖNCE kurulur (CDP init script). Tüm `layout-shift`
# girdilerini toplar; CLS'i session-window kuralıyla birlikte hesaplar.
CLS_RECORDER = """
window.__clsBudget = {
  value: 0, total: 0, sessionValue: 0, session: [], entries: [],
  observerInstalled: false, supported: false, observeError: null,
};
try {
  window.__clsBudget.supported =
    (typeof PerformanceObserver !== 'undefined') &&
    PerformanceObserver.supportedEntryTypes.indexOf('layout-shift') !== -1;
} catch (e) {
  window.__clsBudget.supported = false;
}
if (window.__clsBudget.supported) {
  try {
    const observer = new PerformanceObserver((list) => {
      const s = window.__clsBudget;
      for (const entry of list.getEntries()) {
        if (entry.hadRecentInput) continue;
        const item = { startTime: entry.startTime, value: entry.value };
        const last = s.session[s.session.length - 1];
        if (s.sessionValue && last &&
            item.startTime - last.startTime < 1000 &&
            item.startTime - s.session[0].startTime < 5000) {
          s.sessionValue += item.value;
          s.session.push(item);
        } else {
          s.sessionValue = item.value;
          s.session = [item];
        }
        if (s.sessionValue > s.value) s.value = s.sessionValue;
        s.total += item.value;
        s.entries.push(item);
      }
    });
    observer.observe({ type: 'layout-shift', buffered: true });
    window.__clsBudget.observerInstalled = true;
  } catch (e) {
    window.__clsBudget.observeError = String(e);
  }
}
"""

# Negatif kontrol: görünmez bir spacer'ı en üste ekleyip reflow zorlar, sonra
# yüksekliğini verir — altındaki içerik aşağı kayar (hadRecentInput=false).
INJECT_SHIFT = """
(px) => {
  const d = document.createElement('div');
  d.id = '__cls_budget_probe_spacer';
  d.style.cssText = 'height:0px;width:100%';
  document.body.prepend(d);
  void document.body.offsetHeight;
  d.style.height = px + 'px';
  void document.body.offsetHeight;
}
"""

# Ölçümün anlamlı olması için sayfada bulunması gereken paneller
# (test_dashboard_playwright_smoke.py ile aynı sözleşme).
REQUIRED_PANELS = ("#m-verdict", "#status-board", "#badges")


# ------------------------------------------------------- saf hesap (browser'sız)
def cls_from_session_windows(entries):
    """CLS = en büyük session window toplamı.

    entries: (startTime_ms, value) ikilileri listesi (hadRecentInput olmayan
    girdiler). Chrome'un algoritması: bir pencere, komşu girdiler arası < 1 sn
    ve pencere başı-sonu < 5 sn olduğu sürece uzar.
    """
    cls_value = 0.0
    session_value = 0.0
    session = []
    for start_time, value in entries:
        if (session_value and session and
                (start_time - session[-1][0]) < 1000 and
                (start_time - session[0][0]) < 5000):
            session_value += value
            session.append((start_time, value))
        else:
            session_value = value
            session = [(start_time, value)]
        if session_value > cls_value:
            cls_value = session_value
    return cls_value


def evaluate_budget(cls_value, budget=BUDGET_DEFAULT):
    """(ok, reason) — fail-closed: yok/NaN/negatif/sayısal-değil değer FAIL."""
    if cls_value is None:
        return False, "CLS ölçülemedi (değer yok) — fail-closed"
    if isinstance(cls_value, bool) or not isinstance(cls_value, (int, float)):
        return False, "CLS sayısal değil: %r" % (cls_value,)
    if math.isnan(cls_value):
        return False, "CLS NaN"
    if math.isinf(cls_value):
        return False, "CLS sonsuz"
    if cls_value < 0:
        return False, "CLS negatif: %s" % cls_value
    if cls_value < budget:
        return True, "CLS %.6f < bütçe %s" % (cls_value, budget)
    return False, "CLS %.6f >= bütçe %s" % (cls_value, budget)


def aggregate_verdict(themes):
    """Tüm temalar PASS ise PASS; eksik/FAIL varsa FAIL (fail-closed)."""
    if not themes:
        return "FAIL"
    for name in VALID_THEMES:
        if name not in themes or themes[name].get("verdict") != "PASS":
            return "FAIL"
    return "PASS"


def build_report(themes, budget):
    """Deterministik JSON raporu (sıralı anahtarlar; zaman damgası YOK)."""
    return {
        "budget": budget,
        "themes": themes,
        "verdict": aggregate_verdict(themes),
    }


def write_report(path, report):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, sort_keys=True)
        f.write("\n")


def resolve_budget(env=None):
    """CLS_BUDGET env'ini float'a çevir; geçersizse ValueError (fail-closed)."""
    raw = (env if env is not None else os.environ.get("CLS_BUDGET", "")).strip()
    if not raw:
        return BUDGET_DEFAULT
    try:
        value = float(raw)
    except ValueError:
        raise ValueError("CLS_BUDGET sayısal değil: %r" % raw)
    if not math.isfinite(value) or value <= 0:
        raise ValueError("CLS_BUDGET pozitif sonlu sayı olmalı: %r" % raw)
    return value


def resolve_theme(env=None):
    """DASHBOARD_THEME'i doğrula (dark|light); geçersizse ValueError."""
    raw = (env if env is not None else os.environ.get("DASHBOARD_THEME", "")).strip()
    if not raw:
        return THEME_DEFAULT
    if raw not in VALID_THEMES:
        raise ValueError("DASHBOARD_THEME %s olmalı, alındı: %r" % (
            "/".join(VALID_THEMES), raw))
    return raw


# ------------------------------------------------------------------ sunucu
def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def wait_for_port(host, port, timeout=15):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=1):
                return True
        except (OSError, ConnectionRefusedError):
            time.sleep(0.3)
    return False


def split_base(base):
    """http://127.0.0.1:8010 → ("127.0.0.1", 8010)."""
    m = re.match(r"^https?://([^/:]+):(\d+)", base)
    if not m:
        raise RuntimeError(
            "DASHBOARD_BASE_URL ayrıştırılamadı (host:port yok): %s" % base)
    return m.group(1), int(m.group(2))


def dashboard_url(base, theme):
    return "%s/preview.html?theme=%s" % (base.rstrip("/"), theme)


# ------------------------------------------------------------- saf süit
class ClsBudgetMathTest(unittest.TestCase):
    """Browser'sız: session-window matematiği + bütçe kararı (fail-closed)."""

    def test_single_entry_is_its_own_window(self):
        self.assertAlmostEqual(cls_from_session_windows([(100.0, 0.05)]), 0.05)

    def test_close_entries_merge_into_one_window(self):
        entries = [(100.0, 0.01), (900.0, 0.02), (1500.0, 0.03)]
        self.assertAlmostEqual(cls_from_session_windows(entries), 0.06)

    def test_gap_over_one_second_starts_new_window(self):
        entries = [(100.0, 0.05), (2000.0, 0.04)]
        self.assertAlmostEqual(cls_from_session_windows(entries), 0.05)

    def test_window_wider_than_five_seconds_starts_new_window(self):
        # Komşu aralıklar 900 ms (< 1 sn) ama pencere başı-sonu > 5 sn.
        entries = [(0.0, 0.01), (900.0, 0.01), (1800.0, 0.01),
                   (2700.0, 0.01), (3600.0, 0.01), (4500.0, 0.01),
                   (5400.0, 0.01)]
        # Son girdi 5400 ms'de: 5400-0 = 5400 >= 5000 → yeni pencere.
        self.assertAlmostEqual(cls_from_session_windows(entries), 0.06)

    def test_largest_window_wins_not_the_plain_sum(self):
        # İki ayrı pencere: 0.06 ve 0.03. Düz toplam 0.09 olurdu (yanlış).
        entries = [(0.0, 0.06), (8000.0, 0.03)]
        self.assertAlmostEqual(cls_from_session_windows(entries), 0.06)

    def test_empty_entries_is_zero(self):
        self.assertEqual(cls_from_session_windows([]), 0.0)

    def test_budget_boundary_is_exclusive(self):
        self.assertTrue(evaluate_budget(0.099999, 0.1)[0])
        self.assertFalse(evaluate_budget(0.1, 0.1)[0],
                         "tam bütçe değeri FAIL olmalı (iddia kesin küçüktür)")
        self.assertFalse(evaluate_budget(0.1000001, 0.1)[0])

    def test_missing_measurement_fails_closed(self):
        ok, reason = evaluate_budget(None, 0.1)
        self.assertFalse(ok, "ölçülemeyen CLS PASS sayılamaz")
        self.assertIn("ölçülemedi", reason)

    def test_nan_fails_closed(self):
        self.assertFalse(evaluate_budget(float("nan"), 0.1)[0])

    def test_infinity_fails_closed(self):
        self.assertFalse(evaluate_budget(float("inf"), 0.1)[0])

    def test_negative_fails_closed(self):
        self.assertFalse(evaluate_budget(-0.001, 0.1)[0])

    def test_non_numeric_fails_closed(self):
        self.assertFalse(evaluate_budget("0.01", 0.1)[0])
        self.assertFalse(evaluate_budget(True, 0.1)[0])

    def test_budget_env_override_validates(self):
        self.assertEqual(resolve_budget(""), 0.1)
        self.assertEqual(resolve_budget("0.25"), 0.25)
        for bad in ("abc", "0", "-1", "nan", "inf"):
            with self.assertRaises(ValueError):
                resolve_budget(bad)

    def test_theme_env_override_validates(self):
        self.assertEqual(resolve_theme(""), "dark")
        self.assertEqual(resolve_theme("light"), "light")
        with self.assertRaises(ValueError):
            resolve_theme("blue")

    def test_aggregate_verdict_is_fail_closed(self):
        ok = {"verdict": "PASS"}
        self.assertEqual(aggregate_verdict({"dark": ok, "light": ok}), "PASS")
        # Tek tema fail → FAIL
        self.assertEqual(
            aggregate_verdict({"dark": ok, "light": {"verdict": "FAIL"}}), "FAIL")
        # Eksik tema → FAIL (ölçülmemiş temayı PASS sayma)
        self.assertEqual(aggregate_verdict({"dark": ok}), "FAIL")
        # Hiç tema yok → FAIL
        self.assertEqual(aggregate_verdict({}), "FAIL")

    def test_report_is_deterministic_and_sorted(self):
        themes = {
            "light": {"cls": 0.0, "verdict": "PASS"},
            "dark": {"cls": 0.0, "verdict": "PASS"},
        }
        first = json.dumps(build_report(themes, 0.1), sort_keys=True)
        second = json.dumps(build_report(dict(reversed(list(themes.items()))), 0.1),
                            sort_keys=True)
        self.assertEqual(first, second, "rapor anahtar sırasına duyarsız olmalı")
        self.assertEqual(build_report(themes, 0.1)["verdict"], "PASS")


# --------------------------------------------------------- canlı ölçüm süiti
@unittest.skipIf(sync_playwright is None,
                 "playwright kurulu değil (pip install playwright + chromium)")
class DashboardClsBudgetTest(unittest.TestCase):
    """Canlı dashboard'a karşı gerçek CLS ölçümü + bütçe iddiası."""

    base = None
    proc = None
    _cache = {}

    @classmethod
    def setUpClass(cls):
        cls.budget = resolve_budget()
        cls.theme = resolve_theme()
        cls.proc = None
        if LIVE_BASE:
            host, port = split_base(LIVE_BASE)
            cls.base = LIVE_BASE.rstrip("/")
            if not wait_for_port(host, port, timeout=10):
                raise RuntimeError(
                    "DASHBOARD_BASE_URL=%s erişilemedi (%s:%s dinlemiyor) — "
                    "canlı sunucu ayakta mı?" % (LIVE_BASE, host, port))
            return

        port = free_port()
        cls.proc = subprocess.Popen(
            [sys.executable, SERVER_SCRIPT,
             "--dir", HERE,
             "--preview-dir", HERE,
             "--port", str(port),
             "--bind", "127.0.0.1",
             "--interval", "3600"],
            cwd=HERE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if not wait_for_port("127.0.0.1", port, timeout=15):
            cls.proc.terminate()
            cls.proc.wait(timeout=5)
            raise RuntimeError(
                "preview_server.py 127.0.0.1:%s üzerinde başlamadı (%s)" % (
                    port, SERVER_SCRIPT))
        cls.base = "http://127.0.0.1:%s" % port

    @classmethod
    def _summarize(cls):
        """Tema başına deterministik verdict sözlüğü (rapor + log ortak)."""
        themes = {}
        for theme, data in sorted(cls._cache.items()):
            ok, _ = evaluate_budget(data.get("value"), budget=cls.budget)
            if not (data.get("supported") and
                    data.get("observerInstalled") and
                    data.get("panelsPresent")):
                ok = False
            themes[theme] = {
                "cls": data.get("value"),
                "entries": len(data.get("entries") or []),
                "observer_installed": bool(data.get("observerInstalled")),
                "panels_present": bool(data.get("panelsPresent")),
                "supported": bool(data.get("supported")),
                "total": data.get("total"),
                "verdict": "PASS" if ok else "FAIL",
            }
        return themes

    @classmethod
    def tearDownClass(cls):
        try:
            if cls._cache:
                themes = cls._summarize()
                report = build_report(themes, cls.budget)
                # Ölçüm sayıları HER koşumda stdout'a yazılır: CI log'u
                # bütçenin neresinde olduğumuzu gösterir (gate PASS olsa da).
                detail = " · ".join(
                    "%s=%.6f (%s)" % (t, themes[t]["cls"] or 0.0, themes[t]["verdict"])
                    for t in sorted(themes))
                print("CLS bütçe kapısı: bütçe=%s · %s · karar=%s" % (
                    cls.budget, detail, report["verdict"]), flush=True)
                path = (os.environ.get("CLS_REPORT_PATH") or "").strip()
                if path:
                    write_report(path, report)
        finally:
            if cls.proc is not None:
                cls.proc.terminate()
                try:
                    cls.proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    cls.proc.kill()
                    cls.proc.wait(timeout=5)
                cls.proc = None

    # ------------------------------------------------------------- ölçüm
    @classmethod
    def measure(cls, theme):
        """(theme başına 1 kez) gerçek CLS ölçümü döndür."""
        if theme in cls._cache:
            return cls._cache[theme]
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                page = browser.new_page()
                page.route("/sw.js", lambda route: route.fulfill(body=""))
                page.add_init_script(CLS_RECORDER)
                page.goto(dashboard_url(cls.base, theme),
                          wait_until="domcontentloaded")
                page.wait_for_selector(REQUIRED_PANELS[0], timeout=10000)
                page.wait_for_timeout(SETTLE_MS)
                data = page.evaluate("() => window.__clsBudget")
                present = page.evaluate(
                    "(sels) => sels.every((s) => !!document.querySelector(s))",
                    list(REQUIRED_PANELS))
            finally:
                browser.close()
        data["panelsPresent"] = bool(present)
        cls._cache[theme] = data
        return data

    @classmethod
    def artificial_shift(cls, theme, px=ARTIFICIAL_SHIFT_PX):
        """Negatif kontrol: yapay kaydırma sonrası CLS'i döndür."""
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                page = browser.new_page()
                page.route("/sw.js", lambda route: route.fulfill(body=""))
                page.add_init_script(CLS_RECORDER)
                page.goto(dashboard_url(cls.base, theme),
                          wait_until="domcontentloaded")
                page.wait_for_selector(REQUIRED_PANELS[0], timeout=10000)
                page.wait_for_timeout(SETTLE_MS)
                before = page.evaluate("() => window.__clsBudget.value")
                page.evaluate(INJECT_SHIFT, px)
                page.wait_for_timeout(800)
                after = page.evaluate("() => window.__clsBudget.value")
            finally:
                browser.close()
        return before, after

    # ------------------------------------------------------------- testler
    def test_1_measurement_environment_is_live_and_fail_closed(self):
        data = self.measure(self.theme)
        self.assertTrue(
            data.get("supported"),
            "tarayıcı `layout-shift` PerformanceEntry'yi DESTEKLEMİYOR — bu "
            "ortamda CLS ölçülemez (her sayfa koşulsuz 0 verir), kapı "
            "anlamsızlaşır")
        self.assertTrue(
            data.get("observerInstalled"),
            "layout-shift observer kurulamadı: %r" % data.get("observeError"))
        self.assertIsInstance(
            data.get("value"), (int, float),
            "CLS sayısal dönmedi: %r" % (data.get("value"),))

    def test_2_dashboard_panels_present_so_measurement_is_meaningful(self):
        data = self.measure(self.theme)
        self.assertTrue(
            data.get("panelsPresent"),
            "dashboard panelleri eksik (%s) — boş sayfada shift olmaz, "
            "ölçüm anlamsız" % ", ".join(REQUIRED_PANELS))

    def test_3_dashboard_load_cls_within_budget(self):
        data = self.measure(self.theme)
        ok, reason = evaluate_budget(data.get("value"), budget=self.budget)
        self.assertTrue(
            ok,
            "%s teması: %s — yüklenme sırasında sayfa zıplıyor "
            "(girdiler: %s)" % (
                self.theme, reason,
                (data.get("entries") or [])[:6]))

    def test_4_light_theme_also_within_budget(self):
        data = self.measure("light")
        ok, reason = evaluate_budget(data.get("value"), budget=self.budget)
        self.assertTrue(
            ok, "light teması: %s (girdiler: %s)" % (
                reason, (data.get("entries") or [])[:6]))

    def test_5_artificial_shift_is_detected_and_over_budget(self):
        before, after = self.artificial_shift(self.theme)
        self.assertGreater(
            after, before,
            "yapay %s px kaydırma ölçülmedi (before=%s after=%s) — ölçüm "
            "hattı ölü, test-3'teki PASS güvenilmez" % (
                ARTIFICIAL_SHIFT_PX, before, after))
        ok, reason = evaluate_budget(after, budget=self.budget)
        self.assertFalse(
            ok,
            "yapay kaydırma bütçeyi AŞMADI (%s) — bütçe eşiği gerçekten "
            "uygulanmıyor" % reason)


if __name__ == "__main__":
    unittest.main(verbosity=2)
