#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""generate_vercel_theme.py — Vercel adapter tema varyantını üretir (GENERATED).

Neden: `design-system/vercel/` 19 `--*` token'lık bir marka aynasıdır (light
tema, computed-style yakalaması). `tokens.css` tek başına bir *palet* verir ama
pano/landing hangi repo semantiğinin (`--bg`, `--fg`, `--accent`, …) hangi
Vercel token'ına düştüğünü bilmez. Bu jeneratör o köprüyü üretir:

  `:root[data-theme="vercel"]` — repo semantik yuvaları → Vercel token'ı

Üç parça TEK dosyada, kendi kendine yeter (preview_server tek rota ile servis
eder; 6 kB'lik aynaya ek çalışma-zamanı bağımlılığı olmadan):

  1. ÖN-KOŞULLAR — SLOT_MAP'in referans verdiği token'ların TRANSİTİF kapanışı,
     aynadan (design-system/vercel/tokens.css) BİREBİR kopyalanır.
  2. YUVA EŞLEMESİ — 32 renk yuvasının 28'i bağlanır; 4'ü Vercel'in 19-token
     ışık yakalamasında karşılığı OLMADIĞI için `UNBOUND_SLOTS`'ta adıyla
     ilan edilir (success/warning ailesi). Sessiz kısmi varyant yasaktır:
     ilan edilmemiş eksik yuva da, ilan edilmiş ama bağlanmış yuva da
     `SystemExit`'tir.
  3. PALET KAPSAMI — aynadaki her token ya kapanışta kullanılır ya da
     `UNUSED_TOKENS`'ta gerekçesiyle listelenir; "kullanıldı ∪ ilan edilmiş"
     aynanın TAMAMINI vermeli (sessizce düşen token yok).

Sözleşmeler:
  * Çıktı DETERMİNİSTİKTİR: ön-koşullar isim sırasına göre; değerler aynadan
    `\s+`→tek boşluk normalizasyonuyla birebir gelir.
  * Sayılar aynadan TÜRETİLİR (19 token), elle pinlenmez; ayna yenilenip
    commit edilirse varyant da aynı commit'te yeniden üretilmelidir.
  * `--check` modu çıktıyı diske yazmadan karşılaştırır → elle düzenleme
    (drift) rc 1 (pre-commit check-design-tokens contract 9 bunu koşar).
  * READ-ONLY mod dışında yalnız `theme.css` yazılır; aynaya dokunulmaz.

Kullanım:
  python3 design-system/vercel/scripts/generate_vercel_theme.py
  python3 design-system/vercel/scripts/generate_vercel_theme.py --check
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent.parent
MIRROR = REPO / "design-system" / "vercel" / "tokens.css"
OUT = REPO / "design-system" / "vercel" / "theme.css"

SCOPE = ':root[data-theme="vercel"]'
TOKEN_NAME = re.compile(r"--[A-Za-z0-9_-]+")
PAIR = re.compile(r"(--[A-Za-z0-9_-]+)\s*:\s*([^;{}]+?)\s*;")

# ── YUVA EŞLEMESİ ──────────────────────────────────────────────────────────
# Değer düz `--token` ise referans; `{--token}` geçiyorsa türetilmiş ifade
# (color-mix). Türetmeler yalnız aynadaki tonlardan yapılır; serbest renk
# literali yok (color-mix çapası `black`/`transparent` ton taşımaz).
SLOT_MAP: dict[str, str] = {
    # metin/zemin — Vercel ışık paleti
    "--bg": "--color-background-100",
    "--fg": "--color-gray-1000",
    "--muted": "--color-gray-900",
    # hint metni: %49 nötr gri AA eşiğinin (3.2:1) altında kalır; aynı tondan
    # siyaha %12 karıştırılarak 5.10:1'e çıkarılır (ton ailesi korunur)
    "--fg-dimmed": "color-mix(in srgb, {--color-gray-800} 88%, black)",
    # çizgi + marka aksanı (develop mavisi; beyaz üstünde 4.50:1)
    "--border": "--color-gray-300",
    "--accent": "--develop-text",
    "--on-accent": "--color-background-100",
    # durum renkleri: ship kırmızısı metin için koyulaştırılır (4.58:1),
    # preview pembesi budget rolünde olduğu gibi AA'yı geçer (4.50:1)
    "--err": "color-mix(in srgb, {--ship-text} 80%, black)",
    "--budget": "--preview-text",
    # yüzeyler + legacy alias'lar
    "--surface": "--color-gray-200",
    "--surface-1": "--color-gray-200",
    "--surface-2": "--color-gray-300",
    "--surface-raised": "--color-gray-300",
    "--code-bg": "--color-gray-200",
    "--header-start": "--color-background-100",
    "--header-end": "--color-gray-200",
    "--paper": "--color-background-100",
    "--paper-ink": "--color-gray-1000",
    # durum tint'leri — aynı aileden türetilir (literal renk yok)
    "--tint-err-bg": "color-mix(in srgb, {--ship-text} 15%, transparent)",
    "--tint-err-bg-strong": "color-mix(in srgb, {--ship-text} 12%, transparent)",
    "--tint-err-bg-weak": "color-mix(in srgb, {--ship-text} 10%, transparent)",
    "--tint-budget-bg": "color-mix(in srgb, {--preview-text} 12%, transparent)",
    "--tint-accent-bg": "color-mix(in srgb, {--develop-text} 15%, transparent)",
    "--tint-accent-hover": "color-mix(in srgb, {--develop-text} 10%, transparent)",
    "--tint-accent-active": "color-mix(in srgb, {--develop-text} 20%, transparent)",
    # nötr/unknown tint: aynadaki %8 siyah alpha token'ı BİREBİR
    "--tint-unknown-bg": "--color-gray-alpha-400",
    # gölge/örtü — ayna mürekkebinden (console default #000) türetilir
    "--shadow-tip":
        "0 8px 24px color-mix(in srgb, {--geist-console-text-color-default} "
        "18%, transparent)",
    "--backdrop-lightbox":
        "color-mix(in srgb, {--geist-console-text-color-default} 92%, "
        "transparent)",
}

# Vercel'in 19-token yakalamasında karşılığı OLMAYAN roller. Adıyla ilan
# edilir: varyant bu yuvaları TANIMLAMAZ (taban paletten gelir) ve kapı
# "ilan edilmiş istisna" ile "sessiz eksik yuva"yı birbirinden ayırır.
UNBOUND_SLOTS: dict[str, str] = {
    "--ok": "Vercel yakalamasında success tonu yok",
    "--warn": "Vercel yakalamasında warning tonu yok",
    "--tint-ok-bg": "success tint kaynağı yok (--ok ile aynı istisna)",
    "--tint-warn-bg": "warning tint kaynağı yok (--warn ile aynı istisna)",
}

# tokens.css renk yüzeyinin kanonik listesi (stripe varyantıyla aynı 32 yuva).
REQUIRED_SLOTS = (
    "--bg", "--fg", "--muted", "--fg-dimmed", "--accent", "--ok", "--warn",
    "--err", "--border", "--budget",
    "--surface-1", "--surface-2", "--on-accent",
    "--surface", "--surface-raised", "--header-start", "--header-end",
    "--code-bg", "--paper", "--paper-ink",
    "--tint-ok-bg", "--tint-warn-bg", "--tint-err-bg", "--tint-err-bg-strong",
    "--tint-err-bg-weak", "--tint-budget-bg", "--tint-accent-bg",
    "--tint-accent-hover", "--tint-accent-active", "--tint-unknown-bg",
    "--shadow-tip", "--backdrop-lightbox",
)

# Aynada olup repo semantiğinde yuvası OLMAYAN token'lar. Gerekçe zorunlu:
# "kullanıldı ∪ ilan edilmiş = aynanın tamamı" invariantı sessiz düşüşü
# engeller (yeni bir ayna token'ı eklenip kullanılmazsa jeneratör düşer).
UNUSED_TOKENS: dict[str, str] = {
    "--color-gray-500": "repo semantiğinde yuva yok (ara nötr çizgi tonu)",
    "--color-gray-600": "repo semantiğinde yuva yok (ara nötr ton)",
    "--color-gray-700": "repo semantiğinde yuva yok (metin için AA altı)",
    "--ds-focus-color": "focus rolü repo yuvalarında ayrı sözleşme değil",
    "--geist-console-text-color-blue": "konsol katmanı; UI yuvası yok",
    "--geist-console-text-color-purple": "konsol katmanı; UI yuvası yok",
    "--geist-console-text-color-pink": "konsol katmanı; UI yuvası yok",
    "--geist-selection-text-color": "selection rolü ayrı sözleşme değil",
}

HEADER = """/*
 * design-system/vercel/theme.css — GENERATED, DO NOT EDIT.
 *
 * Vercel adapter tema varyantı: `:root[data-theme="vercel"]` altında
 * pano/landing'in repo semantik yuvalarını (`--bg`, `--fg`, `--accent`, …)
 * design-system/vercel/tokens.css aynasındaki token'lara bağlar.
 *
 * Üretici: scripts/generate_vercel_theme.py
 *   python3 design-system/vercel/scripts/generate_vercel_theme.py
 *   python3 design-system/vercel/scripts/generate_vercel_theme.py --check
 *
 * İçerik: (1) SLOT_MAP'in referans verdiği token'ların transitif kapanışı
 * aynadan birebir, (2) 32 yuvanın %(bound)d'i bağlı, %(unbound)d'i İLAN
 * EDİLMİŞ İSTİSNA (bu yuvalar tanımlanmaz — taban paletten gelir):
%(exceptions)s
 * Kaynak: vercel/README.md ("Tema varyantı"). Elle düzenleme drift sayılır:
 * check-design-tokens contract 9 fail-closed bloke eder (yeniden üret →
 * commit et).
 */

"""


def mirror_tokens() -> dict[str, str]:
    """Aynadan ilk-görülüm token haritası (değerler tek boşluğa normalize)."""
    if not MIRROR.is_file():
        raise SystemExit(f"ayna yok: {MIRROR}")
    text = MIRROR.read_text(encoding="utf-8")
    out: dict[str, str] = {}
    for name, value in PAIR.findall(text):
        out.setdefault(name, re.sub(r"\s+", " ", value).strip())
    if not out:
        raise SystemExit(f"token bulunamadı: {MIRROR}")
    return out


def referenced_tokens() -> list[str]:
    """SLOT_MAP'te geçen ayna token adları (deterministik sıra)."""
    names: set[str] = set()
    for value in SLOT_MAP.values():
        names.update(TOKEN_NAME.findall(value))
    return sorted(names)


def closure(names: list[str], mirror: dict[str, str]) -> list[str]:
    """var() zincirlerini izleyerek transitif kapanışı tamamlar."""
    seen: set[str] = set()
    queue = list(names)
    missing: list[str] = []
    while queue:
        name = queue.pop(0)
        if name in seen:
            continue
        seen.add(name)
        value = mirror.get(name)
        if value is None:
            missing.append(name)
            continue
        for dep in TOKEN_NAME.findall(value):
            if dep not in seen:
                queue.append(dep)
    if missing:
        raise SystemExit(
            "SLOT_MAP aynada olmayan token'a referans veriyor: "
            + ", ".join(sorted(missing)))
    return sorted(seen)


def render() -> str:
    mirror = mirror_tokens()
    overlap = set(SLOT_MAP) & set(UNBOUND_SLOTS)
    if overlap:
        raise SystemExit(
            "yuva hem bağlı hem istisna olamaz: " + ", ".join(sorted(overlap)))
    declared = set(SLOT_MAP) | set(UNBOUND_SLOTS)
    absent = sorted(set(REQUIRED_SLOTS) - declared)
    if absent:
        raise SystemExit(
            "REQUIRED_SLOTS ne bağlanmış ne ilan edilmiş (sessiz eksik yuva): "
            + ", ".join(absent))
    extra = sorted(declared - set(REQUIRED_SLOTS))
    if extra:
        raise SystemExit(
            "kanonik renk yüzeyi dışında yuva: " + ", ".join(extra))
    used = closure(referenced_tokens(), mirror)
    unlisted = sorted(set(mirror) - set(used) - set(UNUSED_TOKENS))
    if unlisted:
        raise SystemExit(
            "ayna token'ı ne kullanılıyor ne ilan edilmiş (sessiz düşüş): "
            + ", ".join(unlisted))
    phantom = sorted(set(UNUSED_TOKENS) - set(mirror))
    if phantom:
        raise SystemExit(
            "UNUSED_TOKENS'te aynada olmayan ad: " + ", ".join(phantom))
    both = sorted(set(used) & set(UNUSED_TOKENS))
    if both:
        raise SystemExit(
            "token hem kullanılıyor hem 'kullanılmıyor' ilan edilmiş: "
            + ", ".join(both))

    exceptions = "\n".join(
        f" *   - {slot}: {reason}" for slot, reason in UNBOUND_SLOTS.items())
    lines = [HEADER % {"bound": len(SLOT_MAP), "unbound": len(UNBOUND_SLOTS),
                       "exceptions": exceptions},
             f"{SCOPE} {{"]
    lines.append("  /* ── ön-koşullar (ayna: vercel/tokens.css, birebir) ── */")
    for name in used:
        lines.append(f"  {name}: {mirror[name]};")
    lines.append("")
    lines.append("  /* ── repo semantiği → Vercel (ilan edilmiş istisnalar hariç) ── */")
    for slot, value in SLOT_MAP.items():
        if value.startswith("--"):
            rendered = f"var({value})"
        else:
            rendered = re.sub(
                r"\{(" + TOKEN_NAME.pattern + r")\}", r"var(\1)", value)
        lines.append(f"  {slot}: {rendered};")
    lines.append("}")
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Vercel adapter tema varyantını üret (GENERATED)")
    ap.add_argument("--check", action="store_true",
                    help="yazmadan karşılaştır; drift varsa rc 1")
    args = ap.parse_args(argv)

    rendered = render()
    used = len(closure(referenced_tokens(), mirror_tokens()))
    if args.check:
        current = OUT.read_text(encoding="utf-8") if OUT.is_file() else ""
        if current != rendered:
            print("VERCEL THEME DRIFT: design-system/vercel/theme.css "
                  "jeneratörle birebir değil — yeniden üret:\n"
                  "  python3 design-system/vercel/scripts/"
                  "generate_vercel_theme.py", file=sys.stderr)
            return 1
        print(f"OK — vercel adapter varyantı jeneratörle birebir "
              f"({len(SLOT_MAP)}/{len(REQUIRED_SLOTS)} yuva, "
              f"{len(UNBOUND_SLOTS)} ilan edilmiş istisna, "
              f"{used}/{len(mirror_tokens())} ayna token'ı)")
        return 0

    OUT.write_text(rendered, encoding="utf-8")
    print(f"yazıldı: {OUT.relative_to(REPO)} "
          f"({len(rendered)} B, {len(SLOT_MAP)} yuva)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
