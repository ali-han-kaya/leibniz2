#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_klayers_contract.py — klayers_contract.py'nin kendi değişmezleri.

Sözleşme sahibi tek modül: katman kümesi, çekirdek/işteğe-bağlı ayrımı,
run summary'nin gösterdiği alt küme, Other kovası ve verdict. Buradaki
testler üç şeyi sabitler:

  - Tablolar arası tutarlılık: her katmanın bir koşum kuralı var
    (aksi halde build_layers_summary onu daima SKIP sayar), koşum
    kuralları yalnız gerçek katmanlara işaret ediyor, RENDER_LAYERS
    gerçek bir katman, OTHER_KEY bir katmanla çakışmıyor.
  - presentation_order: Other önce gelir, bozuk/boş kova yok sayılır,
    eksik K katmanı None olarak ÜRETİLİR (render "sidecar'da yok" basar).
  - run_verdict: gösterilen katmanlardan biri FAIL ise FAIL.

stdlib unittest — tek dış bağımlılık yok.
"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import klayers_contract as kc  # noqa: E402


class TestRunRuleIsTotal(unittest.TestCase):
    """Her LAYER_LABELS girdisi ya çekirdek ya isteğe bağlı olmalı."""

    def test_every_layer_has_a_run_rule(self):
        unruled = sorted(set(kc.LAYER_LABELS)
                         - set(kc.CORE_LAYERS) - set(kc.OPTIONAL_LAYERS))
        self.assertEqual(unruled, [],
                         f"bu katmanların koşum kuralı yok — build_layers_summary "
                         f"hepsini daima SKIP sayar: {unruled}")

    def test_rules_cover_only_real_layers(self):
        phantom = sorted((set(kc.CORE_LAYERS) | set(kc.OPTIONAL_LAYERS))
                         - set(kc.LAYER_LABELS))
        self.assertEqual(phantom, [],
                         f"koşum kuralı olan ama LAYER_LABELS'te olmayan katman: "
                         f"{phantom}")

    def test_core_and_optional_are_disjoint(self):
        overlap = sorted(set(kc.CORE_LAYERS) & set(kc.OPTIONAL_LAYERS))
        self.assertEqual(overlap, [],
                         f"katman hem çekirdek hem isteğe bağlı: {overlap}")


class TestRenderSetIsASubset(unittest.TestCase):
    """RENDER_LAYERS, üreticinin yazdığı katmanların bir alt kümesi."""

    def test_render_layers_exist(self):
        phantom = [k for k in kc.RENDER_LAYERS if k not in kc.LAYER_LABELS]
        self.assertEqual(phantom, [],
                         f"render listesi LAYER_LABELS'te olmayan katman içeriyor "
                         f"(her koşuda hayalet 'sidecar'da yok' bölümü basar): "
                         f"{phantom}")

    def test_render_layers_have_no_duplicates(self):
        dupes = sorted({k for k in kc.RENDER_LAYERS
                        if kc.RENDER_LAYERS.count(k) > 1})
        self.assertEqual(dupes, [],
                         f"render listesinde tekrar eden katman: {dupes}")


class TestOtherKeyDoesNotCollide(unittest.TestCase):
    def test_other_key_is_not_a_layer(self):
        self.assertNotIn(kc.OTHER_KEY, kc.LAYER_LABELS,
                         f"OTHER_KEY ({kc.OTHER_KEY}) gerçek bir katman anahtarıyla "
                         f"çakışıyor — kova o katmanın yerine geçer.")


class TestVerdictReachesBothCarriers(unittest.TestCase):
    """Verdict İKİ temelli taşınır ve ikisi de okur.

    verify_delivery.py run'ı iki yere yazar: `--json` stdout (preview_server
    bunu okur) ve `--klayers-out` sidecar'ı (CI run summary okur). Verdict
    yalnız sidecar'da kaldığı gün dashboard her koşuda "K katmanları ⚠️"
    diyordu — yeşil bir run'ı sarı gösteren yanıltıcı geri bildirim, ve
    163 test dosyasının hiçbiri yakalamıyordu. Bu kapı iki taşıyıcının da
    alanı taşıdığını sabitler.
    """

    @classmethod
    def setUpClass(cls):
        here = os.path.dirname(os.path.abspath(__file__))
        src = os.path.join(here, "verify_delivery.py")
        with open(src, encoding="utf-8") as f:
            cls.text = f.read()

    def test_json_payload_carries_run_status(self):
        # İki taşıyıcı da aynı satırı içerdiği için assertIn tek başına
        # ayırt edemez: --json `out` sözlüğünü KAPSAMAK zorundayız.
        out_start = self.text.index("\n    out = {")
        sidecar = self.text.index("klayers_payload", out_start)
        out_dict = self.text[out_start:sidecar]
        self.assertIn('"run_status": _klc.run_verdict(klayers)', out_dict,
                      "--json stdout yükünde run_status yok — preview_server "
                      "verdiyi okuyamaz, panoyu hep bilinmiyor gösterir.")

    def test_sidecar_payload_carries_run_status(self):
        self.assertGreaterEqual(
            self.text.count('"run_status": _klc.run_verdict(klayers)'), 2,
            "run_status hem --json stdout'a hem --klayers-out sidecar'ına "
            "yazılmalı — iki tüketici iki ayrı yol okur.")

    def test_layers_summary_computed_once(self):
        # İki çağrı iki ayrı hesaplama ve iki temelli kaynak demekti.
        # "= " ile sayılır: `def build_layers_summary(args, findings):`
        # tanımı da aynı alt dizgeyi içerir.
        calls = self.text.count("= build_layers_summary(args, findings)")
        self.assertEqual(calls, 1,
                         f"build_layers_summary {calls} kez çağrılıyor — "
                         f"stdout ve sidecar farklı sözlük alabilir.")


class TestRunVerdict(unittest.TestCase):
    """run_verdict: sidecar'da taşınan tek doğruluk kaynağı."""

    def _layer(self, status="PASS"):
        return {"label": "L", "status": status, "ran": True, "findings": []}

    def test_all_pass(self):
        layers = {k: self._layer() for k in kc.RENDER_LAYERS}
        self.assertEqual(kc.run_verdict(layers), "PASS")

    def test_declared_fail_blocks(self):
        layers = {k: self._layer() for k in kc.RENDER_LAYERS}
        layers["K3"] = self._layer("FAIL")
        self.assertEqual(kc.run_verdict(layers), "FAIL")

    def test_unregistered_fail_blocks(self):
        # Kayıt dışı P0 hiçbir K katmanına düşmez ama kapıyı kapatır —
        # dashboard'ın göremediği tek durumdu.
        layers = {k: self._layer() for k in kc.RENDER_LAYERS}
        layers[kc.OTHER_KEY] = self._layer("FAIL")
        self.assertEqual(kc.run_verdict(layers), "FAIL")

    def test_skip_does_not_block(self):
        layers = {k: self._layer() for k in kc.RENDER_LAYERS}
        layers["K10"] = self._layer("SKIP")
        self.assertEqual(kc.run_verdict(layers), "PASS")

    def test_malformed_other_does_not_crash(self):
        layers = {k: self._layer() for k in kc.RENDER_LAYERS}
        layers[kc.OTHER_KEY] = None
        self.assertEqual(kc.run_verdict(layers), "PASS")

    def test_empty_layers_pass(self):
        self.assertEqual(kc.run_verdict({}), "PASS")


class TestPresentationOrder(unittest.TestCase):
    def _layer(self, status="PASS"):
        return {"label": "L", "status": status, "ran": True, "findings": []}

    def test_empty_layers_yields_absent_render_layers(self):
        # Gezinti RENDER_LAYERS üzerinde TOPLAMDIR: eksik katman atlanmaz,
        # None değerle döner — render() "⏭️ Kn: sidecar'da yok" basabilmeli.
        rows = kc.presentation_order({})
        self.assertEqual([k for k, _ in rows], list(kc.RENDER_LAYERS))
        self.assertEqual([v for _, v in rows], [None] * len(kc.RENDER_LAYERS))

    def test_other_comes_first(self):
        layers = {k: self._layer() for k in ("K1", "K2")}
        layers[kc.OTHER_KEY] = self._layer("FAIL")
        keys = [k for k, _ in kc.presentation_order(layers)]
        self.assertEqual(keys[0], kc.OTHER_KEY,
                         "Other kovası her zaman en başta olmalı")
        self.assertEqual(keys[1:], list(kc.RENDER_LAYERS))

    def test_render_layers_follow_declared_order(self):
        layers = {k: self._layer() for k in ("K2", "K1")}
        keys = [k for k, _ in kc.presentation_order(layers)]
        self.assertEqual(keys, [k for k in kc.RENDER_LAYERS])

    def test_absent_render_layer_yields_none_not_omitted(self):
        # render() "⏭️ Kn: sidecar'da yok" basabilmeli: anahtar ÜRETİLMELİ,
        # değeri None olmalı.
        rows = kc.presentation_order({"K1": self._layer()})
        self.assertEqual(rows[0][0], "K1")
        self.assertIsNone(rows[1][1])

    def test_empty_or_malformed_other_is_not_shown(self):
        for bad in ({}, None, "FAIL", 7):
            with self.subTest(bad=bad):
                layers = {"K1": self._layer(), kc.OTHER_KEY: bad}
                keys = [k for k, _ in kc.presentation_order(layers)]
                self.assertNotIn(kc.OTHER_KEY, keys)

    def test_order_is_independent_of_dict_insertion(self):
        a = {kc.OTHER_KEY: self._layer("FAIL"), "K1": self._layer()}
        b = {"K1": self._layer(), kc.OTHER_KEY: self._layer("FAIL")}
        self.assertEqual(kc.presentation_order(a), kc.presentation_order(b))


if __name__ == "__main__":
    unittest.main()