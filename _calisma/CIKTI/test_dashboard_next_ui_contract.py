#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_dashboard_next_ui_contract.py — dashboard-next UI sözleşmesi (STATİK).

KAYNAK: `findings.md` §"web-design-guidelines review (2026-09-19,
work/2026-09-19)" (commit 5779ab0) — Vercel Web Interface Guidelines taze
çekilip `apps/dashboard-next` yüzeyi denetlendiğinde 13 bulgu çıkmıştı;
inceleme yalnız dokümandı, düzeltmeler sonraki turda uygulandı. Bu dosya
her bulgunun KAYNAK/CSS tarafında bir daha kaymayacağını kilitler;
tarayıcıda gerçekleştiğinin kanıtı `test_dashboard_next_surface_smoke.py`de
(aynı sunucu kablosu; ikinci bir Playwright boot'u yok).

Neden ayrı dosya: bulgular tek bileşende değil sekiz dosyada yaşıyor
(globals.css, lib/format.ts, ThemeInit, layout, ui/button, VerdictCard,
RunsTable, error, app/loading). Mevcut süitler bunların hiçbirini
ölçmüyordu: `test_dashboard_next_style_gates.py` KAPILARIN kendisini,
`..._surface_smoke.py` temayı ölçer. Bu süit tarayıcısız (dosya okur) —
bu yüzden pre-commit bataryasındadır.

Bulgu → iddia eşlemesi:
  1  color-scheme yok .................... ColorSchemeTest
  2  theme-color meta'sı yok ............. ThemeColorTest
  3  animate-pulse + reduced-motion
     (loading + Suspense fallback) ....... ReducedMotionTest (hedefler dahil)
  4  transition-all (buton tabanı) ....... ButtonTransitionTest
  5  rol'süz div üzerinde aria-label ..... LiveRegionTest
  6  sayfalarda h1 yok ................... HeadingTest
  7  ham ts, Intl yerine dilimleme ....... TimestampTest
  8  sayı sütunlarında tabular-nums yok .. TabularNumsTest
  9  hata yüzeyinde role=alert yok ....... LiveRegionTest
 10  marka span'ı translate=no'suz ....... HeadingTest
  (3'ün üç çağrı yeri, 5'in üç dosyada tekrarı, 8'in iki yüzeyi ayrı
  vakalarla ölçülür.)

Ayrıştırıcılar kaba ama KENDİLERİNİ TEST EDER (`ScannerSelfTest`): JSX
etiket tarayıcısı ifade içindeki `>`ten ve JS'teki kesme işaretinden
etkilenmez; CSS blok yürüyücüsü iç içe yolu (`@media … > *`) verir — "beyan
gerçekten medya sorgusunun İÇİNDE mi" sorusu ancak yapı bilgisiyle
yanıtlanır.

Koşum:
  python3 _calisma/CIKTI/test_dashboard_next_ui_contract.py
"""

import json
import os
import pathlib
import re
import unittest

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent.parent
NEXT = REPO / "apps" / "dashboard-next"
APP = NEXT / "app"
COMPONENTS = NEXT / "components"
GLOBALS_CSS = APP / "globals.css"
BRIDGE_CSS = REPO / "design-system" / "tailwind.css"
PREVIEW_HTML = HERE / "preview.html"
TOKENS_CSS = REPO / "design-system" / "tokens.css"
TOKENS_JSON = REPO / "design-system" / "tokens.json"
FORMAT_TS = NEXT / "lib" / "format.ts"
THEME_INIT = COMPONENTS / "ThemeInit.tsx"
LAYOUT = APP / "layout.tsx"
BUTTON = COMPONENTS / "ui" / "button.tsx"
BADGE = COMPONENTS / "ui" / "badge.tsx"
PANEL_STYLE = COMPONENTS / "panel-style.ts"
ERROR_PAGE = APP / "error.tsx"
PANEL_ERROR = COMPONENTS / "PanelError.tsx"
PANEL_BOUNDARY = COMPONENTS / "PanelBoundary.tsx"
PANEL_ERROR_FILES = [
    APP / "(panel)" / "error.tsx",
    APP / "(panel)" / "@verdict" / "error.tsx",
    APP / "(panel)" / "@trend" / "error.tsx",
    APP / "trend" / "error.tsx",
    APP / "layers" / "error.tsx",
]
ROOT_LOADING = APP / "loading.tsx"
VERDICT = APP / "VerdictCard.tsx"
RUNS_TABLE = COMPONENTS / "RunsTable.tsx"
RUN_COMPARE = COMPONENTS / "RunCompareCard.tsx"
REFS_CHART = COMPONENTS / "RefsTrendChart.tsx"
LAYER_GRID = COMPONENTS / "LayerStatusGrid.tsx"
SECURITY_CARD = COMPONENTS / "SecuritySurfaceCard.tsx"
PANEL_CARD = COMPONENTS / "PanelCard.tsx"
PANEL_PAGE = APP / "(panel)" / "page.tsx"
PANEL_LAYOUT = APP / "(panel)" / "layout.tsx"
TREND_PAGE = APP / "trend" / "page.tsx"
LAYERS_PAGE = APP / "layers" / "page.tsx"
LOADING_FILES = [
    ROOT_LOADING,
    APP / "(panel)" / "@verdict" / "loading.tsx",
    APP / "(panel)" / "@trend" / "loading.tsx",
]

ROOT_SELECTOR = ":root"
LIGHT_SELECTOR = ':root[data-theme="light"]'
REDUCE_GUARD = "prefers-reduced-motion"

MANIFEST = HERE / "check_unit_tests.list"
THIS_FILE = "test_dashboard_next_ui_contract.py"
SMOKE_FILE = "test_dashboard_next_surface_smoke.py"
OLD_SMOKE_NAME = "test_dashboard_next_light_theme.py"
CONFIG = REPO / ".pre-commit-config.yaml"

_HEX_RE = re.compile(r"#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})\b")


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


# ── küçük ayrıştırıcılar (kendileri de test edilir) ─────────────────────────

_CSS_COMMENT_RE = re.compile(r"/\*.*?\*/", re.S)


def strip_css_comments(text):
    return _CSS_COMMENT_RE.sub("", text)


def css_blocks(text):
    """(yol, gövde) çiftleri; yol iç içe blokları `>` ile birleştirir.

    Yaprak olmayan blokların gövdesi yalnız SON çocuktan sonraki beyanları
    taşır (iç içe blok metni ebeveyne kopyalanmaz). Amacımız tam bir CSS
    ayrıştırıcısı değil, "beyan gerçekten bu medya sorgusunun İÇİNDE mi"
    sorusunu yanıtlayabilmek.
    """
    src = strip_css_comments(text)
    stack, buf, out = [], "", []
    for ch in src:
        if ch == "{":
            stack.append(" ".join(buf.split()))
            buf = ""
        elif ch == "}":
            sel = stack.pop()
            out.append((" > ".join(stack + [sel]), " ".join(buf.split())))
            buf = ""
        elif ch == ";" and not stack:
            buf = ""  # parantezsiz at-rule (@import …);
        else:
            buf += ch
    return out


_JSX_COMMENT_RE = re.compile(r"\{/\*.*?\*\}", re.S)
_JS_BLOCK_COMMENT_RE = re.compile(r"/\*.*?\*/", re.S)
# `://` korunur: `http://127.0.0.1:8000` bir yorum değildir.
_JS_LINE_COMMENT_RE = re.compile(r"(?<!:)//[^\n]*")
_TAG_RE = re.compile(r"<([A-Za-z][A-Za-z0-9_.:-]*)")


def strip_js_comments(text):
    """Yorumları soy — prose içindeki `<div>` / `aria-label` metni etiket
    sanılmasın (bu, iddiaları sessizce vakum yapardı)."""
    text = _JSX_COMMENT_RE.sub("", text)
    text = _JS_BLOCK_COMMENT_RE.sub("", text)
    return _JS_LINE_COMMENT_RE.sub("", text)


def jsx_tags(source):
    """Açılış etiketleri: {name, attrs, start, end}.

    Kaba ama yeterli iki kural: (1) JSX ifadesi (`{...}`) içindeki `>`
    etiketi kapatmaz (dinamik karşılaştırmalar), (2) tırnaklar yalnız
    öznitelik düzeyinde izlenir — JS'teki kesme işareti (`it's`) etiketi
    yutmaz.
    """
    text = strip_js_comments(source)
    tags = []
    for m in _TAG_RE.finditer(text):
        j, depth, quote = m.end(), 0, None
        while j < len(text):
            ch = text[j]
            if depth:
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
            elif quote:
                if ch == quote:
                    quote = None
            elif ch in "\"'":
                quote = ch
            elif ch == "{":
                depth = 1
            elif ch == ">":
                break
            j += 1
        tags.append(
            {
                "name": m.group(1),
                "attrs": text[m.end() : j],
                "start": m.start(),
                "end": j + 1,
                "text": text,
            }
        )
    return tags


def has_attr(attrs, name):
    return bool(re.search(r"(?:^|\s)" + re.escape(name) + r"\s*=", attrs))


def attr_value(attrs, name):
    m = re.search(
        r'(?:^|\s)' + re.escape(name) + r'=\s*"([^"]*)"', attrs
    )
    return m.group(1) if m else None


def element_inner(tag):
    """Etiketin kapanışına kadarki iç metin (`<time>` gövdesi için)."""
    text = tag["text"]
    close = text.find("</%s>" % tag["name"], tag["end"])
    return text[tag["end"] : close if close != -1 else len(text)]


_SOURCES = None


def tsx_sources():
    """(yol, kaynak) — app/ + components/ + lib/ altındaki tüm TS/TSX.

    `.ts` de dahil: biçimleyici ve tema çözümleyici (lib/) JSX taşımaz ama
    sözleşmenin parçasıdır; taramayı dar tutmak iddiaları sessizce eksik
    bırakırdı. `node_modules`/`.next` kapsam dışıdır (yol listesi açık).
    """
    global _SOURCES
    if _SOURCES is None:
        files = sorted(
            {p for root in (APP, COMPONENTS, NEXT / "lib")
             for pat in ("*.ts", "*.tsx") for p in root.rglob(pat)}
        )
        _SOURCES = [(p, read(p)) for p in files]
    return _SOURCES


def rel(path):
    return os.path.relpath(path, REPO)


# ── ayrıştırıcıların kendi testleri ─────────────────────────────────────────

class ScannerSelfTest(unittest.TestCase):
    def test_jsx_scanner_ignores_expressions_and_prose(self):
        src = (
            "// prose içinde <div> ve aria-label geçiyor, etiket değil\n"
            "<div\n"
            '  className={cn("a", "b")}\n'
            '  data-x={n > 0 ? "x" : "y"}\n'
            '  aria-label="rol\'süz"\n'
            '  role="status"\n'
            ">\n"
            "  {formatTimestamp(ts)}\n"
            "</div>\n"
        )
        tags = jsx_tags(src)
        self.assertEqual([t["name"] for t in tags], ["div"], tags)
        attrs = tags[0]["attrs"]
        self.assertTrue(has_attr(attrs, "aria-label"))
        self.assertEqual(attr_value(attrs, "role"), "status")

    def test_jsx_scanner_reads_time_body_and_attribute(self):
        src = (
            "<time className={x} dateTime={latest.ts}>\n"
            "  {formatTimestamp(latest.ts)}\n"
            "</time>\n"
        )
        (tag,) = jsx_tags(src)
        self.assertEqual(tag["name"], "time")
        self.assertTrue(has_attr(tag["attrs"], "dateTime"))
        self.assertIn("formatTimestamp(", element_inner(tag))

    def test_css_walker_reports_nesting_path(self):
        css = (
            ":root {\n  --bg: #000;\n  color-scheme: dark;\n}\n"
            "@media (prefers-reduced-motion: reduce) {\n"
            "  *, *::before {\n    animation-duration: 0.001ms !important;\n  }\n"
            "}\n"
        )
        blocks = dict(css_blocks(css))
        self.assertIn("color-scheme: dark;", blocks[":root"])
        self.assertIn("animation-duration: 0.001ms !important;",
                      blocks["@media (prefers-reduced-motion: reduce) > *, *::before"])

    def test_strip_js_comments_keeps_urls(self):
        out = strip_js_comments('const u = "http://127.0.0.1:8000"; // not\n')
        self.assertIn("http://127.0.0.1:8000", out)
        self.assertNotIn("not", out)


# ── 1. color-scheme ─────────────────────────────────────────────────────────

class ColorSchemeTest(unittest.TestCase):
    """Bulgu: `color-scheme` yok — tarayıcı yerleşik UI'ı (kaydırma çubuğu,
    form kontrolleri) açık koyu temada yanlış boyanıyordu."""

    @classmethod
    def setUpClass(cls):
        cls.blocks = dict(css_blocks(read(GLOBALS_CSS)))

    def test_dark_root_declares_dark_scheme(self):
        self.assertIn(ROOT_SELECTOR, self.blocks)
        self.assertIn("color-scheme: dark;", self.blocks[ROOT_SELECTOR])

    def test_light_theme_block_declares_light_scheme(self):
        self.assertIn(
            LIGHT_SELECTOR,
            self.blocks,
            "globals.css açık tema bloğu yok — color-scheme dönmez",
        )
        self.assertIn("color-scheme: light;", self.blocks[LIGHT_SELECTOR])

    def test_scheme_lives_in_the_hand_written_sheet(self):
        """`color-scheme` bir ANAHTAR SÖZCÜK, renk değil: token köprüsü
        (GENERATED `design-system/tailwind.css`) yalnız custom property
        kopyalar, dolayısıyla tema başına elle yazılmalı. Köprüye sızarsa
        jeneratör sözleşmesi bozulmuştur."""
        self.assertNotIn("color-scheme", read(BRIDGE_CSS))


# ── 2. theme-color ──────────────────────────────────────────────────────────

class ThemeColorTest(unittest.TestCase):
    """Bulgu: `<meta name="theme-color">` yok — mobil tarayıcı çubuğu paleti
    izlemiyordu."""

    @classmethod
    def setUpClass(cls):
        cls.src = read(THEME_INIT)

    def test_meta_is_created_and_written_at_runtime(self):
        self.assertIn('meta[name="theme-color"]', self.src)
        self.assertIn("document.createElement(\"meta\")", self.src)
        self.assertIn("meta.content", self.src)

    def test_value_comes_from_the_bg_token(self):
        """Sabit hex gömülü olamaz: hem tema tek kaynaktan gelir hem
        `check-design-tokens` uygulama kaynağında hex literalini bloke eder."""
        self.assertIn("getComputedStyle", self.src)
        self.assertIn('getPropertyValue("--bg")', self.src)
        self.assertIsNone(
            _HEX_RE.search(self.src),
            "ThemeInit'te hex literal var — meta token'dan okunmuyor",
        )

    def test_exactly_one_writer(self):
        writers = [rel(p) for p, s in tsx_sources() if "theme-color" in s]
        self.assertEqual(
            writers, [rel(THEME_INIT)],
            "theme-color'ı birden fazla yer yazıyor (tek kaynak ihlali): %s"
            % writers,
        )


# ── 3. prefers-reduced-motion ───────────────────────────────────────────────

class ReducedMotionTest(unittest.TestCase):
    """Bulgu: `animate-pulse` `prefers-reduced-motion`e saygı göstermiyordu
    (üç akış iskeleti: kök `loading.tsx` + iki paralel rota slotu)."""

    @classmethod
    def setUpClass(cls):
        # YALNIZ beyan taşıyan (yaprak) bloklar: medya çerçevesinin kendi
        # gövdesi boştur — onu saymak iddiayı sahte biçimde geçirirdi.
        cls.media = [
            (path, body)
            for path, body in css_blocks(read(GLOBALS_CSS))
            if path.startswith("@media") and REDUCE_GUARD in path and body
        ]

    def test_reduce_block_exists_and_is_universal(self):
        self.assertTrue(
            self.media,
            "globals.css'te `%s: reduce` bloğu yok" % REDUCE_GUARD,
        )
        for path, _ in self.media:
            self.assertIn("*", path, "kural evrensel seçici kullanmıyor: %s" % path)

    def test_reduce_block_zeroes_animation_and_transition(self):
        body = " ".join(b for _, b in self.media)
        for decl in ("animation-duration", "animation-iteration-count",
                     "transition-duration"):
            self.assertIn(decl, body)
        self.assertEqual(
            body.count("!important"), 3,
            "süreleri sıfırlayan her beyan !important olmalı (utility'lerin "
            "kendi süreleri var) — ölçülen: %s" % body,
        )

    def test_pulse_has_targets(self):
        """Vakum kapısı: kural kalır ama nabız tümden kaldırılırsa bu blok
        ölü olur. Üç iskeletin `animate-pulse` taşıdığını doğrula."""
        for path in LOADING_FILES:
            self.assertIn(
                "animate-pulse", read(path),
                "%s nabız taşımıyor — azaltma kuralı hedefsiz kaldı" % rel(path),
            )

    def test_preview_html_uses_the_same_declarations(self):
        """İki yüzey (preview.html + pano) aynı kuralı taşımalı; biri
        güncellenip diğeri geride kalırsa erişilebilirlik sessizce ayrışır."""
        m = re.search(
            r"@media\s*\(\s*prefers-reduced-motion\s*:\s*reduce\s*\)\s*\{"
            r"(?P<body>.*?)\n\}",
            read(PREVIEW_HTML),
            re.S,
        )
        self.assertIsNotNone(m, "preview.html'de azaltma bloğu bulunamadı")
        claimed = dict(
            (prop, val)
            for prop, val in re.findall(r"([a-z-]+)\s*:\s*([^;{}]+)", m.group("body"))
        )
        observed = {}
        for _, body in self.media:
            observed.update(
                (prop, val)
                for prop, val in re.findall(r"([a-z-]+)\s*:\s*([^;{}]+)", body)
            )
        self.assertEqual(
            {k: " ".join(v.split()) for k, v in observed.items()},
            {k: " ".join(v.split()) for k, v in claimed.items()},
            "panonun azaltma bloğu preview.html'inkinden ayrıştı",
        )


# ── 4. transition-all → açık özellik listesi ────────────────────────────────

# shadcn primitive tabanları: cva adı → dosya. Kusur SINIF düzeyinde
# (`transition-all`) ve İKİ primitive'de birden vardı.
PRIMITIVES = [("buttonVariants", BUTTON), ("badgeVariants", BADGE)]

# İki primitive'in ORTAK taahhüdü: hover/focus görünüşünü taşıyan dört
# özellik ailesi. Listeler birebir aynı olmak zorunda değil (butonun
# transform/opacity'si rozette yok) ama bu dördünü ikisi de kapsamalı,
# yoksa aynı sınıf ailesi iki yüzeyde farklı şeyi canlandırır.
SHARED_TRANSITION_PROPS = {
    "color", "background-color", "border-color", "box-shadow",
}

# İşaret → o işaretin değiştirdiği özellik. Gereksinim tabandan TÜRETİLİR:
# işaret varsa özellik listede olmalı; işaret de doğrulanır (vakum değil).
TRANSITION_MARKERS = {
    "buttonVariants": {
        "translate-y": "transform",
        "disabled:opacity-": "opacity",
        "focus-visible:ring-": "box-shadow",
        "hover:bg-": "background-color",
        "hover:text-": "color",
        "focus-visible:border-": "border-color",
    },
    "badgeVariants": {
        "focus-visible:ring-": "box-shadow",
        "focus-visible:border-": "border-color",
        "hover:bg-": "background-color",
        "hover:text-": "color",
    },
}


def cva_base(source, name):
    """`const <name> = cva("…"` taban dizgesi."""
    m = re.search(r'const %s = cva\(\s*"((?:[^"\\]|\\.)*)"' % name, source)
    if not m:
        raise AssertionError("%s taban dizgesi bulunamadı" % name)
    return m.group(1)


def transition_props(base):
    m = re.search(r"transition-\[([^\]]+)\]", base)
    return {p.strip() for p in m.group(1).split(",")} if m else set()


class PrimitiveTransitionTest(unittest.TestCase):
    """Bulgu: primitive tabanı `transition-all` — tema değişiminde
    (data-theme) layout/paint özellikleri de geçişe giriyordu. Aynı kusur
    iki primitive'de vardı; rozet panoda canlı (VerdictCard istatistikleri)."""

    @classmethod
    def setUpClass(cls):
        cls.sources = {name: read(path) for name, path in PRIMITIVES}

    def test_no_transition_all_in_any_primitive(self):
        for name, path in PRIMITIVES:
            with self.subTest(primitive=rel(path)):
                self.assertNotIn("transition-all",
                                 cva_base(self.sources[name], name))

    def test_single_transition_utility_per_primitive(self):
        """Birden çok `transition-*` utility'si birbirini ezer — liste tek
        yerde olmalı."""
        for name, path in PRIMITIVES:
            with self.subTest(primitive=rel(path)):
                base = cva_base(self.sources[name], name)
                self.assertEqual(len(re.findall(r"transition-", base)), 1,
                                 "taban sınıfta birden fazla transition var")

    def test_property_list_covers_every_animated_marker(self):
        for name, path in PRIMITIVES:
            src = self.sources[name]
            props = transition_props(cva_base(src, name))
            for marker, prop in TRANSITION_MARKERS[name].items():
                with self.subTest(primitive=rel(path), marker=marker):
                    self.assertIn(marker, src, "işaret kayboldu: %s" % marker)
                    self.assertIn(
                        prop, props,
                        "`%s` animasyonlu ama `%s` geçiş listesinde yok: %s"
                        % (marker, prop, sorted(props)),
                    )
            with self.subTest(primitive=rel(path), marker="text-decoration"):
                # Bilinçli DIŞARIDA: `text-decoration-line` ayrık (discrete)
                # bir özellik, geçiş üretmez. `link` varyantındaki
                # `hover:underline` için listeye eklemek sözleşmeyi süsler.
                self.assertNotIn("text-decoration", props)

    def test_shared_property_families_are_present_in_both(self):
        """Drift kilidi: listeler farklı olabilir ama ortak aileler ikisinde
        de bulunmalı (bir primitive geride kalırsa hover/focus görünüşü
        yarı animasyonlu kalır)."""
        for name, path in PRIMITIVES:
            props = transition_props(cva_base(self.sources[name], name))
            with self.subTest(primitive=rel(path)):
                self.assertTrue(
                    SHARED_TRANSITION_PROPS <= props,
                    "eksik aileler: %s" % sorted(SHARED_TRANSITION_PROPS - props),
                )


# ── 4b. odak işareti (halka primitive'lerden nav bağlantılarına) ────────────

class FocusIndicatorTest(unittest.TestCase):
    """Bulgu ailesi (devamı): odak halkası yalnız primitive tabanlarındaydı.
    Üst kabuktaki nav bağlantıları klavyeyle gezildiğinde işaretsiz kalıyordu
    ve dizgeleri ikisinde kopyalanmıştı."""

    def test_nav_links_use_the_shared_style(self):
        layout = read(LAYOUT)
        links = [t for t in jsx_tags(layout) if t["name"] == "Link"]
        self.assertGreaterEqual(len(links), 2, "nav bağlantıları bulunamadı")
        for tag in links:
            self.assertIn("navLink(", tag["attrs"],
                          "nav bağlantısı `navLink`ten beslenmiyor: %s"
                          % tag["attrs"].strip())

    def test_focus_ring_contract_matches_the_button_base(self):
        """İki yüzey AYNI odak işaretini göstermeli: kaynak tek yerde
        (buton tabanı) tanımlı, nav onu tekrar eder."""
        button = cva_base(read(BUTTON), "buttonVariants")
        nav = cva_base(read(PANEL_STYLE), "navLink")
        for token in ("focus-visible:ring-3", "focus-visible:ring-ring/50"):
            self.assertIn(token, button, "buton tabanında ring sözleşmesi eksik")
            self.assertIn(token, nav, "navLink buton halkasını taşımıyor")

    def test_every_link_declares_a_focus_indicator(self):
        """Genel kural: her `<Link>`/`<a>` ya primitive tabanından (buton
        varyantı) ya `navLink`ten ya da açık `focus-visible:` sınıfından
        odak işareti alır — yeni bir bağlantı sessizce işaretsiz kalamaz."""
        seen = 0
        for path, src in tsx_sources():
            for tag in jsx_tags(src):
                if tag["name"] not in ("Link", "a"):
                    continue
                seen += 1
                attrs = tag["attrs"]
                with self.subTest(file=rel(path), text=attrs.strip()[:40]):
                    self.assertTrue(
                        "navLink(" in attrs
                        or "buttonVariants(" in attrs
                        or "focus-visible:" in attrs,
                        "%s: <%s> odak işareti taşımıyor: %s"
                        % (rel(path), tag["name"], attrs.strip()),
                    )
        self.assertGreaterEqual(seen, 4, "bağlantı taraması vakum")


# ── panel hata sınırları ─────────────────────────────────────────────────────

class PanelBoundaryTest(unittest.TestCase):
    """Her panelin KENDİ `error.tsx`i var: bir kaynak hatası diğer paneli
    düşürmemeli.

    Neden segment başına dosya: App Router'da `error.tsx` yalnız kendi
    segmentini sarar. Slot (`@verdict`, `@trend`) için dosya yoksa hata
    gruba/köke tırmanır ve iki panel birden kaybolur.
    """

    def test_each_panel_segment_has_a_client_error_boundary(self):
        for path in PANEL_ERROR_FILES:
            with self.subTest(path=rel(path)):
                self.assertTrue(path.is_file(), "%s yok" % rel(path))
                self.assertIn('"use client"', read(path),
                              "%s istemci bileşeni olmalı" % rel(path))

    def test_boundaries_share_one_retry_surface(self):
        for path in PANEL_ERROR_FILES:
            src = read(path)
            with self.subTest(path=rel(path)):
                self.assertIn('from "@/components/PanelError"', src)
                self.assertIn("onRetry={reset}", src)
                # Hata kartı panel başına kopyalanmaz: tek görsel sözleşme.
                self.assertNotIn("<PanelCard", src)

    def test_shared_surface_is_an_alert_with_a_retry(self):
        surface = read(PANEL_ERROR)
        tags = [t for t in jsx_tags(surface) if t["name"] == "PanelCard"]
        self.assertTrue(tags, "PanelError'da PanelCard yok")
        self.assertEqual(attr_value(tags[0]["attrs"], "role"), "alert")
        self.assertIn("<Button", surface)
        # Buton artık doğrudan sınır state'ini temizlemiyor: retry = state
        # temizliği + RSC tazeleme (aşağıdaki sınıf sözleşmeyi sabitler).
        self.assertIn("onClick={retry}", surface)

    def test_boundary_is_a_real_react_error_boundary(self):
        src = read(PANEL_BOUNDARY)
        self.assertIn("class PanelBoundary extends Component", src)
        self.assertIn("static getDerivedStateFromError", src)

    def test_boundary_drops_a_stale_error_when_fresh_data_arrives(self):
        """`resetKey` sözleşmesi: yapışkan hata kalmamalı.

        E2E'de ölçüldü: bir panel retry edilip RSC tazelenince kardeş
        paneller hata durumunda ASILI kalıyor ve mesaj React'in minify
        edilmiş iç hatasına dönüşüyordu. Sınır, her yeni sunucu turunda
        değişen anahtarla hatayı bırakmalı.
        """
        src = read(PANEL_BOUNDARY)
        self.assertIn("resetKey", src)
        self.assertIn("static getDerivedStateFromProps", src)
        self.assertRegex(src, r"return \{ error: null, resetKey: props\.resetKey \};")

    def test_pages_pass_a_per_render_reset_key(self):
        trend = read(APP / "trend" / "page.tsx")
        self.assertIn("const renderKey = Date.now();", trend)
        self.assertEqual(trend.count("resetKey={renderKey}"), 3,
                         "/trend'deki üç sınır da anahtarı almalı")
        home = read(APP / "(panel)" / "page.tsx")
        self.assertIn("resetKey={renderKey}", home)

    def test_trend_page_wraps_every_data_panel(self):
        page = read(APP / "trend" / "page.tsx")
        self.assertEqual(page.count("<PanelBoundary"), 3)
        self.assertEqual(page.count("</PanelBoundary>"), 3)
        for component in ("RunsTableData", "RunComparePanel", "RefsTrendPanel"):
            self.assertIn("<%s" % component, page,
                          "%s sınırın içinde olmalı" % component)
        # Veri çekmesi sınırın ALTINDA (panel server component'inde) —
        # sayfada await olsaydı hata sınır kurulmadan oluşurdu.
        for module in ("RunComparePanel.tsx", "RefsTrendPanel.tsx"):
            self.assertIn("await getTrendBundle(", read(COMPONENTS / module))

    def test_home_security_card_has_its_own_boundary(self):
        src = read(APP / "(panel)" / "page.tsx")
        self.assertIn("<PanelBoundary", src)
        self.assertIn("<SecuritySurfaceCard />", src)
        self.assertIn("Güvenlik yüzeyi yüklenemedi", src)


# ── panel retry + otomatik tazeleme ────────────────────────────────────────

class PanelRetryAndRefreshTest(unittest.TestCase):
    """'Tekrar dene' gerçekten fetch eder; kartlar canlı koşumda kendini tazeler.

    Neden ölçülüyor: yalnız `reset()` çağıran bir retry KOZMETİKTİR — istemci
    state'ini temizler ama hata veren sunucu bileşenini yeniden çalıştırmaz,
    yani kaynak düzelmiş olsa bile eski hatayı basar. Aynı şekilde
    `router.refresh()` çağrısı olmadan "otomatik tazeleme" yalnız bir sayaç
    olurdu: SSE gelse de ekran değişmez.
    """

    def test_retry_clears_boundary_state_and_refetches_rsc(self):
        src = read(PANEL_ERROR)
        self.assertIn('from "next/navigation"', src)
        self.assertIn("useRouter()", src)
        self.assertRegex(src, r"onRetry\?\.\(\)")
        self.assertIn("router.refresh()", src)
        # Sıra önemli: state temizlenmeden tazelenirse hata çerçevesi kalır.
        # Yalnız gerçek `retry` gövdesine bakılır (yorum metni sayılmaz).
        body = src[src.index("const retry = () => {"):]
        body = body[:body.index("};\n")]
        self.assertLess(body.index("onRetry?.()"), body.index("router.refresh()"))
        # Sınır dosyaları reset'i geçirmeye devam ediyor (state temizliği).
        for path in PANEL_ERROR_FILES:
            with self.subTest(path=rel(path)):
                self.assertIn("onRetry={reset}", read(path))

    def test_auto_refresh_subscribes_and_cleans_up(self):
        src = read(COMPONENTS / "PanelAutoRefresh.tsx")
        self.assertIn('"use client"', src)
        self.assertIn('new EventSource("/api/events', src)
        self.assertIn("router.refresh()", src)
        # Sızıntı yasağı: abonelik ve zamanlayıcı unmount'ta kapanmalı.
        self.assertIn("source.close()", src)
        self.assertIn("clearInterval(timer)", src)
        # Arka plan sekmesi sunucuyu yormamalı + dönüşte telafi.
        self.assertIn('document.visibilityState !== "visible"', src)
        self.assertIn('"visibilitychange"', src)
        # Fırtına koruması: aynı saniyede birden çok snapshot tek tur atmalı.
        self.assertIn("MIN_REFRESH_GAP_MS", src)

    def test_auto_refresh_ignores_repeated_run_ids(self):
        """Aynı `ts` tekrar geldiğinde tazeleme yapılmamalı (vakum denetimi:
        karşılaştırma yoksa her keepalive/reconnect bir RSC turu açar)."""
        src = read(COMPONENTS / "PanelAutoRefresh.tsx")
        self.assertRegex(src, r"if \(lastTs\.current === ts\) return;")
        self.assertIn("lastTs.current = ts;", src)

    def test_verdict_slot_refreshes_with_its_ssr_baseline(self):
        src = read(APP / "(panel)" / "@verdict" / "page.tsx")
        self.assertIn("<PanelAutoRefresh", src)
        # Baseline bilinmeden ilk snapshot bir doğrulama turu açar; SSR
        # damgasını geçirmek bu fazladan turu İLK AÇILIŞTA önler.
        self.assertIn("<PanelAutoRefresh baselineTs={latest.ts ?? null}>", src)
        self.assertIn("getLatest()", src)
        self.assertIn("<VerdictCard />", src)

    def test_trend_page_has_exactly_one_refresher_around_all_panels(self):
        page = read(APP / "trend" / "page.tsx")
        self.assertEqual(page.count("<PanelAutoRefresh"), 1)
        self.assertEqual(page.count("</PanelAutoRefresh>"), 1)
        # Sarmalayıcı üç sınırı da kapsamalı: biri dışarıda kalsa o panel
        # canlı tazelemeden mahrum kalırdı.
        start = page.index("<PanelAutoRefresh")
        end = page.index("</PanelAutoRefresh>")
        block = page[start:end]
        for component in ("RunsTableData", "RunComparePanel", "RefsTrendPanel"):
            self.assertIn("<%s" % component, block,
                          "%s tazeleyicinin dışında kaldı" % component)


# ── 5 + 9. canlı bölge rolleri ──────────────────────────────────────────────

class LiveRegionTest(unittest.TestCase):
    """Bulgular: (5) loading iskeletlerinde rol'süz div üzerinde `aria-label`
    (yok sayılır — axe `aria-prohibited-attr`), (9) hata yüzeyinde
    `role="alert"` yok."""

    def test_every_aria_label_belongs_to_a_roled_element(self):
        seen = 0
        for path, src in tsx_sources():
            for tag in jsx_tags(src):
                if not has_attr(tag["attrs"], "aria-label"):
                    continue
                seen += 1
                self.assertTrue(
                    has_attr(tag["attrs"], "role"),
                    "%s: rol'süz <%s> üzerinde aria-label — etiket yok sayılır"
                    % (rel(path), tag["name"]),
                )
        self.assertGreaterEqual(
            seen, 3,
            "aria-label taraması vakum: üç iskelet etiketi bulunmalıydı",
        )

    def test_error_surface_is_an_alert(self):
        tags = [t for t in jsx_tags(read(ERROR_PAGE)) if t["name"] == "PanelCard"]
        self.assertTrue(tags, "error.tsx'te PanelCard bulunamadı")
        self.assertEqual(attr_value(tags[0]["attrs"], "role"), "alert")

    def test_verdict_is_a_status_region(self):
        """`role="status"` `aria-live="polite"`ı zaten kapsar; ikisini
        birlikte yazmak yinelemeli olurdu."""
        src = read(VERDICT)
        tags = [t for t in jsx_tags(src) if attr_value(t["attrs"], "role") == "status"]
        self.assertEqual(len(tags), 1, "verdict `role=\"status\"` bölgesi yok")
        self.assertEqual(tags[0]["name"], "p")
        # Yineleme yasağı ATTRÜBÜT düzeyinde ölçülür; yorumların metni
        # ("eski `aria-live` özniteliği rolle değişti") sayılmaz.
        live = [t for t in jsx_tags(src) if has_attr(t["attrs"], "aria-live")]
        self.assertEqual(live, [], "role=status ile birlikte aria-live yinelemeli")


# ── 6 + 10. başlık hiyerarşisi ve çevrilmez marka ───────────────────────────

class HeadingTest(unittest.TestCase):
    """Bulgular: (6) sayfalarda `<h1>` yok (bölüm `<h2>`leri köksüzdü),
    (10) marka `<span>`ı `translate="no"` taşımıyordu."""

    def test_exactly_one_h1_and_it_lives_in_the_root_layout(self):
        found = []
        for path, src in tsx_sources():
            tags = [t for t in jsx_tags(src) if t["name"] == "h1"]
            found.extend((rel(path), t) for t in tags)
        self.assertEqual(
            [p for p, _ in found], [rel(LAYOUT)],
            "tek kök `<h1>` kök layout'ta olmalı; bulunan: %s"
            % [p for p, _ in found],
        )

    def test_brand_h1_is_not_translatable(self):
        h1 = [t for t in jsx_tags(read(LAYOUT)) if t["name"] == "h1"][0]
        self.assertEqual(attr_value(h1["attrs"], "translate"), "no")
        self.assertIn("STOIC-HUME V5", element_inner(h1))

    def test_section_titles_are_still_h2(self):
        """`<h1>` eklenirken bölüm başlıkları düşmemeli: kabuk `<h2>` basar."""
        self.assertIn("<h2", read(PANEL_CARD))


# ── 7. Intl ile zaman biçimlendirme ─────────────────────────────────────────

class TimestampTest(unittest.TestCase):
    """Bulgu: ham `ts` dilimlenerek basılıyordu (`Intl.DateTimeFormat`
    yerine elle kesme) — yerel ayar ve 12/24 saat kuralı ıskalanıyordu."""

    @classmethod
    def setUpClass(cls):
        cls.fmt = read(FORMAT_TS)

    def test_formatter_is_created_once_with_pinned_locale_and_zone(self):
        self.assertEqual(
            len(re.findall(r"new Intl\.DateTimeFormat", self.fmt)), 1,
            "biçimleyici her çağrıda yeniden kurulmamalı (modül düzeyi tek)",
        )
        self.assertRegex(self.fmt, r'TIMESTAMP_LOCALE\s*=\s*"tr-TR"')
        self.assertRegex(self.fmt, r'TIMESTAMP_TIME_ZONE\s*=\s*"UTC"')
        self.assertIn("timeZone", self.fmt)

    def test_broken_values_fall_back_to_the_placeholder(self):
        self.assertIn("EMPTY_VALUE", self.fmt)
        self.assertIn("Number.isNaN", self.fmt)

    def test_consumers_go_through_the_formatter(self):
        for path in (VERDICT, RUNS_TABLE):
            src = read(path)
            self.assertIn('from "@/lib/format"', src,
                          "%s biçim modülünü import etmiyor" % rel(path))
            self.assertIn("formatTimestamp(", src)

    def test_every_time_element_carries_the_machine_stamp(self):
        """Yüzey kuralı: görünen metin biçimlenmiş, makine damgası
        `dateTime` özniteliğinde. `<time>` sayısı 0'sa iddia vakumdur."""
        seen = 0
        for path, src in tsx_sources():
            for tag in jsx_tags(src):
                if tag["name"] != "time":
                    continue
                seen += 1
                self.assertTrue(
                    has_attr(tag["attrs"], "dateTime"),
                    "%s: `<time>` dateTime özniteliksiz" % rel(path),
                )
                self.assertIn(
                    "formatTimestamp(", element_inner(tag),
                    "%s: `<time>` gövdesi biçimlenmemiş (ham ts basılıyor)"
                    % rel(path),
                )
        self.assertGreaterEqual(seen, 2, "`<time>` taraması vakum")

    def test_placeholder_has_a_single_source(self):
        """Yer tutucu tek sabitten gelir; bileşenler onu yeniden yazmaz."""
        definitions = sorted(
            rel(p) for p, s in tsx_sources()
            if re.search(r"(?:const|export const)\s+EMPTY_VALUE", s)
        )
        self.assertEqual(
            definitions, [rel(FORMAT_TS)],
            "EMPTY_VALUE tanımı tek kaynakta olmalı: %s" % definitions,
        )
        for path in (VERDICT, RUNS_TABLE):
            src = read(path)
            self.assertIn("EMPTY_VALUE", src)
            self.assertNotIn(
                '"—"', src,
                "%s yer tutucuyu yeniden yazıyor (EMPTY_VALUE kullan)" % rel(path),
            )


# ── 8. tabular-nums ─────────────────────────────────────────────────────────

class TabularNumsTest(unittest.TestCase):
    """Bulgu: sayı sütunlarında `tabular-nums` yok — rakamlar satır satır
    kayıyor, sütunlar hizalanmıyordu."""

    @classmethod
    def setUpClass(cls):
        cls.table = read(RUNS_TABLE)
        cls.style = read(PANEL_STYLE)
        cls.verdict = read(VERDICT)

    def test_table_cells_inherit_tabular_from_one_place(self):
        """Reçete artık ÜÇ tablonun ortak `tableCell`i (panel-style.ts)."""
        m = re.search(
            r'export const tableCell = cva\(\s*"((?:[^"\\]|\\.)*)"',
            self.style,
        )
        self.assertIsNotNone(m, "tableCell taban dizgesi bulunamadı")
        self.assertIn("tabular-nums", m.group(1))

    def test_no_table_cell_bypasses_the_variant(self):
        """Hücre `tableCell` dışından sınıf alsaydı tabular-nums'ı
        sessizce atlardı."""
        cells = [t for t in jsx_tags(self.table) if t["name"] == "TableCell"]
        self.assertTrue(cells, "tablo hücresi bulunamadı")
        for tag in cells:
            self.assertIn("tableCell(", tag["attrs"],
                          "ad-hoc hücre sınıfı: %s" % tag["attrs"].strip())

    def test_number_columns_still_exist(self):
        """Vakum kapısı: sütunlar kaldırılırsa tabular-nums ölçülecek bir şey
        bulamaz."""
        for expr in ("r.p0", "r.p1", "r.duration_s", "r.z3_total"):
            self.assertIn(expr, self.table)

    def test_verdict_numbers_are_tabular(self):
        dl = [t for t in jsx_tags(self.verdict) if t["name"] == "dl"]
        self.assertEqual(len(dl), 1, "verdict istatistik ızgarası bulunamadı")
        self.assertIn("tabular-nums", dl[0]["attrs"])
        for tag in (t for t in jsx_tags(self.verdict) if t["name"] == "time"):
            self.assertIn("tabular-nums", tag["attrs"])


# ── 12. tipografi + boşluk ölçeği: design-system TEK kaynak ────────────────

SURFACE_FILES = (
    PANEL_STYLE,
    PANEL_CARD,
    VERDICT,
    RUNS_TABLE,
    RUN_COMPARE,
    REFS_CHART,
    LAYER_GRID,
    SECURITY_CARD,
    PANEL_PAGE,
    PANEL_LAYOUT,
    TREND_PAGE,
    LAYERS_PAGE,
    PANEL_ERROR,
    ERROR_PAGE,
)


class TypeSpaceScaleTest(unittest.TestCase):
    """Pano puntosu, harf aralığı ve yerleşim aralığı design-system'den gelir.

    Bulgu: aynı ölçüler çağrı yerlerinde yeniden yazılıyordu —
    `text-5xl` (hüküm, köprüde olmayan Tailwind 30px ölçeği),
    `font-serif` (Tailwind'in kendi yığını, `--font-verdict` değil) ve
    `tracking-[0.22em]` (üç dosyada arbitrary). Kart/tablo armonisi de
    ölçüydü: hücre dolgusu 10px + kart dolgusu 14px = 24px'te başlarken
    başlık 14px'te kalıyordu.
    """

    def test_roles_live_in_the_token_sheet(self):
        css = read(TOKENS_CSS)
        for decl in (
            "--text-display: 48px;",
            "--lh-display: 1;",
            "--ls-label: 0.22em;",
            "--ls-data: 0.14em;",
            "--ls-chrome: 0.12em;",
            "--panel-gutter: var(--space-8);",
            "--panel-section-gap: var(--space-7);",
            "--panel-block-gap: var(--space-5);",
            "--panel-tight-gap: var(--space-2);",
            "--panel-table-cell: var(--space-2) var(--card-padding);",
        ):
            self.assertIn(decl, css, "design-system rolü eksik: %s" % decl)

    def test_bridge_exposes_the_role_utilities(self):
        bridge = read(BRIDGE_CSS)
        for key in (
            "--text-display: var(--text-display);",
            "--leading-display: var(--lh-display);",
            "--tracking-label: var(--ls-label);",
            "--tracking-data: var(--ls-data);",
            "--tracking-chrome: var(--ls-chrome);",
            "--font-verdict: var(--font-verdict);",
        ):
            self.assertIn(key, bridge, "köprüde utility yok: %s" % key)

    def test_json_mirrors_the_new_scale(self):
        data = json.loads(read(TOKENS_JSON))
        self.assertEqual(data["font-size"]["display"], "48px")
        self.assertEqual(data["line-height"]["display"], 1)
        self.assertEqual(data["letter-spacing"]["label"], "0.22em")
        self.assertEqual(data["letter-spacing"]["data"], "0.14em")
        self.assertEqual(data["letter-spacing"]["chrome"], "0.12em")
        for key in ("gutter", "section-gap", "block-gap", "tight-gap",
                    "table-cell"):
            self.assertIn(key, data["panel"])

    def test_no_arbitrary_type_or_tracking_in_the_panel_surface(self):
        for path in SURFACE_FILES:
            with self.subTest(path=rel(path)):
                src = strip_js_comments(read(path))
                self.assertNotRegex(src, r"tracking-\[",
                                    "arbitrary harf aralığı — rol token'ı kullan")
                self.assertNotRegex(src, r"text-\[\d+px\]",
                                    "arbitrary punto — ölçek token'ı kullan")
                self.assertNotIn("font-serif", src,
                                 "Tailwind serif yığını — font-verdict kullan")
                self.assertNotIn("text-5xl", src,
                                 "ölçek dışı punto — text-display kullan")

    def test_verdict_uses_the_display_and_verdict_voices(self):
        src = read(PANEL_STYLE)
        self.assertIn("font-verdict", src)
        self.assertIn("text-display", src)
        self.assertIn("leading-display", src)

    def test_pages_use_the_section_rhythm_role(self):
        for path in (PANEL_PAGE, PANEL_LAYOUT, TREND_PAGE, LAYERS_PAGE):
            with self.subTest(path=rel(path)):
                src = read(path)
                self.assertIn("panelStack()", src,
                              "kartlar arası ritim rolü kullanılmıyor")
                self.assertNotIn("space-y-6", src,
                                 "sayısal aralık rolü baypas ediyor")

    def test_root_font_comes_from_the_token_sheet(self):
        src = strip_js_comments(read(LAYOUT))
        self.assertNotIn("next/font", src,
                         "ikinci font kaynağı (design-system --font-sans)")
        self.assertNotIn("Geist", src)

    def test_card_and_table_share_the_cell_gutter(self):
        style = read(PANEL_STYLE)
        head = re.search(
            r'export const tableHead = cn\(\s*microLabel\(\),\s*"([^"]*)"',
            style,
        )
        self.assertIsNotNone(head, "tableHead reçetesi bulunamadı")
        self.assertIn("p-(--panel-table-cell)", head.group(1))
        self.assertIn("h-auto", head.group(1),
                      "shadcn h-10 sabiti gövde satırıyla oynuyor")

        bleed = re.search(
            r'export const panelTableBleed = cva\(\s*"([^"]*)"', style)
        self.assertIsNotNone(bleed, "panelTableBleed reçetesi bulunamadı")
        self.assertIn("calc(var(--card-padding)*-1)", bleed.group(1),
                      "tablo kart dolgusunun dışına taşmalı")

        for path in (RUNS_TABLE, RUN_COMPARE, REFS_CHART):
            with self.subTest(path=rel(path)):
                src = read(path)
                self.assertIn("tableCell(", src, "ortak hücre reçetesi yok")
                self.assertIn("<PanelTable>", src, "ortak tablo kabı yok")


# ── 11. Next 16 View Transition kablosu (gezinme haritası sözleşmesi) ──────

class ViewTransitionTest(unittest.TestCase):
    """Next 16 yükseltmesiyle rayına oturan ertelenmiş VT desenleri
    (findings.md §"vercel-react-view-transitions tour"): yanal geçiş
    YALIN crossfade'dir (transitionTypes YASAK — sahte mekânsal derinlik),
    header uzamsal çapadır, panel slotları Suspense reveal yapar.

    Prodüksiyon-derleme kuralı: VT kablosu KAYNAKTA aranır; canlı kanıt
    `next start` (production build) ister — `next dev` VT'yi desteklemez,
    o yüzden dev-sunucu kanıtı ASLA ölçüt olamaz.
    """

    @classmethod
    def setUpClass(cls):
        cls.css = read(GLOBALS_CSS)
        cls.panel_page = read(APP / "(panel)" / "page.tsx")
        cls.trend_page = read(APP / "trend" / "page.tsx")
        cls.verdict_slot = read(APP / "(panel)" / "@verdict" / "page.tsx")
        cls.trend_slot = read(APP / "(panel)" / "@trend" / "page.tsx")
        cls.layout = read(LAYOUT)

    def test_panel_page_wraps_content_in_view_transition(self):
        tags = [t for t in jsx_tags(self.panel_page) if t["name"] == "ViewTransition"]
        self.assertEqual(len(tags), 1,
                         "panel sayfası tek ViewTransition sarmalayıcısı bekler")

    def test_trend_page_wraps_content_in_view_transition(self):
        tags = [t for t in jsx_tags(self.trend_page) if t["name"] == "ViewTransition"]
        self.assertEqual(len(tags), 1,
                         "/trend sayfası tek ViewTransition sarmalayıcısı bekler")

    def test_no_directional_transition_types_anywhere(self):
        # Gezinme haritası YASAĞI: / <-> /trend yanal geçişi yön taşıyamaz.
        # Tarama YALNIZ JSX etiket özniteliklerinde (Link + ViewTransition):
        # dosya metni, yasağı ANLATAN yorumu da taşır — onu saymak
        # yanlış-pozitif üretirdi (ölçüldü: ilk sürüm tam olarak buna
        # yakalandı; tarayıcı iddianın ne kadar spesifik olduğunu kanıtladı).
        for name, src in (("panel page", self.panel_page),
                          ("trend page", self.trend_page),
                          ("verdict slot", self.verdict_slot),
                          ("trend slot", self.trend_slot)):
            attrs = " ".join(t["attrs"] for t in jsx_tags(src))
            self.assertNotIn("transitionTypes", attrs,
                             "%s: transitionTypes yasak (yönsüz geçiş)" % name)
            self.assertNotIn("nav-forward", attrs, "%s: yön tipi yasak" % name)
            self.assertNotIn("nav-back", attrs, "%s: yön tipi yasak" % name)

    def test_imported_from_react_not_a_shim(self):
        # Guide: ViewTransition doğrudan `react`ten gelir (Next 16 App Router
        # kanal vendor eder). Shim ya da react-experimental import'u
        # sürüklenme olur (kanal çabuk bayatlar).
        for name, src in (("panel page", self.panel_page),
                          ("trend page", self.trend_page)):
            self.assertIn('import { ViewTransition } from "react";', src,
                          "%s: import kaynağı `react` olmalı" % name)
        self.assertNotIn("react-experimental", self.panel_page + self.trend_page)

    def test_header_has_view_transition_name(self):
        self.assertIn('viewTransitionName: "site-header"', self.layout,
                      "header VT adı yok — uzamsal çapa kurulamadı")

    def test_header_anchor_css_rules(self):
        for rule in ("::view-transition-group(site-header)",
                     "::view-transition-old(site-header)",
                     "::view-transition-new(site-header)"):
            self.assertIn(rule, self.css,
                          "header çapa kuralı yok: %s" % rule)
        group = next(b for p, b in css_blocks(self.css)
                     if p == "::view-transition-group(site-header)")
        self.assertIn("animation: none", group)
        self.assertIn("z-index: 100", group)
        old = next(b for p, b in css_blocks(self.css)
                   if p == "::view-transition-old(site-header)")
        self.assertIn("display: none", old, "eski header snapshot'ı gizlenmeli")

    def test_crossfade_css_is_undirected(self):
        # YALIN crossfade: süre/timing tanımı vardır; YÖN anahtarı (nav-*)
        # ve yatay kaydırma YOKTUR (harita yasağı).
        self.assertIn("::view-transition-old(root)", self.css)
        self.assertIn("::view-transition-new(root)", self.css)
        self.assertNotIn("nav-forward", self.css)
        self.assertNotIn("nav-back", self.css)
        self.assertNotIn("translateX", self.css,
                         "yanal geçişte yatay kaydırma olmamalı")

    def test_pointer_events_guard_present(self):
        # Geçiş overlay'i tıklamaları yutmamalı (guide: interactive page).
        block = next(b for p, b in css_blocks(self.css)
                     if p == "::view-transition")
        self.assertIn("pointer-events: none", block)

    def test_slot_suspense_reveal_pair(self):
        # Her iki panel slotu da slot-exit (hızlı çıkış) + slot-enter
        # (gecikmeli giriş) sınıflarını kullanır; sınıf adları CSS ile eşleşir.
        for name, src in (("verdict slot", self.verdict_slot),
                          ("trend slot", self.trend_slot)):
            self.assertIn('"slot-exit": "slot-exit"', src,
                          "%s: exit sınıfı eksik" % name)
            self.assertIn('"slot-enter": "slot-enter"', src,
                          "%s: enter sınıfı eksik" % name)
            self.assertIn('default: "none"', src,
                          "%s: default none yok — geçiş crossfade'ine sızar" % name)
        for pseudo in ("::view-transition-old(.slot-exit)",
                       "::view-transition-new(.slot-enter)"):
            self.assertIn(pseudo, self.css, "reveal kuralı yok: %s" % pseudo)

    def test_slot_transition_isolated_from_navigation(self):
        # default:none YALNIZ slot sarmalayıcısında: panel sayfası/trend
        # sayfası YALIN sarmalayıcıdır (navigasyonda crossfade ateşlenir).
        for name, src in (("panel page", self.panel_page),
                          ("trend page", self.trend_page)):
            tag = next(t for t in jsx_tags(src) if t["name"] == "ViewTransition")
            self.assertNotIn("default", tag["attrs"],
                             "%s: yalın sarmalayıcı default:none taşımalı değil" % name)


# ── süit kaydı (isim/refactor drift'i) ─────────────────────────────────────

class WiringTest(unittest.TestCase):
    def test_module_is_in_the_battery(self):
        listed = [
            ln.strip() for ln in read(MANIFEST).splitlines() if ln.strip()
        ]
        self.assertIn(THIS_FILE, listed)

    def test_hook_coverage_maps_unit_tests(self):
        import sys

        sys.path.insert(0, str(HERE))
        import test_coverage_report as cov

        self.assertIn(THIS_FILE, cov.HOOK_COVERAGE["check-unit-tests"])

    def test_smoke_rename_is_consistent_everywhere(self):
        """Yüzey smoke'u (eski adı `..._light_theme.py`) kapsamı genişleyince
        yeniden adlandırıldı: EXCLUDE + CHECK_EXEMPT aynı adı taşımalı; eski
        ad hiçbir yerde kalmamalı (tek kaynak ilkesi — yarısı güncellenmiş
        referans sessiz bir boşluk bırakırdı).

        `verify.yml` BİLEREK kapsam dışı: workflow bu süiti hiçbir adımda
        adıyla anmıyor (`git log -S` ile doğrulandı), yani dosya adının orada
        bulunmasını beklemek var olmayan bir kablolamayı iddia etmek olurdu.
        `CI_JOB_COVERAGE["dashboard-next"]` kaydı ayrı bir sözleşme
        tartışmasıdır (kayıt var, job yok → fail-open ailesi)."""
        for path in (HERE / "sync_check_unit_tests.py",
                     HERE / "test_coverage_report.py"):
            src = read(path)
            self.assertIn(SMOKE_FILE, src, "%s: yeni ad yok" % rel(path))
            self.assertNotIn(OLD_SMOKE_NAME, src,
                             "%s: eski ad kaldı" % rel(path))

    def test_smoke_suite_is_not_in_the_battery(self):
        """Next boot'u pre-commit bütçesine sığmaz: EXCLUDE'da kalmalı."""
        src = read(HERE / "sync_check_unit_tests.py")
        self.assertIn(SMOKE_FILE, src)
        listed = [
            ln.strip() for ln in read(MANIFEST).splitlines() if ln.strip()
        ]
        self.assertNotIn(SMOKE_FILE, listed)


if __name__ == "__main__":
    unittest.main()
