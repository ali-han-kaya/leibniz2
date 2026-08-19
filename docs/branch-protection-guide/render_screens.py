#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""render_screens.py — guide.html'daki her `.screen` bölümünü PNG'ye çevirir.

Playwright Chromium (headless) kullanır: `pip install playwright && playwright
install chromium` gerekir (venv: _calisma/.venv_z3). Her ekran öğesi
(screen-01 … screen-08) 2x çözünürlükte (device_scale_factor=2) tek tek
yakalanır → docs/branch-protection-guide/step-0N-*.png.

Kullanım:
  _calisma/.venv_z3/bin/python docs/branch-protection-guide/render_screens.py

Yeniden üretilebilir: kaynak guide.html değişince scripti tekrar koş — PNG'ler
aynı boyutlarda yeniden yazılır (deterministik).
"""
import pathlib

from playwright.sync_api import sync_playwright

HERE = pathlib.Path(__file__).resolve().parent
GUIDE = HERE / "guide.html"

# (element id, çıktı dosyası) — sıra PUBLISH_SCENARIO web UI adımlarıyla uyumlu.
SCREENS = [
    ("screen-01", "step-01-branches.png"),
    ("screen-02", "step-02-add-rule.png"),
    ("screen-03", "step-03-pr-review.png"),
    ("screen-04", "step-04-status-checks.png"),
    ("screen-05", "step-05-enforce.png"),
    ("screen-06", "step-06-create.png"),
    ("screen-07", "step-07-result.png"),
    ("screen-08", "step-08-verify-terminal.png"),
]


def main() -> int:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 900},
                                device_scale_factor=2)
        page.goto(GUIDE.as_uri())
        page.wait_for_timeout(400)
        for elem_id, out_name in SCREENS:
            loc = page.locator(f"#{elem_id}")
            if loc.count() == 0:
                print(f"UYARI: #{elem_id} bulunamadı — atlandı")
                continue
            dest = HERE / out_name
            loc.screenshot(path=str(dest))
            print(f"yazıldı: {dest.name}")
        browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
