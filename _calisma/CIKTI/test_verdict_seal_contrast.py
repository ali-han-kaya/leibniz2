#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_verdict_seal_contrast.py — verdict mühürünün kontrast sözleşmesi (WCAG 1.4.3).

NEDEN BU KAPI VAR (ölçüm, 2026-10-12):
axe-core 4.10.3 mührün metin düğümlerini KARARA BAĞLAYAMIYOR. Kapının
kendi koşumunda (a11y_gate.py, /preview.html, iki tema) color-contrast
sonucu `incomplete` olarak raporlanıyor ve kaydedilen gerekçe şu:

    halka (textPath)            -> elmPartiallyObscuring
    .seal-verdict / .seal-hash  -> bgOverlap
    (hepsinde fgColor/bgColor=null, contrastRatio=0)

a11y_gate_config.json'da `incomplete: "report-only"` olduğu için bu üç
düğüm hiçbir verdict'i etkilemiyor. Sonuç: mühür mürekkebi kâğıdın
rengine çekilse bile kapı PASS veriyor. Mutasyonla ölçüldü — mürekkep
`--paper`'a eşitlendiğinde (ring 1.16:1, hash 1.21:1, verdict 3.77:1,
yani pratikte görünmez) axe yine yalnız `incomplete` üretiyor ve HEAD
kapısı iki config'de de PASS kaldı. Mührün kontrastını ölçen başka bir
kapı yoktu; bu test o boşluğu statik olarak kapatır (tarayıcı gerekmez,
bu yüzden tarayıcısız bataryada da kırmızıya dönebilir).

GİRDİNİN TAMAMI SAYFANIN KENDİ CSS'İNDEN ÇÖZÜLÜR:
  * mühür `.sheet` İÇİNDE durur, palet orada SABİTLENİR
    (--muted #655e56, --ok #1f6b33, --err #a9271c, --fg-dimmed #56504a),
    yani tema değişse de mühür kâğıt üzerinde kalır;
  * mürekkep: .seal-ring / .seal-verdict / .seal-hash `fill` değeri
    (durum sınıfları --pass/--fail ile birlikte, base kural ezilir);
  * yüzey: `--paper` (tokens.css; koyu #f4efe5, açık #fffdf8) üzerine
    `.seal-circle` dolgusunun (rgba tint) bileşkesi.

MODEL PİKSELLE ÇAPRAZ DOĞRULANDI (4x DPR ekran, canlı dashboard +
kapı koşumu, 2026-10-12). Statik modelin matrisi: koyu tema 5.10–6.63,
açık tema 5.71–7.43; en dar 5.10:1 (FAIL/ring, koyu). Pikselden okunan
en kötü gerçek durum ise 4.93:1 (aynı hücre) — yani model antialias, iç
halka konturu ve drop-shadow'u saymadığı için ~0.2 İYİMSER. Marj bu
yüzden 0.43'tür (4.93 vs AA 4.5): mürekkep ya da kâğıt oynarsa bu kapı
yeşil kalırken boyanan sonuç AA'nın altına inebilir. Kapı yine de
anlamlıdır (1.16:1'lik mühür burada kırmızı), ama "ölçüm" tarafının
kaydı yukarıdaki piksel sayılarıdır.

KAPSAM SINIRI (bilerek, fail-closed): model "opak kâğıt + tek
yarısaydam tint" varsayar. Çözülemeyen her renk (hsl()/color-mix()/
isimli renk/tanımsız ya da fallback'li var()) kapıyı KIRAR — sessiz
PASS yok. preview.js mührü yalnız sınıf ve metin üzerinden boyamalı;
inline fill/stil yazarsa bu model yalan söylemeye başlar, o yüzden
test o kanalı da kilitler.
"""

import pathlib
import re
import unittest

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent.parent
PREVIEW_HTML = HERE / "preview.html"
PREVIEW_JS = HERE / "preview.js"
TOKENS = REPO / "design-system" / "tokens.css"

AA_NORMAL = 4.5

# Mührü tema-bağımsız yapan sabitlemeler: .sheet bu token'ları yeniden
# tanımlar, mühür de yalnız bunları tüketir.
SHEET_PINS = ("--muted", "--ok", "--err", "--fg-dimmed")
INK_ROLES = (".seal-ring", ".seal-verdict", ".seal-hash")
THEMES = (("koyu", ":root"), ("acik", ':root[data-theme="light"]'))


class Unresolved(Exception):
    """Çözülemeyen renk/stil — kapı bunu PASS'a çevirmez (fail-closed)."""


def _strip_comments(css):
    """CSS yorumları kural denetimini kirletir: canlı kural değiller."""
    return re.sub(r"/\*.*?\*/", " ", css, flags=re.S)


def _rule_body(css, selector):
    """`selector { ... }` gövdesi (yoksa None). `.sheet-body` gibi daha uzun
    seçiciler eşleşmez: kural `{` ile bitmeli."""
    m = re.search(re.escape(selector) + r"\s*\{([^}]*)\}", css)
    return m.group(1) if m else None


def _declarations(body):
    out = {}
    for prop, value in re.findall(r"([a-z-]+)\s*:\s*([^;]+)", body or ""):
        out[prop.strip()] = value.strip()
    return out


def _theme_vars(css, selector):
    m = re.search(r"(?m)^" + re.escape(selector) + r"\s*\{([^}]*)\}", css)
    if not m:
        raise Unresolved("%s bloğu tokens.css içinde yok" % selector)
    return dict(re.findall(r"(--[a-z0-9-]+)\s*:\s*(#[0-9a-fA-F]{3,8})",
                           m.group(1)))


def _colour(value, scope):
    """CSS renk değerini (r, g, b, a) dörtlüsüne çözer.

    Tanımadığı her sözdizimini Unresolved ile reddeder: model yalnız
    opak hex/rgb ve düz `var(--token)` çözebilir, gerisi sessizce
    yanlış hesaba dönüşmemelidir.
    """
    text = value.strip()
    m = re.fullmatch(r"var\((--[a-z0-9-]+)\)", text)
    if m:
        name = m.group(1)
        if name not in scope:
            raise Unresolved("%s kapsamda tanımsız" % text)
        return _colour(scope[name], scope)
    if "var(" in text:
        raise Unresolved("%s iç içe/fallback'li var() — kapı çözemez" % text)
    m = re.fullmatch(r"#([0-9a-fA-F]{3})", text)
    if m:
        return tuple(int(c * 2, 16) for c in m.group(1)) + (1.0,)
    m = re.fullmatch(r"#([0-9a-fA-F]{6})", text)
    if m:
        h = m.group(1)
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4)) + (1.0,)
    m = re.fullmatch(
        r"rgba?\(\s*([0-9.]+)\s*,\s*([0-9.]+)\s*,\s*([0-9.]+)"
        r"\s*(?:,\s*([0-9.]+)\s*)?\)", text)
    if m:
        r, g, b, a = m.groups()
        return (float(r), float(g), float(b), float(a) if a else 1.0)
    raise Unresolved("%s çözülemedi — kapı bu renk sözdizimini tanımıyor" % text)


def _over(src, dst):
    """Yarısaydam `src` katmanını opak `dst` üzerine bindirir."""
    sa = src[3]
    return tuple(sa * src[i] + (1.0 - sa) * dst[i] for i in range(3))


def _channel(value):
    value /= 255.0
    return value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4


def relative_luminance(rgb):
    r, g, b = rgb[:3]
    return 0.2126 * _channel(r) + 0.7152 * _channel(g) + 0.0722 * _channel(b)


def contrast_ratio(fg, bg):
    la, lb = relative_luminance(fg), relative_luminance(bg)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def _hex(rgb):
    return "#%02x%02x%02x" % tuple(int(round(c)) for c in rgb[:3])


def _function_body(source, name):
    """`function <name>(...) { ... }` gövdesini süslü parantez sayarak döndürür."""
    start = source.find("function %s(" % name)
    if start < 0:
        raise Unresolved("preview.js içinde function %s bulunamadı" % name)
    depth = 0
    for i in range(start, len(source)):
        if source[i] == "{":
            depth += 1
        elif source[i] == "}":
            depth -= 1
            if depth == 0:
                return source[start:i + 1]
    raise Unresolved("%s gövdesi kapanmadı" % name)


class VerdictSealContrast(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = PREVIEW_HTML.read_text(encoding="utf-8")
        cls.css = _strip_comments(cls.source)
        body = _rule_body(cls.css, ".sheet")
        if body is None:
            raise Unresolved("preview.html'de .sheet kuralı yok")
        cls.sheet = _declarations(body)
        cls.tokens = TOKENS.read_text(encoding="utf-8")

    # ------------------------------------------------------------- çözümleme
    def _scope(self, theme, overrides=None):
        """Tema kökü + .sheet sabitlemeleri (sheet kazanır)."""
        scope = dict(_theme_vars(self.tokens, dict(THEMES)[theme]))
        scope.update(self.sheet)
        if overrides:
            scope.update(overrides)
        return scope

    def _prop(self, selector, state, prop):
        decls = _declarations(_rule_body(self.css, selector))
        if state:
            override = _rule_body(self.css, ".seal-%s %s" % (state, selector))
            decls.update(_declarations(override))
        if prop not in decls:
            raise Unresolved("%s (durum=%s) kuralında %s yok" %
                             (selector, state, prop))
        return decls[prop]

    def _surface(self, theme, state, overrides=None):
        scope = self._scope(theme, overrides)
        paper = _colour(scope["--paper"], scope)
        if paper[3] != 1.0:
            raise Unresolved("--paper opak olmalı; saydam kâğıt modeli yok")
        tint = _colour(self._prop(".seal-circle", state, "fill"), scope)
        return _over(tint, paper)

    def _ratio(self, theme, state, selector, overrides=None):
        scope = self._scope(theme, overrides)
        ink = _colour(self._prop(selector, state, "fill"), scope)
        surface = self._surface(theme, state, overrides)
        return contrast_ratio(ink, surface), ink, surface

    def _worst(self, overrides=None):
        worst = None
        for theme, _ in THEMES:
            for state in (None, "pass", "fail"):
                for selector in INK_ROLES:
                    ratio, ink, surface = self._ratio(
                        theme, state, selector, overrides)
                    if worst is None or ratio < worst[0]:
                        worst = (ratio, theme, state, selector, ink, surface)
        return worst

    # ------------------------------------------------------------ yapı sabiti
    def test_sheet_pins_the_palette_the_seal_inherits(self):
        """.sheet sabitlemeleri duruyor mu (mührü tema-bağımsız yapan şey)."""
        for token in SHEET_PINS:
            self.assertIn(
                token, self.sheet,
                ".sheet artık %s tanımlamıyor — mühür tema token'larını "
                "miras alır ve kâğıt üstündeki ölçüm geçersizleşir" % token,
            )

    def test_seal_lives_inside_the_sheet(self):
        """Mühür .sheet içinde olmalı: palet orada sabitleniyor."""
        start = self.source.find('<section class="sheet"')
        self.assertGreaterEqual(start, 0, ".sheet bölümü bulunamadı")
        depth, end = 0, -1
        i = start
        while i < len(self.source):
            if self.source.startswith("</section", i):
                depth -= 1
                if depth == 0:
                    end = i
                    break
            elif self.source.startswith("<section", i):
                depth += 1
            i += 1
        self.assertGreater(end, start, ".sheet bölümü kapanmadı")
        seal = self.source.find('id="verdict-seal"')
        self.assertTrue(
            start < seal < end,
            "verdict-seal artık .sheet dışında — sabitlenmiş palet değil, "
            "tema token'ları geçerli olur; bu testin ölçümü geçersiz",
        )

    def test_markup_carries_the_three_ink_roles(self):
        """Ölçülen üç mürekkep düğümü sayfada gerçekten var mı."""
        for selector in INK_ROLES:
            self.assertIn(
                'class="%s"' % selector.lstrip("."), self.source,
                "%s işaretlemesi yok — kapı var olmayan düğümü ölçüyor olurdu"
                % selector,
            )

    # ------------------------------------------------------------- oranlar
    def test_ring_ink_clears_aa_in_both_themes(self):
        """Halka mürekkebi (--muted) her iki temada AA'yı geçmeli."""
        for theme, _ in THEMES:
            ratio, ink, surface = self._ratio(theme, None, ".seal-ring")
            self.assertGreaterEqual(
                ratio, AA_NORMAL,
                "%s tema: halka mürekkebi %s, kâğıt+tint %s üzerinde yalnızca "
                "%.2f:1" % (theme, _hex(ink), _hex(surface), ratio),
            )

    def test_verdict_ink_clears_aa_in_every_state(self):
        """Verdict mürekkebi PASS (--ok) ve FAIL (--err) durumunda geçmeli."""
        for theme, _ in THEMES:
            for state in ("pass", "fail"):
                ratio, ink, surface = self._ratio(theme, state, ".seal-verdict")
                self.assertGreaterEqual(
                    ratio, AA_NORMAL,
                    "%s tema/%s: verdict mürekkebi %s, kâğıt+tint %s üzerinde "
                    "yalnızca %.2f:1 — AA %s:1 gerekiyor" %
                    (theme, state, _hex(ink), _hex(surface), ratio, AA_NORMAL),
                )

    def test_undecided_verdict_ink_clears_aa(self):
        """Kararsız durumda da (.seal-pass/.seal-fail yok) mürekkep okunmalı."""
        for theme, _ in THEMES:
            ratio, ink, surface = self._ratio(theme, None, ".seal-verdict")
            self.assertGreaterEqual(
                ratio, AA_NORMAL,
                "%s tema/kararsız: verdict mürekkebi %s, kâğıt+tint %s üzerinde "
                "yalnızca %.2f:1" % (theme, _hex(ink), _hex(surface), ratio),
            )

    def test_hash_ink_clears_aa_in_both_themes(self):
        """Kısa hash mürekkebi (--fg-dimmed) her iki temada geçmeli."""
        for theme, _ in THEMES:
            ratio, ink, surface = self._ratio(theme, None, ".seal-hash")
            self.assertGreaterEqual(
                ratio, AA_NORMAL,
                "%s tema: hash mürekkebi %s, kâğıt+tint %s üzerinde yalnızca "
                "%.2f:1" % (theme, _hex(ink), _hex(surface), ratio),
            )

    def test_worst_case_seal_ratio_is_recorded_and_passing(self):
        """En kötü durum AA'yı geçmeli ve ölçülen değer raporlanır."""
        worst = self._worst()
        ratio, theme, state, selector, ink, surface = worst
        self.assertGreaterEqual(
            ratio, AA_NORMAL,
            "en kötü mühür oranı %s/%s/%s: %.2f:1 (mürekkep %s, yüzey %s)" %
            (theme, state, selector, ratio, _hex(ink), _hex(surface)),
        )

    # -------------------------------------------------------- mutasyon kanıtı
    def test_mutation_sheet_pin_removal_is_caught(self):
        """MUTASYON #1: .sheet sabitlemesi kalkarsa koyu tema token'ı sızar.

        Sabitleme silinirse mühür `--ok`/`--muted` olarak koyu temanın
        parlak değerlerini alır (#3fb950 / #8b949e) ve kâğıt üstünde
        2.2–2.6:1'e düşer. Yani bu kapı "paletin sabitlenmiş olması"
        olgusunu da ölçüyor; sabitleme kaldırılırsa kırmızıya döner.
        """
        dark = _theme_vars(self.tokens, ":root")
        for token in ("--ok", "--muted"):
            leaks = {token: dark[token]}
            worst = self._worst(overrides=leaks)
            self.assertLess(
                worst[0], AA_NORMAL,
                "koyu tema %s=%s kâğıt üstünde %.2f:1 veriyor — sabitleme "
                "kaldırıldığında kapı kırmızıya dönmüyor demektir" %
                (token, dark[token], worst[0]),
            )

    def test_mutation_paper_ink_is_caught(self):
        """MUTASYON #2: mürekkep kâğıda eşitlenirse (ölçülen 1.16–3.77:1).

        Bu, doğrulamada elle üretilen mutasyonun ta kendisi: mühür
        görünmez olur ama axe yalnız `incomplete` der, yani bu test
        olmasa hiçbir kapı kırmızıya dönmez.
        """
        paper = self._scope("koyu")["--paper"]
        for token in ("--ok", "--err", "--muted", "--fg-dimmed"):
            worst = self._worst(overrides={token: paper})
            self.assertLess(
                worst[0], AA_NORMAL,
                "%s=%s (kâğıdın kendi rengi) hâlâ AA geçiyor görünüyor "
                "(%.2f:1) — kontrast formülü ya da yüzey modeli bozulmuş" %
                (token, paper, worst[0]),
            )

    # ------------------------------------------------------------- fail-closed
    def test_unresolvable_colour_is_rejected(self):
        """Modelin çözemediği renk sözdizimi sessizce geçmemeli."""
        for bad in ("hsl(210 50% 50%)", "color-mix(in srgb, #fff, #000)",
                    "papayawhip", "currentColor", "var(--yok)",
                    "var(--paper, #fff)"):
            with self.assertRaises(Unresolved, msg=bad):
                _colour(bad, {"--paper": "#f4efe5"})

    def test_transparent_paper_is_rejected(self):
        """Yüzey modeli saydam kâğıt kabul etmez (arka plan belirsizleşir)."""
        with self.assertRaises(Unresolved):
            self._surface(
                "koyu", "pass", overrides={"--paper": "rgba(244,239,229,0.5)"})

    def test_preview_js_does_not_paint_the_seal_inline(self):
        """Mührü JS inline stille boyarsa statik model yalan söyler."""
        body = _function_body(PREVIEW_JS.read_text(encoding="utf-8"),
                              "renderVerdictSeal")
        for pattern in (r"\.style\.", r"setAttribute\(\s*['\"](?:fill|style)",
                        r"cssText"):
            self.assertIsNone(
                re.search(pattern, body),
                "renderVerdictSeal artık %s kullanıyor — mühür rengi CSS'in "
                "dışından geliyor olabilir; bu kapı onu göremez" % pattern,
            )


if __name__ == "__main__":
    unittest.main()
