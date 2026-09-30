#!/usr/bin/env python3
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
"""
import json
import re
import sys

import yaml

WF = ".github/workflows/verify.yml"
PS = "docs/PUBLISH_SCENARIO.md"
OUT = "docs/superpowers/specs/2026-09-24-verify-jobs-map.excalidraw"
UPD = 1789588800000

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
_seed = [200]


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


# ── 1) kaynaklar ─────────────────────────────────────────────────────────────
wf = yaml.safe_load(open(WF, encoding="utf-8"))
jobs = wf["jobs"]

ps_text = open(PS, encoding="utf-8").read()
rows = re.findall(r"^\|\s*(\d+)\s*\|\s*([ABCD])\s*\|\s*([^|]+?)\s*\|", ps_text, re.M)
cat_by_name = {name: cat for _, cat, name in rows}

# fail-closed senkron: workflow ↔ PUBLISH_SCENARIO
wf_names = {j.get("name") for j in jobs.values()}
ps_names = set(cat_by_name)
if wf_names != ps_names:
    print("SENKRON HATASI: workflow ↔ PUBLISH_SCENARIO isim kümesi farklı")
    print("  workflow-only:", sorted(wf_names - ps_names))
    print("  doc-only:", sorted(ps_names - wf_names))
    sys.exit(1)

# ── 2) katmanlar (en-uzun yol) ───────────────────────────────────────────────
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

# ── 3) yerleşim ──────────────────────────────────────────────────────────────
pos = {}
max_bottom = 0
for col in sorted(columns):
    y = Y0
    for jid in columns[col]:
        x = X0 + col * (W + GAP_X)
        pos[jid] = {"x": x, "y": y, "width": W, "height": H}
        elements.extend(box(jobs[jid]["name"], x, y, W, H, cat_by_name[jobs[jid]["name"]]))
        y += H + GAP_Y
    max_bottom = max(max_bottom, y)

# ── 4) kenarlar ──────────────────────────────────────────────────────────────
for jid in jobs:
    needs = jobs[jid].get("needs") or []
    if isinstance(needs, str):
        needs = [needs]
    for n in needs:
        elements.extend(arrow(pos[n], pos[jid]))

# ── 5) başlık + gösterge ─────────────────────────────────────────────────────
counts = {}
for name in cat_by_name.values():
    counts[name] = counts.get(name, 0) + 1
elements.insert(0, text(
    "verify.yml · Job İlişki Haritası (needs-DAG) — %d job" % len(jobs),
    X0, 20, 760, 36, size=28))
elements.insert(1, text(
    "ok → needs (bağımlılık) · renk = PUBLISH_SCENARIO kategorisi · "
    "%d A (gerekli) + %d B (advisory) + %d C (PR-only) + %d D (PR comment)"
    % (counts.get("A", 0), counts.get("B", 0), counts.get("C", 0), counts.get("D", 0)),
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
with open(OUT, "w", encoding="utf-8") as f:
    json.dump(doc, f, ensure_ascii=False, indent=2)
    f.write("\n")

n_arrows = sum(1 for e in elements if e["type"] == "arrow")
print("jobs=%d layers=%d arrows=%d elements=%d" % (
    len(jobs), len(columns), n_arrows, len(elements)))
print("kolonlar:", {c: len(v) for c, v in sorted(columns.items())})
print("OUT:", OUT)
