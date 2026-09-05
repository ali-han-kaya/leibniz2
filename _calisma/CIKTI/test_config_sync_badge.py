#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_config_sync_badge.py — preview.html configSyncBadge() senkron kapısı.

Dashboard'un "Schema Sync (CONFIG_BASENAMES)" panelindeki rozet mantığını
sabitler: /api/latest `config_sync` özetinden — check_config_sync.py --json
sonucu (verify.yml ↔ CONFIG_BASENAMES ↔ config.json üçlüsü; CI config-sync
job'ıyla birebir). Rozet "7/7" gibi verified/total gösterir: drift varsa
"✗ Schema Sync: 6/7 (2 drift)" (kırmızı), yoksa "✓ Schema Sync: 7/7"
(yeşil); veri yoksa gri.

configSyncBadge() preview.html'deki saf JS fonksiyonuyla BİREBİR senkron
tutulmalıdır — bu dosya JS'in Python karşılığını + HTML'de varlığı sabitler.
stdlib unittest — ek bağımlılık yok.
"""
import pathlib
import unittest

SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
PREVIEW_HTML = SCRIPT_DIR / "preview.html"


def config_sync_badge(s):
    """preview.html configSyncBadge() ile aynı mantık (Python karşılığı)."""
    if not isinstance(s, dict) or s.get("available") is not True:
        return {"cls": "unknown", "text": "Schema Sync: veri yok"}
    vt = "%d/%d" % (s.get("verified") or 0, s.get("total") or 0)
    if s.get("has_drift"):
        return {"cls": "err",
                "text": "✗ Schema Sync: %s (%d drift)"
                        % (vt, s.get("error_count") or 0)}
    return {"cls": "ok", "text": "✓ Schema Sync: %s" % vt}


class TestConfigSyncBadge(unittest.TestCase):
    def test_no_data_unknown(self):
        self.assertEqual(config_sync_badge(None),
                         {"cls": "unknown", "text": "Schema Sync: veri yok"})
        self.assertEqual(config_sync_badge({}),
                         {"cls": "unknown", "text": "Schema Sync: veri yok"})
        self.assertEqual(config_sync_badge({"available": False}),
                         {"cls": "unknown", "text": "Schema Sync: veri yok"})

    def test_drift_marks_badge(self):
        b = config_sync_badge({"available": True, "ok": False, "has_drift": True,
                               "error_count": 2, "verified": 5, "total": 7})
        self.assertEqual(b["cls"], "err")
        self.assertEqual(b["text"], "✗ Schema Sync: 5/7 (2 drift)")

    def test_drift_zero_error_count_fallback(self):
        b = config_sync_badge({"available": True, "has_drift": True})
        self.assertEqual(b["text"], "✗ Schema Sync: 0/0 (0 drift)")

    def test_synced_marks_ok(self):
        b = config_sync_badge({"available": True, "ok": True, "has_drift": False,
                               "error_count": 0, "verified": 7, "total": 7})
        self.assertEqual(b["cls"], "ok")
        self.assertEqual(b["text"], "✓ Schema Sync: 7/7")

    def test_synced_zero_verified_fallback(self):
        b = config_sync_badge({"available": True, "has_drift": False})
        self.assertEqual(b["text"], "✓ Schema Sync: 0/0")


class TestHtmlSync(unittest.TestCase):
    """preview.html'de panel + rozet fonksiyonu var; JS, Python'la aynı doku."""

    def test_js_function_present(self):
        html = PREVIEW_HTML.read_text(encoding="utf-8")
        self.assertIn("function configSyncBadge(s)", html)
        self.assertIn("function renderConfigSync(s)", html)

    def test_panel_elements_present(self):
        html = PREVIEW_HTML.read_text(encoding="utf-8")
        self.assertIn('id="config-sync-badge"', html)
        self.assertIn('id="config-sync-body"', html)
        self.assertIn('id="cs-ts"', html)

    def test_apply_snapshot_wired(self):
        html = PREVIEW_HTML.read_text(encoding="utf-8")
        self.assertIn("renderConfigSync(d.config_sync)", html)

    def test_js_uses_same_text_shapes(self):
        html = PREVIEW_HTML.read_text(encoding="utf-8")
        self.assertIn('"Schema Sync: veri yok"', html)
        self.assertIn('"✗ Schema Sync: "', html)
        self.assertIn('"✓ Schema Sync: "', html)
        self.assertIn("s.verified || 0) + \"/\" + (s.total || 0)", html)

    def test_badge_class_names_match(self):
        html = PREVIEW_HTML.read_text(encoding="utf-8")
        # Rozet cls değerleri CSS'te var olan sınıflar (unknown/err/ok)
        for cls_name in ("badge unknown", "badge err", "badge ok"):
            self.assertIn(cls_name, html)


if __name__ == "__main__":
    unittest.main()
