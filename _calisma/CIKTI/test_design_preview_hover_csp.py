#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SECURITY-TIER: browser
"""test_design_preview_hover_csp.py — demo artifact'ı hover tooltip'lerinin
GERÇEK tarayıcıda, ÜRETİM CSP'si altında kanıtı.

NEDEN BU SÜİT VAR
-----------------
`design_preview.html` (üretilmiş demo artifact'ı, commit dışı) bugüne kadar
yalnız STATİK tarandı: `preview_inline_audit.INLINE_HANDLER_RE` sayaсı
"nitelik handler yok" der, `test_preview_server.py` de bunu kapıya bağlar.
Sayaç `onmousemove` yokluğunu kanıtlar; ama artifact'ın KENDİ kablolamasının
(data-tip + SVG-düzeyi delege mousemove → `#tip`) gerçekten çalıştığını
hiçbir tarayıcı doğrulamıyordu. VERIFY-001'in sınıfı tam buydu: nitelik
handler CSP altında sessizce ölür ve statik sayaç sıfır kalabilir.

ÖLÇÜLEN İKİ GERÇEK (2026-10-21, bu süit yazılırken)
---------------------------------------------------
1. Artifact HTML'i TEK içerikli inline `<script>` taşır ve **nonce'suzdur**.
   Üretim CSP'si `script-src 'self' 'nonce-…'` olduğu için tarayıcı onu
   BLOKLAR: `window.__DESIGN_AUDIT__` tanımsız, hiç hit-alanı yok, konsolda
   "Executing inline script violates the following Content Security Policy
   directive 'script-src …'" yazar. Yani artifact "CSP altında" ancak servis
   eden katman nonce enjekte ederse çalışır — `preview_server.serve_preview`
   `preview.html` için tam olarak bunu yapıyor.
2. Bu süit, servis katmanının nonce enjeksiyonunu birebir taklit eder
   (CSP başlığı ve nonce `preview_server`'dan OKUNUR, uydurulmaz) ve
   nonce'lu sayfada üç grafiğin tooltip'inin satıra bağlı çalıştığını
   gerçek fare hareketiyle gösterir.

İKİ KATMAN (biri diğerini çürütmesin diye ayrı testler)
-------------------------------------------------------
* **Ham artifact + üretim CSP'si** → inline script BLOKLANIR. Bu bir pozitif
  kontroldür: harness'in uyguladığı CSP gerçekten yürürlükteyse buradadır;
  CSP gevşetilirse (ör. 'unsafe-inline' eklenirse) bu test kırmızıya düşer.
* **Nonce'lu artifact + aynı CSP** → script çalışır, hover tooltip'i o
  satırın değerlerini gösterir, üç grafikte de delege çalışır ve konsolda
  CSP ihlali OLMAZ.

SINIR (açıkça): bu süit "artifact nonce olmadan da CSP altında çalışır"
demiyor — çalışmıyor, ve bunu (1) piniyor. Kanıtlanan şey tooltip
kablolamasının CSP-uyumlu olduğu (nitelik handler'a dayanmadığı) ve servis
katmanının vereceği nonce ile uçtan uca çalıştığıdır.

NOT (ölçüldü, ayrı bulgu): artifact'ın kendi iç denetimi bu süitte
KİLİTLENMEZ çünkü kendisi hatalı — `__DESIGN_AUDIT__` s2/s3 değerleri
False çıkıyor: (i) s2 FAIL durumunda halkada "VERIFIED" arıyor (render
"JOB FAILED" yazar, yani koşul hiç sağlanamaz), (ii) `applySnapshot`
`document.startViewTransition` kullanınca güncelleme ERTELENİR, denetim ise
DOM'u senkron okur (500 ms sonra sınıf doğru: seal-fail). Bu yüzden burada
yalnız "script koştu ve hata vermedi" (canlılık) doğrulanır; yanlış
denetime değerler pinlenmez.

Çalıştırma:
  python3 -m unittest discover -s _calisma/CIKTI -p "test_design_preview_hover_csp.py" -v
Playwright/Chromium yoksa SKIP — ama `check_security_posture.sh` SKIP'i
REDDEDER (browser roster'da); yani CI'da bu kanıt Chromium'suz yeşile dönmez.
"""
import http.server
import pathlib
import re
import sys
import tempfile
import threading
import unittest

try:
    from playwright.sync_api import sync_playwright
except ImportError:  # Chromium/Playwright yoksa SKIP (posture kapısı reddeder)
    sync_playwright = None

HERE = pathlib.Path(__file__).resolve().parent
if str(HERE) not in sys.path:  # yardımcı modüller CIKTI içinde
    sys.path.insert(0, str(HERE))

# Chrome'un CSP ihlali mesaj kalıpları (canlı tooltip süitiyle aynı sınıf).
CSP_MARKERS = (
    "Content Security Policy",
    "Refused to execute",
    "Refused to apply",
)

# Artifact'ın kendi iç denetimi: CSP altında script hiç koşmazsa tanımsız.
AUDIT_PROBE = "() => window.__DESIGN_AUDIT__ || null"


def _load_production_csp():
    """Üretim CSP başlığını ve nonce'u SUNUCUDAN oku (tek kaynak)."""
    import preview_server as ps

    csp = dict(ps.Handler._SECURITY_HEADERS)["Content-Security-Policy"]
    return csp, ps.BUILD_TS_NONCE


def inject_nonce(html, nonce):
    """Servis katmanının nonce enjeksiyonunu taklit et (serve_preview deseni).

    Her `<script …>` etiketine nonce ekler; JS gövdesindeki `"<script"`
    gibi string'ler etkilenmez (lookahead yalnız boşluk/`>` kabul eder).
    Nonce'suz script kalırsa çağıran taraf FAIL eder — sessiz yarım enjeksiyon
    testi yanlış yeşile çeviremez.
    """
    out, count = re.subn(r"<script(?=[\s>])",
                         '<script nonce="%s"' % nonce, html)
    leftover = re.search(r"<script(?! nonce=\")(?=[\s>])", out)
    if count == 0 or leftover:
        raise AssertionError(
            "nonce enjeksiyonu eksik: %d etiket, kalan nonce'suz script=%r"
            % (count, leftover.group(0) if leftover else None))
    return out, count


class _ArtifactServer(http.server.ThreadingHTTPServer):
    """Artifact'ı iki modda servis eder; üretim CSP başlığını aynen basar."""

    daemon_threads = True
    allow_reuse_address = True


def _make_handler(bodies, csp):
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 — stdlib arayüz adı
            path = self.path.split("?", 1)[0]
            body = bodies.get(path)
            if body is None:
                self.send_error(404)
                return
            payload = body.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Security-Policy", csp)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *args):  # sunucu logu testi kirletmesin
            pass

    return Handler


@unittest.skipIf(sync_playwright is None,
                 "playwright kurulu değil (pip install playwright + "
                 "playwright install chromium)")
class DesignPreviewHoverUnderCSPTest(unittest.TestCase):
    """Üretilen demo artifact'ı: CSP'li gerçek tarayıcıda hover kanıtı."""

    @classmethod
    def setUpClass(cls):
        import preview_inline_audit as audit

        cls.tmp = tempfile.TemporaryDirectory(prefix="design-preview-csp-")
        cls.addClassCleanup(cls.tmp.cleanup)
        artifact = pathlib.Path(cls.tmp.name) / "design_preview.html"
        try:
            cls.raw_html = audit.generate_design_preview(artifact)
        except audit.ArtifactBuildError as exc:  # fail-closed, SKIP değil
            raise RuntimeError(
                "design_preview.html üretilemedi: %s" % exc) from exc
        cls.artifact_path = artifact

        cls.csp, cls.nonce = _load_production_csp()
        # Fail-closed: CSP'nin gerçekten nonce taşıdığını burada doğrula;
        # aksi halde "nonce enjekte ettik" iddiası boş olurdu.
        if "nonce-%s" % cls.nonce not in cls.csp:
            raise RuntimeError(
                "üretim CSP'si BUILD_TS_NONCE taşımıyor — nonce enjeksiyonu "
                "testi anlamsız olurdu: %r" % cls.csp)
        cls.nonced_html, cls.nonce_count = inject_nonce(cls.raw_html,
                                                        cls.nonce)

        cls.server = _ArtifactServer(
            ("127.0.0.1", 0),
            _make_handler({"/raw": cls.raw_html,
                           "/nonced": cls.nonced_html}, cls.csp))
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever,
                                      daemon=True)
        cls.thread.start()
        cls.addClassCleanup(cls._stop_server)

    @classmethod
    def _stop_server(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)

    def setUp(self):
        self._pw = sync_playwright().start()
        self.browser = self._pw.chromium.launch(headless=True)
        self.context = self.browser.new_context(service_workers="block")
        self.page = self.context.new_page()
        self.console = []
        self.errors = []
        self.page.on("console", lambda m: self.console.append(
            "%s: %s" % (m.type, m.text)))
        self.page.on("pageerror", lambda e: self.errors.append(str(e)))
        self.response = None

    def tearDown(self):
        self.context.close()
        self.browser.close()
        self._pw.stop()

    # ------------------------------------------------------------- yardımcı
    def _open(self, route):
        self.response = self.page.goto(
            "http://127.0.0.1:%d%s" % (self.port, route),
            wait_until="domcontentloaded")
        self.page.wait_for_timeout(700)
        return self.response

    def _csp_violations(self):
        return [line for line in self.console + self.errors
                if any(marker in line for marker in CSP_MARKERS)]

    def _tip_state(self):
        return self.page.evaluate(
            "(() => { const t = document.getElementById('tip');"
            " if (!t) return {missing: true};"
            " return {display: t.style.display,"
            " text: (t.textContent || ''),"
            " visible: getComputedStyle(t).display !== 'none'}; })()")

    def _seed_refs(self):
        """refs-trend'i SAYFANIN KENDİ render fonksiyonuyla doldur.

        Hiçbir markup test tarafından uydurulmaz: hit-alanlarını üretim
        kodu (`renderRefsTrend`) basar; refs_verified her satırda farklı
        (10, 17, 24, 31) → tooltip'in satıra bağlı olduğu ayırt edilir.
        """
        self.page.evaluate(
            """(() => {
              const rows = Array.from({length: 4}, (_, i) => ({
                ts: new Date(Date.now() - (4 - i) * 3600e3).toISOString(),
                refs_verified: 10 + i * 7,
                refs_total: 40,
                refs_mismatch: i,
                verdict: "PASS", p0: 0, p1: 0,
              }));
              renderRefsTrend(rows);
            })()""")
        self.page.wait_for_timeout(200)

    def _seed_trend(self):
        self.page.evaluate(
            """(() => {
              const rows = Array.from({length: 3}, (_, i) => ({
                ts: new Date(Date.now() - (3 - i) * 3600e3).toISOString(),
                duration_s: 2 + i, verdict: "PASS", p0: 0, p1: 0,
                z3_passed: 5 + i, z3_total: 10, z3_failed: 0,
                lean_ok: true, budget_usd: 3 + i,
              }));
              renderTrend(rows);
            })()""")
        self.page.wait_for_timeout(200)

    def _seed_hookenv(self):
        self.page.evaluate(
            """(() => {
              const rows = Array.from({length: 3}, (_, i) => ({
                ts: new Date(Date.now() - (3 - i) * 3600e3).toISOString(),
                verdict: "PASS", p0: 0, p1: 0,
                hook_env: {python: "3.11.1", z3: "4.8.17"},
              }));
              renderHookEnvTrend(rows);
            })()""")
        self.page.wait_for_timeout(200)

    def _hit_rects(self, svg_id, expect):
        """Hit-alanları: sayı ZORLANIR (0 alanda "yeşil" boş kanıt olurdu)."""
        rects = self.page.locator("#%s rect[data-tip]" % svg_id)
        self.assertEqual(
            rects.count(), expect,
            "#%s hit-alanı sayısı %d değil — delege/rect üretimi bozuk"
            % (svg_id, expect))
        return rects

    # ------------------------------------------------- testler: CSP katmanı
    def test_harness_uses_the_production_csp_header_verbatim(self):
        """Harness'in CSP'si üretim başlığının TA KENDİSİ olmalı.

        Testin kendi gevşettiği bir CSP ile "CSP altında çalışıyor" demek
        sahte kanıt olurdu; burada başlık kaynaktan okunur ve yanıtla
        birebir karşılaştırılır.
        """
        response = self._open("/raw")
        self.assertEqual(
            response.headers.get("content-security-policy"), self.csp,
            "servis edilen CSP üretim başlığıyla aynı değil")
        script_src = re.search(r"script-src[^;]*", self.csp).group(0)
        self.assertIn("'self'", script_src)
        self.assertIn("'nonce-", script_src)
        self.assertNotIn("unsafe-inline", script_src)
        self.assertNotIn("unsafe-eval", script_src)

    def test_raw_artifact_is_blocked_by_the_production_csp(self):
        """POZİTİF KONTROL: nonce'suz artifact gerçekten engellenir.

        Bu test düşerse (yani ham artifact çalışırsa) harness'in CSP'si
        yürürlükte değildir ve aşağıdaki tüm tooltip kanıtları çürük olurdu.
        Aynı zamanda artifact'ın servis sözleşmesini pinler: inline script
        yalnız servis katmanı nonce verirse çalışır. Artifact bir gün
        harici `<script src=…>`'e taşınırsa bu beklenti ANLAMSIZLAŞIR (o
        durumda CSP altında doğrudan ÇALIŞMALI) — o yüzden önce şekil
        doğrulanır ki kırmızı, "CSP bozuldu" diye yanlış okunmasın.
        """
        inline_tags = [t for t in re.findall(r"<script[^>]*>", self.raw_html)
                       if "src=" not in t]
        self.assertTrue(
            inline_tags,
            "artifact artık inline <script> taşımıyor — bu kontrolü, artifact'ın "
            "CSP altında DOĞRUDAN çalıştığını kanıtlayacak şekilde güncelle")
        self._open("/raw")
        self.assertIsNone(
            self.page.evaluate(AUDIT_PROBE),
            "CSP yürürlükte değil: nonce'suz inline script KOŞTU")
        self.assertEqual(
            self.page.locator("rect[data-tip]").count(), 0,
            "nonce'suz sayfada hit-alanı oluşmuş — script koşmuş olmalı")
        violations = self._csp_violations()
        self.assertTrue(
            violations,
            "konsolda CSP ihlali yok — harness CSP'yi uygulamıyor olabilir")
        self.assertTrue(
            any("Executing inline script violates" in line
                for line in violations),
            "beklenen inline-script ihlali konsolda yok: %r"
            % (violations[:3],))

    # ------------------------------------------- testler: nonce'lu gerçek sayfa
    def test_artifact_runs_when_the_serving_layer_grants_the_nonce(self):
        self._open("/nonced")
        self.assertGreaterEqual(self.nonce_count, 1)
        audit_result = self.page.evaluate(AUDIT_PROBE)
        self.assertIsInstance(audit_result, dict,
                              "nonce'lu sayfada artifact script'i koşmadı")
        self.assertNotIn("error", audit_result,
                         "artifact kendi iç denetiminde hata verdi: %r"
                         % (audit_result,))
        self.assertEqual(self.page.evaluate(
            "() => typeof window.renderRefsTrend"), "function",
            "renderRefsTrend global değil — sayfa yapısı değişti")
        self.assertIsNotNone(self.page.query_selector("#tip"),
                             "#tip tooltip kapsayıcısı yok")

    def test_hover_shows_that_rows_refs_values(self):
        """ASIL KANIT: fare sütuna girince tooltip O SATIRIN verisini gösterir."""
        self._open("/nonced")
        self.assertFalse(self._tip_state()["visible"],
                         "hover öncesi tooltip görünür olmamalı")
        self._seed_refs()
        rects = self._hit_rects("refs-trend", 4)
        rects.nth(1).hover()
        self.page.wait_for_timeout(250)
        tip = self._tip_state()
        self.assertTrue(
            tip["visible"],
            "hover sonrası tooltip GÖRÜNMEDİ — CSP altında delege mousemove "
            "ölmüş olabilir (VERIFY-001 regresyonu)")
        self.assertIn("refs", tip["text"], "tooltip refs satırı içermiyor")
        self.assertIn("17", tip["text"],
                      "2. sütunun refs_verified=17 değeri yok: %r"
                      % tip["text"][:200])
        self.assertIn("40", tip["text"], "refs_total=40 görünmüyor")

    def test_hover_on_another_column_changes_the_tooltip(self):
        """Delege İNDEKSİ doğru: sabit tooltip değil, satıra bağlı içerik."""
        self._open("/nonced")
        self._seed_refs()
        rects = self._hit_rects("refs-trend", 4)
        rects.nth(1).hover()
        self.page.wait_for_timeout(250)
        first = self._tip_state()["text"]
        rects.nth(3).hover()
        self.page.wait_for_timeout(250)
        second = self._tip_state()["text"]
        self.assertNotEqual(first, second,
                            "iki farklı sütun aynı tooltip'i gösteriyor — "
                            "data-i delegesi çalışmıyor")
        self.assertIn("31", second, "4. sütun refs_verified=31 göstermiyor")

    def test_leaving_the_chart_hides_the_tooltip(self):
        self._open("/nonced")
        self._seed_refs()
        self._hit_rects("refs-trend", 4).first.hover()
        self.page.wait_for_timeout(250)
        self.assertTrue(self._tip_state()["visible"])
        self.page.mouse.move(5, 5)
        self.page.wait_for_timeout(300)
        self.assertFalse(self._tip_state()["visible"],
                         "grafikten çıkınca tooltip gizlenmedi "
                         "(mouseleave yolu ölü)")

    def test_trend_chart_hover_works_in_the_artifact(self):
        self._open("/nonced")
        self._seed_trend()
        rects = self._hit_rects("trend", 3)
        rects.nth(1).hover()
        self.page.wait_for_timeout(250)
        tip = self._tip_state()
        self.assertTrue(tip["visible"], "trend tooltip görünmedi")
        self.assertIn("z3", tip["text"],
                      "trend tooltip z3 satırı içermiyor: %r"
                      % tip["text"][:200])

    def test_hookenv_chart_hover_works_in_the_artifact(self):
        self._open("/nonced")
        self._seed_hookenv()
        rects = self._hit_rects("he-trend", 3)
        rects.nth(1).hover()
        self.page.wait_for_timeout(250)
        tip = self._tip_state()
        self.assertTrue(tip["visible"], "hook-env tooltip görünmedi")
        self.assertIn("4.8.17", tip["text"],
                      "hook-env tooltip araç sürümünü göstermiyor: %r"
                      % tip["text"][:200])

    def test_no_csp_violation_while_hovering_all_three_charts(self):
        """Kanıtın sıfır noktası: üç grafikte de hover sırasında ihlal YOK.

        Her sütun gerçekten gezilir (boş sayfada "temiz konsol" kanıt
        olmazdı) ve tooltip'in göründüğü her adımda doğrulanır.
        """
        self._open("/nonced")
        self._seed_refs()
        self._seed_trend()
        self._seed_hookenv()
        for svg_id, expect in (("refs-trend", 4), ("trend", 3),
                               ("he-trend", 3)):
            rects = self._hit_rects(svg_id, expect)
            for i in range(expect):
                rects.nth(i).hover()
                self.page.wait_for_timeout(120)
                self.assertTrue(
                    self._tip_state()["visible"],
                    "%s %d. sütunda tooltip görünmedi — konsol temizliği "
                    "kanıtlanmadı" % (svg_id, i))
        self.page.mouse.move(5, 5)
        self.page.wait_for_timeout(200)
        violations = self._csp_violations()
        self.assertEqual(
            violations, [],
            "CSP ihlali konsola düştü (%d mesaj):\n%s"
            % (len(violations), "\n".join(violations[:10])))

    def test_rendered_dom_has_no_inline_attribute_handlers(self):
        """Statik sayacın GERÇEK DOM karşılığı: işaretlemede handler yok.

        `preview_inline_audit` metni tarar; burada tarayıcının ayrıştırdığı
        DOM'a bakılır — JS'in `innerHTML` ile sonradan basabileceği bir
        nitelik handler'ı da yakalanır (statik tarama kaynak metni görür,
        çalışma anındaki DOM'u görmez).
        """
        self._open("/nonced")
        self._seed_refs()
        self._seed_trend()
        self._seed_hookenv()
        self.assertGreater(
            self.page.locator("rect[data-tip]").count(), 0,
            "hiç hit-alanı yok — DOM denetimi boş küme üzerinde anlamsız")
        handlers = self.page.evaluate(
            """(() => {
              const sel = '[onclick],[onmousemove],[onmouseover],'
                        + '[onmouseleave],[onload],[oninput],[onchange]';
              return [...document.querySelectorAll(sel)]
                .map(el => el.tagName + ':' +
                     [...el.attributes].filter(a => /^on/i.test(a.name))
                       .map(a => a.name).join(','));
            })()""")
        self.assertEqual(
            handlers, [],
            "çalışma anı DOM'unda inline event-handler var — CSP altında "
            "sessizce ölür: %r" % (handlers[:5],))

    def test_hit_areas_are_delegated_by_data_attributes(self):
        """Düzeltmenin izi: hit-alanları data-tip/data-i taşır, handler taşımaz."""
        self._open("/nonced")
        self._seed_refs()
        attrs = self.page.evaluate(
            """(() => [...document.querySelectorAll(
                 '#refs-trend rect[data-tip]')].map(e => ({
                   tip: e.dataset.tip, i: e.dataset.i,
                   onclick: e.getAttribute('onclick'),
                   onmousemove: e.getAttribute('onmousemove')})))()""")
        self.assertEqual([a["tip"] for a in attrs], ["refs"] * 4)
        self.assertEqual([a["i"] for a in attrs], ["0", "1", "2", "3"])
        for a in attrs:
            self.assertIsNone(a["onmousemove"],
                              "hit-alanı inline mousemove taşıyor: %r" % (a,))
            self.assertIsNone(a["onclick"],
                              "hit-alanı inline click taşıyor: %r" % (a,))


if __name__ == "__main__":
    unittest.main(verbosity=2)
