#!/usr/bin/env python3
"""test_incidental_banner.py — Incidental Proof header-banner sözleşmesi.

Banner = canvas/incidental_proof_banner.svg'in preview.html header'ına
data-URI ile gömülü dekoratif-katmanı. Dört sözleşmeyi sabitler:

  1) Tek-kaynak + gömülme: banner-SVG diskte durur; preview.html'deki
     data-URI bunun birebir base64'üdür (drift = fail). Aracı yok —
     el-yazımı base64 bozulursa test kırılır (fail-closed).
  2) CSP/boyut disiplini: img-src data: CSP izniyle uyum (svg+xml),
     katman gerçek bir aria-hidden DOM-düğümüdür (.header-decor — a11y-gate
     color-contrast'ın metin-zeminini çözebilmesi için header::after
     pseudo-katmanından taşındı, 2026-09-24); header interaktif-çocukları
     z-index:1 ile dokunulmaz.
  3) Kontrast-koruma: her iki temada katman-opaklığı eşik-altında
     (dark ≤ .18, light ≤ .25) — metin-kontrastını düşürmez; ayrıca
     banner-SVG'nin vermilion'u tek (testifies-only) kalır.

  4) SERİ-KAYDI (kolofon): plate-book'un kolofon yaprağı (LEAF 6) banner'ı
     adreslenebilir biçimde taşır — main'e bağlı depo URL'si, dashboard
     entegrasyon kaydı (/preview.html · .header-decor · data-URI) ve kaynağın
     sha256 parmak izi; kayıt DİSKE bağlıdır (drift = kırmızı) ve teslim
     edilen PDF'in kolofon yaprağında birebir bulunmalıdır.

  5) RUNTIME (tarayıcı + Pillow): iki-temalı axe (header bağlamı, dark/light
     sıfır ihlal) + EKRAN-GÖRÜNTÜ karşılaştırması: tema değişimi header'ı
     gerçekten yeniden çizer; banner katmanı görüntüde belirgindir AMA metin
     kontrastını değiştirmez (sıkı metin-kutusunun min/max WCAG oranı her
     iki temada AA üstü kalır). Tarayıcı/PIL yoksa bu sınıf SKIP eder; statik
     sınıflar yine koşar (dosya tarayıcısız da kırmızıya dönebilir).

Çalıştırma: python3 -m unittest _calisma.CIKTI.test_incidental_banner
"""
import base64
import hashlib
import io
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request

try:  # runtime katmanı: tarayıcı yoksa SKIP (statik sınıflar yine koşar)
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None

try:  # ekran-görüntüsü çözümü (CI verify job'ı Pillow kurar)
    from PIL import Image, ImageChops, ImageStat
except ImportError:
    Image = None

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

BANNER_PATH = os.path.join(HERE, "canvas", "incidental_proof_banner.svg")
HTML_PATH = os.path.join(HERE, "preview.html")


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


class TestBannerEmbedding(unittest.TestCase):
    """Tek-kaynak zinciri: banner.svg → data-URI → .header-decor katmanı."""

    def setUp(self):
        self.svg = _read(BANNER_PATH)
        self.html = _read(HTML_PATH)
        self.expected_uri = "data:image/svg+xml;base64," + base64.b64encode(
            self.svg.encode("utf-8")
        ).decode("ascii")

    def test_banner_svg_exists_and_is_svg(self):
        self.assertIn("<svg", self.svg)
        self.assertIn('viewBox="0 0 1440 160"', self.svg)

    def test_data_uri_matches_disk_svg_byte_for_byte(self):
        # Gömülü URI diskteki SVG'in birebir base64'ü olmalı —
        # el-değmesi/drift olmadan yeniden-üretilebilir.
        self.assertIn(self.expected_uri, self.html)

    def test_banner_used_in_header_decor_layer(self):
        # Katman .header-decor'da yaşar: gerçek DOM-düğümü, aria-hidden=true
        # (a11y-gate'in color-contrast çözümü pseudo-katmanda tıkanıyordu;
        # dekor metinlerin KARDEŞİ olarak atanınca ata-yığını temizlendi).
        m = re.search(r"\.header-decor\s*\{[^}]*\}", self.html)
        self.assertIsNotNone(m, ".header-decor katmanı yok")
        block = m.group(0)
        self.assertIn("background-image", block)
        self.assertIn("pointer-events:none", block)
        # İşaretleme: aria-hidden ile AT'ye açıkça kapalı.
        self.assertRegex(
            self.html,
            r'<div class="header-decor" aria-hidden="true">',
        )

    def test_header_children_above_layer(self):
        # Interaktif-çocuklar katmanın üstünde: z-index:1 (tıklama/odak
        # dokunulmazlığı — banner asla hedef çalmaz).
        self.assertRegex(self.html, r"header\s*>\s*\*\s*\{\s*position:relative;\s*z-index:1;")


class TestBannerContrastBudget(unittest.TestCase):
    """Kontrast-koruma: katman opaklığı tema-başına eşiğin altında."""

    def setUp(self):
        self.html = _read(HTML_PATH)

    def _opacity_of(self, selector_fragment):
        m = re.search(
            re.escape(selector_fragment) + r"[^}]*opacity:\s*([0-9.]+)", self.html
        )
        self.assertIsNotNone(m, f"opaklık bulunamadı: {selector_fragment}")
        return float(m.group(1))

    def test_dark_theme_opacity_under_threshold(self):
        self.assertLessEqual(self._opacity_of(".header-decor"), 0.18)

    def test_light_theme_opacity_under_threshold(self):
        self.assertLessEqual(
            self._opacity_of(':root[data-theme="light"] .header-decor'), 0.25
        )


class TestBannerVermilionDiscipline(unittest.TestCase):
    """Levha-disiplini banner'da yaşar: vermilion tek, sadece şahitlik."""

    def setUp(self):
        self.svg = _read(BANNER_PATH)

    def test_vermilion_is_the_only_saturated_voice(self):
        # Üç-ses paleti: fathom tonları + vermilion; dördüncü doygun-renk yok.
        colors = {"#" + c.upper() for c in re.findall(r"#([0-9A-Fa-f]{6})", self.svg)}
        verm = "#C1440E"
        self.assertIn(verm, colors)
        saturated = {
            c
            for c in colors
            if c != verm and self._saturation(c) > 0.35
        }
        self.assertEqual(saturated, set(), f"dördüncü doygun-renk: {saturated}")

    @staticmethod
    def _saturation(hex6):
        h = hex6.lstrip("#")
        r, g, b = (int(h[i : i + 2], 16) / 255 for i in (0, 2, 4))
        mx, mn = max(r, g, b), min(r, g, b)
        return 0 if mx == 0 else (mx - mn) / mx


# ---------------------------------------------------------- series record
# Seri-kaydı bütünlüğü: tek-kaynak zinciri üç yüzeyi birlikte kapsar —
#   disk (banner baytları) → dashboard (data-URI, .header-decor) → basılı kayıt.
# Kolofon kaydı diske BAĞLIDIR: banner yeniden yazılırsa test kırmızıya döner
# ve kitap bilinçli olarak yeniden basılır; sessiz sürüklenme yoktur.

BOOK_TEX = os.path.join(HERE, "canvas", "incidental_proof_book.tex")
BOOK_PDF = os.path.join(HERE, "canvas", "incidental_proof_book.pdf")
REPO_SLUG = "ali-han-kaya/leibniz2"
COLOPHON_LEAF = 6  # altı yapraklı kitapta kolofon yaprağı


class TestSeriesRecordColophon(unittest.TestCase):
    """Kolofondaki seri-kaydı: banner URL'si + dashboard entegrasyonu + sha256."""

    def setUp(self):
        self.tex = _read(BOOK_TEX)

    def _colophon(self):
        """LEAF 6 (kolofon) yaprağının tex gövdesini döndürür."""
        m = re.search(r"% =+ LEAF 6 — COLOPHON.*?\\end\{tikzpicture\}", self.tex, re.S)
        self.assertIsNotNone(m, "kolofon yaprağı (LEAF 6) bulunamadı")
        return m.group(0)

    def _record(self):
        """Kolofon kaydını ayrıştırır: (url, sha256, kolofon gövdesi)."""
        colophon = self._colophon()
        u = re.search(r"(https://github\.com/\S+?\.svg)", colophon)
        if u is None:
            self.fail("kolofonda banner URL'si yok")
        url = u.group(1).replace("\\_", "_")  # TeX kaçışı geri alınır: \_ → _
        d = re.search(r"SHA256~~([0-9a-f]{64})", colophon)
        if d is None:
            self.fail("kolofonda banner sha256 parmak izi yok")
        return url, d.group(1), colophon

    def test_colophon_url_resolves_to_the_banner_single_source(self):
        # Kayıt adreslenebilir olmalı VE var olan tek-kaynağı göstermeli:
        # yazım hatası ya da yeniden adlandırma kaydı sessizce bozamaz.
        url, _, _ = self._record()
        m = re.fullmatch(r"https://github\.com/(\S+?)/blob/(\S+?)/(\S+)", url)
        self.assertIsNotNone(m, f"URL biçimi beklenenden farklı: {url}")
        slug, ref, path = m.groups()
        self.assertEqual(slug, REPO_SLUG, "URL yanlış depoyu gösteriyor")
        self.assertEqual(ref, "main", "URL kalıcı ref'e (main) bağlı olmalı")
        rel = os.path.relpath(BANNER_PATH, REPO_ROOT).replace(os.sep, "/")
        self.assertEqual(path, rel, "URL yolu banner tek-kaynağını göstermiyor")
        self.assertTrue(os.path.isfile(os.path.join(REPO_ROOT, path)), path)

    def test_colophon_records_dashboard_integration_surface(self):
        # Entegrasyon kaydı var olan yüzeyi adlandırmalı: dosya + katman +
        # gömülme mekanizması; uydurma katman yeşil geçemez.
        _, _, colophon = self._record()
        self.assertRegex(colophon, r"DASHBOARD~~/preview\.html")
        self.assertIn(".header-decor", colophon)
        self.assertIn("data-URI", colophon)
        self.assertIn('<div class="header-decor" aria-hidden="true"></div>',
                      _read(HTML_PATH))

    def test_colophon_fingerprint_is_the_banner_bytes(self):
        # Parmak izi diskteki baytların aynısı olmalı (lockstep): banner
        # dosyasına dokunulursa kayıt da yenilenmek zorunda kalır.
        _, digest, _ = self._record()
        with open(BANNER_PATH, "rb") as f:
            raw = f.read()
        self.assertEqual(digest, hashlib.sha256(raw).hexdigest(),
                         "kolofon parmak izi diskteki banner baytlarından farklı")

    def test_colophon_fingerprint_is_the_embedded_data_uri_source(self):
        # Basılı kayıt dashboard'a gömülen baytları damgalar: data-URI'nin
        # çözümü ile kolofondaki parmak izi aynı olmalı (tek-kaynak zinciri
        # disk → dashboard → baskı olarak kapanır).
        _, digest, _ = self._record()
        m = re.search(r"data:image/svg\+xml;base64,([A-Za-z0-9+/=]+)", _read(HTML_PATH))
        if m is None:
            self.fail("preview.html'de gömülü banner data-URI yok")
        embedded = base64.b64decode(m.group(1))
        self.assertEqual(hashlib.sha256(embedded).hexdigest(), digest,
                         "kolofon kaydı dashboard'a gömülü baytları damgalamıyor")

    @unittest.skipUnless(shutil.which("pdftotext"), "pdftotext yok (poppler)")
    def test_delivered_pdf_carries_the_record_on_the_colophon_leaf(self):
        # Teslim edilen artifact katmanı: kayıt gerçekten basılı sayfada
        # olmalı (kaçış/glif hatası sessizce düşmesin) ve YALNIZ kolofon
        # yaprağında bulunmalı. .tex değişip PDF yeniden basılmazsa bayat
        # artifact bu testte kırmızıya döner.
        url, digest, _ = self._record()

        def text(n=None):
            cmd = ["pdftotext"] + (["-f", str(n), "-l", str(n)] if n else []) \
                + [BOOK_PDF, "-"]
            r = subprocess.run(cmd, capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            return r.stdout

        colophon = text(COLOPHON_LEAF)
        self.assertIn("COLOPHON", colophon, f"yaprak {COLOPHON_LEAF} artık kolofon değil")
        self.assertIn(url, colophon, "banner URL'si basılı kolofonda yok")
        self.assertIn(digest, colophon, "parmak izi basılı kolofonda yok")
        self.assertIn(".header-decor", colophon, "entegrasyon kaydı basılı sayfada yok")
        self.assertEqual(text().count(url), 1,
                         "banner URL'si kolofon dışında da basılmış")


# ---------------------------------------------------------------- runtime
# İki-temalı axe + ekran-görüntüsü karşılaştırması. Hermetic: preview_server
# geçici bir kopya üzerinde koşar (canlı çalışma ağacının verisine bağlı
# değil); verify_delivery.py stub'ı uyur — hiçbir gerçek denetim tetiklenmez.

AXE_PATH = os.path.join(HERE, "vendor", "axe.min.js")
SERVER_SCRIPT = os.path.join(HERE, "preview_server.py")
REPO_ROOT = os.path.dirname(ROOT)  # _calisma/.. = depo kökü
TOKENS_PATH = os.path.join(REPO_ROOT, "design-system", "tokens.css")


def _free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_health(port, timeout=30):
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


def _runtime_skip_reason():
    if sync_playwright is None:
        return ("playwright kurulu değil "
                "(pip install playwright + playwright install chromium)")
    if Image is None:
        return "Pillow kurulu değil (pip install Pillow) — ekran-görüntüsü çözümü"
    try:
        with sync_playwright() as p:
            exe = p.chromium.executable_path
    except Exception as exc:  # bozuk/eksik kurulum
        return "Chromium çözülemedi: %s" % exc
    if not os.path.isfile(exe):
        return "Chromium indirilmemiş (playwright install chromium)"
    return ""


_SKIP_RUNTIME = _runtime_skip_reason()


def _relative_luminance(rgb):
    """WCAG 2.x bağıl parlaklık (sRGB)."""
    def f(c):
        c = c / 255.0
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = rgb[:3]
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def _contrast_ratio(l1, l2):
    hi, lo = max(l1, l2), min(l1, l2)
    return (hi + 0.05) / (lo + 0.05)


def _text_min_max_ratio(img, box):
    """Sıkı metin kutusunda min/max parlaklık → WCAG oranı + piksel sayısı.

    Antialias ölçülen oranı gerçek orandan BÜYÜK gösteremez (uçlar gerçek
    renklere yaklaşır, aşamaz) — ölçüm muhafazakâr alt sınırdır.
    """
    crop = img.crop(box).convert("RGB")
    lums = [_relative_luminance(px) for px in crop.getdata()]
    return _contrast_ratio(min(lums), max(lums)), len(lums)


@unittest.skipIf(_SKIP_RUNTIME, _SKIP_RUNTIME)
class TestBannerTwoThemeRuntime(unittest.TestCase):
    """Tema-değişiminde kontrast korunuyor mu? axe + ekran-görüntüsü (dark/light).

    ÖLÇÜM 2026-10-08 (yerel Chromium, hermetic preview_server, 1400x900):
      axe (header bağlamı)  : dark/light → 0 ihlal; gradient yüzünden
                              .imprint/h1/#live-status 'incomplete' kalır →
                              bu yüzden kontrast iddiası EKRAN GÖRÜNTÜSÜNDEN
                              ölçülür (axe yalnız kural taramasıdır).
      sıkı metin-kutusu     : #live-status (banner bandıyla 26 px KESİŞİR)
                              dark 5.90:1 / light 5.81:1; h1 15.88 / 13.60;
                              .imprint 5.85 / 6.02 (min-max WCAG oranı).
      katman etkisi         : oran farkı ≤ 0.10 (dark #live-status 5.90→5.95)
                              ama bant görüntüsü belirgin (mean Δ 0.69-1.45) →
                              dekor gerçekten çiziliyor, kontrastı düşürmüyor.
      dark vs light         : tüm header mean Δ 208/255 → tema gerçekten
                              yeniden çiziliyor.
    """

    @classmethod
    def setUpClass(cls):
        cls.root = tempfile.mkdtemp(prefix="banner-runtime-")
        prev = os.path.join(cls.root, "preview")
        verify = os.path.join(cls.root, "verify")
        os.makedirs(prev)
        os.makedirs(verify)
        for name in ("preview.html", "preview.js"):
            shutil.copy2(os.path.join(HERE, name), os.path.join(prev, name))
        # Tasarım tokenleri ayrı servis edilir; eksikse sayfa beyaz zemine
        # düşer ve kontrast ölçümü anlamsızlaşır (fail-closed: kopyala ya da
        # net bir hata ver).
        if not os.path.isfile(TOKENS_PATH):
            raise RuntimeError("design-system/tokens.css yok: %s" % TOKENS_PATH)
        shutil.copy2(TOKENS_PATH, os.path.join(prev, "design-system-tokens.css"))
        with open(os.path.join(verify, "verify_delivery.py"), "w",
                  encoding="utf-8") as f:
            f.write("import time\ntime.sleep(3600)\n")
        cls.port = _free_port()
        cls.server_log = open(os.path.join(cls.root, "server.log"), "w")
        cls.proc = subprocess.Popen(
            [sys.executable, SERVER_SCRIPT,
             "--dir", verify, "--preview-dir", prev,
             "--port", str(cls.port), "--bind", "127.0.0.1",
             "--interval", "3600"],
            cwd=HERE, stdout=cls.server_log, stderr=subprocess.STDOUT)
        if not _wait_health(cls.port, timeout=30):
            cls.proc.kill()
            raise RuntimeError("preview_server sağlık kontrolü gelmedi; log: %s"
                               % os.path.join(cls.root, "server.log"))
        cls.base = "http://127.0.0.1:%d/" % cls.port

    @classmethod
    def tearDownClass(cls):
        if cls.proc.poll() is None:
            cls.proc.terminate()
            try:
                cls.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                cls.proc.kill()
                cls.proc.wait(timeout=5)
        cls.server_log.close()
        if not os.environ.get("BANNER_RUNTIME_KEEP"):
            shutil.rmtree(cls.root, ignore_errors=True)

    # ── ortak yardımcılar ──────────────────────────────────────────────────
    _TIGHT_BOX = """(sel) => {
      const el = document.querySelector(sel);
      const r = document.createRange();
      r.selectNodeContents(el);
      const b = r.getBoundingClientRect();
      const h = document.querySelector('header').getBoundingClientRect();
      return {x: b.x - h.x, y: b.y - h.y, w: b.width, h: b.height};
    }"""

    def _open(self, page):
        """Sayfayı aç ve tarama-hazır işaretine kadar bekle (deterministik)."""
        page.route("/sw.js", lambda route: route.fulfill(body=""))
        page.goto(self.base, wait_until="domcontentloaded")
        page.wait_for_selector("body[data-scan-ready='1']", state="attached",
                               timeout=120000)

    def _set_theme(self, page, theme):
        """Tema anahtarını GERÇEK tıklamayla hedefe getir; DOM kontratını doğrula."""
        current = page.evaluate("() => document.documentElement.dataset.theme")
        if current != theme:
            page.click("#theme-toggle")
        got = page.evaluate("() => document.documentElement.dataset.theme")
        self.assertEqual(got, theme,
                         "tema anahtarı %s'e geçmedi (DOM=%s)" % (theme, got))

    def _text_box(self, page, sel, hbox):
        tb = page.evaluate(self._TIGHT_BOX, sel)
        x = int(hbox["x"] + tb["x"])
        y = int(hbox["y"] + tb["y"])
        return (x, y, int(x + tb["w"]) + 1, int(y + tb["h"]) + 1)

    @staticmethod
    def _mean_abs_diff(a, b, box=None):
        if box:
            a = a.crop(box)
            b = b.crop(box)
        diff = ImageChops.difference(a.convert("RGB"), b.convert("RGB"))
        stat = ImageStat.Stat(diff)
        return sum(stat.mean) / 3.0

    def _shoot(self, header):
        return Image.open(io.BytesIO(header.screenshot())).convert("RGB")

    # ── 1) tema değişimi gerçekten repaint ediyor mu? ──────────────────────
    def test_theme_toggle_repaints_header_both_ways(self):
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1400, "height": 900})
            self._open(page)
            header = page.locator("header")
            self.assertEqual(
                page.evaluate("() => document.documentElement.dataset.theme"), "dark",
                "taze context koyu temayla başlamalı (yerel depo boş)")
            page.wait_for_timeout(150)
            dark = self._shoot(header)
            self._set_theme(page, "light")
            self.assertEqual(
                page.get_attribute("#theme-toggle", "aria-pressed"), "true",
                "açık temada aria-pressed=true olmalı")
            page.wait_for_timeout(150)
            light = self._shoot(header)
            mean = self._mean_abs_diff(dark, light)
            self.assertGreaterEqual(
                mean, 50.0,
                "tema değişimi header'ı yeniden çizmedi (mean Δ %.2f/255)" % mean)
            # Çift yön: koyuya dönüş de DOM'da gerçek olmalı.
            self._set_theme(page, "dark")
            self.assertEqual(
                page.get_attribute("#theme-toggle", "aria-pressed"), "false",
                "koyu temada aria-pressed=false olmalı")
            dark_again = self._shoot(header)
            back = self._mean_abs_diff(dark, dark_again)
            self.assertLessEqual(
                back, 5.0,
                "koyu temaya dönüş aynı görüntüyü üretmedi (mean Δ %.2f/255)" % back)
            browser.close()

    # ── 2) banner katmanı kontrastı koruyor mu? (dark/light pass) ──────────
    def test_banner_layer_keeps_header_contrast_in_both_themes(self):
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            # axe, a11y_gate.py'nin kullandığı yolla enjekte edilir
            # (preview_server nonce-CSP'si inline script'i bloklar).
            ctx = browser.new_context(bypass_csp=True,
                                      viewport={"width": 1400, "height": 900})
            page = ctx.new_page()
            self._open(page)
            with open(AXE_PATH, encoding="utf-8") as f:
                page.add_script_tag(content=f.read())
            header = page.locator("header")
            for theme in ("dark", "light"):
                self._set_theme(page, theme)
                page.wait_for_timeout(150)
                self._assert_axe_header_clean(page, theme)
                hbox = header.bounding_box()
                band = page.locator(".header-decor").bounding_box()
                self.assertIsNotNone(
                    hbox, "%s temasında header render edilmiyor" % theme)
                self.assertIsNotNone(
                    band,
                    "%s temasında .header-decor render edilmiyor "
                    "(bounding_box yok) — banner katmanı DOM'da değil" % theme)
                band_box = (int(band["x"] - hbox["x"]), int(band["y"] - hbox["y"]),
                            int(band["x"] - hbox["x"] + band["width"]),
                            int(band["y"] - hbox["y"] + band["height"]))
                img_on = self._shoot(header)
                for sel in ("h1", ".imprint", "#live-status"):
                    ratio, n = _text_min_max_ratio(img_on, self._text_box(page, sel, hbox))
                    self.assertGreater(n, 0, "%s: ölçüm kutusu boş" % sel)
                    self.assertGreaterEqual(
                        ratio, 4.5,
                        "%s temasında %s kontrastı AA altı: %.2f:1" % (theme, sel, ratio))
                # #live-status banner bandıyla KESİŞMELİ: yoksa "banner üzerinde
                # kontrast korunuyor" iddiası vakum olurdu.
                status = self._text_box(page, "#live-status", hbox)
                overlap = max(0, min(status[2], band_box[2]) - max(status[0], band_box[0]))
                self.assertGreater(
                    overlap, 0,
                    "#live-status banner bandıyla kesişmiyor (overlap=0) — "
                    "kanıt banner'ın üzerinde değil")
                # Katman gerçekten çiziliyor mu? Görüntü farkı bantta belirgin
                # olmalı; susuyorsa aşağıdaki "kontrast değişmiyor" iddiası da
                # vakum olurdu (katman yoksa karşılaştırılacak bir şey yok).
                page.evaluate(
                    "() => { document.querySelector('.header-decor').style.display='none'; }")
                page.wait_for_timeout(80)
                img_off = self._shoot(header)
                band_diff = self._mean_abs_diff(img_on, img_off, box=band_box)
                self.assertGreaterEqual(
                    band_diff, 0.3,
                    "%s temasında banner katmanı ekran görüntüsünde görünmüyor "
                    "(bant mean Δ %.2f/255)" % (theme, band_diff))
                ratio_on = _text_min_max_ratio(img_on, self._text_box(page, "#live-status", hbox))[0]
                ratio_off = _text_min_max_ratio(img_off, self._text_box(page, "#live-status", hbox))[0]
                delta = abs(ratio_on - ratio_off)
                self.assertLessEqual(
                    delta, 0.5,
                    "%s temasında banner katmanı metin kontrastını değiştirdi "
                    "(katmanlı %.2f:1 / katmansız %.2f:1)" % (theme, ratio_on, ratio_off))
                page.evaluate(
                    "() => { document.querySelector('.header-decor').style.display=''; }")
                page.wait_for_timeout(80)
            browser.close()

    def _assert_axe_header_clean(self, page, theme):
        """Header bağlamında axe temiz + kuralın gerçekten çalıştığı kanıtlı."""
        res = page.evaluate("""async () => {
          const res = await axe.run(document.querySelector('header'));
          const cc = [...res.passes, ...res.incomplete].filter(v => v.id === 'color-contrast');
          return {
            violations: res.violations.map(v => ({id: v.id, impact: v.impact,
                        targets: v.nodes.map(n => n.target.join(' '))})),
            contrast_nodes: cc.reduce((n, v) => n + v.nodes.length, 0),
          };
        }""")
        self.assertEqual(
            res["violations"], [],
            "%s temasında axe (header bağlamı) ihlal buldu: %s" % (theme, res["violations"]))
        self.assertGreaterEqual(
            res["contrast_nodes"], 3,
            "%s temasında axe color-contrast header metinlerini değerlendirmedi "
            "— tarama vakum olabilir (%s node)" % (theme, res["contrast_nodes"]))
        # POZİTİF KONTROL: bilerek bozuk kontrast enjekte edilir; kural yine
        # susuyorsa yukarıdaki yeşil iddia vakumdur.
        probe = page.evaluate("""async () => {
          const d = document.createElement('div');
          d.id = 'contrast-probe';
          d.setAttribute('style', 'color:#151515;background-color:#000000;font-size:14px');
          d.textContent = 'probe';
          document.querySelector('header').appendChild(d);
          const res = await axe.run(d);
          d.remove();
          return res.violations.map(v => v.id);
        }""")
        self.assertIn(
            "color-contrast", probe,
            "%s temasında axe enjekte edilen bozuk kontrastı görmedi (tarama vakum)" % theme)


if __name__ == "__main__":
    unittest.main()
