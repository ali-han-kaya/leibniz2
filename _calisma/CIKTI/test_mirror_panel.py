#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_mirror_panel.py — dashboard Mirror sync (K17) panelinin regresyon kapısı.

preview.html'deki `renderMirrorSync()` mantığını (GÜNCEL/BAYAT/hata rozeti +
K17 exit kodu + BAYAT/EKSİK dosya listesi) Python karşılığıyla sabitler ve
preview.html/preview_server.py ile senkron guard'ları koşar:

  1. Mantık: mirror raporu {ok, exit, stale_files, auto_synced} → rozet
     sınıfı (ok/err) + rozet metni (GÜNCEL / GÜNCEL (otomatik sync) /
     BAYAT / hata) + bayat dosya listesi (preview.html renderMirrorSync
     ile aynı).
  2. Server ekstraksiyonu: mirror.output'taki "BAYAT/EKSİK:" satırlarından
     bayat dosya listesi (preview_server.py `mirror_stale` ile aynı).
  3. Senkron: preview.html'de id=mirror-body / id=mirror-ts /
     function renderMirrorSync + çağrılar; preview_server.py'de
     mirror_sync/mirror_stale alanları; verify_delivery.py'de stale_files
     üretimi.

stdlib unittest — ek bağımlılık yok.
"""
import pathlib
import re
import unittest

SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
PREVIEW_HTML = SCRIPT_DIR / "preview.html"
PREVIEW_SERVER = SCRIPT_DIR / "preview_server.py"
VERIFY_DELIVERY = SCRIPT_DIR / "verify_delivery.py"


# ── renderMirrorSync() mantığının Python karşılığı (preview.html ile senkron) ──
def mirror_panel_state(m):
    """preview.html renderMirrorSync() ile aynı karar mantığı.

    m: /api/latest `mirror_sync` ({ok, exit, detail, stale_files,
    auto_synced, …}) veya None (K17 bu run'da koşmadı).
    Döndürür {cls, badge, exit, stale, auto}.
    """
    if m is None:
        return {"cls": None, "badge": None, "exit": None,
                "stale": [], "auto": False}
    ok = m.get("ok") is True
    exit_code = m.get("exit")
    stale = list(m.get("stale_files") or [])
    auto = m.get("auto_synced") is True
    # TCC rotası: ok=True ama exit=None → launchd agent ~/Desktop'ı
    # okuyamadı, denetim atlandı — sahte GÜNCEL yerine "denetlenemedi" (warn).
    skip_tcc = ok and exit_code is None
    if skip_tcc:
        badge = "denetlenemedi (TCC)"
        cls = "warn"
    elif ok and auto:
        badge = "GÜNCEL (otomatik sync)"
        cls = "ok"
    elif ok:
        badge = "GÜNCEL"
        cls = "ok"
    else:
        badge = "BAYAT" if exit_code == 1 else "hata"
        cls = "err"
    return {"cls": cls, "badge": badge,
            "exit": exit_code, "stale": stale, "auto": auto}


# ── preview_server.py `mirror_stale` ekstraksiyonu (aynı mantık) ──
def extract_stale_from_output(output):
    """preview_server.py'deki mirror_stale comprehension'ının karşılığı."""
    return [ln.split("BAYAT/EKSİK:", 1)[1].strip()
            for ln in (output or "").splitlines()
            if "BAYAT/EKSİK:" in ln]


class TestMirrorPanelState(unittest.TestCase):
    """mirror_panel_state() — renderMirrorSync karar mantığı."""

    def test_none_koşmadı(self):
        s = mirror_panel_state(None)
        self.assertIsNone(s["cls"])
        self.assertIsNone(s["badge"])

    def test_guncel(self):
        s = mirror_panel_state({"ok": True, "exit": 0, "stale_files": [],
                                "auto_synced": False})
        self.assertEqual(s["cls"], "ok")
        self.assertEqual(s["badge"], "GÜNCEL")
        self.assertEqual(s["exit"], 0)

    def test_guncel_otomatik_sync(self):
        s = mirror_panel_state({"ok": True, "exit": 0, "stale_files": [],
                                "auto_synced": True, "before_exit": 1})
        self.assertEqual(s["cls"], "ok")
        self.assertEqual(s["badge"], "GÜNCEL (otomatik sync)")
        self.assertTrue(s["auto"])

    def test_bayat(self):
        s = mirror_panel_state({"ok": False, "exit": 1,
                                "stale_files": ["verify_delivery.py"],
                                "auto_synced": False})
        self.assertEqual(s["cls"], "err")
        self.assertEqual(s["badge"], "BAYAT")
        self.assertEqual(s["stale"], ["verify_delivery.py"])

    def test_hata_exit_2(self):
        s = mirror_panel_state({"ok": False, "exit": 2, "stale_files": [],
                                "auto_synced": False})
        self.assertEqual(s["cls"], "err")
        self.assertEqual(s["badge"], "hata")

    def test_tcc_skip(self):
        # TCC rotası: ok=True + exit=None → warn "denetlenemedi (TCC)".
        s = mirror_panel_state({"ok": True, "exit": None, "stale_files": [],
                                "auto_synced": False})
        self.assertEqual(s["cls"], "warn")
        self.assertEqual(s["badge"], "denetlenemedi (TCC)")
        self.assertIsNone(s["exit"])


class TestStaleExtraction(unittest.TestCase):
    """mirror.output → BAYAT/EKSİK dosya listesi (server/verify ortak parse)."""

    def test_no_stale_lines_empty(self):
        self.assertEqual(
            extract_stale_from_output("GÜNCEL: verify_delivery.py\n"
                                      "SONUÇ: mirror güncel · git abc123\n"),
            [])

    def test_verify_mirror_stale_line(self):
        out = ("GÜNCEL: preview/preview.html\n"
               "BAYAT/EKSİK: verify_delivery.py\n"
               "SONUÇ: mirror BAYAT — 'sync_verify_mirror.sh' çalıştırın\n")
        self.assertEqual(extract_stale_from_output(out),
                         ["verify_delivery.py"])

    def test_lean_and_preview_prefixes(self):
        out = ("BAYAT/EKSİK: lean_reduct/Content.lean\n"
               "BAYAT/EKSİK: preview/preview.html (guide)\n")
        self.assertEqual(extract_stale_from_output(out),
                         ["lean_reduct/Content.lean",
                          "preview/preview.html (guide)"])

    def test_none_output_empty(self):
        self.assertEqual(extract_stale_from_output(None), [])

    def test_verify_delivery_has_stale_files_field(self):
        # verify_delivery.py mirror raporuna stale_files üretimi eklenmiş mi?
        text = VERIFY_DELIVERY.read_text(encoding="utf-8")
        self.assertIn("stale_files", text)
        self.assertIn("BAYAT/EKSİK:", text)


class TestMirrorPanelSync(unittest.TestCase):
    """preview.html + preview_server.py senkron guard'ları."""

    def _html(self):
        return PREVIEW_HTML.read_text(encoding="utf-8")

    def test_html_has_mirror_section(self):
        html = self._html()
        self.assertIn('id="mirror-body"', html)
        self.assertIn('id="mirror-ts"', html)

    def test_html_has_render_mirror_sync_function(self):
        html = self._html()
        self.assertIn("function renderMirrorSync", html)
        self.assertIn("BAYAT/EKSİK dosyalar", html)

    def test_html_calls_render_mirror_sync(self):
        html = self._html()
        # initLoad + snapshot + update akışlarında çağrılıyor.
        self.assertEqual(html.count("renderMirrorSync("), 4)

    def test_html_reads_mirror_sync_field(self):
        html = self._html()
        self.assertIn("data.mirror_sync", html)

    def test_server_has_mirror_fields(self):
        text = PREVIEW_SERVER.read_text(encoding="utf-8")
        self.assertIn('"mirror_sync": data.get("mirror")', text)
        self.assertIn('"mirror_stale"', text)

    def test_server_stale_matches_verify_parse(self):
        # İki taraftaki ayrıştırma aynı kalıbı kullanmalı: "BAYAT/EKSİK:".
        server = PREVIEW_SERVER.read_text(encoding="utf-8")
        verify = VERIFY_DELIVERY.read_text(encoding="utf-8")
        self.assertIn('"BAYAT/EKSİK:"', server)
        self.assertIn('"BAYAT/EKSİK:"', verify)


if __name__ == "__main__":
    unittest.main()
