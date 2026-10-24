#!/usr/bin/env python3
"""test_preview_interaction_cdp.py — dashboard hover/etkileşim E2E (CDP katmanı).

İKİNCİ katman: gerçek tarayıcıda gerçek fare/klavye olayları (Playwright =
CDP). Dört akış:
  1. trend hover → #tip tooltip (grafiğin transparan hover hedefleri) ve
     fare çekilince tooltip'in gizlenmesi;
  2. run-history filtresi (all/PASS/FAIL/P0) → aktif buton + sayaç + satır
     sayısı tutarlılığı;
  3. Z3 lightbox → slayt tıklaması, ←/→, Escape, odak dönüşü ve Tab tuzağı
     (WCAG 2.4.3);
  4. dolu scroll yüzeyleri → #runstream (run replay) ve #stdout (satır
     tıklaması) taşarken axe `scrollable-region-focusable` ATEŞLEMEZ ve
     odak halkası görünür; negatif kontrol (tabindex'ler kaldırılınca kural
     serious ateşler) testin İÇİNDE, böylece iddia vakum olamaz.

Statik katman (tarayıcısız, her ortamda koşar): bildirilen her scroll
konteyneri klavyeyle erişilebilir olmalı — ScrollableRegionFocusContractTest.

BİRİNCİ katman tarayıcısızdır: test_preview_interaction_dom.js aynı üç akışı
Node vm sandbox'ta koşar ve tarayıcı yoksa da KIRMIZIYA dönebilir. Bu dosya
Playwright/Chromium yoksa SKIP eder — fail-open DEĞİL, çünkü statik katman
zorunlu ve her ortamda koşar (CI'da ayrıca bu dosyayı koşan iş vardır).

Neden ayrı katman: swap-baskısı altında ağır tek-süreç Electron/webview
koşumu yerine ölçeklenebilir, başsız (headless) ve dar kapsamlı bir hat.

Hermetik veri: sunucu GEÇİCİ bir kopya dizin üzerinde koşar — preview.html ve
preview.js canlı kaynaktan kopyalanır, history.jsonl + runs/*.json sentetiktir.
Böylece beklentiler yerel çalışma ağacının verisine bağlı olmaz ve test
her ortamda aynı sayıları doğrular.

Kullanım:
  python3 _calisma/CIKTI/test_preview_interaction_cdp.py
  PREVIEW_CDP_KEEP=1 ...   # geçici dizini silme (hata ayıklama)
"""

import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest

try:
    from playwright.sync_api import sync_playwright
except ImportError:  # CI/runner'da playwright yoksa SKIP (statik katman yine koşar)
    sync_playwright = None

HERE = os.path.dirname(os.path.abspath(__file__))
SERVER_SCRIPT = os.path.join(HERE, "preview_server.py")

# Sentetik history satırları: trend grafiğinde 5 hover hedefi üretir.
HISTORY_ROWS = [
    {"ts": "2026-10-08T10:00:00Z", "verdict": "PASS", "p0": 0, "p1": 0,
     "duration_s": 9, "budget_usd": 1.5, "budget_limit": 30,
     "refs_verified": 20, "refs_total": 20, "pdf_pages": 12, "lean_ok": True,
     "z3_passed": 12, "z3_total": 12},
    {"ts": "2026-10-08T10:05:00Z", "verdict": "FAIL", "p0": 2, "p1": 1,
     "duration_s": 12, "budget_usd": 31, "budget_limit": 30,
     "refs_verified": 18, "refs_total": 20, "pdf_pages": 12, "lean_ok": False,
     "z3_passed": 10, "z3_total": 12},
    {"ts": "2026-10-08T10:10:00Z", "verdict": "ERROR", "p0": 0, "p1": 0,
     "duration_s": 3, "budget_usd": 0.5, "budget_limit": 30,
     "refs_verified": 0, "refs_total": 0, "pdf_pages": 0, "lean_ok": None,
     "z3_passed": 0, "z3_total": 12},
    {"ts": "2026-10-08T10:15:00Z", "verdict": "PASS", "p0": 0, "p1": 3,
     "duration_s": 20, "budget_usd": 40, "budget_limit": 30,
     "refs_verified": 20, "refs_total": 20, "pdf_pages": 11, "lean_ok": True,
     "z3_passed": 12, "z3_total": 12},
    {"ts": "2026-10-08T10:20:00Z", "verdict": "PASS", "p0": 0, "p1": 0,
     "duration_s": 8, "budget_usd": 2, "budget_limit": 30,
     "refs_verified": 20, "refs_total": 20, "pdf_pages": 12, "lean_ok": True,
     "z3_passed": 12, "z3_total": 12},
]

# Filtre sözleşmesi (preview.js loadRunHistory): PASS → verdict=PASS ∧ p0=0;
# FAIL → verdict FAIL|ERROR; P0 → p0 > 0. Beklenen sayaçlar aynı listenin
# türevi — sentetik veri değişirse burada da güncellenir (test kendini
# doğrulamaz, sözleşmeyi doğrular).
FILTER_EXPECTED = {
    "all": (5, None),
    "PASS": (3, 5),
    "FAIL": (2, 5),
    "P0": (1, 5),
}

REPLAY_RUNS = 5

AXE_PATH = os.path.join(HERE, "vendor", "axe.min.js")

# Dolu scroll yüzeyleri için sentetik run çıktısı: #runstream sayfa açılışında
# run replay ile, #stdout satır tıklamasında /api/run-stdout ile dolar (DOM
# uydurma yok — daemon'ın kendi yolu). Deterministik: saat/rastgelelik yok.
FIXTURE_STDOUT = "\n".join(
    "[OK] K%d katman satiri %d %s" % (i % 18, i, "x" * 60) for i in range(240))
FIXTURE_STDERR = "\n".join("stderr satiri %d" % i for i in range(12))


def _run_file_name(ts):
    return "run-" + ts.replace(":", "").replace("+", "").replace(".", "") + ".json"


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def wait_for_health(port, timeout=30):
    import urllib.request

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(
                "http://127.0.0.1:%d/api/health" % port, timeout=3
            ) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            time.sleep(0.3)
    return False


def build_fixture(root):
    """Geçici preview dizinini kur: canlı html/js + sentetik history/runs."""
    prev = os.path.join(root, "preview")
    runs = os.path.join(prev, "runs")
    os.makedirs(runs)
    os.makedirs(os.path.join(root, "verify"))
    for name in ("preview.html", "preview.js"):
        shutil.copy2(os.path.join(HERE, name), os.path.join(prev, name))
    slides = os.path.join(HERE, "slides_z3")
    if os.path.isdir(slides):
        shutil.copytree(slides, os.path.join(prev, "slides_z3"))
    # Dashboard tokenleri ayrı bir kopyadan servis edilir
    # (PREVIEW_DIR/design-system-tokens.css); yoksa sayfa stil hatası basar.
    tokens = os.path.join(os.path.dirname(os.path.dirname(HERE)),
                          "design-system", "tokens.css")
    if os.path.isfile(tokens):
        shutil.copy2(tokens, os.path.join(prev, "design-system-tokens.css"))
    else:
        with open(os.path.join(prev, "design-system-tokens.css"), "w",
                  encoding="utf-8") as fh:
            fh.write("/* design-system/tokens.css bulunamadı */\n")
    with open(os.path.join(prev, "history.jsonl"), "w", encoding="utf-8") as fh:
        for row in HISTORY_ROWS:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    for row in HISTORY_ROWS:
        with open(os.path.join(runs, _run_file_name(row["ts"])), "w",
                  encoding="utf-8") as fh:
            json.dump(dict(row, stdout=FIXTURE_STDOUT, stderr=FIXTURE_STDERR),
                      fh, ensure_ascii=False)
    # preview_server.py, verify_delivery.py olmadan başlamaz; --interval 3600
    # onu hiç koşmaz, stub uykuya yatar (hızlı ve yan etkisiz).
    with open(os.path.join(root, "verify", "verify_delivery.py"), "w",
              encoding="utf-8") as fh:
        fh.write("import time\ntime.sleep(30)\n")
    return prev


def _skip_reason():
    if sync_playwright is None:
        return "playwright kurulu değil (pip install playwright + playwright install chromium)"
    try:
        with sync_playwright() as p:
            exe = p.chromium.executable_path
    except Exception as exc:  # bozuk/eksik kurulum
        return "Chromium çözülemedi: %s" % exc
    if not os.path.isfile(exe):
        return "Chromium indirilmemiş (playwright install chromium)"
    return ""


_SKIP = _skip_reason()


@unittest.skipIf(_SKIP, _SKIP)
class PreviewInteractionCdpTest(unittest.TestCase):
    """Gerçek tarayıcıda hover/filtre/lightbox akışları (tek sunucu, 3 test)."""

    root = None
    proc = None
    port = None
    base = None
    server_log = None

    @classmethod
    def setUpClass(cls):
        cls.root = tempfile.mkdtemp(prefix="preview-interaction-cdp-")
        build_fixture(cls.root)
        cls.port = free_port()
        cls.server_log = open(os.path.join(cls.root, "server.log"), "w")
        cls.proc = subprocess.Popen(
            [sys.executable, SERVER_SCRIPT,
             "--dir", os.path.join(cls.root, "verify"),
             "--preview-dir", os.path.join(cls.root, "preview"),
             "--port", str(cls.port),
             "--bind", "127.0.0.1",
             "--interval", "3600",
             "--replay-runs", str(REPLAY_RUNS)],
            cwd=HERE, stdout=cls.server_log, stderr=subprocess.STDOUT)
        if not wait_for_health(cls.port, timeout=30):
            cls.proc.terminate()
            raise RuntimeError(
                "preview_server.py sağlık kontrolü 30s içinde gelmedi; "
                "log: %s" % os.path.join(cls.root, "server.log"))
        cls.base = "http://127.0.0.1:%d/" % cls.port

    @classmethod
    def tearDownClass(cls):
        if cls.proc is not None:
            cls.proc.terminate()
            try:
                cls.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                cls.proc.kill()
                cls.proc.wait(timeout=5)
        if cls.server_log is not None:
            cls.server_log.close()
        if cls.root and not os.environ.get("PREVIEW_CDP_KEEP"):
            shutil.rmtree(cls.root, ignore_errors=True)

    # ── yardımcılar ────────────────────────────────────────────────────────
    def _open(self, page):
        """Dashboard'u aç; service worker'ı blokla (cache bypass gürültüsü)."""
        errors = []
        page.route("/sw.js", lambda route: route.fulfill(body=""))
        page.on(
            "console",
            lambda msg: errors.append(msg.text)
            if msg.type == "error"
            and not msg.text.startswith("Failed to load resource")
            else None,
        )
        page.goto(self.base, wait_until="domcontentloaded")
        return errors

    # ── 1) hover → tooltip ─────────────────────────────────────────────────
    def test_trend_hover_opens_tooltip_and_mouseleave_hides_it(self):
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1400, "height": 900})
            errors = self._open(page)

            hits = page.locator('#trend rect[fill="transparent"]')
            hits.first.wait_for(state="attached", timeout=15000)
            self.assertEqual(
                hits.count(), len(HISTORY_ROWS),
                "her trend run'ı için bir hover hedefi olmalı")
            # Kablolama: inline handler YOK (CSP script-src 'self' + nonce
            # inline event handler'ları bloklar); hedefler data-tip-i taşır ve
            # mousemove SVG üzerinde delege edilir.
            self.assertEqual(
                page.locator('#trend rect[onmousemove], #trend rect[onmouseleave]').count(), 0,
                "hover hedefleri inline handler taşımamalı (CSP bloklar)")
            for i in range(hits.count()):
                self.assertEqual(
                    hits.nth(i).get_attribute("data-tip-i"), str(i),
                    "hover hedefi delege için data-tip-i taşımalı")

            tip = page.locator("#tip")
            self.assertFalse(tip.is_visible(), "tooltip açılışta gizli olmalı")

            hits.nth(1).hover()
            tip.wait_for(state="visible", timeout=5000)
            text = tip.inner_text()
            self.assertIn("verdict :", text, "tooltip verdict satırını taşımalı")
            self.assertIn("budget  :", text, "tooltip bütçe satırını taşımalı")
            self.assertIn("duration:", text, "tooltip süre satırını taşımalı")
            self.assertEqual(
                tip.evaluate("el => el.style.display"), "block",
                "hover tooltip'i display:block yapmalı")

            page.mouse.move(4, 4)
            page.wait_for_function(
                "() => document.getElementById('tip').style.display === 'none'",
                timeout=5000)
            self.assertFalse(tip.is_visible(), "mouseleave tooltip'i gizlemeli")

            self.assertEqual(errors, [], "hover akışında JS konsol hatası olmamalı")
            browser.close()

    # ── 2) run-history filtresi ────────────────────────────────────────────
    def test_run_history_filter_clicks_stay_consistent(self):
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1400, "height": 900})
            errors = self._open(page)

            rows = page.locator("#run-history .rh-row")
            rows.first.wait_for(state="attached", timeout=15000)
            self.assertEqual(rows.count(), len(HISTORY_ROWS),
                             "all filtresi tüm run'ları listelemeli")

            for name, (counted, total) in FILTER_EXPECTED.items():
                page.click('.rh-filter button[data-f="%s"]' % name)
                want = "(%d)" % counted if total is None else "(%d / %d)" % (counted, total)
                page.wait_for_function(
                    "t => document.getElementById('run-history-count').textContent === t",
                    arg=want, timeout=10000)
                self.assertEqual(
                    rows.count(), counted,
                    "%s filtresi %d satır listelemeli" % (name, counted))
                active = page.locator(".rh-filter button.active")
                self.assertEqual(active.count(), 1,
                                 "aynı anda tek filtre aktif olmalı")
                self.assertEqual(active.first.get_attribute("data-f"), name)

            self.assertEqual(errors, [], "filtre akışında JS konsol hatası olmamalı")
            browser.close()

    # ── 3) lightbox ────────────────────────────────────────────────────────
    def test_slide_click_opens_lightbox_and_escape_restores_focus(self):
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1400, "height": 1000})
            errors = self._open(page)

            slide = page.locator("#z3-slides .z3-slide").nth(1)
            slide.wait_for(state="visible", timeout=15000)
            opener_label = slide.get_attribute("aria-label")
            slide.click()

            box = page.locator("#z3-lightbox")
            box.wait_for(state="visible", timeout=5000)
            img = page.locator("#z3-lightbox-image")
            src0 = img.get_attribute("src")
            self.assertTrue(src0.startswith("/slides_z3/"),
                            "lightbox gerçek slayt yolunu göstermeli: %r" % src0)
            self.assertEqual(
                page.evaluate("() => document.activeElement.id"), "z3-close",
                "açılışta odak kapat butonuna gitmeli (WCAG 2.4.3)")

            page.click("#z3-next")
            src1 = img.get_attribute("src")
            self.assertNotEqual(src1, src0, "→ sonraki slayta geçmeli")
            page.click("#z3-prev")
            self.assertEqual(img.get_attribute("src"), src0, "← önceki slayta dönmeli")

            page.keyboard.press("ArrowRight")
            page.wait_for_function(
                "s => document.getElementById('z3-lightbox-image').getAttribute('src') === s",
                arg=src1, timeout=5000)
            page.keyboard.press("ArrowLeft")
            page.wait_for_function(
                "s => document.getElementById('z3-lightbox-image').getAttribute('src') === s",
                arg=src0, timeout=5000)

            # Tab tuzağı: son öğeden (kapat) Tab → ilk öğeye (önceki).
            page.focus("#z3-close")
            page.keyboard.press("Tab")
            self.assertEqual(
                page.evaluate("() => document.activeElement.id"), "z3-prev",
                "Tab son öğeden ilk öğeye dönmeli (odak diyalogda kalır)")

            page.keyboard.press("Escape")
            box.wait_for(state="hidden", timeout=5000)
            self.assertTrue(page.locator("#z3-lightbox").is_hidden(),
                            "Escape lightbox'ı kapatmalı")
            self.assertEqual(
                page.evaluate(
                    "() => (document.activeElement.getAttribute('aria-label') || '')"),
                opener_label,
                "kapanışta odak açan slayda dönmeli (WCAG 2.4.3)")
            self.assertEqual(
                page.evaluate("() => document.activeElement.classList.contains('z3-slide')"),
                True, "dönen odak gerçekten slayt düğmesi olmalı")

            self.assertEqual(errors, [], "lightbox akışında JS konsol hatası olmamalı")
            browser.close()

    # ── 4) dolu scroll yüzeyleri: klavye erişimi + axe ─────────────────────
    def test_filled_scrollable_regions_stay_keyboard_reachable(self):
        """#runstream/#stdout taşarken axe scrollable-region-focusable ateşlemez."""
        scan = (
            "async () => {"
            "  const res = await axe.run(document, {runOnly: {type: 'rule',"
            "    values: ['scrollable-region-focusable']}});"
            "  return res.violations.map(v => ({id: v.id, impact: v.impact,"
            "    targets: v.nodes.map(n => n.target.join(' '))}));"
            "}"
        )
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            # a11y_gate.py axe'ı bypass_csp'li context'te enjekte eder
            # (preview_server nonce-CSP'si inline script'i bloklar) — kapının
            # kendi yolu burada birebir kullanılır.
            ctx = browser.new_context(bypass_csp=True,
                                      viewport={"width": 1400, "height": 900})
            page = ctx.new_page()
            self._open(page)

            # #runstream daemon'ın replay'iyle dolar (DOM uydurma yok).
            page.wait_for_function(
                "() => { const r = document.getElementById('runstream');"
                " return !!r && r.scrollHeight > r.clientHeight + 1; }",
                timeout=20000)
            # #stdout gerçek kullanıcı yoluyla dolar: run-history satırına
            # tıkla -> loadRunStdout -> /api/run-stdout -> applyStdout.
            row = page.locator("#run-history .rh-row").first
            row.wait_for(state="attached", timeout=15000)
            row.click()
            page.wait_for_function(
                "() => { const s = document.getElementById('stdout');"
                " return !!s && s.scrollHeight > s.clientHeight + 1; }",
                timeout=20000)

            with open(AXE_PATH, encoding="utf-8") as fh:
                axe_src = fh.read()
            page.add_script_tag(content=axe_src)

            # Odak halkası (WCAG 2.4.7): tabindex'li yüzey klavye
            # modalitesinde odaklanınca görünür outline çizmeli.
            # ÖLÇÜM 2026-10-08: fare tıklamasından sonra düz programatik odak
            # :focus-visible EŞLEŞTİRMİYOR (click -> page.focus: False);
            # focus({focusVisible:true}) ve Tab-sonrası odak True. Bu yüzden
            # gerçek klavye modalitesini bu API ile kuruyoruz.
            page.evaluate(
                "() => document.getElementById('stdout')"
                ".focus({focusVisible: true})")
            ring = page.evaluate(
                "() => { const el = document.getElementById('stdout');"
                " const s = getComputedStyle(el);"
                " return {active: document.activeElement === el,"
                " visible: el.matches(':focus-visible'),"
                " style: s.outlineStyle, width: s.outlineWidth}; }")
            self.assertTrue(ring["active"], "#stdout odaklanamadı: %s" % ring)
            self.assertTrue(ring["visible"],
                            ":focus-visible eşleşmedi; focus-ring kuralı yok: %s" % ring)
            self.assertEqual(ring["style"], "solid", "odak halkası çizilmiyor: %s" % ring)
            self.assertNotIn(ring["width"], ("0px", "", None),
                             "odak halkası genişliği sıfır: %s" % ring)

            clean = page.evaluate(scan)
            self.assertEqual(
                clean, [],
                "dolu scroll yüzeylerinde scrollable-region-focusable ateşledi "
                "(axe serious -> a11y kapısı FAIL): %s" % clean)

            # NEGATİF KONTROL: tabindex'ler kaldırılınca kural AYNI sayfada
            # ateşlemeli; ateşlemezse yukarıdaki yeşil iddia vakum olurdu.
            page.evaluate(
                "() => { for (const id of ['stdout', 'runstream']) {"
                " const n = document.getElementById(id);"
                " if (n) n.removeAttribute('tabindex'); } }")
            mutated = page.evaluate(scan)
            targets = sorted(t for v in mutated for t in v["targets"])
            self.assertEqual(
                targets, ["#runstream", "#stdout"],
                "negatif kontrol kuralı ateşlemedi (tarama vakum olabilir): %s"
                % mutated)
            browser.close()


def read_source(name):
    """Dashboard kaynağını oku (statik katman için)."""
    with open(os.path.join(HERE, name), encoding="utf-8") as fh:
        return fh.read()


class InlineHandlerCspContractTest(unittest.TestCase):
    """Tarayıcısız statik katman — her ortamda koşar ve tek başına kırmızıya döner.

    preview_server.py her sayfa yanıtına `script-src 'self' 'nonce-…'`
    gönderir (`'unsafe-inline'` YOK). Bu politikada inline event handler'lar
    (onclick/onmousemove/…) ÇALIŞMAZ: ölçüldü (Chromium 148) —
    "Executing inline event handler violates the following Content Security
    Policy directive". Dashboard etkileşimleri bu yüzden addEventListener /
    delegasyon ile bağlanır (hover: SVG `data-tip-i` delegasyonu; filtre
    butonları ve bütçe-aşım toggle'ı: addEventListener; run satırları:
    `#run-history` delegasyonu). Bir inline handler geri gelirse bu test
    tarayıcı OLMADAN da kırmızıya döner — yani bu dosya hiçbir ortamda
    sessizce boş PASS olamaz.
    """

    _INLINE = re.compile(
        r'\bon(?:click|mousemove|mouseleave|mouseover|keydown|keyup|keypress'
        r'|change|input|submit|focus|blur|load|error)\s*=\s*"')

    def test_no_inline_event_handlers_in_dashboard_sources(self):
        offenders = []
        for name in ("preview.html", "preview.js"):
            text = read_source(name)
            lines = text.splitlines()
            for match in self._INLINE.finditer(text):
                line_no = text.count("\n", 0, match.start()) + 1
                line = lines[line_no - 1].strip()
                if line.startswith("//") or line.startswith("*"):
                    continue  # yorum: örnek/anlatım metni olabilir
                offenders.append("%s:%d %s" % (name, line_no, line[:90]))
        self.assertEqual(
            offenders, [],
            "CSP (script-src 'self' + nonce) inline event handler'ları bloklar; "
            "addEventListener/delegasyon kullanılmalı. Bulunanlar: %s" % offenders)


class ScrollableRegionFocusContractTest(unittest.TestCase):
    """Tarayıcısız: bildirilen her scroll yüzeyi klavyeyle erişilebilir olmalı.

    Ölçüm (2026-10-08, gerçek Chromium + canlı preview_server, W worktree):
    dolu panoda #stdout (391 px taşma) ve #runstream (9204 px) tabindex="0"
    taşıdığı için axe `scrollable-region-focusable` 0 ihlal veriyor; tabindex
    kaldırılınca aynı kural serious ×2 yalnız bu iki hedefte ateşliyor
    (dinamik testin negatif kontrolü). #run-history kendi tabindex'ini
    taşımıyor ama satırları preview.js'te role="button" tabindex="0" ile
    üretiliyor.

    Bu sınıf tarayıcısız koşar ve tek başına kırmızıya dönebilir: yeni bir
    scroll konteyneri klavye erişimi olmadan eklenirse burada patlar.
    """

    def _style_text(self):
        html = read_source("preview.html")
        match = re.search(r"<style>(.*?)</style>", html, re.S)
        self.assertIsNotNone(match, "preview.html <style> bloğu bulunamadı")
        return match.group(1), html

    def test_declared_scroll_containers_are_registered(self):
        style, html = self._style_text()
        declared = set()
        for selectors, body in re.findall(r"([^{}]+)\{([^{}]*)\}", style):
            if not re.search(r"overflow(?:-y)?\s*:\s*(?:auto|scroll)", body):
                continue
            if "max-height" not in body:
                continue
            declared.update(sel.strip() for sel in selectors.split(",") if sel.strip())
        self.assertEqual(
            declared, {"pre", ".ref-list"},
            "preview.html'de yeni scroll konteyneri bildirildi; klavye erişimi "
            "sözleşmesine ekleyin (tabindex ya da odaklanabilir çocuk): %s"
            % sorted(declared))
        inline = set(re.findall(
            r'id="([a-z0-9-]+)"[^>]*style="[^"]*overflow(?:-y)?\s*:\s*(?:auto|scroll)',
            html))
        self.assertEqual(
            inline, {"run-history"},
            "inline scroll konteyneri kümesi değişti; klavye erişimi kanıtı "
            "gerekli: %s" % sorted(inline))

    def test_scroll_surfaces_are_keyboard_reachable(self):
        html = read_source("preview.html")
        js = read_source("preview.js")
        pres = re.findall(r"<pre\b[^>]*>", html)
        self.assertTrue(pres, "preview.html'de <pre> yüzeyi yok")
        for tag in pres:
            # pre kuralı (overflow:auto + max-height:420px) her <pre>'yi
            # potansiyel scroll yüzeyi yapar.
            self.assertIn('tabindex="0"', tag,
                          "scrollable <pre> klavye erişimi yok (axe serious): %s" % tag)
        refs = re.search(r'<ul\b[^>]*class="ref-list"[^>]*>', html)
        self.assertIsNotNone(refs, ".ref-list konteyneri bulunamadı")
        self.assertIn('tabindex="0"', refs.group(0),
                      "scrollable .ref-list klavye erişimi yok: %s" % refs.group(0))
        row_lines = [ln.replace('\\"', '"') for ln in js.splitlines() if "rh-row" in ln]
        self.assertTrue(
            any('class="rh-row"' in ln and 'role="button"' in ln
                and 'tabindex="0"' in ln for ln in row_lines),
            "#run-history satırları odaklanabilir değil (role=button + "
            "tabindex=0 gerekli): %s" % row_lines[:3])

    def test_tabindex_focus_ring_is_declared(self):
        style, _html = self._style_text()
        rules = [(sel.strip(), body) for sel, body
                 in re.findall(r"([^{}]+)\{([^{}]*)\}", style)
                 if "[tabindex]:focus-visible" in sel]
        self.assertTrue(rules, "[tabindex]:focus-visible focus-ring kuralı yok")
        self.assertTrue(
            any(re.search(r"outline\s*:\s*[1-9]\d*px", body) for _s, body in rules),
            "focus-ring outline genişliği yok/sıfır: %s" % rules)


if __name__ == "__main__":
    unittest.main(verbosity=2)
