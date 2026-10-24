#!/usr/bin/env python3
"""test_design_token_contrast.py — design token kontrast sozlesmesi (WCAG 1.4.3).

NEDEN BU KAPI VAR (olcum, 2026-10-02):
a11y_gate.py yalnizca VARSAYILAN (koyu) temayi tarar; light temada
tarama yapilmaz. Ayni kapinin main kosumunda (run37035461060, job
110932448513) `h1` ve `#live-status` icin

    [INCOMPLETE] color-contrast (impact: serious) nodes=2
    messageKey: bgGradient — "background color could not be determined
    due to a background gradient"

raporladi. Bu bir INCOMPLETE'dir, ihlal degil: axe header'daki
`linear-gradient(180deg, --header-start, --header-end)` uzerinde efektif
arka plan rengini cozemedigi icin karar veremez. Allowlist bunu COZMEZ —
a11y_gate.py allowlist'i yalniz `violations`a uygular, `incomplete`
girdileri dosyada aynen yazilir (bkz. a11y_gate.py: incomplete dongusu
_allowlisted_nodes'i cagrrmaz).

Bu yuzden iki node elle OLCULDU (WCAG relative luminance, her iki gradyan
ucuna karsi = en kotu durum):

    node            koyu en-kotu   acik en-kotu (eski #70695f)
    h1              14.64:1        11.94:1     -> gecerli
    #live-status     5.62:1         4.34:1     -> KALDI  (11px, normal metin)

Yani raporlanan bulgunun KENDISI yanlis-pozitiftir, ama ayni ogenin
acik temada GERCEK bir kontrast hatasi vardir ve kapı bunu gormez.
Ek olarak `--muted`, `--surface-raised`/`--code-bg` (#e9e1d3) uzerinde
4.17:1 idi — yani hata header ile sinirli degildi.

Bu test o olcumu kalici kilitler: her iki temada `--muted` butun yuzey
token'larina karsi WCAG AA 4.5:1'i gecmeli. Deger koyulastirilirsa
(--muted #70695f -> #655e56) ve test mutasyonla kanitlidir.

Kapsam disi bilerek: `--accent`, `--ok`, `--warn`, `--err` gibi durum
renkleri kendi `--*-bg` yuzeyleriyle degerlendirilir; bu sozlesme yalniz
metin token'larini (`--muted`, `--fg`, `--fg-dimmed`) kapsar.
"""
import pathlib
import re
import unittest

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent.parent
TOKENS = REPO / "design-system" / "tokens.css"
TAILWIND = REPO / "design-system" / "tailwind.css"

# Metin token'lari hangi yuzeylerin UZERINDE durabilir?
#
# DIKKAT: `--paper` bilerek UI metin listesi DIŞINDA. Koyu temada `--paper`
# ACIK bir yuzeydir (#f4efe5) ve kendi eşleşen yazı rengi `--paper-ink`
# ile kullanilir; `--fg` (açık UI metni) onun üstünde anlamsızdır ve
# 1.03:1 verir. Bu eşleştirme ilk yazım denemesinde ölçülerek bulundu —
# blanket "her metin × her yuzey" modeli yanlış çiftler üretiyordu.
UI_BACKGROUNDS = (
    "--bg",
    "--surface",
    "--surface-raised",
    "--header-start",
    "--header-end",
    "--code-bg",
)
UI_TEXT_TOKENS = ("--fg", "--muted", "--fg-dimmed")
AA_NORMAL = 4.5

# Duzeltme oncesi deger — mutasyon kaniti icin.
PRE_FIX_LIGHT_MUTED = "#70695f"


def _channel(value: float) -> float:
    value /= 255.0
    return value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4


def relative_luminance(hex_color: str) -> float:
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return 0.2126 * _channel(r) + 0.7152 * _channel(g) + 0.0722 * _channel(b)


def contrast_ratio(fg: str, bg: str) -> float:
    la, lb = relative_luminance(fg), relative_luminance(bg)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def _theme_vars(css: str, selector: str) -> dict:
    """Bir tema blogundaki `--token: #hex;` ciftlerini dondurur.

    `selector` ÇIPLAK olmalı (`":root"`, `':root[data-theme="light"]'`) —
    blok parantezi regex'in işi. Satır-ankarlı arama, koyu blogun light
    blogunun icinde yanlislıkla bulunmasini engeller.
    """
    m = re.search(r"(?m)^" + re.escape(selector) + r"\s*\{([^}]*)\}", css)
    assert m, f"{selector} blogu tokens.css icinde yok"
    out = {}
    for name, value in re.findall(r"(--[a-z0-9-]+)\s*:\s*(#[0-9a-fA-F]{3,8})", m.group(1)):
        out[name] = value
    return out


def _read(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


class DesignTokenContrast(unittest.TestCase):
    def _worst_case(self, text_tokens, bg_tokens, theme: str, vars_: dict) -> tuple:
        worst = (float("inf"), None, None, None)
        for fg_name in text_tokens:
            fg = vars_.get(fg_name)
            assert fg, f"{theme}: {fg_name} tanimsiz"
            for bg_name in bg_tokens:
                bg = vars_.get(bg_name)
                assert bg, f"{theme}: {bg_name} tanimsiz"
                ratio = contrast_ratio(fg, bg)
                if ratio < worst[0]:
                    worst = (ratio, fg_name, bg_name, fg)
        return worst

    def _assert_theme_ok(self, text_tokens, bg_tokens, theme, selector, css):
        vars_ = _theme_vars(css, selector)
        ratio, fg_name, bg_name, fg = self._worst_case(
            text_tokens, bg_tokens, theme, vars_
        )
        self.assertGreaterEqual(
            ratio, AA_NORMAL,
            f"{theme}/{fg_name}={fg} uzerinde {bg_name}={vars_[bg_name]} "
            f"yalnizca {ratio:.2f}:1 — WCAG AA {AA_NORMAL}:1 gerekiyor",
        )
        return ratio

    def test_dark_theme_text_clears_aa(self):
        """Koyu tema (a11y_gate.py'nin taradigi tema) AA'yi gecmeli."""
        ratio = self._assert_theme_ok(
            UI_TEXT_TOKENS, UI_BACKGROUNDS, "koyu", ":root", _read(TOKENS)
        )
        self.assertGreaterEqual(ratio, AA_NORMAL)

    def test_light_theme_text_clears_aa(self):
        """Acik tema de AA'yi gecmeli — kapı bunu TARAMIYOR, test ediyor."""
        ratio = self._assert_theme_ok(
            UI_TEXT_TOKENS, UI_BACKGROUNDS,
            "acik", ':root[data-theme="light"]', _read(TOKENS),
        )
        self.assertGreaterEqual(ratio, AA_NORMAL)

    def test_paper_ink_clears_aa_on_paper(self):
        """--paper kendi eslesen yazı rengiyle degerlendirilir (her iki tema).

        `--paper` koyu temada acik bir yuzey (#f4efe5); dogru cift
        `--paper-ink` (#2b2926) onun uzerinde durur.
        """
        css = _read(TOKENS)
        for theme, selector in (("koyu", ":root"),
                                ("acik", ':root[data-theme="light"]')):
            vars_ = _theme_vars(css, selector)
            ratio = contrast_ratio(vars_["--paper-ink"], vars_["--paper"])
            self.assertGreaterEqual(
                ratio, AA_NORMAL,
                f"{theme}: --paper-ink={vars_['--paper-ink']} uzerinde "
                f"--paper={vars_['--paper']} yalnizca {ratio:.2f}:1",
            )

    def test_header_gradient_text_clears_aa_at_both_ends(self):
        """Gradyan uclarinin IKISINE karsi gecmeli (en kotu durum)."""
        for theme, selector in (("koyu", ":root"),
                                ("acik", ':root[data-theme="light"]')):
            vars_ = _theme_vars(_read(TOKENS), selector)
            for fg_name in ("--fg", "--muted"):
                for end in ("--header-start", "--header-end"):
                    ratio = contrast_ratio(vars_[fg_name], vars_[end])
                    self.assertGreaterEqual(
                        ratio, AA_NORMAL,
                        f"{theme}/{fg_name} uzerinde {end}: {ratio:.2f}:1",
                    )

    def test_pre_fix_value_is_rejected(self):
        """MUTASYON KANITI: duzeltme oncesi deger ayni sozlesmeyi kirar.

        Deger yeniden açilirsa (koyu temaya dekir), bu test kirmiziya döner;
        yani "yesil" bir allowlist/rapor degil, olcumle kilitlenmis bir
        sozlesmedir.
        """
        light = _theme_vars(_read(TOKENS), ':root[data-theme="light"]')
        old = dict(light)
        old["--muted"] = PRE_FIX_LIGHT_MUTED
        ratio, fg_name, bg_name, _ = self._worst_case(
            ("--muted",), UI_BACKGROUNDS, "acik(eski deger)", old
        )
        self.assertLess(
            ratio, AA_NORMAL,
            f"{PRE_FIX_LIGHT_MUTED} artik AA geciyor gibi duruyor ({ratio:.2f}:1) "
            f"— ya kontrast formulu ya da yuzey listesi degismis olabilir; "
            f"duzeltme gerekcesini tazele",
        )

    def test_tailwind_bridge_mirrors_light_muted(self):
        """tailwind.css :root, tokens.css :root ile birebir esit olmali.

        check_tokens.py kural 6 bunu zaten bloklar; bu test, iki dosya
        ayri ayri duzeltilirse (ya da biri unutulursa) hangi degerin
        gecersiz kaldigini gosterir.
        """
        css = _read(TOKENS)
        bridge = _read(TAILWIND)
        light = _theme_vars(css, ':root[data-theme="light"]')
        bridge_light = _theme_vars(bridge, ':root[data-theme="light"]')
        self.assertEqual(
            light["--muted"], bridge_light["--muted"],
            "tailwind.css ve tokens.css --muted degerleri ayrismis",
        )


if __name__ == "__main__":
    unittest.main()