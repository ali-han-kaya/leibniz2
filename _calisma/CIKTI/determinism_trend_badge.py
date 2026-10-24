#!/usr/bin/env python3
"""determinism_trend_badge.py — TeX motor determinizmi trend grafiği + rozet.

docs/determinism_trend/determinism_trend.jsonl'ı okur (satır-başına ölçüm;
üretici: record_determinism_trend.py) ve iki çıktı üretir:

  determinism-trend.svg   — küçük SVG zaman serisi (nokta = ölçüm; tooltip:
                            tarih + platform + motor hash öneki + gate;
                            yeşil çizgi = ardışık aynı-hash zinciri)
  determinism-trend.json  — {generated, badge, rows[]} (satır-başına badge)

--update-preview: preview dashboard'ı panele bağlar (idempotent — işaret
  metinleri varsa dokunmaz):
  - preview.html:             #det-trend bölümü (badge + legend + svg)
  - preview.js:               determinismTrendBadge/renderDeterminismTrend
                              + /api/determinism-trend fetch
  - preview_server.py:        /api/determinism-trend route +
                              serve_determinism_trend handler +
                              DETERMINISM_TREND_PATH global + main() init
  - test_api_method_contract.py: API_CONTRACT + ROUTE_TOKENS girdileri

Sözleşme testi: test_determinism_trend_badge.py.
Badge mantığının JS karşılığı determinismTrendBadge() ile birebir senkrondur
(aynı dosyada `determinismTrendFamilyOf` yardımcısıyla; test, JS davranışını
node ile Python çıktısıyla birebir karşılaştırır).

AİLELER (2026-10-08): aynı jsonl iki bağımsız seri taşır (manuscript + canvas).
Badge AİLE BAŞINA son kayda bakar: `rows[-1]`e bakmak, taze bir canvas
satırı için BAYAT/FAILED manuscript serisini yeşile boyardı — fail-open
regresyon testi bunu kilitler. Zincir (aynı-hash çizgisi) ve tooltip de aile ayrımı
yapar: aileler arası çizgi anlamsızdır.

stdlib only — OFFLINE.
"""
import argparse
import datetime
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CIKTI = os.path.join(ROOT, "_calisma", "CIKTI")
TREND = os.path.join(ROOT, "docs", "determinism_trend", "determinism_trend.jsonl")
DEFAULT_OUT_DIR = os.path.join(ROOT, "determinism-trend")

# Aileler — record_determinism_trend.py ile AYNI değer (jsonl tek, iki seri).
# Bağımsız tanımlı: modül stdlib-only ve bağımsız import edilir; davranış
# eşitliği test_determinism_trend_badge.py kilitler.
FAMILY_MANUSCRIPT = "manuscript"
FAMILY_CANVAS = "canvas"
FAMILIES = (FAMILY_MANUSCRIPT, FAMILY_CANVAS)

SHA_PREFIX_LEN = 8          # tooltip/badge'de gösterilecek hash öneki
SVG_W, SVG_H, PAD = 1160, 90, 24
COLOR_OK, COLOR_WARN, COLOR_UNKNOWN = "#3fb950", "#d29922", "#8b949e"


def rows_from(path):
    """jsonl → dict satırları; dosya yoksa None, bozuk satırlar atlanır."""
    if not path or not os.path.isfile(path):
        return None
    rows = []
    with open(path, encoding="utf-8") as f:
        for ln in f:
            ln = ln.strip()
            if not ln:
                continue
            try:
                r = json.loads(ln)
            except json.JSONDecodeError:
                continue
            if isinstance(r, dict):
                rows.append(r)
    return rows


def family_of(row):
    """Satırın ailesi; alan yoksa/boşsa manuscript (geriye dönük okuma).

    record_determinism_trend.family_of ile AYNI kural (oradaki sabitlerle
    bağımsız; davranış eşitliği test_determinism_trend_badge kilitler).
    """
    fam = row.get("family") if isinstance(row, dict) else None
    return fam if isinstance(fam, str) and fam else FAMILY_MANUSCRIPT


def badge(rows):
    """rows → {cls, text}. AİLE BAŞINA son kayda bakılır: iki seri tek dosyada
    yaşadığı için taze/temiz bir aile, diğer ailenin kırmızısını kapatamaz.

    Tek ailede metin biçimi eskisiyle birebir aynı (sözleşme sabiti); çok
    ailede ihlal eden aile(ler) adıyla yazılır. Sayım toplam ölçüm sayısıdır.
    JS karşılığı determinismTrendBadge() ile senkron.
    """
    if not rows:
        return {"cls": "unknown", "text": "determinizm: veri yok"}
    n = len(rows)
    last_of = {}
    for r in rows:
        last_of[family_of(r)] = r
    fams = list(last_of)
    bad = [f for f in fams if last_of[f].get("gate") != "PASS"]
    if not bad:
        return {"cls": "ok", "text": "✓ DETERMİNİZM PASS · %d ölçüm" % n}
    if len(fams) == 1:
        gate = last_of[fams[0]].get("gate")
        return {"cls": "warn",
                "text": "⚠️ determinizm gate %s · %d ölçüm" % (gate or "?", n)}
    detail = ", ".join("%s %s" % (f, last_of[f].get("gate") or "?")
                       for f in bad)
    return {"cls": "warn",
            "text": "⚠️ determinizm gate %s · %d ölçüm" % (detail, n)}


def _row_title(r):
    # Aile etiketi + yalnız TAŞINAN hash'ler: canvas satırında texlive bacağı
    # yoktur (boş "texlive  ·" yazmak yanlış bilgidir).
    bits = [str(r.get("date") or "?"), str(r.get("platform") or "?"),
            family_of(r)]
    for key, label in (("texlive_canonical_sha256", "texlive"),
                       ("tectonic_canonical_sha256", "tectonic")):
        if r.get(key):
            bits.append("%s %s" % (label, str(r[key])[:SHA_PREFIX_LEN]))
    bits.append("gate %s" % (r.get("gate") or "?"))
    return " · ".join(bits)


def _x(i, n):
    return (SVG_W / 2.0) if n == 1 else PAD + (SVG_W - 2 * PAD) * i / (n - 1)


def svg(rows):
    """rows → küçük SVG zaman serisi (deterministik çıktı)."""
    have = [r for r in (rows or [])
            if r.get("date") and r.get("platform") is not None]
    parts = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %d %d" '
             'width="100%%" height="%d" role="img" '
             'aria-label="TeX motor determinizm trend grafiği">'
             % (SVG_W, SVG_H, SVG_H)]
    if not have:
        parts.append('<text x="%d" y="%d" fill="%s" font-size="12">'
                     'veri yok — koşum bekleniyor</text>'
                     % (SVG_W // 2, SVG_H // 2, COLOR_UNKNOWN))
    else:
        n = len(have)
        for i, r in enumerate(have):
            color = COLOR_OK if r.get("gate") == "PASS" else COLOR_WARN
            parts.append(
                '<circle cx="%.1f" cy="%d" r="5" fill="%s">'
                '<title>%s</title></circle>'
                % (_x(i, n), SVG_H // 2, color, _row_title(r)))
        for i in range(1, n):
            a, b = have[i - 1], have[i]
            if (family_of(a) == family_of(b)
                    and a.get("texlive_canonical_sha256") == b.get("texlive_canonical_sha256")
                    and a.get("tectonic_canonical_sha256")
                    == b.get("tectonic_canonical_sha256")):
                parts.append('<line x1="%.1f" y1="%d" x2="%.1f" y2="%d" '
                             'stroke="%s" stroke-width="2"/>'
                             % (_x(i - 1, n), SVG_H // 2, _x(i, n),
                                SVG_H // 2, COLOR_OK))
    parts.append("</svg>")
    return "".join(parts)


def build_json(rows):
    return {"generated": datetime.datetime.now(tz=datetime.timezone.utc).isoformat(),
            "badge": badge(rows),
            "rows": [dict(r, badge=badge([r])) for r in (rows or [])]}


def _patch_once(path, old, new):
    """old'u bir kez bulup new ile değiştirir; old yoksa (idempotent) False."""
    with open(path, encoding="utf-8") as f:
        src = f.read()
    if new in src or old not in src:
        return False
    with open(path, "w", encoding="utf-8") as f:
        f.write(src.replace(old, new, 1))
    return True


HTML_SECTION = '''  <section>
    <h2>TeX motor determinizm trend <span class="ts" id="det-trend-ts"></span></h2>
    <div style="display:flex;align-items:center;gap:10px;margin-bottom:6px;flex-wrap:wrap">
      <span class="badge unknown" id="det-trend-badge">determinizm: veri yok</span>
      <span class="muted" id="det-trend-legend" style="font-size:11px">nokta = ölçüm (yeşil PASS, amber gate-sorun) · çizgi = aynı-hash zinciri</span>
    </div>
    <div class="card" style="padding:8px">
      <svg id="det-trend" viewBox="0 0 1160 90" width="100%" height="90" role="img"
           aria-label="TeX motor determinizm trend grafiği"></svg>
    </div>
  </section>

  <section>
    <h2>P0 / P1 trend — son 100 run'''

JS_CODE = '''
// ─── TeX motor determinizm trend ─────────────────────────────────────────
// Python karşılığı (determinism_trend_badge) ile BİREBİR SENKRON: aşağıdaki
// üç fonksiyonun metni determinism_trend_badge.JS_CODE ile bu dosyada birebir
// aynıdır (test_determinism_trend_badge.py hem metin eşitliğini hem node
// ile davranış eşitliğini kilitler).
//
// AİLELER: aynı jsonl iki bağımsız seri taşır (manuscript + canvas). Badge
// aile BAŞINA son kayda bakar — `rows[-1]`e bakmak taze bir canvas satırı
// için bayat/FAILED manuscript serisini yeşile boyardı (fail-open).
function determinismTrendFamilyOf(row) {
  return row && typeof row.family === "string" && row.family
    ? row.family
    : "manuscript";
}

function determinismTrendBadge(rows) {
  if (!rows || !rows.length) return { cls: "unknown", text: "determinizm: veri yok" };
  const n = rows.length;
  const lastOf = {};
  rows.forEach((r) => { lastOf[determinismTrendFamilyOf(r)] = r; });
  const fams = Object.keys(lastOf);
  const bad = fams.filter((f) => lastOf[f].gate !== "PASS");
  if (!bad.length) return { cls: "ok", text: "✓ DETERMİNİZM PASS · " + n + " ölçüm" };
  if (fams.length === 1) {
    const gate = lastOf[fams[0]].gate;
    return { cls: "warn", text: "⚠️ determinizm gate " + (gate || "?") + " · " + n + " ölçüm" };
  }
  const detail = bad.map((f) => f + " " + (lastOf[f].gate || "?")).join(", ");
  return { cls: "warn", text: "⚠️ determinizm gate " + detail + " · " + n + " ölçüm" };
}

function determinismTrendRowTitle(r) {
  const bits = [String(r.date || "?"), String(r.platform || "?"), determinismTrendFamilyOf(r)];
  if (r.texlive_canonical_sha256) bits.push("texlive " + String(r.texlive_canonical_sha256).slice(0, 8));
  if (r.tectonic_canonical_sha256) bits.push("tectonic " + String(r.tectonic_canonical_sha256).slice(0, 8));
  bits.push("gate " + (r.gate || "?"));
  return bits.join(" · ");
}

function renderDeterminismTrend(rows) {
  const badgeEl = $("det-trend-badge");
  const svg = $("det-trend");
  if (!badgeEl && !svg) return;
  const b = determinismTrendBadge(rows);
  if (badgeEl) {
    badgeEl.textContent = b.text;
    badgeEl.className = "badge " + b.cls;
  }
  if (svg) {
    const have = (rows || []).filter(r => r.date && r.platform != null);
    const W = 1160, H = 90, PAD = 24;
    const xAt = (i, n) => n === 1 ? W / 2 : PAD + (W - 2 * PAD) * i / (n - 1);
    let parts = [];
    if (!have.length) {
      parts.push(`<text x="${W / 2}" y="${H / 2}" fill="#8b949e" font-size="12">veri yok — koşum bekleniyor</text>`);
    } else {
      const n = have.length;
      have.forEach((r, i) => {
        const color = r.gate === "PASS" ? "#3fb950" : "#d29922";
        parts.push(
          `<circle cx="${xAt(i, n).toFixed(1)}" cy="${H / 2}" r="5" fill="${color}">` +
            `<title>${determinismTrendRowTitle(r)}</title></circle>`
        );
      });
      for (let i = 1; i < n; i++) {
        const a = have[i - 1], b2 = have[i];
        if (
          determinismTrendFamilyOf(a) === determinismTrendFamilyOf(b2) &&
          a.texlive_canonical_sha256 === b2.texlive_canonical_sha256 &&
          a.tectonic_canonical_sha256 === b2.tectonic_canonical_sha256
        ) {
          parts.push(`<line x1="${xAt(i - 1, n).toFixed(1)}" y1="${H / 2}" x2="${xAt(i, n).toFixed(1)}" y2="${H / 2}" stroke="#3fb950" stroke-width="2"/>`);
        }
      }
    }
    svg.innerHTML = parts.join("");
  }
}

function loadDeterminismTrend() {
  fetch("/api/determinism-trend").then(r => r.json()).then(data => {
    const rows = Array.isArray(data) ? data : ((data && data.rows) || []);
    renderDeterminismTrend(rows);
  }).catch(() => renderDeterminismTrend([]));
}
'''

HANDLER_CODE = '''    def serve_determinism_trend(self):
        """determinism_trend.jsonl'ı badge'li satırlarla döndür (TeX motor
        determinizm trend paneli — determinism_trend_badge.py üreticisi)."""
        import determinism_trend_badge as dtb
        rows = dtb.rows_from(DETERMINISM_TREND_PATH) or []
        enriched = [dict(r, badge=dtb.badge([r])) for r in rows]
        self._send(200, json.dumps({"badge": dtb.badge(rows),
                                    "rows": enriched},
                                   ensure_ascii=False),
                   content_type="application/json; charset=utf-8")

    def serve_run_history(self):'''


def update_preview():
    changed = []
    if _patch_once(os.path.join(CIKTI, "preview.html"),
                   '  <section>\n    <h2>P0 / P1 trend — son 100 run',
                   HTML_SECTION):
        changed.append("preview.html")
    if _patch_once(os.path.join(CIKTI, "preview.js"),
                   "function loadOverrideTrend() {",
                   JS_CODE + "\nfunction loadOverrideTrend() {"):
        changed.append("preview.js")
    server = os.path.join(CIKTI, "preview_server.py")
    if _patch_once(server,
                   '    if p == "/api/override-trend":\n'
                   '        return "override_trend"\n',
                   '    if p == "/api/override-trend":\n'
                   '        return "override_trend"\n'
                   '    if p == "/api/determinism-trend":\n'
                   '        return "det_trend"\n'):
        changed.append("preview_server.py:route")
    if _patch_once(server, "    def serve_run_history(self):", HANDLER_CODE):
        changed.append("preview_server.py:handler")
    if _patch_once(server,
                   "OVERRIDE_TREND_PATH = None       # main()'de set edilir;"
                   " override-trend.json yolu\n",
                   "OVERRIDE_TREND_PATH = None       # main()'de set edilir;"
                   " override-trend.json yolu\n"
                   "DETERMINISM_TREND_PATH = None    # main()'de set edilir;"
                   " determinism_trend.jsonl yolu\n"):
        changed.append("preview_server.py:global")
    if _patch_once(server,
                   "    OVERRIDE_TREND_PATH = _ot_candidate if os.path.isfile"
                   "(_ot_candidate) else None\n",
                   "    OVERRIDE_TREND_PATH = _ot_candidate if os.path.isfile"
                   "(_ot_candidate) else None\n\n"
                   "    # determinism_trend.jsonl: versiyonlu trend verisi\n"
                   "    # (record_determinism_trend.py üreticisi).\n"
                   "    _dt_candidate = os.path.join(REPO_ROOT, \"docs\",\n"
                   "                                 \"determinism_trend\",\n"
                   "                                 \"determinism_trend.jsonl\")\n"
                   "    DETERMINISM_TREND_PATH = (_dt_candidate\n"
                   "                              if os.path.isfile(_dt_candidate)\n"
                   "                              else None)\n"):
        changed.append("preview_server.py:init")
    contract = os.path.join(CIKTI, "test_api_method_contract.py")
    if _patch_once(server,
                   '        elif route == "override_trend":\n'
                   '            self.serve_override_trend()\n',
                   '        elif route == "override_trend":\n'
                   '            self.serve_override_trend()\n'
                   '        elif route == "det_trend":\n'
                   '            self.serve_determinism_trend()\n'):
        changed.append("preview_server.py:dispatch")
    if _patch_once(contract,
                   '    "/api/override-trend": "/api/override-trend",\n',
                   '    "/api/override-trend": "/api/override-trend",\n'
                   '    "/api/determinism-trend": "/api/determinism-trend",\n'):
        changed.append("test_api_method_contract.py:live-urls")
    if _patch_once(contract,
                   '    "/api/override-trend": {"GET"},\n',
                   '    "/api/override-trend": {"GET"},\n'
                   '    "/api/determinism-trend": {"GET"},\n'):
        changed.append("test_api_method_contract.py:contract")
    if _patch_once(contract,
                   '    "/api/override-trend": \'"override_trend"\',\n',
                   '    "/api/override-trend": \'"override_trend"\',\n'
                   '    "/api/determinism-trend": \'"det_trend"\',\n'):
        changed.append("test_api_method_contract.py:tokens")
    return changed


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--trend", default=TREND, help="determinism_trend.jsonl yolu")
    ap.add_argument("--out-dir", default=DEFAULT_OUT_DIR, help="çıktı dizini")
    ap.add_argument("--update-preview", action="store_true",
                    help="dashboard panel-bağlantısını uygula (idempotent)")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)

    rows = rows_from(args.trend) or []
    os.makedirs(args.out_dir, exist_ok=True)
    with open(os.path.join(args.out_dir, "determinism-trend.svg"), "w",
              encoding="utf-8") as f:
        f.write(svg(rows))
    with open(os.path.join(args.out_dir, "determinism-trend.json"), "w",
              encoding="utf-8") as f:
        json.dump(build_json(rows), f, ensure_ascii=False, indent=1)
    if not args.quiet:
        print("[determinism-trend] svg + json yazıldı: %s (%d ölçüm)"
              % (args.out_dir, len(rows)))
    if args.update_preview:
        for item in update_preview():
            if not args.quiet:
                print("[determinism-trend] panel bağlandı: " + item)
    return 0


if __name__ == "__main__":
    sys.exit(main())
