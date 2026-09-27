#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""generate_mirror_tailwind.py — marka aynaları için Tailwind v4 @theme köprüsü.

Neden: `design-system/{stripe,linear,primer,vercel}/tokens.css` aynaları marka
paletlerini `var(--…)` olarak taşır ama Tailwind utility'si üretmez. Bu
jeneratör her ayna için kendi `<marka>/tailwind.css` köprüsünü üretir — kök
köprünün (`scripts/generate_tailwind.py` → `design-system/tailwind.css`)
marka aynalarına genişletilmiş hâli.

Üretilen dosya iki parçadan oluşur (kendi kendine yeter, ayrıca
`<marka>/tokens.css` import etmek gerekmez):

  1. ÖN-KOŞULLAR — köprünün referans verdiği ayna token'larının TRANSİTİF
     kapanışı, aynadan BİREBİR değerle ama `<marka>-` ön-ekli adla:
       `--stripe-hds-color-util-white: #ffffff;`
  2. @theme — her yuva tek bir Tailwind v4 theme anahtarına bağlanır ve
     değeri yalnız `var(<marka>-…)` olur (literal yasak):
       `--color-stripe-surface-bg-quiet: var(--stripe-hds-color-surface-bg-quiet);`

TEMEL PALET DOKUNULMAZ: kök köprü `--color-bg` / `--color-accent` gibi
anahtarlar kullanır. Linear ve Vercel token'ları da `--color-*` adları taşır;
ön-ek olmasaydı yan yana import edildiklerinde `bg-bg`/`bg-accent` sessizce
marka paletine kayardı. Bu yüzden (a) ön-koşul adları `<marka>-` ön-ekli,
(b) @theme anahtarları `<namespace>-<marka>-*`. Kapı
(`check_mirror_bridges.py`) bu ayrıklığı fail-closed doğrular.

KAPSAM (değer sınıfına göre; deterministik, ayna başına elle harita YOK):
  * `colour`      → `--color-<marka>-*`
  * `font-family` → `--font-<marka>-*`
  * `ease`        → `--ease-<marka>-*`
  * `shadow`      → `--shadow-<marka>-*`
  * `length`      → adı `radius` geçiyorsa `--radius-*`, `space|spacing|gap`
                    geçiyorsa `--spacing-*`; başka uzunluk kapsam dışı
Sayı, süre, composite (çok-token), url/gradient, dış referans (`--sx-*` gibi)
ve tanınmayan değerler kapsam dışıdır — ama SESSİZCE değil: dosyaya sayım
bloğu yazılır ve `aliases + skipped == tokens` eşitliği kapıyla kilitlenir.

Ad kuralı: token adının ilk segmenti Tailwind theme namespace'i değilse ve
ikinci segment (alias sonrası) öyleyse ilk segment marka katmanıdır ve
düşülür (`--hds-color-surface-bg-quiet` → `--color-stripe-surface-bg-quiet`).
Düşürme sonuç üretmezse düşürülmemiş biçim denenir — sıra sabittir, çıktı
deterministiktir.

Kullanım:
  python3 design-system/scripts/generate_mirror_tailwind.py          # üret
  python3 design-system/scripts/generate_mirror_tailwind.py --check   # drift denetimi
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from check_brand_mirrors import (  # noqa: E402
    DEFAULT_ROSTER,
    SetupError,
    load_roster,
)

REPO = HERE.parent.parent
BRIDGE_NAME = "tailwind.css"
TOKENS_NAME = "tokens.css"

PAIR = re.compile(r"(--[A-Za-z0-9_-]+)\s*:\s*([^;{}]+?)\s*;")
ROOT_BLOCK = re.compile(r":root\s*\{(.*?)\}", re.S)
# `var(--x)` VE `var(--x, fallback)` yakalanır: kapanış parantezi aranmaz,
# böylece fallback'li zincirler de kapanışa ve ön-ek yeniden yazımına girer.
VAR_ANY = re.compile(r"var\(\s*(--[A-Za-z0-9_-]+)")

# ── değer sınıflandırıcı ───────────────────────────────────────────────────
# Tek kaynak kural: "renkli mi" sorusunu AD değil DEĞER yanıtlar. Böylece
# `--color-alpha: 255` (sayı) ya da `--font-heading-1-size` (uzunluk) gibi
# ada-kanmayan token'lar yanlış namespace'e düşmez.
HEX_RE = re.compile(r"^#[0-9a-fA-F]{3,8}$")
COLOUR_FN_RE = re.compile(
    r"^(?:rgb|rgba|hsl|hsla|hwb|oklch|oklab|lab|lch|color|color-mix|light-dark)\(")
COLOUR_KEYWORDS = frozenset({
    "transparent", "currentcolor", "white", "black", "red", "green", "blue",
    "yellow", "orange", "purple", "pink", "gray", "grey", "silver", "maroon",
    "navy", "teal", "olive", "lime", "aqua", "fuchsia",
})
EASE_FN_RE = re.compile(r"^(?:cubic-bezier|steps|linear)\(")
EASE_KEYWORDS = frozenset({
    "linear", "ease", "ease-in", "ease-out", "ease-in-out",
    "step-start", "step-end",
})
LENGTH_RE = re.compile(
    r"^-?(?:\d+\.?\d*|\.\d+)(?:px|rem|em|%|vh|vw|vmin|vmax|ch|ex|pt|pc|cm|mm|in|q)$")
NUMBER_RE = re.compile(r"^-?(?:\d+\.?\d*|\.\d+)$")
TIME_RE = re.compile(r"^-?(?:\d+\.?\d*|\.\d+)(?:s|ms)$")
FONT_STACK_RE = re.compile(r"^(?:\"[^\"]*\"|'[^']*'|[A-Za-z][\w-]*)\s*,")
GENERIC_FONTS = ("sans-serif", "serif", "monospace", "cursive", "fantasy",
                 "system-ui", "ui-sans-serif", "ui-serif", "ui-monospace",
                 "emoji", "math")
# Uzunluk birimi arayan gevşek desen: `calc(4px * .8)` gibi ifadeler için.
UNIT_HINT_RE = re.compile(r"\d(?:px|rem|em|%|vh|vw|ch|ex|pt|cm|mm|in|q)\b")

# ── Tailwind v4 theme namespace'leri ───────────────────────────────────────
# İki parçalı olanlar ÖNCE denenir (`font-weight` ≠ `font`).
TWO_SEGMENT_NS = ("font-weight", "drop-shadow")
ONE_SEGMENT_NS = (
    "color", "font", "text", "tracking", "leading", "spacing", "radius",
    "shadow", "inset", "ease", "animate", "blur", "breakpoint", "container",
    "perspective", "aspect",
)
KNOWN_NS = frozenset(TWO_SEGMENT_NS + ONE_SEGMENT_NS)
# Kapsam: yalnız bu 6 namespace üretilir. Tanınan ama kapsam dışı bir
# namespace (ör. `font-weight`) sessizce `font`'a DÜŞMEZ — atlanır ve sayılır.
TARGET_NS = ("color", "font", "ease", "shadow", "radius", "spacing")
ACCEPTED = {
    "color": frozenset({"colour"}),
    "font": frozenset({"font-family"}),
    "ease": frozenset({"ease"}),
    "shadow": frozenset({"shadow"}),
    "radius": frozenset({"length"}),
    "spacing": frozenset({"length"}),
}
# Aynadaki ad ile Tailwind namespace'i arasındaki tek eşleme: HDS'in `space-*`
# katmanı Tailwind'de `spacing-*`'tir.
NAME_ALIASES = {"space": "spacing"}
# @theme blok sırası (deterministik).
NS_ORDER = ("color", "font", "ease", "shadow", "radius", "spacing")
# Atlama gerekçeleri — öncelik sırası (ilk uyan gerekçe raporlanır).
REASON_ORDER = (
    "namespace-not-in-scope", "class-mismatch", "key-collision",
    "class-number", "class-time", "class-composite-ref", "class-url",
    "class-cycle", "class-external-ref", "class-unknown",
    "no-namespace-length", "no-key",
)
SUMMARY_KEYS = ("tokens", "aliases", "preconditions", "skipped",
                "external_refs", "collisions")


# ═══════════════════════════════════════════════════════════════════════════
# SINIFLANDIRMA
# ═══════════════════════════════════════════════════════════════════════════

def classify(value: str, tokens: dict, depth: int = 0) -> str:
    """Ayna değerini sınıflar (var() zincirini izleyerek).

    Sınıflar: colour, font-family, ease, shadow, length, number, time,
    composite-ref, url, external-ref, cycle, unknown.
    """
    v = re.sub(r"\s+", " ", value).strip()
    if depth > 12:
        return "cycle"
    whole_var = re.fullmatch(r"var\(\s*(--[A-Za-z0-9_-]+)\s*\)", v)
    if whole_var:
        ref = whole_var.group(1)
        if ref in tokens:
            return classify(tokens[ref], tokens, depth + 1)
        return "external-ref"
    low = v.lower()
    if HEX_RE.match(v) or low in COLOUR_KEYWORDS:
        return "colour"
    # Sayı/uzunluk/gölge ile BAŞLAYAN değer renk fonksiyonu değildir: gölge
    # içindeki `rgba(...)` bu yüzden yanlışlıkla `colour` sayılmaz.
    numeric_led = bool(re.match(r"^[-\d.]", v)) or low.startswith("inset")
    if not numeric_led:
        if COLOUR_FN_RE.match(low):
            return "colour"
        if EASE_FN_RE.match(low) or low in EASE_KEYWORDS:
            return "ease"
    if low.startswith("calc("):
        return "length" if UNIT_HINT_RE.search(low) else "number"
    if numeric_led:
        if LENGTH_RE.match(v):
            return "length"
        if NUMBER_RE.match(v):
            return "number"
        if TIME_RE.match(v):
            return "time"
        parts = v.split()
        has_len = any(LENGTH_RE.match(p) or NUMBER_RE.match(p) for p in parts)
        has_colour = (
            bool(re.search(r"#[0-9a-fA-F]{3,8}\b", v))
            or bool(re.search(r"\b(?:rgb|rgba|hsl|hsla|hwb|oklch|oklab|lab|lch|"
                              r"color|color-mix|light-dark)\(", low))
            or any(p.lower() in COLOUR_KEYWORDS for p in parts)
        )
        if has_len and has_colour:
            return "shadow"
        return "unknown"
    if "var(" in v:
        return "composite-ref"
    if FONT_STACK_RE.match(v) or any(g in low for g in GENERIC_FONTS):
        return "font-family"
    if "url(" in low or "gradient(" in low:
        return "url"
    return "unknown"


def _ns_of(segment: str):
    """Segment bir namespace başlangıcı mı (alias uygulanmış hâliyle)."""
    if segment in KNOWN_NS:
        return segment
    return NAME_ALIASES.get(segment)


def _strip_candidates(segments: list) -> list:
    """Düşürme adayları — sıralı ve deterministik (1 sonra 0)."""
    if (len(segments) > 1 and _ns_of(segments[0]) is None
            and _ns_of(segments[1]) is not None):
        return [1, 0]
    return [0]


def _declared_ns(segments: list):
    """(namespace, tüketilen segment sayısı) ya da (None, 0)."""
    if len(segments) > 1 and "-".join(segments[:2]) in TWO_SEGMENT_NS:
        return "-".join(segments[:2]), 2
    ns = _ns_of(segments[0])
    if ns is not None:
        return ns, 1
    return None, 0


def _class_default_ns(cls: str, segments: list):
    """Ad hiç namespace belirtmiyorsa sınıfın varsayılan hedefi."""
    if cls == "colour":
        return "color"
    if cls == "font-family":
        return "font"
    if cls == "ease":
        return "ease"
    if cls == "shadow":
        return "shadow"
    if cls == "length":
        joined = "-".join(segments).lower()
        if "radius" in joined:
            return "radius"
        if "space" in joined or "spacing" in joined or "gap" in joined:
            return "spacing"
    return None


def _slug(segments: list) -> str:
    raw = "-".join(segments)
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", raw.lower())).strip("-")


def _pick_reason(reasons: list) -> str:
    """Deterministik gerekçe seçimi (REASON_ORDER önceliği)."""
    if not reasons:
        return "unknown"
    ranked = sorted(set(reasons),
                    key=lambda r: (REASON_ORDER.index(r)
                                   if r in REASON_ORDER else len(REASON_ORDER), r))
    return ranked[0]


def plan_token(mirror: str, name: str, value: str, tokens: dict):
    """(theme anahtarı, kaynak adı, namespace AÇIKÇA mı) ya da (None, gerekçe).

    Üçüncü alan çakışma hakemliğinde kullanılır: adında namespace'i taşıyan
    token (ör. `--color-blue`) kısa anahtarı hak eder, çıkarımsal olan
    (`--blue`) ayrıştırıcıyı kaybeder. Uydurma ek yok: kaybeden anahtar
    almaz, değeri yine ön-koşul olarak dosyada kalır.
    """
    cls = classify(value, tokens)
    segments = name[2:].split("-")
    reasons = []
    for strip in _strip_candidates(segments):
        seg = segments[strip:]
        if not seg:
            reasons.append("no-key")
            continue
        declared, consumed = _declared_ns(seg)
        if declared is not None and declared not in TARGET_NS:
            reasons.append("namespace-not-in-scope")
            continue
        if declared is not None and cls not in ACCEPTED[declared]:
            reasons.append("class-mismatch")
            continue
        ns = declared if declared is not None else _class_default_ns(cls, seg)
        if ns is None:
            reasons.append("no-namespace-length" if cls == "length"
                           else "class-%s" % cls)
            continue
        rest = seg[consumed:] if declared is not None else seg
        key = _slug(rest)
        if not key:
            reasons.append("no-key")
            continue
        return "--%s-%s-%s" % (ns, mirror, key), name, declared is not None
    return None, _pick_reason(reasons), False


def prefers_short_key(name: str) -> bool:
    """Adında namespace'i AÇIKÇA taşıyan token kısa anahtarı tercih eder."""
    segments = name[2:].split("-")
    for strip in _strip_candidates(segments):
        seg = segments[strip:]
        if seg and _declared_ns(seg)[0] is not None:
            return True
    return False


# ═══════════════════════════════════════════════════════════════════════════
# AYNA OKUMA + ÖN-KOŞUL KAPANIŞI
# ═══════════════════════════════════════════════════════════════════════════

def mirror_tokens(mirror: str, root: Path) -> dict:
    """Aynanın `:root` bloğundaki token haritası (ilk görülüm, tek boşluk)."""
    path = root / "design-system" / mirror / TOKENS_NAME
    if not path.is_file():
        raise SetupError("ayna tokens.css yok: %s" % path)
    match = ROOT_BLOCK.search(path.read_text(encoding="utf-8"))
    if not match:
        raise SetupError(":root bloğu bulunamadı: %s" % path)
    out = {}
    for name, value in PAIR.findall(match.group(1)):
        out.setdefault(name, re.sub(r"\s+", " ", value).strip())
    if not out:
        raise SetupError("ayna boş: %s" % path)
    return out


def precondition_name(mirror: str, token: str) -> str:
    """Ayna token'ının ön-koşul adı: `<marka>-` ön-ekli (temel paletle çakışmaz)."""
    return "--%s-%s" % (mirror, token[2:])


def rewrite_value(mirror: str, value: str, tokens: dict) -> str:
    """Değerdeki ayna-içi `var()` referanslarını ön-ekli adlara çevirir.

    Dış referanslar (`--sx-*`, `--Carousel-gap`) aynanın parçası olmadığı
    için ELLENMEZ: onları yeniden adlandırmak uydurma bir token yaratırdı.
    """
    def sub(match):
        ref = match.group(1)
        if ref in tokens:
            return "var(--%s-%s" % (mirror, ref[2:])
        return match.group(0)
    return VAR_ANY.sub(sub, value)


def closure(sources: list, tokens: dict, mirror: str):
    """Ön-koşul kapanışı: (sıralı token adları, dış referanslar)."""
    seen = []
    external = set()
    queue = sorted(sources)
    while queue:
        name = queue.pop(0)
        if name in seen:
            continue
        seen.append(name)
        for ref in VAR_ANY.findall(tokens[name]):
            if ref in tokens:
                if ref not in seen:
                    queue.append(ref)
            else:
                external.add(ref)
    return sorted(seen), sorted(external)


# ═══════════════════════════════════════════════════════════════════════════
# ÇIKTI
# ═══════════════════════════════════════════════════════════════════════════

HEADER = """/*
 * design-system/{mirror}/tailwind.css — GENERATED, DO NOT EDIT.
 *
 * {mirror} marka aynasının Tailwind CSS v4 `@theme` köprüsü.
 * Tek doğru kaynak: design-system/{mirror}/tokens.css
 *
 * Üretici: scripts/generate_mirror_tailwind.py
 *   python3 design-system/scripts/generate_mirror_tailwind.py          # üret
 *   python3 design-system/scripts/generate_mirror_tailwind.py --check   # drift
 * Kapı: scripts/check_mirror_bridges.py (pre-commit: check-mirror-bridges).
 *
 * Sözleşmeler (kapı fail-closed doğrular):
 *   1. TEMEL PALET DOKUNULMAZ — ön-koşullar `<marka>-` ön-ekli,
 *      @theme anahtarları `<namespace>-<marka>-*`. `bg-bg`/`text-fg` gibi
 *      kök utility'ler bu dosya import edildiğinde DEĞİŞMEZ.
 *   2. LİTERAL YOK — her @theme değeri `var(<marka>-…)`; değerin kendisi
 *      aynadan birebir gelir (yalnız ayna-içi var() referansları ön-eklenir).
 *   3. SESSİZ KAYIP YOK — aliases + skipped = aynadaki token sayısı; kapsam
 *      dışı sınıflar aşağıdaki sayım bloğunda gerekçesiyle listelenir.
 *
 * Kullanım:
 *   @import "tailwindcss";
 *   @import "./design-system/{mirror}/tailwind.css";
 *   → bg-{mirror}-…  text-{mirror}-…  border-{mirror}-…  rounded-{mirror}-…
 */

"""


def analyse(mirror: str, root: Path) -> dict:
    """Aynanın köprü planı: yuvalar, ön-koşullar, atlananlar, sayımlar.

    `render()` ve kapı aynı planı paylaşır — kapı, jeneratörün İÇİNDE hata
    aramaz; planın yapısal sözleşmelerini bağımsız doğrular.
    """
    tokens = mirror_tokens(mirror, root)
    buckets = {}
    skipped = {}
    for name in sorted(tokens):
        theme_name, info, _declared = plan_token(mirror, name, tokens[name],
                                                 tokens)
        if theme_name is None:
            skipped[name] = info
        else:
            buckets.setdefault(theme_name, []).append(name)

    # Çakışma hakemliği (deterministik): kısa anahtarı adında namespace'i
    # açıkça taşıyan token alır; kalanlar anahtar ALMAZ ama değerleri ön-koşul
    # olarak dosyada kalır (sessiz kayıp yok, gerekçe sayılır).
    plans = {}
    losers = []
    for theme_name in sorted(buckets):
        members = buckets[theme_name]
        if len(members) == 1:
            plans[theme_name] = members[0]
            continue
        winner = min(members, key=lambda n: (0 if prefers_short_key(n) else 1,
                                             n))
        plans[theme_name] = winner
        for name in members:
            if name != winner:
                skipped[name] = "key-collision"
                losers.append(name)

    preconditions, external = closure(
        sorted(set(plans.values()) | set(losers)), tokens, mirror)
    reasons = {}
    for reason in skipped.values():
        reasons[reason] = reasons.get(reason, 0) + 1
    return {
        "mirror": mirror,
        "tokens": tokens,
        "plans": plans,
        "skipped": skipped,
        "preconditions": preconditions,
        "external": external,
        "reasons": reasons,
        "collisions": len(losers),
    }


def render(mirror: str, root: Path) -> str:
    info = analyse(mirror, root)
    tokens, plans = info["tokens"], info["plans"]
    preconditions, external = info["preconditions"], info["external"]
    skipped, reasons = info["skipped"], info["reasons"]

    lines = [HEADER.format(mirror=mirror)]
    lines.append("/* ── ön-koşullar (ayna: %s/%s, birebir) ── */"
                 % (mirror, TOKENS_NAME))
    lines.append(":root {")
    for name in preconditions:
        lines.append("  %s: %s;" % (precondition_name(mirror, name),
                                    rewrite_value(mirror, tokens[name], tokens)))
    lines.append("}")
    lines.append("")
    lines.append("@theme {")
    for ns in NS_ORDER:
        group = sorted(tn for tn in plans if tn[2:].split("-")[0] == ns)
        if not group:
            continue
        lines.append("  /* ── %s (%d) ── */" % (ns, len(group)))
        for theme_name in group:
            lines.append("  %s: var(%s);"
                         % (theme_name, precondition_name(mirror,
                                                          plans[theme_name])))
    lines.append("}")
    lines.append("")
    lines.append("/*")
    lines.append(" * ── sayımlar (kapı bunları kilitler) ──")
    lines.append(" *   tokens=%d" % len(tokens))
    lines.append(" *   aliases=%d" % len(plans))
    lines.append(" *   preconditions=%d" % len(preconditions))
    lines.append(" *   skipped=%d" % len(skipped))
    lines.append(" *   external_refs=%d" % len(external))
    lines.append(" *   collisions=%d" % info["collisions"])
    for reason in sorted(reasons):
        lines.append(" *   skip:%s=%d" % (reason, reasons[reason]))
    for ref in external:
        lines.append(" *   external=%s" % ref)
    lines.append(" */")
    return "\n".join(lines) + "\n"


def bridge_path(mirror: str, root: Path) -> Path:
    return root / "design-system" / mirror / BRIDGE_NAME


def mirror_names(root: Path, roster: Path) -> list:
    """Roster'daki (exempt olmayan) marka aynaları — tek kaynak."""
    entries, _exempt = load_roster(roster)
    return sorted(e["dir"] for e in entries)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Marka aynaları için Tailwind v4 @theme köprüsü üret")
    ap.add_argument("--check", action="store_true",
                    help="yazmadan karşılaştır; drift varsa rc 1")
    ap.add_argument("--root", default=str(REPO),
                    help="repo kökü (varsayılan: script konumundan türetilir)")
    ap.add_argument("--roster", default=str(DEFAULT_ROSTER),
                    help="marka roster'ı (varsayılan: brand_mirrors.list)")
    ap.add_argument("--mirror", action="append", default=None,
                    help="yalnız bu aynayı işle (tekrarlanabilir)")
    args = ap.parse_args(argv)

    root = Path(args.root).resolve()
    try:
        mirrors = sorted(args.mirror) if args.mirror else mirror_names(
            root, Path(args.roster))
        if not mirrors:
            raise SetupError("işlenecek marka aynası yok (roster boş)")
        rendered = {m: render(m, root) for m in mirrors}
    except SetupError as exc:
        print("generate-mirror-tailwind: YAPISAL HATA: %s" % exc,
              file=sys.stderr)
        return 2

    if args.check:
        drift = []
        for mirror in mirrors:
            out = bridge_path(mirror, root)
            current = out.read_text(encoding="utf-8") if out.is_file() else ""
            if current != rendered[mirror]:
                drift.append(mirror)
        if drift:
            print("MIRROR BRIDGE DRIFT: %s köprüsü jeneratörle birebir değil "
                  "— yeniden üret:\n  python3 "
                  "design-system/scripts/generate_mirror_tailwind.py"
                  % ", ".join(drift), file=sys.stderr)
            return 1
        stats = {m: analyse(m, root) for m in mirrors}
        summary = ", ".join(
            "%s %d/%d yuva" % (m, len(stats[m]["plans"]), len(stats[m]["tokens"]))
            for m in mirrors)
        print("OK — %d/%d marka köprüsü jeneratörle birebir (%s)"
              % (len(mirrors), len(mirrors), summary))
        return 0

    for mirror in mirrors:
        out = bridge_path(mirror, root)
        out.write_text(rendered[mirror], encoding="utf-8")
        print("yazıldı: design-system/%s/%s (%d B)"
              % (mirror, BRIDGE_NAME, len(rendered[mirror])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
