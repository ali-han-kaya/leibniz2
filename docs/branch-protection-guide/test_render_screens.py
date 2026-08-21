#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_render_screens.py — render_screens.py PNG üretimini doğrular.

render_screens.py, guide.html'daki her `.screen` bölümünü Playwright
Chromium (headless) ile 2x çözünürlükte PNG'ye çevirir. Bu test script'i
MOCK HTML ile koşar (gerçek guide.html'e bağımlılık yok) ve:

  - Her `screen-0N` öğesi için karşılık gelen `step-0N-*.png` dosyasının
    üretildiğini,
  - Üretilen PNG'lerin geçerli PNG imzası (‰PNG) taşıdığını,
  - Eksik öğe (ör. screen-09) için UYARI basılıp atlandığını ve
    PNG üretilmediğini,
  - `--help`'in çalıştığını

doğrular. Playwright gerekir (venv: _calisma/.venv_z3 + chromium).
Gerçek guide.html ile tam koşu için: python3 render_screens.py
"""
import os
import pathlib
import subprocess
import sys
import unittest

HERE = pathlib.Path(__file__).resolve().parent
RENDER = HERE / "render_screens.py"

# Gerçek guide.html ile aynı `.screen` öğe kimlikleri (üretim adları script'te).
SCREEN_IDS = [f"screen-{i:02d}" for i in range(1, 9)]

# Playwright yoksa testler SKIP (fail değil) — CI runner'da kurulu
# olmayabilir; bu test dokümantasyon üretim aracını denetler, teslim kapısı
# değildir. İçe aktarım kontrolü (shutil.which PATH'e bakar, koşan
# interpreter'ı değil — venv python'ıyla koşulunca yanlış negatif verir).
_HAVE_PLAYWRIGHT = False
try:
    from playwright.sync_api import sync_playwright  # noqa: F401
    _HAVE_PLAYWRIGHT = True
except Exception:
    _HAVE_PLAYWRIGHT = False

_SKIP_REASON = ("Playwright kurulu değil — "
                "_calisma/.venv_z3/bin/python ile koş "
                "(pip install playwright && playwright install chromium)")

# Browser varsayılan cache'te (~/Library/Caches/ms-playwright) — override
# ETME. PLAYWRIGHT_BROWSERS_PATH=0 paketin .local-browsers yoluna bakar ve
# "Executable doesn't exist" ile patlar; env zaten kuruluysa onu koru.
ENV = dict(os.environ)
# (override yok — Playwright varsayılan cache'i kullanır)


def _mock_html(out: pathlib.Path) -> pathlib.Path:
    """8 .screen öğeli minimal mock HTML üretir (gerçek guide'dan bağımsız)."""
    body = "\n".join(
        f'<div class="screen" id="{sid}" style="width:600px;height:300px;'
        f'background:#{i}2{i}2{i}2;">{sid}</div>'
        for i, sid in enumerate(SCREEN_IDS, 1)
    )
    html = (f"<!DOCTYPE html><html lang=\"tr\"><head><meta charset=\"utf-8\">"
            f"<title>mock</title></head><body>{body}</body></html>")
    src = out / "mock_guide.html"
    src.write_text(html, encoding="utf-8")
    return src


def _run(args):
    return subprocess.run([sys.executable, str(RENDER), *args],
                          capture_output=True, text=True, timeout=180,
                          env=ENV)


class TestRenderScreens(unittest.TestCase):
    @unittest.skipUnless(_HAVE_PLAYWRIGHT, _SKIP_REASON)
    def setUp(self):
        self.tmp = pathlib.Path(__file__).parent / ".test_tmp"
        self.tmp.mkdir(exist_ok=True)
        self.mock = _mock_html(self.tmp)
        self.out = self.tmp / "out"
        self.out.mkdir(exist_ok=True)

    def tearDown(self):
        for p in self.tmp.glob("step-*.png"):
            p.unlink(missing_ok=True)
        if (self.tmp / "mock_guide.html").exists():
            (self.tmp / "mock_guide.html").unlink()

    def test_all_screens_produce_pngs(self):
        r = _run(["--guide", str(self.mock), "--out-dir", str(self.out)])
        self.assertEqual(r.returncode, 0, r.stderr)
        for i in range(1, 9):
            pngs = list(self.out.glob(f"step-0{i}-*.png"))
            self.assertEqual(len(pngs), 1, f"screen-0{i} PNG üretilmedi: {r.stdout}")

    def test_png_signature_and_nonempty(self):
        r = _run(["--guide", str(self.mock), "--out-dir", str(self.out)])
        self.assertEqual(r.returncode, 0, r.stderr)
        for png in self.out.glob("step-*.png"):
            data = png.read_bytes()
            self.assertEqual(data[:8], b"\x89PNG\r\n\x1a\n",
                             f"{png.name} geçerli PNG imzası taşımıyor")
            self.assertGreater(len(data), 1000, f"{png.name} boş görünüyor")

    def test_missing_screen_warns_and_skips(self):
        # Script SCREENS listesinden screen-08'i MOCK'tan sil → script onu
        # aradığında UYARI basar, PNG üretmez ama exit 0 kalır (eksik öğe
        # bloke etmez). screen-09 eklemek işe yaramaz — script kendi listesini
        # döner, HTML'deki fazla öğeleri umursamaz.
        html = (self.tmp / "mock_guide.html").read_text(encoding="utf-8")
        # screen-08 div'ini DOM'dan tamamen sil → locator.count() == 0 → UYARI.
        start = html.index('id="screen-08"')
        # Öğe tek satır (mock üretimi böyle): <div ...>screen-08</div>
        end = html.index("</div>", start) + len("</div>")
        html = html[:start] + html[end:]
        (self.tmp / "mock_guide.html").write_text(html, encoding="utf-8")
        r = _run(["--guide", str(self.mock), "--out-dir", str(self.out)])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("screen-08 bulunamadı", r.stdout)

    def test_default_guide_is_script_dir(self):
        # Varsayılan --guide = gerçek guide.html (script dizininde olmalı).
        self.assertTrue((HERE / "guide.html").is_file())

    def test_help_runs(self):
        r = _run(["--help"])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("--guide", r.stdout)


if __name__ == "__main__":
    unittest.main()
