#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""report_token_contrast.py — statik WCAG kontrast denetimi (Vercel + pano).

Neden: erişilebilirlik kontrastı bugüne kadar yalnız **runtime** axe kapısıyla
(`a11y_gate.py`, tarayıcı + DOM) ölçülüyordu. O kapı yalnız gerçekten RENDER
edilen düğümleri görür; token paletinin kendi içinde tanımlı ama o an ekranda
olmayan rol çiftleri (ör. Vercel varyantında bir success tonunun açık yüzey
üzerinde okunması) hiç ölçülmez. Bu araç aynı paleti **statik** ölçer:
`var()` zincirini, `color-mix(in srgb, …)` türevlerini ve alfa bindirmesini
çözüp WCAG 2.1 bağıl parlaklık formülünü uygular. Tarayıcı yok, ağ yok.

Kapsam (paletler):
  1. `dashboard-dark`  — design-system/tokens.css `:root`
  2. `dashboard-light` — aynı dosyanın `:root[data-theme="light"]` bindirmesi
  3. `vercel-variant`  — pano açık rolleriyle `:root[data-theme="vercel"]`
                         (design-system/vercel/theme.css; koyu taban + varyant)
  4. `vercel-mirror`   — Vercel'in KENDİ ışık yakalaması
                         (design-system/vercel/tokens.css, 19 token)

Ölçüm kuralları:
  * Oran: (L_açık + 0.05) / (L_koyu + 0.05), L = WCAG bağıl parlaklık.
  * Eşikler: `text` 4.5 (AA) · `large` 3.0 (≥18.66px kalın / ≥24px, AA) ·
    `ui` 3.0 (WCAG 1.4.11 non-text) · AAA 7.0 raporlanır ama bloklamaz.
  * Yarı saydam ön plan/arka plan, eşleşmede bildirilen yüzeye bindirilir
    (`over`); `color-mix(… , transparent)` alfası korunur.
  * Çözülemeyen değer sessizce atlanmaz: `unresolved` olarak raporlanır.

Ayrıca paletin KENDİ sayısal iddialarını (tokens.css yorumlarındaki
"AA 4.5:1", "5.78:1", "7.49:1" gibi) yeniden ölçüp karşılaştırır — beyan ile
ölçüm ayrışırsa `claim` bulgusu düşer.

Kullanım:
    python3 design-system/scripts/report_token_contrast.py            # tablo
    python3 design-system/scripts/report_token_contrast.py --json     # tek JSON (stdout)
    python3 design-system/scripts/report_token_contrast.py --md-out P # markdown rapor
    python3 design-system/scripts/report_token_contrast.py --check    # tazelik + eşik
    python3 design-system/scripts/report_token_contrast.py --selftest # WCAG referansları
    python3 design-system/scripts/report_token_contrast.py --base HEAD  # farklı taban

Rapor, girdilerin `--base` (varsayılan HEAD) ile ilişkisini de yazar
(`aynı` / `FARKLI` / `ref'te yok`): bayat çalışma ağacı dosyası ölçümü
kaydırabilir ve bu raporda gizlenmez.

Exit: 0 = eşik ihlali yok, 1 = ihlal/bayat rapor, 2 = kullanım/ölçüm hatası.
OFFLINE, READ-ONLY, stdlib-only.
"""
import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent

TOKENS = "design-system/tokens.css"
VERCEL_THEME = "design-system/vercel/theme.css"
VERCEL_MIRROR = "design-system/vercel/tokens.css"
REPORT_PATH = "_calisma/CIKTI/KONTRAST_DENETIMI_RAPORU.md"

SCHEMA = "token-contrast/1"
BASE_REF = "HEAD"

# Eşikler (WCAG 2.1): AA metin 4.5, büyük metin/UI 3.0, AAA metin 7.0.
TEXT_AA = 4.5
LARGE_AA = 3.0
TEXT_AAA = 7.0

COMMENT_RE = re.compile(r"/\*.*?\*/", re.S)
BLOCK_RE = re.compile(r"([^{}]+)\{([^{}]*)\}", re.S)
DECL_RE = re.compile(r"(--[\w-]+)\s*:\s*([^;]+)")
NAMED = {"white": (255.0, 255.0, 255.0), "black": (0.0, 0.0, 0.0)}

# Palet → çift listesi. Çift: (ön plan yuvası, arka plan yuvası, tür, over, not)
# `kind`: text (4.5) · large (3.0) · ui (3.0, 1.4.11 non-text)
KIND_MIN = {"text": TEXT_AA, "large": LARGE_AA, "ui": LARGE_AA}


class MeasurementError(Exception):
    pass


# ── CSS okuma ─────────────────────────────────────────────────────────────
def read_blocks(rel):
    """{selector: {var: value}} — dosya başına blok sözlüğü."""
    path = REPO / rel
    if not path.is_file():
        raise MeasurementError("dosya yok: %s" % rel)
    text = COMMENT_RE.sub("", path.read_text(encoding="utf-8"))
    out = {}
    for sel, body in BLOCK_RE.findall(text):
        decls = {name: re.sub(r"\s+", " ", value).strip()
                 for name, value in DECL_RE.findall(body)}
        if not decls:
            continue
        out.setdefault(re.sub(r"\s+", " ", sel).strip(), {}).update(decls)
    return out


def sha256(rel):
    return hashlib.sha256((REPO / rel).read_bytes()).hexdigest()


def git_file(rel, ref):
    """(durum, içerik): durum ∈ ok|missing|nogit|error.

    "missing" (ref'te yok) ile "nogit" (git kurulu değil/bilinmiyor)
    AYRI tutulur: bilinmeyeni "yok" diye raporlamak yanlış olurdu.
    """
    import subprocess
    for pre in (["git", "-C", str(REPO)],
                ["git", "--git-dir=%s/.git" % REPO, "--work-tree=%s" % REPO]):
        try:
            proc = subprocess.run(pre + ["show", "%s:%s" % (ref, rel)],
                                  capture_output=True, text=True)
        except OSError:
            return "nogit", None
        if proc.returncode == 0:
            return "ok", proc.stdout
        if "not a git repository" in proc.stderr:
            continue
        return "missing", None               # ref'te bu yol yok
    return "error", None


def revision_info(ref):
    """Her girdi için: same | differ | absent (çalışma ağacı vs <ref>).

    Bayat çalışma ağacı dosyası raporu yanıltmasın diye ölçüm tabanı
    gizlenmez; fark varsa raporda görünür.
    """
    out = {}
    for rel in (TOKENS, VERCEL_THEME, VERCEL_MIRROR):
        state, ref_text = git_file(rel, ref)
        if state != "ok":
            out[rel] = {"missing": "absent"}.get(state, "unknown")
        elif ref_text == (REPO / rel).read_text(encoding="utf-8"):
            out[rel] = "same"
        else:
            out[rel] = "differ"
    return {"base": ref, "inputs": out}


def chain(*maps):
    """Palet = taban + bindirmeler (sonraki kazanır)."""
    out = {}
    for m in maps:
        out.update(m)
    return out


# ── renk çözümleme ────────────────────────────────────────────────────────
def parse_color(value):
    """(r, g, b, a) → 0-255 float + alfa 0-1. Çözülemezse None."""
    v = value.strip()
    if v in NAMED:
        return NAMED[v] + (1.0,)
    if v == "transparent":
        return (0.0, 0.0, 0.0, 0.0)
    m = re.fullmatch(r"#([0-9a-fA-F]{3,8})", v)
    if m:
        h = m.group(1)
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        if len(h) == 4:
            h = "".join(c * 2 for c in h)
        if len(h) == 6:
            h += "ff"
        if len(h) != 8:
            return None
        return (float(int(h[0:2], 16)), float(int(h[2:4], 16)),
                float(int(h[4:6], 16)), int(h[6:8], 16) / 255.0)
    m = re.fullmatch(r"rgba?\(([^)]+)\)", v)
    if m:
        parts = [p.strip() for p in m.group(1).replace("/", " ").split(",")]
        parts = [p for p in re.split(r"[\s,]+", m.group(1)) if p]
        if len(parts) not in (3, 4):
            return None
        try:
            r, g, b = (float(p.rstrip("%")) * (2.55 if p.endswith("%") else 1.0)
                       for p in parts[:3])
            a = float(parts[3]) if len(parts) == 4 else 1.0
        except ValueError:
            return None
        return (r, g, b, a)
    m = re.fullmatch(r"hsla?\(([^)]+)\)", v)
    if m:
        parts = [p for p in re.split(r"[\s,]+", m.group(1)) if p]
        if len(parts) < 3:
            return None
        try:
            h = float(parts[0].rstrip("deg")) % 360
            s = float(parts[1].rstrip("%")) / 100.0
            li = float(parts[2].rstrip("%")) / 100.0
            a = float(parts[3]) if len(parts) > 3 else 1.0
        except ValueError:
            return None
        return _hsl(h, s, li) + (a,)
    if v.startswith("color-mix("):
        return resolve_mix(v, None)
    return None


def _hsl(h, s, li):
    def ch(n):
        k = (n + h / 30.0) % 12
        a = s * min(li, 1 - li)
        return (li - a * max(-1.0, min(k - 3, 9 - k, 1))) * 255.0
    return (ch(0), ch(8), ch(4))


def _split_top(text):
    """Virgülleri parantez derinliğine göre ayır (color-mix argümanları)."""
    out, depth, cur = [], 0, ""
    for ch in text:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            out.append(cur.strip())
            cur = ""
            continue
        cur += ch
    out.append(cur.strip())
    return [p for p in out if p]


def resolve_mix(value, slots):
    """`color-mix(in srgb, C p%, C2 [p2%])` → (r, g, b, a).

    srgb karışımı premultiplied alfa ile yapılır: `transparent` ikinci renk
    olarak verildiğinde sonuç alfası p olur (tint reçetesi).
    """
    inner = value.strip()[len("color-mix("):-1]
    args = _split_top(inner)
    if len(args) < 3 or not args[0].startswith("in "):
        return None
    colors, weights = [], []
    for arg in args[1:]:
        parts = arg.split()
        w = None
        if len(parts) > 1 and parts[-1].endswith("%"):
            try:
                w = float(parts[-1][:-1]) / 100.0
            except ValueError:
                return None
            parts = parts[:-1]
        colors.append(" ".join(parts))
        weights.append(w)
    if len(colors) != 2:
        return None
    p1, p2 = weights[0], weights[1]
    if p1 is None and p2 is None:
        p1 = p2 = 0.5
    elif p1 is None:
        p1 = 1.0 - p2
    elif p2 is not None:
        return None
    p1 = max(0.0, min(1.0, p1))
    p2 = 1.0 - p1
    ca, cb = (parse_color(c) if not c.startswith("var(") else None
              for c in colors)
    if ca is None or cb is None:
        m = re.fullmatch(r"var\((--[\w-]+)\)", colors[0])
        if m and slots and m.group(1) in slots:
            ca = resolve(slots[m.group(1)], slots)
        m = re.fullmatch(r"var\((--[\w-]+)\)", colors[1])
        if m and slots and m.group(1) in slots:
            cb = resolve(slots[m.group(1)], slots)
    if ca is None or cb is None:
        return None
    alpha = ca[3] * p1 + cb[3] * p2
    if alpha == 0:
        return (0.0, 0.0, 0.0, 0.0)
    return tuple(
        (ca[i] * ca[3] * p1 + cb[i] * cb[3] * p2) / alpha for i in range(3)
    ) + (alpha,)


def resolve(value, slots, _depth=0):
    """Yuva değerini literale indir: var() zinciri + color-mix. None = çözülemedi."""
    if _depth > 12:
        return None
    v = value.strip()
    m = re.fullmatch(r"var\((--[\w-]+)\)", v)
    if m:
        if m.group(1) not in slots:
            return None
        return resolve(slots[m.group(1)], slots, _depth + 1)
    if v.startswith("color-mix("):
        return resolve_mix(v, slots)
    return parse_color(v)


def over(fg, bg):
    """fg'yi bg üzerine bindir (alfa kompozisyon)."""
    if fg[3] >= 1.0:
        return fg
    a = fg[3]
    return tuple(fg[i] * a + bg[i] * (1 - a) for i in range(3)) + (1.0,)


# ── WCAG ──────────────────────────────────────────────────────────────────
def luminance(rgb):
    def ch(x):
        x = x / 255.0
        return x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4
    r, g, b = (ch(v) for v in rgb[:3])
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a, b):
    hi, lo = sorted((luminance(a), luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def hexof(rgb):
    return "#%02x%02x%02x" % tuple(int(round(max(0.0, min(255.0, c))))
                                   for c in rgb[:3])


# ── paletler ve çiftler ───────────────────────────────────────────────────
def build_palettes():
    tok = read_blocks(TOKENS)
    theme = read_blocks(VERCEL_THEME)
    mirror = read_blocks(VERCEL_MIRROR)
    dark = tok.get(":root", {})
    light = chain(dark, tok.get(':root[data-theme="light"]', {}))
    vercel = chain(dark, theme.get(':root[data-theme="vercel"]', {}))
    if not dark:
        raise MeasurementError("design-system/tokens.css: :root bloğu yok")
    if ':root[data-theme="light"]' not in tok:
        raise MeasurementError("design-system/tokens.css: light bloğu yok")
    if ':root[data-theme="vercel"]' not in theme:
        raise MeasurementError("vercel/theme.css: varyant bloğu yok")
    vercel_mirror = mirror.get(":root", {})
    if not vercel_mirror:
        raise MeasurementError("vercel/tokens.css: :root bloğu yok")
    return {
        "dashboard-dark": dark,
        "dashboard-light": light,
        "vercel-variant": vercel,
        "vercel-mirror": vercel_mirror,
    }


SURFACES = ("--bg", "--surface-1", "--surface-2")
FG_ROLES = ("--fg", "--muted", "--fg-dimmed", "--accent", "--ok", "--warn",
            "--err", "--budget")
TINTS = (("--err", "--tint-err-bg"), ("--ok", "--tint-ok-bg"),
         ("--warn", "--tint-warn-bg"), ("--budget", "--tint-budget-bg"),
         ("--accent", "--tint-accent-bg"))

# Varyantın ilan edilmiş istisnaları: bu yuvalar Vercel aynasında kaynak
# bulamadığı için tanımlanmaz ve KOYU taban paletten gelir (vercel/theme.css).
VERCEL_EXCEPTION_SLOTS = ("--ok", "--warn", "--tint-ok-bg", "--tint-warn-bg")

# Denetlenmeyen token'lar: savunulabilir bir rol çifti YOK (uydurma eşleşme
# yazmak yerine gerekçesiyle listelenir).
NOT_AUDITED = (
    ("vercel-mirror", "--geist-selection-text-color",
     "seçim yüzeyi (selection background) yakalanmadı; metin tonu yalnız "
     "o yüzeyin üzerinde anlamlıdır"),
)


# Çift: (fg, bg, kind, over, note, gerekli)
# `gerekli=False` → WCAG 1.4.11 kapsamı DIŞI (dekoratif ayırıcı/kenarlık):
# ölçüm raporlanır ama eşik ihlali sayılmaz.
def pairs_for(name):
    """Palet başına (fg, bg, kind, over, note, gerekli) çift listesi."""
    if name == "vercel-mirror":
        bg = "--color-background-100"
        return [
            ("--color-gray-1000", bg, "text", None, "Vercel varsayılan metni", True),
            ("--color-gray-900", bg, "text", None, "ikincil metin (gri-900)", True),
            ("--color-gray-800", bg, "large", None,
             "ipucu/ikincil ton — büyük metin varsayımı (AA 3.0)", True),
            ("--color-gray-700", bg, "large", None,
             "ipucu/ikincil ton — büyük metin varsayımı (AA 3.0)", True),
            ("--color-gray-600", bg, "large", None,
             "ipucu/ikincil ton — büyük metin varsayımı (AA 3.0)", True),
            ("--ship-text", bg, "text", None,
             "üretim (ship) kırmızısı — beyaz üzerinde metin", True),
            ("--develop-text", bg, "text", None, "geliştirme (develop) mavisi", True),
            ("--preview-text", bg, "text", None, "önizleme (preview) pembesi", True),
            ("--geist-console-text-color-default", bg, "text", None,
             "konsol metni", True),
            ("--geist-console-text-color-blue", bg, "text", None,
             "konsol mavi", True),
            ("--geist-console-text-color-purple", bg, "text", None,
             "konsol mor", True),
            ("--geist-console-text-color-pink", bg, "text", None,
             "konsol pembe", True),
            ("--color-gray-500", bg, "ui", None,
             "ayırıcı/kenar — dekoratif", False),
            ("--color-gray-300", bg, "ui", None,
             "yüzey kenarı — dekoratif", False),
            ("--color-gray-200", bg, "ui", None,
             "yüzey ayrımı — dekoratif", False),
            ("--color-gray-alpha-400", bg, "ui", None,
             "alfa kenarlık — dekoratif (alfa beyaza bindirilir)", False),
            ("--ds-focus-color", bg, "ui", None,
             "odak halkası (1.4.11 — gerekli)", True),
            ("--ds-focus-color", "--color-gray-200", "ui", None,
             "odak halkası / gri yüzey (gerekli)", True),
        ]
    out = []
    for role in FG_ROLES:
        for surface in SURFACES:
            out.append((role, surface, "text", None,
                        "%s / %s" % (role, surface), True))
    for role, tint in TINTS:
        out.append((role, tint, "text", "--surface-1",
                    "%s / kendi tint'i (yüzey-1 üzerine)" % role, True))
        out.append((role, tint, "text", "--bg",
                    "%s / kendi tint'i (bg üzerine)" % role, True))
    out += [
        ("--on-accent", "--accent", "text", None, "buton etiketi / accent", True),
        ("--paper-ink", "--paper", "text", None, "kâğıt paneli metni", True),
        ("--fg", "--code-bg", "text", None, "kod bloğu metni", True),
        ("--fg", "--header-start", "text", None, "başlık metni / header başı", True),
        ("--fg", "--header-end", "text", None, "başlık metni / header sonu", True),
        ("--border", "--bg", "ui", None,
         "ayırıcı kenarlık — dekoratif", False),
        ("--border", "--surface-1", "ui", None,
         "kart kenarlığı — dekoratif", False),
        ("--border", "--surface-2", "ui", None,
         "düğme kenarlığı (yüzey-2) — dekoratif", False),
        ("--accent", "--bg", "ui", None,
         "odak halkası (1.4.11 — gerekli)", True),
        ("--accent", "--surface-1", "ui", None,
         "odak halkası / yüzey-1 (gerekli)", True),
    ]
    return out


# Paletin kendi beyan ettiği sayısal iddialar (tokens.css yorumları).
# (palet, fg, bg, over, iddia, kaynak metin)
CLAIMS = (
    ("dashboard-dark", "--fg-dimmed", "--bg", None, TEXT_AA, "min",
     "--fg-dimmed: AA 4.5:1 bg üzerinde"),
    ("dashboard-dark", "--err", "--tint-err-bg", "--surface-1", 5.78, "pin",
     "--err: on-tint 5.78:1 (eski #f85149 4.35 fail)"),
    ("dashboard-dark", "--on-accent", "--accent", None, 7.49, "pin",
     "--on-accent: accent üzerinde 7.49:1 (beyaz 2.52 fail)"),
    ("dashboard-light", "--fg-dimmed", "--bg", None, TEXT_AA, "min",
     "--fg-dimmed: light bg üzerinde AA 4.5:1+"),
    ("dashboard-light", "--on-accent", "--accent", None, 5.53, "pin",
     "--on-accent: accent üzerinde 5.53:1"),
)


def measure(name, palette, fg_role, bg_role, over_role):
    """(ratio, fg_hex, bg_hex) — çözülemeyen yuva None döner."""
    missing = [s for s in (fg_role, bg_role, over_role)
               if s and s not in palette]
    if missing:
        return None, missing
    fg = resolve(palette[fg_role], palette)
    bg = resolve(palette[bg_role], palette)
    if fg is None or bg is None:
        return None, [s for s, c in ((fg_role, fg), (bg_role, bg)) if c is None]
    base = resolve(palette[over_role], palette) if over_role else None
    if over_role and base is None:
        return None, [over_role]
    if base is not None:
        bg = over(bg, base)
    fg_flat = over(fg, bg) if fg[3] < 1.0 else fg
    return contrast(fg_flat, bg), (fg_flat, bg)


def audit():
    palettes = build_palettes()
    rows, skipped = [], []
    for name in ("dashboard-dark", "dashboard-light", "vercel-variant",
                 "vercel-mirror"):
        palette = palettes[name]
        for fg_role, bg_role, kind, over_role, note, required in pairs_for(name):
            ratio, payload = measure(name, palette, fg_role, bg_role, over_role)
            if ratio is None:
                skipped.append({"palette": name, "fg": fg_role, "bg": bg_role,
                                "missing": payload})
                continue
            fg_flat, bg_flat = payload
            rows.append({
                "palette": name, "fg": fg_role, "bg": bg_role, "kind": kind,
                "over": over_role, "note": note, "required": required,
                "ratio": round(ratio, 4),
                "fg_hex": hexof(fg_flat), "bg_hex": hexof(bg_flat),
                "min": KIND_MIN[kind],
                "meets_min": ratio >= KIND_MIN[kind],
                "identical": abs(ratio - 1.0) < 0.01,
                "meets_text_aa": ratio >= TEXT_AA,
                "meets_text_aaa": ratio >= TEXT_AAA,
            })
    claims = []
    for name, fg_role, bg_role, over_role, claim, mode, source in CLAIMS:
        ratio, payload = measure(name, palettes[name], fg_role, bg_role,
                                 over_role)
        if ratio is None:
            skipped.append({"palette": name, "fg": fg_role, "bg": bg_role,
                            "missing": payload})
            continue
        claims.append({
            "palette": name, "pair": "%s / %s" % (fg_role, bg_role),
            "claimed": claim, "mode": mode, "measured": round(ratio, 4),
            "ok": ratio + 0.005 >= claim, "source": source,
        })
    findings = [r for r in rows if not r["meets_min"] and r["required"]]
    advisory = [r for r in rows if not r["meets_min"] and not r["required"]]
    claim_drift = [c for c in claims if not c["ok"]]
    counts = {
        "pairs": len(rows), "skipped": len(skipped),
        "fail_required": len(findings),
        "advisory_below": len(advisory),
        "identical": sum(1 for r in rows if r["identical"]),
        "text_rows_below_aa": sum(1 for r in rows
                                  if r["kind"] == "text"
                                  and not r["meets_text_aa"]),
        "claim_drift": len(claim_drift),
    }
    counts["fail_min"] = counts["fail_required"] + counts["advisory_below"]
    doc = {
        "schema": SCHEMA,
        "status": "ok" if not findings and not claim_drift else "findings",
        "counts": counts,
        "inputs": {rel: sha256(rel) for rel in (TOKENS, VERCEL_THEME,
                                                VERCEL_MIRROR)},
        "palettes": {name: sorted(palettes[name]) for name in palettes},
        "thresholds": {"text_aa": TEXT_AA, "large_aa": LARGE_AA,
                       "text_aaa": TEXT_AAA},
        "revision": revision_info(BASE_REF),
        "vercel_exceptions": list(VERCEL_EXCEPTION_SLOTS),
        "palette_summary": palette_summary(rows),
        "boundary_pairs": boundary_pairs(rows),
        "worst": min((r for r in rows if r["required"]),
                      key=lambda r: r["ratio"], default=None),
        "not_audited": [{"palette": p, "token": t, "reason": " ".join(r.split())}
                        for p, t, r in NOT_AUDITED],
        "rows": rows, "skipped": skipped, "claims": claims,
    }
    return doc


# ── rapor ─────────────────────────────────────────────────────────────────
PALETTE_TITLE = {
    "dashboard-dark": "Pano — koyu (`:root`)",
    "dashboard-light": "Pano — açık (`:root[data-theme=\"light\"]`)",
    "vercel-variant": "Vercel varyantı (pano açık rolleriyle, `:root[data-theme=\"vercel\"]`)",
    "vercel-mirror": "Vercel aynası (kendi ışık yakalaması, 19 token)",
}


def suff(n):
    """Türkçe sayı eki (son basamağın ünlü uyumu): 0'ı, 9'u, 24'ü."""
    return {"0": "ı", "1": "i", "2": "i", "3": "ü", "4": "ü",
            "5": "i", "6": "ı", "7": "i", "8": "i", "9": "u"}[str(n)[-1]]


def palette_summary(rows):
    """Palet başına gerekli rol skoru (dekoratif çiftler sayılmaz)."""
    out = {}
    for r in rows:
        if not r["required"]:
            continue
        s = out.setdefault(r["palette"], {"required": 0, "fail": 0})
        s["required"] += 1
        if not r["meets_min"]:
            s["fail"] += 1
    for name, s in out.items():
        s["verdict"] = "pass" if s["fail"] == 0 else "fail"
    return out


def boundary_pairs(rows):
    """AA (4.5) sınırına pinli metin çiftleri — pay yok demektir."""
    return [{"palette": r["palette"], "fg": r["fg"], "bg": r["bg"],
             "ratio": r["ratio"]}
            for r in rows if r["required"] and r["kind"] == "text"
            and TEXT_AA <= r["ratio"] < TEXT_AA + 0.02]


def render_md(doc):
    lines = [
        "# Kontrast denetimi — Vercel + pano (koyu/açık)",
        "",
        "Statik WCAG 2.1 ölçümü (`design-system/scripts/report_token_contrast.py`).",
        "Tarayıcı yok; `var()` zinciri, `color-mix(in srgb, …)` türevleri ve alfa",
        "bindirmesi çözülür. Eşikler: metin **4.5** (AA), büyük metin/UI **3.0**",
        "(WCAG 1.4.11), AAA **7.0** (raporlanır, bloklamaz).",
        "",
        "## Girdiler (sha256)",
        "",
        "| Kaynak | sha256 |",
        "|---|---|",
    ]
    for rel, digest in sorted(doc["inputs"].items()):
        lines.append("| `%s` | `%s` |" % (rel, digest[:16]))
    rev = doc.get("revision", {"base": "?", "inputs": {}})
    lines += ["", "## Revizyon tabanı (`%s`)" % rev["base"], "",
              "| Kaynak | Çalışma ağacı ↔ %s |" % rev["base"], "|---|---|"]
    for rel, state in sorted(rev["inputs"].items()):
        lines.append("| `%s` | %s |" % (rel, {
            "same": "aynı ✅",
            "differ": "**FARKLI** ⚠️ (ölçüm çalışma ağacından; commit'li palet sapıyor)",
            "absent": "**ref'te yok** ⚠️ (commit'siz dosya)",
            "unknown": "**bilinmiyor** (git yok/başarısız — taban ölçülemedi)",
        }.get(state, state)))
    c = doc["counts"]
    lines += [
        "",
        "## Özet",
        "",
        "- ölçülen çift: **%d** · çözülemeyen: %d" % (c["pairs"], c["skipped"]),
        "- **gerekli** eşik altında: **%d** · yalnız uyarı (dekoratif ayırıcı): %d"
        % (c["fail_required"], c["advisory_below"]),
        "- `kind=text` çiftlerinden AA (4.5) altında: **%d**"
        % c["text_rows_below_aa"],
        "- birebir aynı renk çifti (görünmez ayırıcı riski): **%d**"
        % c["identical"],
        "- beyan↔ölçüm sapması: **%d**" % c["claim_drift"],
        "- Vercel varyantının ilan edilmiş istisnaları (koyu tabandan gelir): "
        + ", ".join("`%s`" % s for s in doc["vercel_exceptions"]),
        "",
    ]
    per_palette = {}
    for row in doc["rows"]:
        per_palette.setdefault(row["palette"], []).append(row)
    for name in ("dashboard-dark", "dashboard-light", "vercel-variant",
                 "vercel-mirror"):
        rows = per_palette.get(name, [])
        fails = [r for r in rows if not r["meets_min"]]
        lines += ["## %s" % PALETTE_TITLE[name], "",
                  "%d çift · rol eşiği altında %d" % (len(rows), len(fails)), "",
                  "| Ön plan | Arka plan | Tür | Oran | Eşik | AA metin | AAA |",
                  "|---|---|---|---|---|---|---|"]
        for r in sorted(rows, key=lambda r: r["ratio"]):
            mark = ("✅" if r["meets_min"]
                    else ("❌" if r["required"] else "⚠️"))
            lines.append("| `%s` | `%s`%s | %s | **%.2f** %s | %.1f | %s | %s |"
                         % (r["fg"], r["bg"],
                            " (üzerine: `%s`)" % r["over"] if r["over"] else "",
                            r["kind"], r["ratio"], mark, r["min"],
                            "✅" if r["meets_text_aa"] else "❌",
                            "✅" if r["meets_text_aaa"] else "—"))
        lines.append("")
    if doc["skipped"]:
        lines += ["## Çözülemeyen çiftler (sessiz atlama yok)", "",
                  "| Palet | Ön plan | Arka plan | Eksik yuva |", "|---|---|---|---|"]
        for s in doc["skipped"]:
            lines.append("| %s | `%s` | `%s` | %s |"
                         % (s["palette"], s["fg"], s["bg"],
                            ", ".join("`%s`" % m for m in s["missing"])))
        lines.append("")
    lines += ["## Öne çıkanlar", ""]
    for name, s in sorted(doc["palette_summary"].items()):
        lines.append("- **%s**: gerekli %d çiftin %d'%s eşik altında → %s"
                     % (name, s["required"], s["fail"], suff(s["fail"]),
                        "✅ geçti" if s["verdict"] == "pass" else "❌ kaldı"))
    worst = doc["worst"]
    if worst:
        lines.append("- En düşük gerekli oran: **%.2f** — %s · `%s` → `%s`%s"
                     % (worst["ratio"], worst["palette"], worst["fg"],
                        worst["bg"],
                        " (üzerine `%s`)" % worst["over"] if worst["over"] else ""))
    b = doc["boundary_pairs"]
    lines.append("- AA (4.5) sınırına pinli metin çifti: **%d**%s"
                 % (len(b), "" if not b else " → " + ", ".join(
                     "%s `%s`/`%s` (%.2f)" % (p["palette"], p["fg"], p["bg"],
                                              p["ratio"]) for p in b)))
    lines.append("- Paletin kendi beyanıyla uyuşmayan ölçüm: **%d**"
                 % doc["counts"]["claim_drift"])
    lines.append("")
    lines += ["## Paletin kendi iddiaları (beyan ↔ ölçüm)", "",
              "| Palet | Çift | Beyan | Ölçüm | Sonuç |", "|---|---|---|---|---|"]
    for cl in doc["claims"]:
        shown = ("≥ %.2f:1" % cl["claimed"] if cl.get("mode") == "min"
                 else "%.2f:1" % cl["claimed"])
        lines.append("| %s | `%s` | %s | **%.2f**:1 | %s |"
                     % (cl["palette"], cl["pair"], shown,
                        cl["measured"], "✅" if cl["ok"] else "❌ SAPMA"))
    if not doc["claims"]:
        lines.append("| — | — | — | — | (iddia kaydı yok) |")
    lines += [
        "",
        "## Bulgular",
        "",
    ]
    required_fail = [r for r in doc["rows"] if r["required"] and not r["meets_min"]]
    advisory_fail = [r for r in doc["rows"] if not r["required"] and not r["meets_min"]]
    identical = [r for r in doc["rows"] if r["identical"]]
    lines.append("### Gerekli eşik altı (%d)" % len(required_fail))
    if not required_fail:
        lines.append("")
        lines.append("Yok — gerekli rollerin tamamı eşiğini geçiyor.")
    else:
        lines.append("")
        lines.append("| Palet | Çift | Tür | Ölçüm | Eşik | Not |")
        lines.append("|---|---|---|---|---|---|")
        for r in sorted(required_fail, key=lambda r: r["ratio"]):
            lines.append("| %s | `%s` → `%s`%s | %s | **%.2f** | %.1f | %s |"
                         % (r["palette"], r["fg"], r["bg"],
                            " (üzerine `%s`)" % r["over"] if r["over"] else "",
                            r["kind"], r["ratio"], r["min"], r["note"]))
    lines += ["", "### Dekoratif ayırıcılar (uyarı: 1.4.11 kapsamı dışı, %d)"
              % len(advisory_fail), ""]
    if not advisory_fail:
        lines.append("Yok.")
    else:
        lines.append("Bunlar WCAG 1.4.11'in zorunlu kıldığı *bileşen/state* "
                     "sınırları değil; ayırıcı okunurluğu için yine de bilgi "
                     "değeri taşır:")
        lines.append("")
        for r in sorted(advisory_fail, key=lambda r: r["ratio"]):
            lines.append("- %s · `%s` → `%s`: **%.2f** (< %.1f) — %s"
                         % (r["palette"], r["fg"], r["bg"], r["ratio"],
                            r["min"], r["note"]))
    lines += ["", "### Birebir aynı renk (%.0f çift)" % len(identical), ""]
    if not identical:
        lines.append("Yok.")
    else:
        for r in identical:
            lines.append("- %s · `%s` → `%s`: **%.2f** — %s"
                         % (r["palette"], r["fg"], r["bg"], r["ratio"],
                            r["note"]))
    if doc.get("not_audited"):
        lines += ["## Denetlenmeyen token'lar (gerekçeli)", "",
                  "| Palet | Token | Gerekçe |", "|---|---|---|"]
        for item in doc["not_audited"]:
            lines.append("| %s | `%s` | %s |"
                         % (item["palette"], item["token"], item["reason"]))
        lines.append("")
    lines += [
        "",
        "## Sınırlamalar",
        "",
        "- **Vercel koyu paleti bu depoda yok**: yakalama yalnız ışık temasıdır",
        "  (19 token). Vercel için koyu denetim yapılamaz; `vercel-variant`",
        "  satırları panonun açık rolleriyle okunur.",
        "- Ölçüm **statiktir**: yalnız token değerleri karşılaştırılır;",
        "  `mix-blend-mode`, gradyan, görsel (image) arka plan ve gerçek punto",
        "  dikkate alınmaz. Render edilen DOM için runtime axe kapısı",
        "  (`a11y_gate.py`, `color-contrast`) tamamlayıcıdır.",
        "- Ölçüm **çalışma ağacı** dosyalarına karşıdır; yukarıdaki sha256",
        "  hangi içeriğin ölçüldüğünü pinler. Revizyon tablosundaki `FARKLI`/",
        "  `ref'te yok` kayıtları raporun commit'li paletten saptığını gösterir.",
        "- Yarı saydam yüzeyler eşleşmede bildirilen `over` yuvasına bindirilir;",
        "  başka bir yüzey üzerinde oran değişir (her iki yüzey de listelenir).",
        "",
    ]
    return "\n".join(lines) + "\n"


# ── self-test ─────────────────────────────────────────────────────────────
def selftest():
    """WCAG referans değerleri + alfa/color-mix çözümü. Yeşil kanıt değildir:
    her iddia bağımsız referans sayılarla karşılaştırılır."""
    checks = []

    def eq(label, got, want, tol=0.01):
        checks.append((label, abs(got - want) <= tol, got, want))

    black, white = parse_color("#000"), parse_color("#fff")
    eq("#000/#fff = 21", contrast(black, white), 21.0)
    eq("#767676/#fff = 4.54 (bilinen AA sınırı)", 
       contrast(parse_color("#767676"), white), 4.54)
    eq("#777777/#fff = 4.48 (AA altı)", 
       contrast(parse_color("#777777"), white), 4.48)
    eq("sıra bağımsız", contrast(white, black), contrast(black, white))
    eq("aynı renk = 1", contrast(parse_color("#0e1116"), parse_color("#0e1116")), 1.0)
    eq("hsla eşdeğeri",
       contrast(parse_color("hsla(0, 0%, 100%, 1)"), black), 21.0)
    eq("#fff == #ffffff", contrast(parse_color("#fff"), black),
       contrast(parse_color("#ffffff"), black))
    # alfa bindirme: %50 siyah beyaz üzerinde → #808080 civarı
    comp = over(parse_color("rgba(0,0,0,0.5)"), white)
    eq("alfa bindirme kanalı", comp[0], 127.5, 0.6)
    # color-mix tint: #ff5b4f %15 + transparent → alfa 0.15
    mixed = resolve_mix("color-mix(in srgb, var(--c) 15%, transparent)",
                        {"--c": "#ff5b4f"})
    eq("color-mix tint alfası", mixed[3], 0.15, 0.001)
    eq("color-mix tint kanalı", mixed[0], 255.0, 0.01)
    # color-mix ile siyah çapa: gray-800 (%49) %88 + black → %43.12
    mixed = resolve_mix("color-mix(in srgb, var(--g) 88%, black)",
                        {"--g": "hsla(0, 0%, 49%, 1)"})
    eq("color-mix siyah çapa", mixed[0], 255 * 0.49 * 0.88, 0.5)
    failed = [c for c in checks if not c[1]]
    for label, ok, got, want in checks:
        print("%s %-38s ölçüm=%s beklenen=%s"
              % ("✓" if ok else "✗", label, round(got, 4), want))
    print("SELFTEST: %d/%d" % (len(checks) - len(failed), len(checks)))
    return 1 if failed else 0


# ── CLI ───────────────────────────────────────────────────────────────────
def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Kontrast denetimi (Vercel + pano koyu/açık, statik WCAG)")
    ap.add_argument("--json", action="store_true",
                    help="stdout'a tek JSON belgesi yaz")
    ap.add_argument("--md-out", metavar="PATH",
                    help="markdown rapor yaz")
    ap.add_argument("--check", action="store_true",
                    help="commit'li raporun tazeliğini + eşikleri doğrula")
    ap.add_argument("--base", default="HEAD", metavar="REF",
                    help="rapor edilecek revizyon tabanı (varsayılan HEAD)")
    ap.add_argument("--selftest", action="store_true",
                    help="WCAG referans değerleriyle matematik self-test")
    args = ap.parse_args(argv)

    def diag(*a):
        print(*a, file=sys.stderr)

    global BASE_REF
    BASE_REF = args.base

    if args.selftest:
        return selftest()

    try:
        doc = audit()
    except MeasurementError as exc:
        diag("HATA: %s" % exc)
        return 2

    md = render_md(doc)
    rc = 0
    if args.check:
        target = REPO / REPORT_PATH
        if not target.is_file():
            diag("HATA: rapor yok: %s (üret: --md-out)" % REPORT_PATH)
            return 2
        if target.read_text(encoding="utf-8") != md:
            diag("HATA: %s bayat — jeneratör çıktısıyla birebir değil "
                 "(yeniden üret ve commit et)" % REPORT_PATH)
            rc = 1
        if doc["counts"]["fail_required"] or doc["counts"]["claim_drift"]:
            diag("HATA: gerekli eşik altında %d çift, beyan sapması %d "
                 "(uyarı: %d dekoratif)"
                 % (doc["counts"]["fail_required"],
                    doc["counts"]["claim_drift"],
                    doc["counts"]["advisory_below"]))
            rc = 1

    if args.json:
        print(json.dumps(doc, ensure_ascii=False, sort_keys=True, indent=1))
    elif not args.md_out and not args.check:
        for name in ("dashboard-dark", "dashboard-light", "vercel-variant",
                     "vercel-mirror"):
            rows = [r for r in doc["rows"] if r["palette"] == name]
            print("── %s (%d çift, %d eşik altı)"
                  % (name, len(rows),
                     sum(1 for r in rows if not r["meets_min"])))
            for r in sorted(rows, key=lambda r: r["ratio"])[:6]:
                print("   %-52s %6.2f %s (min %.1f)"
                      % ("%s / %s%s" % (r["fg"], r["bg"],
                                        " over %s" % r["over"] if r["over"] else ""),
                         r["ratio"], "PASS" if r["meets_min"] else "FAIL",
                         r["min"]))
        if doc["skipped"]:
            print("── çözülemeyen: %d" % len(doc["skipped"]))
        for cl in doc["claims"]:
            print("── iddia %s %s: beyan %.2f · ölçüm %.2f · %s"
                  % (cl["palette"], cl["pair"], cl["claimed"],
                     cl["measured"], "OK" if cl["ok"] else "SAPMA"))

    if args.md_out:
        Path(args.md_out).write_text(md, encoding="utf-8")

    c = doc["counts"]
    diag("[token-contrast] çift=%d gerekli-altı=%d uyarı=%d metin-AA-altı=%d "
         "iddia-sapması=%d çözülemeyen=%d durum=%s"
         % (c["pairs"], c["fail_required"], c["advisory_below"],
            c["text_rows_below_aa"], c["claim_drift"], c["skipped"],
            doc["status"]))
    if not args.check and (c["fail_required"] or c["claim_drift"]):
        diag("UYARI: bulgular var (rapor: --md-out %s)" % REPORT_PATH)
    return rc


if __name__ == "__main__":
    sys.exit(main())
