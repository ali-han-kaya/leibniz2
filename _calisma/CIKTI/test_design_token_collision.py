#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tasarım tokenı sözleşmesi: bir semantik token çelişemez.

Ölçülen durum (2026-10-04, tailwind-design-system turu): Tailwind v4'te
token'lar iki ayrı `@theme` bloğunda yeniden açığa çıkarılıyor:

  1. design-system/tailwind.css      — GENERATED köprü (tokens.json →
     tokens.css → generate_tailwind.py). 30 `--color-*` adı, hex palet.
  2. apps/dashboard-next/app/globals.css — shadcn namespace, `@theme inline`.
     31 `--color-*` adı, OKLCH palet.

`--color-accent`, `--color-border` ve `--color-muted` İKİSİNDE de geçiyor.

İLK TESPİT DÜZELTİLDİ: başlangıçta bu "çakışma" import sırasına göre
kazananı belirler, dolayısıyla palet sürüklenmesi yaratır diye yazıldı.
Ölçüm bunun YANLIŞ olduğunu gösterdi: üç adın da sağ tarafı iki dosyada
AYNI (`var(--accent)`, `var(--border)`, `var(--muted)`). Yani tekrarlar
çelişkili değil, YEDEK. Hangisi kazanırsa kazansın utility aynı değere
çözülür.

Bu yüzden sözleşme "bir kez tanımla" DEĞİLDİR — o, zararsız bir tekrarı
da kırar ve gerçek hatayı maskede eder. Sözleşme şudur:

  **Bir `--color-*` adı iki blokta geçiyorsa DEĞERLERİ AYNI OLMALI.**

Farklı değerler palet sürüklenmesidir (utility adı sabit, çözülen renk
sürüklenir) ve fail-closed bloklanır. Aynı değerler geçerlidir: köprü ile
app aynı semantik token'a işaret eder, tutarlılık korunur.

Kapsam: yalnız bu çelişki sözleşmesi. Tema ÇÖZÜMLEME davranışı (hangi
değer gerçekte render ediliyor) bu kapının konusu DEĞİLDİR — o, computed-style
ölçümü gerektirir ve ayrı bir seam'dir.
"""

import re
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]

BRIDGE = REPO / "design-system" / "tailwind.css"
APP_CSS = REPO / "apps" / "dashboard-next" / "app" / "globals.css"
BUTTON = REPO / "apps" / "dashboard-next" / "components" / "ui" / "button.tsx"


def _theme_color_decls(path):
    """Bir dosyanın @theme bloklarındaki `--color-*` AD → DEĞER eşlemesi.

    Yorumlar temizlenir (CSS'te `--color-` geçen açıklama satırları yanıltır).
    Hem `@theme {` hem `@theme inline {` biçimlerini kapsar. Değerler
    normalize edilir (boşluk/sondaki `;`) ki aynı eşleme farklı yazımla
    yazıldığında yanlışlıkla "çelişki" sayılmasın.
    """
    css = re.sub(r"/\*.*?\*/", " ", path.read_text(encoding="utf-8"), flags=re.S)
    decls = {}
    for match in re.finditer(r"@theme(?:\s+inline)?\s*\{", css):
        depth, i = 1, match.end()
        while i < len(css) and depth:
            if css[i] == "{":
                depth += 1
            elif css[i] == "}":
                depth -= 1
            i += 1
        body = css[match.end():i - 1]
        for name, value in re.findall(
                r"(--color-[a-z0-9-]+)\s*:\s*([^;]+);", body):
            decls[name] = " ".join(value.split())
    return decls


class TestTokenNameNotDeclaredTwice(unittest.TestCase):
    """Bir semantik token tek bir değere çözülmelidir."""

    def test_no_conflicting_color_token_values(self):
        bridge = _theme_color_decls(BRIDGE)
        app = _theme_color_decls(APP_CSS)
        self.assertTrue(bridge, "köprü @theme bloğu boş çıktı — parser bozuk")
        self.assertTrue(app, "app @theme bloğu boş çıktı — parser bozuk")

        shared = sorted(set(bridge) & set(app))
        conflicts = [(n, bridge[n], app[n]) for n in shared
                     if bridge[n] != app[n]]
        self.assertEqual(
            [], conflicts,
            f"{len(conflicts)} semantik token iki @theme bloğunda FARKLI "
            "değere çözülüyor: "
            + "; ".join(f"{n}: köprü={b} vs app={a}" for n, b, a in conflicts)
            + " — utility adı sabitken çözülen renk sürükler (palet drift). "
            "İki taraf aynı semantik token'a işaret etmeli.")

    def test_bridge_is_generated_not_hand_edited(self):
        """Çakışmanın kaynağı üreticidir — sözleşme üreticide aranmalı.

        Köprü elle düzenlenirse üretici sözleşmesi zaten bozulur; bu test
        üreticinin tek kaynak olduğunu hatırlatır ve çakışmanın app'te
        düzeltilmesi gerektiğini gösterir.
        """
        header = BRIDGE.read_text(encoding="utf-8")[:600]
        self.assertIn("GENERATED", header,
                      "köprü GENERATED olarak işaretlenmemiş — "
                      "generate_tailwind.py sözleşmesi kaybolmuş")

    def test_muted_text_token_is_not_used_for_button_hover_background(self):
        """`--muted` köprüde bir metin rengi; yüzey hover'ı `surface-raised`."""
        button = BUTTON.read_text(encoding="utf-8")
        self.assertNotRegex(
            button, r"(?:hover:|aria-expanded:)bg-muted(?:/|\\b)",
            "bg-muted, metin-tokenı --muted'u yüzeymiş gibi kullanıyor; "
            "hover/expanded yüzeyi bg-surface-raised olmalı.")
        self.assertIn("hover:bg-surface-raised", button)
        self.assertIn("aria-expanded:bg-surface-raised", button)


if __name__ == "__main__":
    unittest.main()