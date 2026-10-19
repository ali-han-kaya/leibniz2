#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_dashboard_next_surface_smoke.py — dashboard-next YÜZEY smoke'u.

İKİ İDDİA, TEK YÜZEY (bu yüzden tek dosya + tek sunucu kablosu):

  A) AÇIK TEMA. `apps/dashboard-next` panosu tüm renklerini anlamsal
token'lardan alır (koda gömülü ton YOK — `check-design-tokens` bunu
fail-closed kilitler); bu yüzden köprüdeki açık tema bloğu
(`:root[data-theme="light"]`) devreye girdiğinde palet GERÇEKTEN döner.
     Neden gerekliydi: açık tema `dashboard-next` ÜZERİNDE hiçbir gate
tarafından ölçülmüyordu. `test_dashboard_playwright_smoke.py` ile a11y/CWV
job'ları YALNIZ `preview.html` yüzeyini (preview_server) tarar;
`test_surface_cwv_report.py` dashboard-next'i ölçer ama tema parametresiz —
varsayılan (koyu) palete bakar. Açık tema bloğu silinse, gölgelense ya da
tüketilmeyen bir sheet'te kalsa hiçbir şey kırmızıya düşmezdi.

  B) UI BULGULARI (statik eşi: `test_dashboard_next_ui_contract.py`).
Statik süit kaynağı denetler; buradaki canlı katman aynı bulguların
TARAYICIDA gerçekleştiğini kanıtlar: `color-scheme` hesaplanan değeri, meta
`theme-color` içeriği, tek `<h1 translate="no">`, verdict `role="status"`,
`tabular-nums` (hesaplanan `font-variant-numeric`), `<time datetime>`
üzerinde Intl ile biçimlenmiş metin ve `prefers-reduced-motion` altında
nabzın gerçekten durması. Ayrı bir Playwright dosyası ikinci bir sunucu
başlatma hattı (drift + ~10 sn) demekti; ölçülen yüzey aynı olduğu için
katman buraya eklendi. Dosya adı `light_theme` iken kapsam genişledi —
CI/EXCLUDE/coverage üçlüsünün tek kaynağı olduğu için ad `surface_smoke`a
çekildi, referanslar aynı turda güncellendi.

İki katman:
  1. SÖZLEŞME (tarayıcısız, her yerde koşar) — `ThemeTokenContractTest`:
     tüketilen sheet'te açık tema bloğu var mı, açık/koyu palet gerçekten
     FARKLI mı (yoksa canlı smoke vakum olur), `data-theme` kablosu ve
     `dashboard-theme` depolama anahtarı `preview.js` ile uyumlu mu.
  2. CANLI SMOKE (Playwright) — `/` koyu, `/?theme=light` açık paleti
     uygular; sorgu override'ı KALICI OLMAZ; konsol hatası yok; yüzey
     sözleşmeleri (h1/rol/tabular-nums/time/reduced-motion) tutar.

Beklenen renkler KODA GÖMÜLMEZ: token sheet'inden okunur ve
`getComputedStyle` çıktısıyla karşılaştırılır. Sabit ton yazsaydık test
"panonun rengi şu" derdi; ölçülen iddia ise "panonun rengi TOKEN'ın değeri" —
sheet değişince test onu takip eder, çürümez. Aynı disiplin diğer
iddialarda da geçerli: `translate="no"` ve `tabular-nums` sabit DEĞİL,
yüzeyden okunur.

Sunucular hazır kablodan gelir (kopyalanmaz): `preview_server.py` +
`next start` sırası ve argümanları `test_surface_cwv_report.py`'den import
edilir — ikinci bir başlatma hattı drift üretirdi.

Koşum:
  python3 _calisma/CIKTI/test_dashboard_next_surface_smoke.py
  # derleme yoksa: npm run build --prefix apps/dashboard-next

Playwright/Chromium ya da `.next` derlemesi yoksa canlı katman SKIP eder
(fail değil); sözleşme katmanı yine koşar. Dosya `check_unit_tests.list`
DIŞINDA tutulur (sync_check_unit_tests.EXCLUDE): Next boot'u pre-commit'in
10 sn'lik dosya bütçesini aşar — CI'da derlemenin zaten yapıldığı
`dashboard-next` job'ı koşar.
"""

import os
import re
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(HERE))
DESIGN_SYSTEM = os.path.join(REPO_ROOT, "design-system")
TOKENS_CSS = os.path.join(DESIGN_SYSTEM, "tokens.css")
# Panonun TÜKETTİĞİ sheet: `apps/dashboard-next/app/globals.css` bunu import
# eder. Açık tema bloğu yalnız tokens.css'te duruyorsa token'lar "doğru" olur
# ama pano yine koyu kalır — ölçtüğümüz yüzey bu yüzden KÖPRÜdür.
BRIDGE_CSS = os.path.join(DESIGN_SYSTEM, "tailwind.css")
NEXT_DIR = os.path.join(REPO_ROOT, "apps", "dashboard-next")
NEXT_BUILD_ID = os.path.join(NEXT_DIR, ".next", "BUILD_ID")
NEXT_BIN = os.path.join(NEXT_DIR, "node_modules", ".bin", "next")
THEME_INIT_TSX = os.path.join(NEXT_DIR, "components", "ThemeInit.tsx")
THEME_LIB_TS = os.path.join(NEXT_DIR, "lib", "theme.ts")
ROOT_LAYOUT = os.path.join(NEXT_DIR, "app", "layout.tsx")
PREVIEW_JS = os.path.join(HERE, "preview.js")

# Sunucu kablosu TEK kaynaktan: aynı spawner'lar, aynı sıra.
sys.path.insert(0, HERE)
import test_dashboard_cls_budget as cwv_core  # noqa: E402
import test_surface_cwv_report as cwv  # noqa: E402

try:
    from playwright.sync_api import sync_playwright
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
except ImportError:  # CI runner'da playwright kurulu değilse SKIP (fail değil)
    sync_playwright = None
    PlaywrightTimeoutError = None

# Akış tamamlanınca iskeletler (`aria-busy`) kalkar; ölçüm bu işaretle
# beklenir (React'in iç konteyner adına bağlanmak yerine kendi markup'ımıza).
BUSY_SELECTOR = '[aria-busy="true"]'

_DURATION_RE = re.compile(r"^\s*([0-9.eE+-]+)\s*(ms|s)\s*$")


_OKLAB_RE = re.compile(r"oklab\(([^)]*)\)")
_NUMBER_RE = re.compile(r"-?\d*\.?\d+(?:e-?\d+)?")


def oklab_numbers(text):
    """İlk `oklab(...)` renk bileşenlerini sayı olarak döndürür.

    Chromium `color-mix(in oklab, …)` sonucunu `oklab(...)` olarak
    serileştirir (Tailwind'in `/50` saydamlığı bu yola girer); bileşenleri
    sayıya çevirmek metin biçimine bağlanmadan karşılaştırma sağlar.
    """
    m = _OKLAB_RE.search(text or "")
    if not m:
        return []
    return [float(n) for n in _NUMBER_RE.findall(m.group(1))]


def css_seconds(value):
    """`getComputedStyle` süresini SANİYEYE çevirir.

    Chromium bir zaman değerini serileştirirken birim değiştirebilir:
    `0.001ms` → `1e-06s` (ölçüldü). Metin karşılaştırması bu yüzden
    kırılgan; eşik karşılaştırması ise sözleşmenin kendisini ("süre sıfıra
    indi mi") ölçer. Ayrıştırılamayan değer sessizce 0 olmaz — FAIL.
    """
    m = _DURATION_RE.match(value or "")
    if not m:
        raise AssertionError("CSS süresi ayrıştırılamadı: %r" % (value,))
    n = float(m.group(1))
    return n / 1000.0 if m.group(2) == "ms" else n


DARK_SELECTOR = ":root"
LIGHT_SELECTOR = ':root[data-theme="light"]'
STORAGE_KEY = "dashboard-theme"

_COMMENT_RE = re.compile(r"/\*.*?\*/", re.S)
_BLOCK_RE = re.compile(r"(?P<sel>[^{}]+)\{(?P<body>[^{}]*)\}", re.S)
_DECL_RE = re.compile(r"--(?P<name>[A-Za-z0-9_-]+)\s*:\s*(?P<value>[^;]+);")
_HEX_RE = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def token_map(css_text):
    """Kaba selector → {custom-property: value} haritası (yorumlar soyulur).

    Tam bir CSS ayrıştırıcısı değil; yalnız düz `selector { --x: v; }`
    bloklarını okur. Aradığımız iki selector (`:root` ve
    `:root[data-theme="light"]`) bu biçimdedir.
    """
    out = {}
    for m in _BLOCK_RE.finditer(_COMMENT_RE.sub("", css_text)):
        selector = " ".join(m.group("sel").split())
        decls = out.setdefault(selector, {})
        for d in _DECL_RE.finditer(m.group("body")):
            decls[d.group("name")] = d.group("value").strip()
    return out


def hex_to_rgb(value):
    """`#rgb`/`#rrggbb` → (r, g, b). Geçersizse ValueError (sessiz 0 YOK)."""
    v = value.strip()
    if not _HEX_RE.match(v):
        raise ValueError("hex renk bekleniyordu, bulundu: %r" % (value,))
    digits = v[1:]
    if len(digits) == 3:
        digits = "".join(c * 2 for c in digits)
    return tuple(int(digits[i : i + 2], 16) for i in (0, 2, 4))


def css_rgb(value):
    """Tarayıcının `getComputedStyle` biçimi: `rgb(r, g, b)`."""
    return "rgb(%d, %d, %d)" % hex_to_rgb(value)


class ThemeTokenContractTest(unittest.TestCase):
    """Tarayıcısız katman: canlı smoke atlansa bile sözleşmeyi kilitler."""

    @classmethod
    def setUpClass(cls):
        cls.tokens = token_map(read(TOKENS_CSS))
        cls.bridge = token_map(read(BRIDGE_CSS))

    def test_consumed_sheet_declares_light_block(self):
        """Pano hangi sheet'i import ediyorsa açık tema ORADA olmalı."""
        self.assertIn(
            LIGHT_SELECTOR,
            self.bridge,
            "apps/dashboard-next'in import ettiği design-system/tailwind.css "
            "açık tema bloğu içermiyor — pano ?theme=light'ta koyu kalır",
        )
        for name in ("bg", "fg"):
            self.assertIn(name, self.bridge[LIGHT_SELECTOR])

    def test_light_and_dark_palettes_are_distinct(self):
        """Vakum kapısı: iki palet aynıysa canlı smoke hiçbir şey kanıtlamaz."""
        for label, table in (("tokens.css", self.tokens), ("tailwind.css", self.bridge)):
            dark, light = table[DARK_SELECTOR], table[LIGHT_SELECTOR]
            for name in ("bg", "fg"):
                self.assertNotEqual(
                    dark[name],
                    light[name],
                    "%s: %s açık/koyu AYNI — tema anahtarı renk değiştirmiyor"
                    % (label, name),
                )

    def test_bridge_and_canonical_tokens_agree(self):
        """Köprü üretilmiştir; kaynaktan sapan bir kopya sessizce farklı tema
        boyar (pano ile preview.html ayrışır). İki sheet aynı değerleri taşımalı."""
        for selector in (DARK_SELECTOR, LIGHT_SELECTOR):
            for name in ("bg", "fg"):
                self.assertEqual(
                    self.tokens[selector][name],
                    self.bridge[selector][name],
                    "%s %s: tokens.css ile tailwind.css ayrıştı" % (selector, name),
                )

    def test_hex_parsing_is_fail_closed(self):
        """Ölçüm hattı bozuk token'ı sessizce 0'a düşürmemeli."""
        self.assertEqual(hex_to_rgb("#f3efe7"), (243, 239, 231))
        self.assertEqual(hex_to_rgb("#fff"), (255, 255, 255))
        for bad in ("oklch(0.9 0.02 80)", "var(--bg)", "f3efe7", "#xyzxyz", ""):
            with self.assertRaises(ValueError):
                hex_to_rgb(bad)

    def test_wiring_applies_data_theme_and_mounts(self):
        """Kablo sökülürse canlı katman SKIP olsa bile burada durur."""
        init = read(THEME_INIT_TSX)
        self.assertIn("document.documentElement.dataset.theme", init)
        layout = read(ROOT_LAYOUT)
        self.assertIn("ThemeInit", layout, "kök layout ThemeInit'i bağlamıyor")

    def test_storage_key_and_param_match_preview_contract(self):
        """İki yüzey (preview.html + dashboard-next) AYNI tercihi paylaşmalı;
        anahtar ayrışırsa aynı tarayıcıda iki farklı tema saklanır."""
        lib = read(THEME_LIB_TS)
        preview = read(PREVIEW_JS)
        for key in (STORAGE_KEY, '"theme"'):
            self.assertIn(key, lib)
        self.assertIn(STORAGE_KEY, preview)


@unittest.skipIf(sync_playwright is None,
                 "playwright kurulu değil (pip install playwright + chromium)")
@unittest.skipUnless(
    os.path.isfile(NEXT_BUILD_ID),
    "apps/dashboard-next/.next derlemesi yok — "
    "npm run build --prefix apps/dashboard-next",
)
class DashboardNextLightThemeTest(unittest.TestCase):
    """Canlı: `next start` + preview_server üzerinden gerçek palet ölçümü."""

    preview_proc = None
    next_proc = None

    @classmethod
    def setUpClass(cls):
        if not os.path.isfile(NEXT_BIN):
            raise RuntimeError(
                "apps/dashboard-next/node_modules/.bin/next yok — "
                "npm ci --prefix apps/dashboard-next gerekli")
        bridge = token_map(read(BRIDGE_CSS))
        # Ham token haritası: `theme-color` meta'sı `--bg`yi DÖNÜŞTÜRMEDEN
        # (hex olarak) taşır — karşılaştırma rgb değil ham metin üzerinden.
        cls.bridge_tokens = bridge
        cls.dark = {
            "bg": css_rgb(bridge[DARK_SELECTOR]["bg"]),
            "fg": css_rgb(bridge[DARK_SELECTOR]["fg"]),
        }
        cls.light = {
            "bg": css_rgb(bridge[LIGHT_SELECTOR]["bg"]),
            "fg": css_rgb(bridge[LIGHT_SELECTOR]["fg"]),
        }
        cls._tmp = tempfile.mkdtemp(prefix="next_light_theme_")
        cls.addClassCleanup(shutil.rmtree, cls._tmp, True)
        logs = os.path.join(cls._tmp, "logs")
        os.makedirs(logs, exist_ok=True)

        preview_port = cwv_core.free_port()
        cls.preview_proc = cwv.spawn_preview_server(
            HERE, preview_port, os.path.join(logs, "preview_server.log"))
        cls.addClassCleanup(cwv.terminate, cls.preview_proc)

        next_port = cwv_core.free_port()
        cls.next_proc = cwv.spawn_next_server(
            next_port, "http://127.0.0.1:%d" % preview_port,
            os.path.join(logs, "next_start.log"))
        cls.addClassCleanup(cwv.terminate, cls.next_proc)

        cls.base = "http://127.0.0.1:%d" % next_port

    def _measure(self, path, reduced_motion=None):
        """Sayfayı yükler; tema + palet + yüzey sözleşmesi durumunu döndürür.

        `reduced_motion` verilirse Playwright medya emülasyonu sayfa
        yüklenmeden ÖNCE kurulur (globals.css'teki
        `@media (prefers-reduced-motion: reduce)` bloğunu ölçmenin tek yolu).
        """
        errors = []
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                page = browser.new_page()
                if reduced_motion is not None:
                    page.emulate_media(reduced_motion=reduced_motion)
                page.on(
                    "console",
                    lambda msg: errors.append(msg.text)
                    if msg.type == "error"
                    and not msg.text.startswith("Failed to load resource")
                    else None,
                )
                page.goto(self.base + path, wait_until="domcontentloaded")
                # ThemeInit istemcide uygular (useEffect) — attribute gelene
                # kadar bekle; "gelmedi" sessiz iddiasızlık değil, FAIL'dir.
                try:
                    page.wait_for_function(
                        "() => document.documentElement.dataset.theme !== undefined",
                        timeout=15000,
                    )
                except PlaywrightTimeoutError:
                    # En yaygın neden: `.next` derlemesi `ThemeInit`'ten ESKİ.
                    # `next start` önceden derlenmiş bundle'ı sunar; kaynak
                    # yeni olsa bile eski bundle `data-theme` yazmaz — sessiz
                    # bir 15 sn timeout yerine adı konmuş bir ipucu bırak.
                    raise AssertionError(
                        "data-theme 15 sn içinde uygulanmadı (%s). Olası neden: "
                        ".next derlemesi ThemeInit öncesine ait — yeniden "
                        "derleyin: npm run build --prefix apps/dashboard-next "
                        "(build id: %s)"
                        % (self.base + path, read(NEXT_BUILD_ID).strip())
                    )
                # Akış tamamlanana kadar bekle. Paralel rota slotlarının
                # iskeletleri (`aria-busy`) gerçek kartlarla DEĞİŞTİRİLİR;
                # değişim olmadan ölçüm yapılırsa gerçek içerik hâlâ akış
                # konteynerinde (`div[hidden]`) durur ve iddialar iskeleti
                # ölçer — ölçüldü: iki `<dl>`, ilki iskeletin (yani
                # `font-variant-numeric: normal`). İskeletin kalkmasını
                # beklemek ölçülen yüzeyin GERÇEK pano olduğunu garanti eder.
                try:
                    page.wait_for_function(
                        "() => document.querySelectorAll(%r).length === 0"
                        % BUSY_SELECTOR,
                        timeout=20000,
                    )
                except PlaywrightTimeoutError:
                    raise AssertionError(
                        "paneller 20 sn içinde açılmadı (iskelet kaldı): %s — "
                        "akış tamamlanmadı ya da bir sınır hata durumuna düştü"
                        % (self.base + path)
                    )
                state = page.evaluate(
                    """() => {
                      const body = getComputedStyle(document.body);
                      let stored = null;
                      try { stored = localStorage.getItem("dashboard-theme"); }
                      catch (e) { stored = "<erişilemedi>"; }
                      return {
                        theme: document.documentElement.dataset.theme,
                        bg: body.backgroundColor,
                        fg: body.color,
                        stored,
                        brand: (document.body.textContent || "")
                          .includes("STOIC-HUME V5"),
                        // Bölüm başlıkları `PanelCard` bileşiminden gelir
                        // (paylaşılan kabuk). Yokluğu "kart render edilmedi"
                        // demektir: hata sınırı devreye girmişse palet doğru
                        // olsa bile pano ölçülmüş sayılmaz.
                        headings: Array.from(document.querySelectorAll("h2"))
                          .map((h) => (h.textContent || "").trim()),
                        // --- UI bulguları (statik eşi: ui_contract süiti) ---
                        // Hesaplanan `color-scheme`: tarayıcının kaydırma
                        // çubuğu/form kontrolleri için kullandığı palet.
                        colorScheme: getComputedStyle(
                          document.documentElement
                        ).colorScheme,
                        // `theme-color` meta'sı ThemeInit tarafından TOKEN'dan
                        // yazılır; içerik doğrudan karşılaştırılır.
                        themeColor: (() => {
                          const m = document.head.querySelector(
                            'meta[name="theme-color"]'
                          );
                          return m ? m.content : null;
                        })(),
                        // Tek `<h1>` ve `translate="no"` (marka çevrilmemeli).
                        h1s: Array.from(document.querySelectorAll("h1")).map(
                          (h) => ({
                            text: (h.textContent || "").trim(),
                            translate: h.getAttribute("translate"),
                          })
                        ),
                        // Verdict canlı bölgesi.
                        statusCount: document.querySelectorAll('[role="status"]')
                          .length,
                        // `<time>`: makine damgası öznitelikte, okunur metin
                        // gövdede; `tabular-nums` hesaplanan değeri.
                        times: Array.from(document.querySelectorAll("time")).map(
                          (t) => ({
                            dateTime: t.getAttribute("datetime"),
                            text: (t.textContent || "").trim(),
                            numeric: getComputedStyle(t).fontVariantNumeric,
                          })
                        ),
                        // Sayı yüzeyleri: verdict istatistik ızgarası + tablo
                        // hücresi. Hesaplanan `font-variant-numeric`.
                        statsNumeric: (() => {
                          const dl = document.querySelector("dl");
                          return dl
                            ? getComputedStyle(dl).fontVariantNumeric
                            : null;
                        })(),
                        cellNumeric: (() => {
                          const td = document.querySelector("table td");
                          return td
                            ? getComputedStyle(td).fontVariantNumeric
                            : null;
                        })(),
                        // Hareket azaltma ölçümü: utility sınıfı GERÇEKTEN
                        // yüklü mü (yoksa aşağıdaki iddia vakum olurdu) ve
                        // medya sorgusu süreyi sıfırlıyor mu.
                        pulseDuration: (() => {
                          const probe = document.createElement("div");
                          probe.className = "animate-pulse";
                          document.body.appendChild(probe);
                          const d = getComputedStyle(probe).animationDuration;
                          probe.remove();
                          return d;
                        })(),
                      };
                    }"""
                )
            finally:
                browser.close()
        return state, errors

    def _wait_panels(self, page, path=None):
        """Akışın tamamlanmasını bekler (iskelet iner) — `_measure` ile AYNI
        işaret (`aria-busy`), AYRI yazılmaz. `path` verilirse URL'nin o
        rotaya konuşmuş olduğunu da doğrular (gezinme gerçekten oldu mu).
        """
        try:
            page.wait_for_function(
                "() => document.querySelectorAll(%r).length === 0" % BUSY_SELECTOR,
                timeout=20000,
            )
        except PlaywrightTimeoutError:
            raise AssertionError(
                "paneller 20 sn içinde açılmadı (iskelet kaldı): %s"
                % (path or self.base))
        if path is not None:
            actual = page.evaluate("() => location.pathname")
            self.assertEqual(
                actual, path,
                "gezinme gerçekleşmedi: beklenen %s, olan %s" % (path, actual))

    def _probe_state(self, page):
        """Soft-nav ölçüm dili: window marker'ı + belge kimliği.

        `marker` — testin kendisinin koyduğu probe (`window.__softNavProbe`).
        `popStatePerf` — `performance.timeOrigin`: BELGE doğum zamanı. Soft
        navda sabit kalır (aynı belge), tam yenilemede DEĞİŞİR. Marker
        yalnız başına yetmezdi: bellek içi kalıntı, sayfa gerçekten yeniden
        yüklense bile bozuk bir senaryoda "kalıcı" görünebilirdi — timeOrigin
        bu boşluğu kapatır.
        """
        return page.evaluate(
            """() => ({
              marker: window.__softNavProbe === undefined
                ? null : window.__softNavProbe,
              popStatePerf: performance.timeOrigin,
              path: location.pathname,
            })"""
        )

    def _focus_probe(self, path="/"):
        """İlk TAB sonrası odaklanan öğenin görünür odak işaretini ölçer.

        Klavye odağında `:focus-visible` eşleşir ve `navLink`in halkası
        `box-shadow` olarak hesaplanır; fare tıklamasıyla eşleşmediği için
        bu ölçüm ancak GERÇEK bir TAB ile yapılabilir (sınıf dizgesinin
        varlığı tarayıcının onu uyguladığını kanıtlamaz).
        """
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                page = browser.new_page()
                page.goto(self.base + path, wait_until="domcontentloaded")
                page.wait_for_function(
                    "() => document.querySelectorAll(%r).length === 0"
                    % BUSY_SELECTOR,
                    timeout=20000,
                )
                page.keyboard.press("Tab")
                return page.evaluate(
                    """() => {
                      const el = document.activeElement;
                      // Beklenen halka rengi: AYNI ifade, sayfada çözülür
                      // (`ring-ring/50` → oklab color-mix). Sabit bir rgb
                      // yazmak ölçümü kopya yapardı; böylece palet/token
                      // değişince beklenti onu takip eder.
                      const probe = document.createElement("div");
                      probe.style.color =
                        "color-mix(in oklab, var(--ring) 50%, transparent)";
                      document.body.appendChild(probe);
                      const expectedRing = getComputedStyle(probe).color;
                      probe.remove();
                      return {
                        tag: el.tagName,
                        text: (el.textContent || "").trim(),
                        boxShadow: getComputedStyle(el).boxShadow,
                        expectedRing,
                      };
                    }"""
                )
            finally:
                browser.close()

    def test_nav_link_shows_a_focus_ring_on_keyboard_tab(self):
        """Odak halkası nav bağlantılarına taşındı (buton tabanıyla aynı
        sözleşme). İlk TAB zaten nav'ın ilk bağlantısına gider — sekme
        sırası da bu vakayla kilitlenir."""
        state = self._focus_probe("/")
        self.assertEqual(state["tag"], "A",
                         "ilk TAB bir bağlantıya gitmedi: %s" % state)
        self.assertEqual(state["text"], "ÖZET", "sekme sırası değişti: %s" % state)
        self.assertNotIn(
            state["boxShadow"], ("", "none"),
            "klavye odağında halka yok — odak işareti görünmez: %s" % state)
        self.assertIn("3px", state["boxShadow"],
                      "halka genişliği buton sözleşmesiyle (3px) aynı değil")
        # Halka repo token'ından mı renk alıyor, yoksa bir varsayılan renge mi
        # düşmüş? Beklenen renk SAYFADA aynı ifadeyle çözülür (yukarıdaki
        # prob) ve renk uzayı serileştirmesi (oklab) sayısal olarak
        # karşılaştırılır — `/50` saydamlığı da alfanın 0,5 olmasıyla ölçülür.
        measured = oklab_numbers(state["boxShadow"])
        expected = oklab_numbers(state["expectedRing"])
        self.assertTrue(expected, "beklenen halka rengi ölçülemedi: %s" % state)
        self.assertEqual(len(measured), len(expected),
                         "renk uzayı bileşenleri ayrıştı: %s vs %s"
                         % (measured, expected))
        for got, want in zip(measured, expected):
            self.assertAlmostEqual(
                got, want, places=4,
                msg="halka `--ring` token'ını taşımıyor (ölçülen %s, beklenen %s)"
                    % (measured, expected))
        self.assertAlmostEqual(measured[-1], 0.5, places=2,
                               msg="halka saydamlığı `/50` sözleşmesinden sapmış")

    def test_default_renders_dark_tokens(self):
        state, errors = self._measure("/")
        self.assertEqual(state["theme"], "dark")
        self.assertEqual(state["bg"], self.dark["bg"],
                         "gövde arka planı koyu token'a eşit değil")
        self.assertEqual(state["fg"], self.dark["fg"])
        self.assertTrue(state["brand"], "pano kabuğu (marka) görünmüyor — "
                                        "hata sayfası ölçülüyor olabilir")
        self.assertEqual(errors, [], "konsol hatası: %s" % errors)

    def test_panel_compound_renders_section_headings(self):
        """Paylaşılan kabuk (`PanelCard`) gerçekten basılıyor mu.

        `/` iki panel yuva sunar ve ikisinin de başlığı `PanelCardHeader`
        içinden gelir: verdict kartı ("Son Koşum") ve trend tablosu
        ("Son 5 Koşum"). Başlık `<h2>`dir (a11y bölüm hiyerarşisi) ve veriden
        BAĞIMSIZDır — veri gelmese de basılır, dolayısıyla bu iddia ölçüm
        ortamına değil bileşime bakar. Bileşim bozulursa (başlık `<div>`e
        düşerse, yuva çıkarılırsa) burada kırılır.
        """
        state, errors = self._measure("/")
        self.assertIn("Son Koşum", state["headings"],
                      "verdict paneli başlığı yok — PanelCardHeader basmıyor")
        self.assertIn("Son 5 Koşum", state["headings"],
                      "trend paneli başlığı yok — PanelCardHeader basmıyor")
        self.assertEqual(errors, [], "konsol hatası: %s" % errors)

    def test_query_light_applies_light_tokens(self):
        state, errors = self._measure("/?theme=light")
        self.assertEqual(state["theme"], "light")
        self.assertNotEqual(
            self.light["bg"], self.dark["bg"],
            "test vakum: açık ve koyu token aynı değer",
        )
        self.assertEqual(state["bg"], self.light["bg"],
                         "gövde arka planı AÇIK token'a dönmedi")
        self.assertEqual(state["fg"], self.light["fg"],
                         "gövde metin rengi AÇIK token'a dönmedi")
        self.assertTrue(state["brand"])
        self.assertEqual(errors, [], "konsol hatası: %s" % errors)

    def test_query_override_does_not_persist(self):
        """CI taraması kullanıcının kayıtlı tercihini bozmamalı."""
        light_state, _ = self._measure("/?theme=light")
        self.assertEqual(light_state["theme"], "light")
        self.assertIsNone(
            light_state["stored"],
            "sorgu override'ı localStorage'a YAZILDI — kullanıcı tercihi bozuldu",
        )
        default_state, _ = self._measure("/")
        self.assertEqual(default_state["theme"], "dark",
                         "override kalıcı olmuş: sonraki ziyaret açık kaldı")

    # ── UI bulgularının CANLI kanıtı ────────────────────────────────────────
    # Statik eş bu iddiaları kaynakta kilitler
    # (`test_dashboard_next_ui_contract.py`); buradakiler sözleşmenin
    # tarayıcıda GERÇEKLEŞTİĞİNİ gösterir — kaynakta doğru görünüp
    # hesaplanan stile hiç ulaşmayan bir kural (ölü selector, ezilen
    # utility, yanlış katman) burada düşer.

    def test_color_scheme_follows_theme(self):
        """`color-scheme` tarayıcının UI paletini seçer (kaydırma çubuğu,
        form kontrolleri): koyu temada dark, açık temada light olmalı.

        Ölçülen iddia `:root` bloğunun VARLIĞI değil, tarayıcının
        ÇÖZDÜĞÜ değerdir — kural yanlış seçiciye yazılırsa burada düşer.
        """
        dark_state, _ = self._measure("/")
        self.assertEqual(dark_state["colorScheme"], "dark")
        light_state, _ = self._measure("/?theme=light")
        self.assertEqual(light_state["colorScheme"], "light",
                         ":root[data-theme=light] color-scheme'i döndürmüyor")

    def test_theme_color_meta_tracks_the_token(self):
        """`<meta name="theme-color">` tarayıcı çubuğunu paletle eşler.

        Değer TAHMİN edilmez: token sheet'indeki `--bg`nin kendisiyle
        karşılaştırılır (ThemeInit onu computed style'dan okur). Sabit bir
        hex bekleseydik test token değişince çürürdü; burada tek kaynak
        sheet'tir.
        """
        dark_state, _ = self._measure("/")
        self.assertEqual(
            dark_state["themeColor"], self.bridge_tokens[DARK_SELECTOR]["bg"],
            "theme-color meta'sı koyu --bg token'ını taşımıyor")
        light_state, _ = self._measure("/?theme=light")
        self.assertEqual(
            light_state["themeColor"], self.bridge_tokens[LIGHT_SELECTOR]["bg"],
            "theme-color meta'sı açık temaya dönmedi")

    def test_single_h1_carries_the_untranslatable_brand(self):
        """Sayfada TEK `<h1>` olmalı (bölüm `<h2>`leri ona bağlanır) ve
        marka çevrilmemeli (`translate="no"`)."""
        state, errors = self._measure("/")
        self.assertEqual(len(state["h1s"]), 1,
                         "tek kök başlık yok: %s" % (state["h1s"],))
        h1 = state["h1s"][0]
        self.assertIn("STOIC-HUME V5", h1["text"],
                      "h1 marka değil: %r" % (h1["text"],))
        self.assertEqual(h1["translate"], "no",
                         "marka h1'i çevrilebilir — translate=no düşmüş")
        self.assertEqual(errors, [], "konsol hatası: %s" % errors)

    def test_verdict_is_a_status_region(self):
        """Verdict bir durum mesajıdır: `role="status"` canlı bölge olarak
        render edilmeli (rol'süz/`aria-live`sız metin AT'ye duyurulmaz)."""
        state, _ = self._measure("/")
        self.assertGreaterEqual(
            state["statusCount"], 1,
            "pano yüzeyinde role=status bölgesi yok — verdict duyurulmaz")

    def test_timestamps_are_formatted_and_tabular(self):
        """Ham `ts` KULLANICIYA basılmaz: `<time datetime>` makine damgasını
        taşır, görünen metin Intl biçimidir; rakamlar `tabular-nums`.

        Ölçüm: ISO kalıbı görünen metinde ARANMAZ (yanlış pozitif vermesin
        diye tersine kuruldu — metin ham damgaya EŞİT olamaz).
        """
        state, _ = self._measure("/")
        times = state["times"]
        self.assertTrue(
            times,
            "hiç `<time>` yok — ya veri gelmedi ya da damga bağlanmadı")
        for t in times:
            self.assertTrue(t["dateTime"], "`<time>` dateTime özniteliksiz: %r" % (t,))
            self.assertNotEqual(
                t["text"], t["dateTime"],
                "ham ISO damga göründüğü gibi basılmış: %r" % (t["text"],))
            self.assertNotRegex(
                t["text"], r"\d{4}-\d{2}-\d{2}T",
                "görünen metin hâlâ ISO damgası: %r" % (t["text"],))
            self.assertEqual(
                t["numeric"], "tabular-nums",
                "zaman hücresi tabular-nums taşımıyor: %r" % (t,))
        self.assertEqual(
            state["cellNumeric"], "tabular-nums",
            "tablo sayı hücresi tabular-nums taşımıyor")
        self.assertEqual(
            state["statsNumeric"], "tabular-nums",
            "verdict istatistik ızgarası tabular-nums taşımıyor")

    def test_soft_nav_preserves_window_marker_across_routes(self):
        """Soft-nav kanıtı KALICIDır (findings.md §"webapp-testing E2E",
        2026-09-19: "window marker survived / -> /trend (before=42 after=42)").

        VT'nin tetik ön koşulu client-side routing'dir: tam sayfa yenilemesi
        window nesnesini SIFIRLAR, soft nav KORUR. İşaret bir probe'dur —
        test kendi koyar (`window.__softNavProbe = 42`), uygulama özelliği
        değildir; uygulama onu TANIYOR demek yerine "nesne hayatta mı"
        sorusunu yanıtlar. Tıklama GERÇEK Link tıklamasıdır (page.click):
        `page.goto` ile gitmek iddiayı vakum ederdi — gezinme zaten soft
        olmazdı. İki yönlü ölçülür (/ -> /trend -> /) çünkü Link'ler her
        iki sayfada da bağımsız kabloludur (layout nav + sayfa linki).
        Ayrıca URL `pushState` türevi değişmiş olmalı — yoksa tıklama
        href'e gitmemiştir.
        """
        if sync_playwright is None:
            self.skipTest("Playwright yok — canlı soft-nav kanıtı CI'da koşar")
        errors = []
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                page = browser.new_page()
                page.on(
                    "console",
                    lambda msg: errors.append(msg.text)
                    if msg.type == "error"
                    and not msg.text.startswith("Failed to load resource")
                    else None,
                )
                page.on("pageerror", lambda exc: errors.append(str(exc)))
                page.goto(self.base + "/", wait_until="domcontentloaded")
                self._wait_panels(page)
                page.evaluate("() => { window.__softNavProbe = 42; }")
                before = self._probe_state(page)

                # / -> /trend : layout nav'ındaki TREND Link'i.
                page.click('nav a[href="/trend"]')
                self._wait_panels(page, path="/trend")
                after_trend = self._probe_state(page)

                # geri dönüş: layout nav'ındaki ÖZET Link'i. (Panel sayfasının
                # kendi Link'i yalnız /trend'e GİDER; köke dönen bağlantı
                # nav'dadır — iki yön de nav Link'lerinden ölçülür.)
                page.click('nav a[href="/"]')
                # /trend slotu yerine tam /trend SAYFASI açıldığından burada
                # panel slotu YOK — aria-busy bekleyen iskelet de yoktur.
                # Yine de URL'nin gerçekten döndüğünü doğrulamak şart.
                page.wait_for_function(
                    "() => location.pathname === '/'",
                    timeout=15000,
                )
                after_home = self._probe_state(page)
            finally:
                browser.close()

        self.assertEqual(before["marker"], 42, "probe / üzerinde kurulamadı")
        for label, state in (("/trend", after_trend), ("/ (geri)", after_home)):
            self.assertEqual(
                state["marker"], 42,
                "%s: window marker HAYATTA DEĞİL — navigasyon tam sayfa "
                "yenilemesine döndü (soft nav bozuldu)" % label)
            self.assertEqual(
                state["popStatePerf"], before["popStatePerf"],
                "%s: performance.timeOrigin değişti — belge YENİDEN yüklendi "
                "(marker'ın kalması yalnızca Bellek içi kalıntı olabilir)" % label)
        self.assertEqual(after_trend["path"], "/trend")
        self.assertEqual(after_home["path"], "/")
        self.assertEqual(errors, [], "konsol/sayfa hatası: %s" % errors)

    def test_full_reload_resets_the_marker_counter_proof(self):
        """Karşıt kanıt: AYNI işaret, TAM sayfa yenilemesinde HAYATTA KALMAZ.

        Bu test soft-nav testini boş iddia olmaktan çıkarır: marker'ı
        koruyan şey "window kalıcıdır" iddiası değil, gerçekten soft
        navdır. `page.reload` gerçek bir belge yüklemesidir (yeni
        timeOrigin + sıfırlanmış window) — soft nav testi ile AYNI ölçüm
        dilini kullanır (marker + timeOrigin).
        """
        if sync_playwright is None:
            self.skipTest("Playwright yok — canlı karşıt kanıt CI'da koşar")
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                page = browser.new_page()
                page.goto(self.base + "/", wait_until="domcontentloaded")
                self._wait_panels(page)
                page.evaluate("() => { window.__softNavProbe = 42; }")
                before = self._probe_state(page)
                page.reload(wait_until="domcontentloaded")
                self._wait_panels(page)
                after = self._probe_state(page)
            finally:
                browser.close()

        self.assertEqual(before["marker"], 42, "probe kurulamadı")
        self.assertIsNone(
            after["marker"],
            "tam yenilemede marker hayatta kaldı — ölçüm dili bozuk "
            "(soft-nav testi artık ayrım yapmıyor)")
        self.assertNotEqual(
            after["popStatePerf"], before["popStatePerf"],
            "reload timeOrigin'i değiştirmedi — belge gerçekten yenilenmedi")

    def test_reduced_motion_stops_the_pulse(self):
        """`prefers-reduced-motion: reduce` nabzı GERÇEKTEN durdurmalı.

        Ölçüm iki adımlı: (1) tercih yokken süre SIFIR OLMAMALI — yoksa
        utility hiç yüklü değildir ve ikinci adım vakum olur; (2) tercih
        açıkken süre globals.css'teki değere (0.001ms) inmeli.
        """
        normal, _ = self._measure("/", reduced_motion="no-preference")
        self.assertGreater(
            css_seconds(normal["pulseDuration"]), 0.01,
            "animate-pulse utility'si yüklü/animasyonlu değil — ölçüm vakum "
            "olurdu (ölçülen: %s)" % normal["pulseDuration"])
        reduced, _ = self._measure("/", reduced_motion="reduce")
        self.assertLessEqual(
            css_seconds(reduced["pulseDuration"]), 0.001,
            "prefers-reduced-motion bloğu nabzı durdurmuyor (ölçülen: %s)"
            % reduced["pulseDuration"])


if __name__ == "__main__":
    unittest.main()
