#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_verdict_seal_css.py — verdict mührünün görünürlük kapısı.

Ölçülen hata (2026-10-04): `.seal` TEMEL kuralında `visibility:hidden`
vardı ve onu geri veren başka kural yoktu. `hidden` özniteliğinin UA
kuralı yalnız `display:none` uygular; `.seal[hidden]{display:block}`
bunu eziyordu. Sonuç: preview.js `seal.hidden = false` yapsa bile
hesaplanan visibility "hidden" kalıyordu — yani mühür HİÇ görünmüyordu.

Tarayıcı kanıtı: canlı panelde `hidden=false` sonrası
`getComputedStyle(...).visibility === "hidden"`.

Kapı iki şeyi sabitler:
  1. `visibility:hidden` YALNIZCA `.seal[hidden]` kuralında bulunur —
     temel `.seal` kuralında değil.
  2. `.seal[hidden]` hem `display:block` (CLS için alan rezervasyonu:
     alan baştan durur, snapshot gelince header/Main kaymaz) hem
     `visibility:hidden` (gizliyken çizilmez, AT'ye duyurulmaz) taşır.

Bu ikisi birbirinin yerine geçmez: rezervasyon display ile,
gizlilik+gizli-AT-durumu visibility ile sağlanır.
"""

import re
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
PREVIEW_HTML = HERE / "preview.html"
SOURCE = PREVIEW_HTML.read_text(encoding="utf-8")
# CSS yorumları (`/* ... */`) kural denetimini kirletir: açıklama metni
# "visibility:hidden" gibi ifadeler içerebilir ve canlı kural değildir.
CSS = re.sub(r"/\*.*?\*/", " ", SOURCE, flags=re.S)


def _rule_body(selector):
    """CSS'ten `selector { ... }` gövdesini döndürür (yoksa None)."""
    m = re.search(re.escape(selector) + r"\s*\{([^}]*)\}", CSS)
    return m.group(1) if m else None


class TestSealVisibilityGate(unittest.TestCase):
    def test_base_seal_rule_has_no_visibility_hidden(self):
        """Temel .seal kuralı mührü kalıcı gizlemesin."""
        body = _rule_body(".seal")
        self.assertIsNotNone(body, "preview.html'de .seal kuralı bulunamadı")
        self.assertNotIn(
            "visibility", body,
            ".seal temel kuralında visibility var — hidden özniteliği "
            "kalkınca da mühür görünmez kalır (ölçülen hata). "
            "visibility YALNIZCA .seal[hidden] kuralında olmalı.",
        )

    def test_hidden_rule_reserves_space_and_hides(self):
        """Gizliyken alan rezerve (display) + çizilmez (visibility)."""
        body = _rule_body(".seal[hidden]")
        self.assertIsNotNone(body, ".seal[hidden] kuralı bulunamadı")
        self.assertIn(
            "display:block", body.replace(" ", ""),
            ".seal[hidden] display:block taşımalı — aksi halde UA "
            "display:none uygulayıp 64px kutu akışa girince CLS oluşur.",
        )
        self.assertIn(
            "visibility:hidden", body.replace(" ", ""),
            ".seal[hidden] visibility:hidden taşımalı — gizliyken "
            "hem çizilmemeli hem ekran okuyucuya duyurulmamalı.",
        )

    def test_visible_state_is_not_overridden(self):
        """[hidden] kalksın hiçbir kural visibility'ı gizli tutmamalı.

        `visibility` yalnız `.seal[hidden]` kuralında geçmeli; başka bir
        yerde geçerse mühür yine görünmez olur. Yorumlar temizlenmiş
        CSS üzerinden aranır.
        """
        live = [
            ln.strip() for ln in CSS.splitlines()
            if "visibility" in ln and ".seal[hidden]" not in ln
        ]
        self.assertEqual(
            [], live,
            "preview.html'de .seal[hidden] dışında bir visibility kuralı var — "
            "mühür gösterildiğinde gizlenebilir: " + str(live),
        )

    def test_markup_hides_via_attribute_not_permanent_aria_hidden(self):
        """Gizliyken `hidden` yeterli; kalıcı aria-hidden mührü gömerdi.

        Gizli durumu `.seal[hidden] { visibility:hidden }` zaten taşır —
        visibility:hidden içeriği erişilebilirlik ağacından çıkarır. Öznitelik
        olarak `hidden` da aynı işi görür. Kalıcı `aria-hidden="true"` ise
        JS mührü gösterdiğinde de bastırırdı: düğüm görünür ama verdict +
        hash'i ekran okuyucuya hiç duyurulmazdı.
        """
        m = re.search(r'<div[^>]*id="verdict-seal"[^>]*>', SOURCE)
        self.assertIsNotNone(m, "verdict-seal işaretlemesi bulunamadı")
        markup = m.group(0)
        self.assertIn("hidden", markup,
                      "verdict-seal `hidden` özniteliği taşımıyor — başta "
                      "gizli olmalı.")
        self.assertNotIn(
            'aria-hidden="true"', markup,
            "verdict-seal kalıcı aria-hidden taşıyor — mühür çalışma "
            "zamanında GÖSTERİLİYOR; aria-hidden onu erişilebilirlik "
            "ağacında tutmaya devam eder. Gizli durumu CSS "
            "visibility:hidden zaten ele alıyor.")


if __name__ == "__main__":
    unittest.main()