#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gen_verify_jobs_map.py — verify.yml job needs-DAG'ini Excalidraw'a çevirir.

Tek-koşum jenerator: iş akışındaki `needs` kenarlarını okur, PUBLISH_SCENARIO
tablosundaki A/B/C/D kategorilerini renk olarak eşler ve statik bir Excalidraw
dosyası üretir. Kaynak senkronu fail-closed: workflow job kümesi ile doküman
tablosu birebir eşleşmezse çıkış 1 (sessiz-yeşil yok).

Renkler (PUBLISH_SCENARIO kategorileri):
  A = Gerekli (required check)      → yeşil
  B = Advisory                      → mavi
  C = PR-only (optional)            → turuncu
  D = PR comment                    → mor

Kullanım:
    python3 docs/superpowers/specs/gen_verify_jobs_map.py            # üret/yaz
    python3 docs/superpowers/specs/gen_verify_jobs_map.py --check    # bayat → rc 1

`--check` pre-commit kapısıdır (check-verify-jobs-map): diyagramı YENİDEN
ÜRETİR ve diske yazmadan committed dosyayla BAYT karşılaştırır. verify.yml
veya PUBLISH_SCENARIO.md değişip diyagram yeniden üretilmezse commit bloke
edilir (fail-closed; read-only — dosyaya dokunmaz). Üretim çıktısı zaman
DAMGASI taşımaz: tarih gömen bir çıktı kendi kendini bayatlatır ve
`--check` hiçbir zaman yeşile dönemez (bkz. gen_skill_surface_inventory.py).

Exit: 0 = taze (--check) / yazıldı, 1 = BAYAT veya workflow↔doc senkron
hatası, 2 = ölçüm imkânsız (PyYAML yok, kaynak dosya okunamadı).
"""
import json
import os
import re
import sys

try:
    import yaml
except ImportError:  # kapı ortamında PyYAML olmayabilir — sessiz PASS yok.
    yaml = None

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))

WF = os.path.join(ROOT, ".github", "workflows", "verify.yml")
PS = os.path.join(ROOT, "docs", "PUBLISH_SCENARIO.md")
OUT = os.path.join(ROOT, "docs", "superpowers", "specs",
                   "2026-09-24-verify-jobs-map.excalidraw")
UPD = 1789588800000
SEED0 = 200

W, H = 240, 72           # job kutusu
GAP_X, GAP_Y = 90, 22    # kolon ve satır aralığı
X0, Y0 = 60, 150         # grafik sol-üst köşesi

STYLE = {
    "A": {"strokeColor": "#2b8a3e", "backgroundColor": "#b2f2bb"},
    "B": {"strokeColor": "#1971c2", "backgroundColor": "#a5d8ff"},
    "C": {"strokeColor": "#e8590c", "backgroundColor": "#ffd43b"},
    "D": {"strokeColor": "#9c36b5", "backgroundColor": "#eebefa"},
}

elements = []
_seed = [SEED0]


def seed():
    _seed[0] += 1
    return _seed[0]


def base(kind):
    el = {
        "id": None, "type": kind, "x": 0, "y": 0, "width": 0, "height": 0,
        "angle": 0, "strokeColor": "#1e1e1e", "backgroundColor": "transparent",
        "fillStyle": "solid", "strokeWidth": 2, "strokeStyle": "solid",
        "roughness": 1, "opacity": 100, "groupIds": [], "frameId": None,
        "roundness": None, "seed": seed(), "version": 1, "versionNonce": seed(),
        "isDeleted": False, "boundElements": None, "updated": UPD,
        "link": None, "locked": False,
    }
    return el


def text(t, x, y, w, h, size=16, color="#1e1e1e", align="left", container=None):
    el = base("text")
    el["id"] = "t-%d" % seed()
    el.update({"x": x, "y": y, "width": w, "height": h,
               "text": t, "fontSize": size, "fontFamily": 5,
               "textAlign": align, "verticalAlign": "middle" if container else "top",
               "containerId": container, "lineHeight": 1.25})
    el["strokeColor"] = color
    return el


def box(t, x, y, w, h, cat, size=13):
    el = base("rectangle")
    el["id"] = "b-%d" % seed()
    el.update({"x": x, "y": y, "width": w, "height": h,
               "roundness": {"type": 3}})
    el.update(STYLE[cat])
    lines = wrap(t, 30)
    th = len(lines) * size * 1.25
    tid = "tb-%d" % seed()
    tel = text("\n".join(lines), x + 8, y + (h - th) / 2, w - 16, th,
               size=size, align="center", container=el["id"])
    tel["id"] = tid
    el["boundElements"] = [{"id": tid, "type": "text"}]
    return [el, tel]


def wrap(t, width):
    words, lines, cur = t.split(), [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if len(trial) > width and cur:
            lines.append(cur)
            cur = w
        else:
            cur = trial
    if cur:
        lines.append(cur)
    if len(lines) > 3:
        lines = lines[:3]
        lines[-1] = lines[-1][: width - 1] + "…"
    return lines


def arrow(src, dst, label=None):
    x1 = src["x"] + src["width"]
    y1 = src["y"] + src["height"] / 2
    x2 = dst["x"]
    y2 = dst["y"] + dst["height"] / 2
    el = base("arrow")
    el["id"] = "a-%d" % seed()
    el.update({"x": x1, "y": y1, "width": x2 - x1, "height": y2 - y1,
               "strokeColor": "#343a40",
               "points": [{"x": 0, "y": 0}, {"x": x2 - x1, "y": y2 - y1}],
               "startArrowhead": None, "endArrowhead": "arrow",
               "lastCommittedPoint": None, "startBinding": None,
               "endBinding": None, "elbowed": False})
    out = [el]
    if label:
        out.append(text(label, (x1 + x2) / 2 - 60, (y1 + y2) / 2 - 22, 120, 20,
                        size=13, color="#495057"))
    return out


class MeasurementError(Exception):
    """rc=2: kaynak okunamadı / PyYAML yok — kapı kör, sessiz PASS üretmez."""


class SyncError(Exception):
    """rc=1: workflow ↔ PUBLISH_SCENARIO isim kümesi farklı.

    `lines` insan-okunur ayrıntıdır (workflow-only / doc-only kümeler).
    """

    def __init__(self, lines):
        super().__init__("workflow ↔ PUBLISH_SCENARIO senkron hatası")
        self.lines = lines


def load_sources(wf_path=WF, ps_path=PS):
    """(wf, ps_text) — eksik dosya/PyYAML `MeasurementError` yükseltir."""
    if yaml is None:
        raise MeasurementError(
            "PyYAML yok: verify.yml ayrıştırılamıyor (kapı fail-closed; "
            "sessiz PASS yok). Çözüm: _calisma/.venv_z3 ile koşun.")
    for path in (wf_path, ps_path):
        if not os.path.exists(path):
            raise MeasurementError("kaynak dosya yok: %s" % path)
    try:
        with open(wf_path, encoding="utf-8") as fh:
            wf = yaml.safe_load(fh)
    except (OSError, yaml.YAMLError) as exc:
        raise MeasurementError("verify.yml okunamadı/ayrıştırılamadı: %s" % exc)
    try:
        with open(ps_path, encoding="utf-8") as fh:
            ps_text = fh.read()
    except OSError as exc:
        raise MeasurementError("PUBLISH_SCENARIO.md okunamadı: %s" % exc)
    if not isinstance(wf, dict) or not isinstance(wf.get("jobs"), dict) or not wf["jobs"]:
        raise MeasurementError("verify.yml'de `jobs:` haritası yok/boş: %s" % wf_path)
    return wf, ps_text


def build(wf_path=WF, ps_path=PS):
    """Excalidraw dokümanını + istatistikleri üretir; dosyaya YAZMAZ."""
    elements.clear()
    _seed[0] = SEED0

    wf, ps_text = load_sources(wf_path, ps_path)
    jobs = wf["jobs"]

    # ── 1) kaynaklar ─────────────────────────────────────────────────────────
    rows = re.findall(r"^\|\s*(\d+)\s*\|\s*([ABCD])\s*\|\s*([^|]+?)\s*\|",
                      ps_text, re.M)
    cat_by_name = {name: cat for _, cat, name in rows}

    # fail-closed senkron: workflow ↔ PUBLISH_SCENARIO
    wf_names = {j.get("name") for j in jobs.values()}
    ps_names = set(cat_by_name)
    if wf_names != ps_names:
        raise SyncError([
            "SENKRON HATASI: workflow ↔ PUBLISH_SCENARIO isim kümesi farklı",
            "  workflow-only: %s" % sorted(wf_names - ps_names),
            "  doc-only: %s" % sorted(ps_names - wf_names),
        ])

    # ── 2) katmanlar (en-uzun yol) ───────────────────────────────────────────
    memo = {}

    def layer(jid):
        if jid in memo:
            return memo[jid]
        needs = jobs[jid].get("needs") or []
        if isinstance(needs, str):
            needs = [needs]
        memo[jid] = 0 if not needs else 1 + max(layer(n) for n in needs)
        return memo[jid]

    for jid in jobs:
        layer(jid)

    columns = {}
    for jid in jobs:
        columns.setdefault(memo[jid], []).append(jid)

    # ── 3) yerleşim ──────────────────────────────────────────────────────────
    pos = {}
    max_bottom = 0
    for col in sorted(columns):
        y = Y0
        for jid in columns[col]:
            x = X0 + col * (W + GAP_X)
            pos[jid] = {"x": x, "y": y, "width": W, "height": H}
            elements.extend(box(jobs[jid]["name"], x, y, W, H,
                                cat_by_name[jobs[jid]["name"]]))
            y += H + GAP_Y
        max_bottom = max(max_bottom, y)

    # ── 4) kenarlar ──────────────────────────────────────────────────────────
    for jid in jobs:
        needs = jobs[jid].get("needs") or []
        if isinstance(needs, str):
            needs = [needs]
        for n in needs:
            elements.extend(arrow(pos[n], pos[jid]))

    # ── 5) başlık + gösterge ─────────────────────────────────────────────────
    counts = {}
    for name in cat_by_name.values():
        counts[name] = counts.get(name, 0) + 1
    elements.insert(0, text(
        "verify.yml · Job İlişki Haritası (needs-DAG) — %d job" % len(jobs),
        X0, 20, 760, 36, size=28))
    elements.insert(1, text(
        "ok → needs (bağımlılık) · renk = PUBLISH_SCENARIO kategorisi · "
        "%d A (gerekli) + %d B (advisory) + %d C (PR-only) + %d D (PR comment)"
        % (counts.get("A", 0), counts.get("B", 0), counts.get("C", 0),
           counts.get("D", 0)),
        X0, 64, 900, 20, size=15, color="#495057"))

    ly = max_bottom + 30
    lx = X0
    legend = [
        ("A", "A — Gerekli (required check)"),
        ("B", "B — Advisory"),
        ("C", "C — PR-only (optional)"),
        ("D", "D — PR comment"),
    ]
    for cat, label in legend:
        elements.extend(box(label, lx, ly, 250, 44, cat, size=14))
        lx += 270

    doc = {
        "type": "excalidraw",
        "version": 2,
        "source": "https://excalidraw.com",
        "elements": elements,
        "appState": {"viewBackgroundColor": "#ffffff", "gridSize": 20},
        "files": {},
    }
    n_arrows = sum(1 for e in elements if e["type"] == "arrow")
    stats = {
        "jobs": len(jobs), "layers": len(columns), "arrows": n_arrows,
        "elements": len(elements),
        "columns": {c: len(v) for c, v in sorted(columns.items())},
    }
    return doc, stats


def render(doc):
    """Diske yazılan/karşılaştırılan kanonik metin (zaman damgası YOK)."""
    return json.dumps(doc, ensure_ascii=False, indent=2) + "\n"


def _job_titles(doc):
    """Diyagramdaki job kutusu metinleri (drift raporu için)."""
    ids = {e["id"] for e in doc.get("elements", [])
           if e.get("type") == "rectangle" and e.get("id")}
    out = []
    for e in doc.get("elements", []):
        if e.get("type") == "text" and e.get("containerId") in ids:
            out.append(e.get("text", ""))
    return out


def _drift_lines(committed_text, fresh_text):
    """Bayat diyagram raporu: hangi job kutuları değişti (sınırlı çıktı)."""
    import difflib
    try:
        old = _job_titles(json.loads(committed_text))
        new = _job_titles(json.loads(fresh_text))
    except (ValueError, TypeError):
        return ["  (committed dosya JSON olarak okunamadı — elle üretilmiş olabilir)"]
    delta = [ln for ln in difflib.unified_diff(old, new, "committed", "fresh",
                                               lineterm="", n=0)]
    if not delta:
        return ["  metin kutuları aynı: drift başlık/konum/kenar düzeyinde"]
    head = delta[:14]
    head = ["  " + ln for ln in head]
    if len(delta) > 14:
        head.append("  … (+%d satır)" % (len(delta) - 14))
    return head


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    check = "--check" in args
    unknown = [a for a in args if a != "--check"]
    if unknown:
        print("kullanım: %s [--check]" % os.path.basename(__file__))
        return 2

    try:
        doc, stats = build()
    except MeasurementError as exc:
        print("HATA (ölçüm imkânsız): %s" % exc)
        print("SONUÇ: FAIL (rc=2) — kapı kör; sessiz PASS yok.")
        return 2
    except SyncError as exc:
        print("SONUÇ: FAIL — %s" % exc)
        for ln in exc.lines:
            print(ln)
        print("  çözüm: yeni/yeniden adlanan job'ı PUBLISH_SCENARIO tablosuna "
              "işleyin (ya da tersini).")
        return 1

    payload = render(doc)
    rel_out = os.path.relpath(OUT, ROOT)

    if not check:
        with open(OUT, "w", encoding="utf-8") as fh:
            fh.write(payload)
        print("jobs=%d layers=%d arrows=%d elements=%d" % (
            stats["jobs"], stats["layers"], stats["arrows"], stats["elements"]))
        print("kolonlar:", stats["columns"])
        print("OUT:", rel_out)
        return 0

    # ── --check: BAYT karşılaştırması (read-only, fail-closed) ───────────────
    if not os.path.exists(OUT):
        print("SONUÇ: FAIL — diyagram yok: %s" % rel_out)
        print("  çözüm: python3 %s && git add %s"
              % (os.path.join("docs", "superpowers", "specs",
                              "gen_verify_jobs_map.py"), rel_out))
        return 1
    try:
        with open(OUT, encoding="utf-8") as fh:
            committed = fh.read()
    except OSError as exc:
        print("HATA (ölçüm imkânsız): %s okunamadı: %s" % (rel_out, exc))
        return 2

    if committed == payload:
        print("PASS: diyagram taze (%s · %d job · %d eleman)"
              % (rel_out, stats["jobs"], stats["elements"]))
        return 0

    print("SONUÇ: FAIL — diyagram BAYAT (verify.yml/PUBLISH_SCENARIO ile "
          "uyuşmuyor): %s" % rel_out)
    for ln in _drift_lines(committed, payload):
        print(ln)
    print("  çözüm: python3 docs/superpowers/specs/gen_verify_jobs_map.py "
          "&& git add %s" % rel_out)
    return 1


if __name__ == "__main__":
    sys.exit(main())
