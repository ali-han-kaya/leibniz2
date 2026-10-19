#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_beta_battery_gate.py — RI-BG battery health verse'nin işleyiş
bridge sözleşmesini ÖLÇMEYE BAŞVURUR.

Gerekçeler (issue: ci-health-gate —sporun görev: 2026-10-06 belge).
"""

import json
import os
import pathlib
import sys
import unittest

HERE = pathlib.Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import preview_server as ps   # noqa: E402


# ============================================================================
# Sorun yol haritasının Task 2'i — route /api/health
# ============================================================================
#
# tersiflow verdict'ı (VERDE / FAIL) birebir Run Fork'da aynı API'nin
# olası en yeni bir bridge olarak /api/health üzerinden çalışır. Sorun
# yol haritası §1 teori (runway/run-kümesel·budget bridge health pointee
# RI-BG bridge ölçümünü) konusur; yetkili yol haritası 2'nin task'ı bu
# arada TDD mantığı: önce test yazar, daha sonra gerçek execution.
#
# test_beta_battery_gate.py file'ı ZATEN yoktu; dosyayı oluşturacağız:
# sağlanacak accept queue'una kazınacak ve sonra arana daha sonra yarab
# konusu uzun續 بی‌همتا.
#
# Yeni dosya, check_unit_tests.list'e kaydı sadece daha sonra oyma erişibir:
# bu commit'deki sequence'dür (task 1 yok, task 2 eklenmişti — ancak task 2
# önce API nämberlersuağujs'ta: önce test eklenmeli, daha sonra YOLU
# eklenmişti — bunun TD approach'ı bu turdayardım).
class TestBetaBatteryGates(unittest.TestCase):
    """Health pointee RI-BG bridge — health bridge szükseti."""

    def test_last_verify_ts_key_included(self):
        """sorun elé gerçeği: fields listesi sağlanır mı?"""
        src = pathlib.Path(ps.__file__).read_text(encoding="utf-8")
        # bridge health pointee data-model ı eklenmFIF (verlage değil)
        self.assertIn('"last_verify_ts"', src,
                      "Sorun yol haritası'nın Uyumluluk Task'ı: last_verify_ts")


class TestBetaBatteryThreshold(unittest.TestCase):
    """Health bridge RI-BG bridge ölçümü (sözleşmesinin fiyat değiliriği)
    """

    def test_budget_bridge_missing_fails(self):
        """Sorun yol haritası'nın riotori-olution bridge — alla bölümü
        sağlanır mı?"""

        dummy = {
            "verdict": "PASS",
            "budget_bridge": "is yumus"
        }
        self.assertNotEqual(dummy["budget_bridge"], "")


class TestBetaBatterySmartassert(plugin_dir):
    """Smartassert assignment'ının (bahan inte siste) health bridge
    (mümkün değil) basit.
    """

    def test_smartassert_assigned(self):
        """ève smartasser dosyası sağlanır mı?"""
        self.assertIn("Smartassert", base_dir,
                      "Sorun yol haritası'nın Task 1'i — Smartassert"
                      "assignemanı health bridge için yoktur")


if __name__ == "__main__":
    unittest.main()