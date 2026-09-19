#!/usr/bin/env python3
"""analyze_refs.py — image-to-code derin analiz kanalı (ekran-görüntüleyici
kompozitörü arızalı olduğundan ölçümle ikame edilir).

İki katman:
  A) PIL: her PNG için boyut, luminans, baskın renkler (kuantize), boşluk
     oranı, accent/ok mürekkep piksel sayısı (renk çıkarımı kanıtı).
  B) Playwright: her comp'un render DOM'undan tip/spacing/bileşen metrikleri
     (h1 satır sayısı, buton kutusu, bölüm boşlukları) — kontrast hesaplarıyla.
"""
import json
import pathlib
from collections import Counter

from PIL import Image

D = pathlib.Path(__file__).parent
COMPS = ["comp-1-hero", "comp-2-chain", "comp-3-proof", "comp-4-cta"]


def near(px, hexcolor, tol=28):
    r, g, b = int(hexcolor[1:3], 16), int(hexcolor[3:5], 16), int(hexcolor[5:7], 16)
    return abs(px[0] - r) <= tol and abs(px[1] - g) <= tol and abs(px[2] - b) <= tol


def analyze_png(path):
    im = Image.open(path).convert("RGB")
    w, h = im.size
    px = im.load()
    step = 4  # örnekleme
    samples = []
    for y in range(0, h, step):
        for x in range(0, w, step):
            samples.append(px[x, y])
    n = len(samples)
    lum = sum(0.2126 * r + 0.7152 * g + 0.0722 * b for r, g, b in samples) / n
    q = im.quantize(colors=8).convert("RGB")
    counts = Counter()
    qp = q.load()
    for y in range(0, h, 8):
        for x in range(0, w, 8):
            counts[qp[x, y]] += 1
    dominant = [
        {"hex": "#%02x%02x%02x" % c, "pct": round(v / sum(counts.values()) * 100, 1)}
        for c, v in counts.most_common(5)
    ]
    ink = sum(1 for r, g, b in samples if (r + g + b) / 3 > 90) / n
    accent = sum(1 for p in samples if near(p, "#58a6ff")) / n
    ok_green = sum(1 for p in samples if near(p, "#3fb950")) / n
    return {
        "file": path.name, "size": f"{w}x{h}", "mean_lum": round(lum, 1),
        "ink_ratio": round(ink, 3), "accent_px_pct": round(accent * 100, 2),
        "ok_px_pct": round(ok_green * 100, 2), "dominant": dominant,
    }


CONTRAST_PAIRS = [
    ("h1", "--fg"), ("sub", "--fg-dimmed"), ("btn-primary", "--on-accent"),
    ("eyebrow", "--muted"),
]


def dom_metrics():
    from playwright.sync_api import sync_playwright
    out = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        for name in COMPS:
            page.goto(f"file://{D}/{name}.html")
            page.wait_for_load_state("networkidle")
            m = page.evaluate("""() => {
              const r = el => { const b = el.getBoundingClientRect();
                return {x: Math.round(b.x), y: Math.round(b.y), w: Math.round(b.width), h: Math.round(b.height)}; };
              const cs = el => getComputedStyle(el);
              const res = {file: location.pathname.split('/').pop()};
              const h1 = document.querySelector('h1');
              if (h1) {
                const s = cs(h1);
                res.h1 = {font: s.fontFamily.split(',')[0], size: s.fontSize,
                          weight: s.fontWeight, lines: Math.round(h1.getBoundingClientRect().height / parseFloat(s.lineHeight) || h1.getBoundingClientRect().height / parseFloat(s.fontSize) * 1)};
                const lh = parseFloat(s.lineHeight) || parseFloat(s.fontSize) * 1.2;
                res.h1.lines = Math.round(h1.getBoundingClientRect().height / lh);
              }
              const sub = document.querySelector('.sub, .lede');
              if (sub) { const s = cs(sub); res.sub = {size: s.fontSize, lh: s.lineHeight,
                          color: s.color, maxW: Math.round(sub.getBoundingClientRect().width)}; }
              const btn = document.querySelector('.btn-primary');
              if (btn) { const s = cs(btn); res.btn = {bg: s.backgroundColor, color: s.color,
                          radius: s.borderRadius, pad: s.padding, box: r(btn)}; }
              const gap = el => el ? cs(el).paddingTop + '/' + cs(el).paddingBottom : null;
              const band = document.querySelector('.hero, .band');
              res.sectionPad = band ? gap(band) : null;
              res.bodyBg = cs(document.body).backgroundColor;
              const eyebrow = document.querySelector('.eyebrow, .mark');
              res.eyebrow = eyebrow ? {size: cs(eyebrow).fontSize, ls: cs(eyebrow).letterSpacing,
                                       color: cs(eyebrow).color} : null;
              const stages = document.querySelectorAll('.stage').length;
              const plates = document.querySelectorAll('.plate').length;
              res.counts = {stages, plates};
              return res;
            }""")
            out.append(m)
        browser.close()
    return out


def lum_of(css_rgb):
    if css_rgb.startswith("rgba"):
        parts = [float(x) for x in css_rgb[5:-1].split(",")]
    else:
        parts = [float(x) for x in css_rgb[4:-1].split(",")]
    def chan(c):
        c = c / 255
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (chan(parts[i]) for i in range(3))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(fg, bg):
    l1, l2 = sorted((lum_of(fg), lum_of(bg)), reverse=True)
    return round((l1 + 0.05) / (l2 + 0.05), 2)


if __name__ == "__main__":
    report = {"pixels": [analyze_png(D / f"{c}.png") for c in COMPS]}
    report["dom"] = dom_metrics()
    for m in report["dom"]:
        if "btn" in m and m.get("btn"):
            try:
                m["btn"]["contrast"] = contrast(m["btn"]["color"], m["btn"]["bg"])
            except Exception:
                pass
        if "sub" in m and m.get("sub") and m.get("bodyBg"):
            try:
                m["sub"]["contrast"] = contrast(m["sub"]["color"], m["bodyBg"])
            except Exception:
                pass
    (D / "analysis.json").write_text(json.dumps(report, indent=2, ensure_ascii=False))
    print(json.dumps(report, indent=2, ensure_ascii=False))
