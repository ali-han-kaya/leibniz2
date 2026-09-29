#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_dashboard_next_battery_smoke.py — üç sözleşmenin BATARYA girmiş
(smoke) hâli.

Neden ayrı dosya: bu üç sözleşmenin derin ölçümü zaten var ama
`check_unit_tests.list`in DIŞINDA (EXCLUDE) — Chromium/`next start` bütçesi
gerekçesiyle. Sonuç: **batarya bu üç sözleşme hakkında hiçbir şey
bilmiyor**, ve `check_unit_tests_hook.sh` çıktıyı `/dev/null`'a attığı için
"koştu mu, skip mi oldu" ayrımı da görünmüyor. Kırık bir sözleşme ancak
CI'ın `dashboard-next` job'ında fark edilir.

Buradaki çözüm iki katmanlıdır:

  1. **STATİK katman (HER koşuda, ön koşul YOK).** Sözleşmenin kaynak
     tarafındaki değişmezini okur. Dakikalarca sürmez, Chromium gerektirmez,
     hiçbir ortamda skip olmaz. Bataryadaki asıl garanti bu katmandır —
     dosya, ortam ne olursa olsun bu sözleşmelerden biri sessizce
     ölçülemez hâle gelemez.
  2. **CANLI katman (skip-guard'lı).** Ortam varsa gerçekten ölçer:
     `next start` + Chromium. İki farklı ön koşul profili vardır ve
     SKIP sebebi AÇIKÇA yazılır (sessiz skip, bu depodaki "koşmayan test"
     hastalığının ta kendisidir).

Sözleşmeler:
  A. 20 satırlık trend penceresi — `/trend` limit=20, pano slotu limit=5;
     SSR ile canlı tablo AYNI pencere/ters-sıra kuralını uygular.
  B. React `cache()` dedup — `getLatest`/`getTrend` istek-başına
     önbelleklenir; `getTrend`'in iki tüketicisi FARKLI argümanla
     çağrıldığı için iki AYRI önbellek girdisidir (aynı girdi değil).
  C. `next/link` yumuşak gezinme — pano→/trend geçişi tam yeniden yükleme
     değildir; slotlar `(panel)` grubunda yaşar, `/trend` onları miras
     almaz.

Sunucu kablosu TEK kaynaktan gelir (`test_dashboard_cls_budget` +
`test_surface_cwv_report`), bu yüzden ikinci bir kablolama yazılmaz.

Koşum:
  python3 -m unittest _calisma.CIKTI.test_dashboard_next_battery_smoke
  python3 -m pytest _calisma/CIKTI/test_dashboard_next_battery_smoke.py
"""

import datetime
import json
import os
import pathlib
import re
import shutil
import sys
import tempfile
import threading
import unittest
import urllib.request
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent.parent
NEXT = REPO / "apps" / "dashboard-next"
APP = NEXT / "app"
COMPONENTS = NEXT / "components"
NEXT_BIN = NEXT / "node_modules" / ".bin" / "next"
BUILD_ID = NEXT / ".next" / "BUILD_ID"
TREND_PAGE = APP / "trend" / "page.tsx"
TREND_SLOT = APP / "(panel)" / "@trend" / "page.tsx"
PANEL_PAGE = APP / "(panel)" / "page.tsx"
PANEL_LAYOUT = APP / "(panel)" / "layout.tsx"
RUNS_TABLE_DATA = COMPONENTS / "RunsTableData.tsx"
RUNS_TABLE = COMPONENTS / "RunsTable.tsx"
PREVIEW_LIB = NEXT / "lib" / "preview.ts"
TREND_DB = NEXT / "lib" / "trend-db.ts"

sys.path.insert(0, str(HERE))
import test_dashboard_cls_budget as cwv_core  # noqa: E402
import test_surface_cwv_report as cwv  # noqa: E402

try:
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover - Chromium'sız ortam
    sync_playwright = None

# Sözleşmenin sabitleri. Kullanıcı yüzeyi değişirse (panel özeti 7 olursa)
# hem statik hem canlı katman aynı yerden kırılır — iki yerde ayrı sayı
# yazmıyoruz.
PANEL_LIMIT = 5
TREND_LIMIT = 20


def _read(path):
    return path.read_text(encoding="utf-8")


def _limits_in(text):
    """`limit={N}` geçen tüm N'leri döndür (JSX geçerli sözdiziminde)."""
    return [int(n) for n in re.findall(r"limit=\{(\d+)\}", text)]


def _chromium_missing():
    """Chromium kurulu mu? (import + çalıştırılabilir dosya)"""
    if sync_playwright is None:
        return "playwright kurulu değil"
    try:
        with sync_playwright() as p:
            path = p.chromium.executable_path
    except Exception as exc:  # pragma: no cover - kurulum bozuk
        return "chromium çözülemedi: %s" % exc
    if not os.path.isfile(path):
        return "chromium indirilmemiş (playwright install chromium)"
    return ""


def _next_missing():
    """`next start` için ön koşullar: binary + derlenmiş pano."""
    if not NEXT_BIN.is_file():
        return "apps/dashboard-next/node_modules yok (npm ci gerekli)"
    if not BUILD_ID.is_file():
        return "apps/dashboard-next/.next derlemesi yok (next build gerekli)"
    return ""


# ────────────────────────────────────────────────────────────────────────────
# 1. STATİK KATMAN — her koşuda, hiçbir ön koşul yok
# ────────────────────────────────────────────────────────────────────────────
class TrendWindowStaticContractTest(unittest.TestCase):
    """A. 20 satırlık pencere: kaynakta sabitlenmiş hâli."""

    def test_trend_page_requests_the_twenty_row_window(self):
        limits = _limits_in(_read(TREND_PAGE))
        self.assertEqual(limits, [TREND_LIMIT],
                         "/trend sayfası limit={%d} istemeli, bulunan: %s"
                         % (TREND_LIMIT, limits))

    def test_panel_slot_keeps_its_own_shorter_window(self):
        limits = _limits_in(_read(TREND_SLOT))
        self.assertEqual(limits, [PANEL_LIMIT],
                         "pano özeti limit={%d} olmalı, bulunan: %s"
                         % (PANEL_LIMIT, limits))

    def test_the_two_windows_are_distinct_cache_keys(self):
        """İki tüketici FARKLI argümanla çağrılmalı.

        Aynı argüman olsaydı `getTrend(limit)` iki tüketicide TEK önbellek
        girdisi olurdu ve 20'lik tam sayfa, 5'lik panel isteğinin
        sonucuyla dönerdi (ya da tersi). Ayrı pencere = ayrı girdi.
        """
        self.assertNotEqual(PANEL_LIMIT, TREND_LIMIT,
                            "pano ve tam sayfa aynı pencereyi istiyor — "
                            "getTrend önbelleği iki tüketicide çakışır")

    def test_server_side_window_uses_the_newest_rows(self):
        """`slice(-limit).reverse()` — en yeni, eskiden yeniye.

        `slice(limit)` EN ESKİ N'yi döndürür ve "son 20" başlığı yalan
        söyler; `reverse()` olmazsa tablo en yeniyi üstte göstermez.
        """
        for path in (RUNS_TABLE_DATA, RUNS_TABLE):
            self.assertRegex(
                _read(path), r"slice\(-limit\)\.reverse\(\)",
                "%s en yeni %d satırı, eskiden yeniye sırayla basmalı "
                "(slice(-limit).reverse())" % (path.name, TREND_LIMIT))

    def test_ssr_and_live_share_one_windowing_rule(self):
        """Sunucu ve istemci AYNI ifadeyi kullanmalı.

        İki taraf ayrı kural uygularsa ilk boya ile canlı akış farklı satır
        sayısı gösterir ve tablo "zıplar".
        """
        server = re.search(r"slice\(-limit\)\.reverse\(\)", _read(RUNS_TABLE_DATA))
        client = re.search(r"slice\(-limit\)\.reverse\(\)", _read(RUNS_TABLE))
        self.assertTrue(server and client,
                        "her iki tarafta da pencere kuralı bulunmalı")


class ReactCacheStaticContractTest(unittest.TestCase):
    """B. React `cache()` dedup sözleşmesi, kaynakta."""

    def test_reading_helpers_are_cache_wrapped(self):
        src = _read(PREVIEW_LIB)
        for fn in ("getLatest", "getTrend"):
            self.assertRegex(
                src, r"export const %s = cache\(" % fn,
                "%s React cache() ile sarılmalı — aynı istekte iki tüketici "
                "tek upstream turu paylaşır" % fn)

    def test_db_branch_is_cache_wrapped_too(self):
        """DB dalı da aynı sözleşmeyi taşır; iki dal ayrışmamalı."""
        src = _read(TREND_DB)
        for fn in ("getLatestFromDb", "getTrendFromDb"):
            self.assertRegex(src, r"export const %s = cache\(" % fn,
                             "%s cache() ile sarılmalı" % fn)

    def test_trend_has_exactly_two_call_sites_with_distinct_args(self):
        """İki tüketici, iki argüman — ne eksik ne fazla.

        Üçüncü bir tüketici eklenirse ya da iki tüketici aynı argümanı
        kullanırsa dedup sözleşmesi sessizce değişir; sayı burada sabit.
        """
        args = set(_limits_in(_read(TREND_SLOT)))
        args.update(_limits_in(_read(TREND_PAGE)))
        self.assertEqual(args, {PANEL_LIMIT, TREND_LIMIT},
                         "getTrend çağrı yerleri {limit=5, limit=20} olmalı, "
                         "bulunan: %s" % sorted(args))

    def test_verdict_card_is_the_only_latest_consumer(self):
        """`getLatest` tek tüketicili — N+1 başlangıcı görünmez olsun."""
        consumers = [p for p in (APP / "VerdictCard.tsx", RUNS_TABLE_DATA,
                                 TREND_PAGE, TREND_SLOT, PANEL_PAGE)
                     if "getLatest(" in _read(p)]
        self.assertEqual(len(consumers), 1,
                         "getLatest tüketicisi 1 olmalı, bulunan: %s"
                         % [p.name for p in consumers])


class SoftNavigationStaticContractTest(unittest.TestCase):
    """C. `next/link` yumuşak gezinme sözleşmesi, kaynakta."""

    def test_panel_uses_next_link_for_the_trend_route(self):
        src = _read(PANEL_PAGE)
        self.assertIn('from "next/link"', src,
                      "pano /trend bağlantısını next/link ile kurmalı — ham "
                      "<a> tam yeniden yükleme yapar (durumu ve işaretleri "
                      "kaybeder)")
        self.assertRegex(src, r"<Link[^>]*href=\"/trend\"",
                         "next/link yolu /trend'e işaret etmeli")

    def test_raw_anchor_stays_external_only(self):
        """Ham `<a>` yalnız DIŞ hedef için (preview.html) kalmalı."""
        src = _read(PANEL_PAGE)
        for match in re.findall(r"<a\s[^>]*href=\{?([^}\s>]+)", src):
            self.assertNotIn("/trend", match,
                             "iç rota ham <a> ile verilmiş — yumuşak "
                             "gezinme kaybolur: %s" % match)

    def test_slots_live_inside_the_panel_route_group(self):
        """Slotlar `(panel)` grubunda olmalı.

        Slotlar kök layout'ta olsaydı `/trend` de onları miras alır ve
        Next'in paralel rota semantiği gereği yumuşak geçişte önceki
        durumlarını korurlardı: tam sayfa tablonun üstünde verdict kartı
        kalırdı.
        """
        self.assertTrue(PANEL_LAYOUT.is_file(),
                        "(panel)/layout.tsx yok — slot kapsamı kayboldu")
        for slot in ("@verdict", "@trend"):
            self.assertTrue((APP / "(panel)" / slot / "page.tsx").is_file(),
                            "%s slotu (panel) grubu içinde olmalı" % slot)

    def test_viewtransition_lives_in_page_not_layout(self):
        """`<ViewTransition>` layout'ta değil sayfada olmalı.

        Layout'lar gezinmeler arasında kalıcıdır; enter/exit orada hiç
        ateşlenmez ve sarmalayıcı sessizce hiçbir şey yapmaz.
        """
        layout = _read(PANEL_LAYOUT)
        self.assertNotIn("ViewTransition", layout,
                         "layout'ta ViewTransition ateşlenmez — sayfada "
                         "olmalı")


# ────────────────────────────────────────────────────────────────────────────
# 2. CANLI KATMAN — skip-guard'lı, ortam varsa gerçek ölçüm
# ────────────────────────────────────────────────────────────────────────────
def _ts(index):
    """Tekil ve artan sentetik koşum damgası."""
    base = datetime.datetime(2026, 9, 1, tzinfo=datetime.timezone.utc)
    return (base + datetime.timedelta(minutes=index)).strftime(
        "%Y-%m-%dT%H:%M:%SZ")


class _QuietServer(ThreadingHTTPServer):
    """Tarayıcı bağlantıyı kapattığında yükselen hataları yutar."""

    def handle_error(self, request, client_address):
        pass


class CountingUpstream:
    """İstek SAYAN preview_server taklidi (stdlib, ağ dışına çıkmaz).

    Sayım `(yol? sorgu)` çiftinde: React `cache()` argümana göre
    anahtarlandığı için `/api/trend?limit=5` ile `?limit=20` FARKLI
    girdilerdir ve birleştirilirse dedup iddiası ölçülemez.
    """

    def __init__(self, rows=1):
        self._rows = [{
            "ts": _ts(i), "p0": 0, "p1": 0, "duration_s": 300.0 + i,
            "budget_usd": 12.0, "z3_total": 5,
        } for i in range(rows)]
        self._hits = Counter()
        self._lock = threading.Lock()

        outer = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def do_GET(self):  # noqa: N802 — stdlib arayüz adı
                outer.record(self.path)
                path = self.path.split("?", 1)[0]
                if path == "/api/trend":
                    body = {"history": list(outer.rows())}
                elif path == "/api/latest":
                    newest = outer.newest()
                    body = {"verdict": "PASS", "ts": newest.get("ts"),
                            "p0": 0, "p1": 0, "budget_usd": 12.0,
                            "budget_limit": 30.0, "z3_passed": 5,
                            "z3_total": 5}
                else:
                    self.send_response(404)
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                raw = json.dumps(body).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def log_message(self, *args):
                pass

        self.port = cwv_core.free_port()
        self._server = _QuietServer(("127.0.0.1", self.port), Handler)
        threading.Thread(target=self._server.serve_forever, daemon=True).start()

    @property
    def url(self):
        return "http://127.0.0.1:%d" % self.port

    def rows(self):
        with self._lock:
            return list(self._rows)

    def newest(self):
        with self._lock:
            return dict(self._rows[-1]) if self._rows else {}

    def record(self, path):
        with self._lock:
            self._hits[path] += 1

    def reset(self):
        """Sayacı sıfırla.

        Sınıf düzeyinde TEK upstream paylaşıldığı için sayaç testler
        arasında birikir; sıfırlamazsak "tam 1 istek" iddiası İKİNCİ
        testte kendi kendini çürütür (ve hata çevreden değil testten
        geliyormuş gibi görünür).
        """
        with self._lock:
            self._hits.clear()

    def hits(self):
        with self._lock:
            return dict(self._hits)

    def seam_totals(self):
        totals = Counter()
        for path, count in self.hits().items():
            totals[path.split("?", 1)[0]] += count
        return dict(totals)

    def stop(self):
        self._server.shutdown()
        self._server.server_close()


class _NextAppBase(unittest.TestCase):
    """Yayınlayan upstream + `next start` — canlı katmanın ortak kurulumu."""

    UPSTREAM_ROWS = 1

    def setUp(self):
        # Her test kendi ölçümünü kendi sayacıyla yapsın.
        if type(self).upstream is not None:
            type(self).upstream.reset()

    def _open(self, p, path):
        """Chromium'u aç, sayfayı yükle → (browser, page)."""
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(self.base + path, wait_until="domcontentloaded")
        return browser, page

    @classmethod
    def setUpClass(cls):
        missing = _next_missing()
        if missing:
            raise unittest.SkipTest("canlı katman atlandı: %s" % missing)
        cls._tmp = tempfile.mkdtemp(prefix="next_battery_")
        cls.addClassCleanup(shutil.rmtree, cls._tmp, True)
        cls.upstream = CountingUpstream(rows=cls.UPSTREAM_ROWS)
        cls.addClassCleanup(cls.upstream.stop)
        port = cwv_core.free_port()
        cls.proc = cwv.spawn_next_server(
            port, cls.upstream.url, os.path.join(cls._tmp, "next_start.log"))
        cls.addClassCleanup(cwv.terminate, cls.proc)
        if not cwv_core.wait_for_port("127.0.0.1", port, timeout=30):
            raise RuntimeError("next start ayağa kalkmadı")
        cls.base = "http://127.0.0.1:%d" % port

    def _render(self, path="/"):
        req = urllib.request.Request(self.base + path, method="GET")
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, resp.read().decode("utf-8")


@unittest.skipUnless(not _next_missing(), "next start ön koşulu yok")
class ReactCacheLiveSmokeTest(_NextAppBase):
    """B. Dedup'ın canlı ölçümü — tarayıcı GEREKMEZ.

    Dedup sunucu tarafında olur; yalnız HTTP render yeter. Bu yüzden bu
    katman tarayıcı ön koşulundan bağımsız çalışır ve CI'da Chromium
    olmasa da ölçer.
    """

    def test_panel_render_hits_each_seam_exactly_once(self):
        code, _ = self._render("/")
        self.assertEqual(code, 200, "panel 200 dönmeli")
        seams = self.upstream.seam_totals()
        self.assertEqual(seams.get("/api/latest"), 1,
                         "getLatest için tam 1 upstream isteği: %s" % seams)
        self.assertEqual(seams.get("/api/trend"), 1,
                         "getTrend için tam 1 upstream isteği: %s" % seams)
        self.assertEqual(sum(seams.values()), 2,
                         "panel render'ı toplam 2 upstream isteği atmalı "
                         "(her dikiş 1): %s" % seams)

    def test_dedup_is_per_request_not_per_process(self):
        """İkinci render KENDİ isteğini atmalı.

        Süreç geneli önbellek 0 döner ve pano uygulama yeniden
        başlatılana kadar bayat verdict gösterir — sessiz doğruluk hatası.
        """
        self._render("/")
        self._render("/")
        seams = self.upstream.seam_totals()
        self.assertEqual(seams.get("/api/latest"), 2,
                         "iki render = iki istek (süreç geneli önbellek "
                         "olsaydı 1 olurdu): %s" % seams)
        self.assertEqual(seams.get("/api/trend"), 2, "aynısı trend için: %s"
                         % seams)

    def test_counting_upstream_saw_real_traffic(self):
        """Vakum denetimi — sayaç boş kalırsa yukarıdaki ikisi sahte yeşil."""
        self._render("/")
        self.assertTrue(self.upstream.hits(),
                        "upstream hiç istek almadı — ölçüm geçersiz")


class TrendWindowLiveSmokeTest(_NextAppBase):
    """A. 20 satırlık pencerenin canlı ölçümü (Chromium gerekir)."""

    UPSTREAM_ROWS = 25  # 20'nin üstü: kırpma ancak burada GÖRÜNÜR

    def _row_stamps(self, page):
        return page.eval_on_selector_all(
            "tbody tr time", "els => els.map(e => e.getAttribute('datetime'))")

    def test_trend_page_renders_exactly_twenty_newest_rows(self):
        with sync_playwright() as p:
            browser, page = self._open(p, "/trend")
            try:
                page.wait_for_function(
                    "() => document.querySelectorAll('tbody tr').length > 0",
                    timeout=20000)
                stamps = self._row_stamps(page)
            finally:
                browser.close()
        self.assertEqual(len(stamps), TREND_LIMIT,
                         "upstream %d satır taşırken /trend tam %d satır "
                         "basmalı, basılan: %d"
                         % (self.UPSTREAM_ROWS, TREND_LIMIT, len(stamps)))
        self.assertEqual(stamps[0], self.upstream.newest()["ts"],
                         "ilk satır EN YENİSİ olmalı — ters sırada 'son %d' "
                         "başlığı en eskiyi gösterir" % TREND_LIMIT)
        for newer, older in zip(stamps, stamps[1:]):
            self.assertGreater(newer, older, "sıra yeni→eski değil: %s" % stamps)


@unittest.skipUnless(not _chromium_missing(), "chromium ön koşulu yok")
class SoftNavigationLiveSmokeTest(_NextAppBase):
    """C. `next/link` yumuşak geçişi (Chromium gerekir)."""

    def test_panel_to_trend_navigation_is_soft(self):
        with sync_playwright() as p:
            browser, page = self._open(p, "/")
            try:
                page.wait_for_function(
                    "() => !!document.querySelector('a[href=\"/trend\"]')",
                    timeout=20000)
                # Sayfa yaşamı boyunca korunmalı; tam yeniden yükleme
                # window'ü ve timeOrigin'i sıfırlar.
                page.evaluate("() => { window.__softNavMarker = 42; }")
                origin_before = page.evaluate("() => performance.timeOrigin")

                page.click("a[href=\"/trend\"]")
                page.wait_for_function(
                    "() => location.pathname === '/trend'", timeout=20000)
                page.wait_for_function(
                    "() => document.querySelectorAll('tbody tr').length > 0",
                    timeout=20000)

                marker = page.evaluate("() => window.__softNavMarker")
                origin_after = page.evaluate("() => performance.timeOrigin")
            finally:
                browser.close()

        self.assertEqual(
            marker, 42,
            "window.__softNavMarker kayboldu → TAM YENİDEN YÜKLEME. "
            "Gezinme next/link ile OLMALI (ham <a> tam yükleme yapar)")
        self.assertEqual(origin_after, origin_before,
                         "performance.timeOrigin değişti → tam sayfa "
                         "yeniden yüklendi")


if __name__ == "__main__":
    unittest.main()
