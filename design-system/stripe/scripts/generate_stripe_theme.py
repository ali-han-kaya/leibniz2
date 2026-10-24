#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""generate_stripe_theme.py — Stripe HDS tema varyantını üretir (GENERATED).

Neden: `design-system/stripe/` 710 `--hds-*` HDS token'ı taşıyan bir marka
aynasıdır; `tokens.css` tek başına bir *palet* verir ama pano/landing hangi
repo semantiğinin (`--bg`, `--fg`, `--accent`, …) hangi HDS token'ına
düştüğünü bilmez. Bu jeneratör o köprüyü üretir:

  `:root[data-theme="stripe"]` — repo semantik yuvaları → `--hds-*` referansı

İki parça TEK dosyada, kendi kendine yeter (preview_server tek rota ile
servis eder; 478 kB'lik raw.css'e gerek kalmaz):

  1. HDS ÖN-KOŞULLARI — SLOT_MAP'in referans verdiği `--hds-*` token'larının
     TRANSİTİF kapanışı, aynadan (design-system/stripe/tokens.css) BİREBİR
     kopyalanır (var() zincirleri dahil: `--hds-color-surface-bg-quiet` →
     `--hds-color-util-white` → `--hds-color-core-neutral-0`).
  2. YUVA EŞLEMESİ — 32 renk yuvasının tamamı (tint'ler ve gölgeler dahil)
     tek bir HDS token'ına ya da ondan türeyen color-mix ifadesine bağlanır;
     yuvayı eksik bırakmak yasaktır (koyu palete sessiz geri düşme olur).

Sözleşmeler:
  * Çıktı DETERMİNİSTİKTİR: HDS tanımları isim sırasına göre, yuvarlama yok,
    değerler aynadan `\s+`→tek boşluk normalizasyonuyla birebir gelir.
  * `--check` modu çıktıyı diske yazmadan karşılaştırır → elle düzenleme
    (drift) rc 1 (pre-commit check-design-tokens contract 9 bunu koşar).
  * READ-ONLY mod dışında yalnız `theme.css` yazılır; aynaya dokunulmaz.

Kullanım:
  python3 design-system/stripe/scripts/generate_stripe_theme.py
  python3 design-system/stripe/scripts/generate_stripe_theme.py --check
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent.parent
MIRROR = REPO / "design-system" / "stripe" / "tokens.css"
OUT = REPO / "design-system" / "stripe" / "theme.css"

SCOPE = ':root[data-theme="stripe"]'
HDS_NAME = re.compile(r"--hds-[A-Za-z0-9_-]+")
PAIR = re.compile(r"(--[A-Za-z0-9_-]+)\s*:\s*([^;{}]+?)\s*;")

# ── YUVA EŞLEMESİ ──────────────────────────────────────────────────────────
# Değer `--hds-*` ise düz referans; içinde `{--hds-*}` geçiyorsa türetilmiş
# ifade (color-mix/box-shadow). 32 yuva = tokens.css renk yüzeyinin tamamı;
# `REQUIRED_SLOTS` bunun eksiksiz olmasını kilitler.
SLOT_MAP: dict[str, str] = {
    # metin/zemin
    "--bg": "--hds-color-surface-bg-quiet",
    "--fg": "--hds-color-text-solid",
    "--muted": "--hds-color-text-subdued",
    "--fg-dimmed": "--hds-color-text-soft",
    # durum renkleri (HDS metin kontrastı yüksek tonlar)
    "--ok": "--hds-color-core-success-600",
    "--warn": "--hds-color-core-lemon-500",
    "--err": "--hds-color-core-error-600",
    "--budget": "--hds-color-core-magenta-600",
    # çizgi + marka aksanı
    "--border": "--hds-color-surface-border-quiet",
    "--accent": "--hds-color-action-bg-solid",
    "--on-accent": "--hds-color-action-text-onSolid",
    # yüzeyler + legacy alias'lar
    "--surface": "--hds-color-surface-bg-subdued",
    "--surface-1": "--hds-color-surface-bg-subdued",
    "--surface-2": "--hds-color-core-neutral-50",
    "--surface-raised": "--hds-color-core-neutral-50",
    "--code-bg": "--hds-color-surface-bg-subdued",
    "--header-start": "--hds-color-surface-bg-quiet",
    "--header-end": "--hds-color-surface-bg-subdued",
    "--paper": "--hds-color-surface-bg-quiet",
    "--paper-ink": "--hds-color-text-solid",
    # durum tint'leri — HDS tonundan türetilir (literal renk yok)
    "--tint-ok-bg": "color-mix(in oklab, {--hds-color-core-success-400} 15%, transparent)",
    "--tint-warn-bg": "color-mix(in oklab, {--hds-color-core-lemon-300} 15%, transparent)",
    "--tint-err-bg": "color-mix(in oklab, {--hds-color-core-error-500} 15%, transparent)",
    "--tint-err-bg-strong": "color-mix(in oklab, {--hds-color-core-error-500} 12%, transparent)",
    "--tint-err-bg-weak": "color-mix(in oklab, {--hds-color-core-error-500} 10%, transparent)",
    "--tint-budget-bg": "color-mix(in oklab, {--hds-color-core-magenta-350} 12%, transparent)",
    "--tint-accent-bg": "color-mix(in oklab, {--hds-color-action-bg-solid} 15%, transparent)",
    "--tint-accent-hover": "color-mix(in oklab, {--hds-color-action-bg-solid} 10%, transparent)",
    "--tint-accent-active": "color-mix(in oklab, {--hds-color-action-bg-solid} 20%, transparent)",
    "--tint-unknown-bg": "color-mix(in oklab, {--hds-color-text-subdued} 15%, transparent)",
    # gölge/örtü — HDS mürekkebinden türetilir
    "--shadow-tip":
        "0 8px 24px color-mix(in oklab, {--hds-color-text-solid} 18%, transparent)",
    "--backdrop-lightbox":
        "color-mix(in oklab, {--hds-color-text-solid} 92%, transparent)",
}

# tokens.css renk yüzeyinin kanonik listesi: varyant bunların TAMAMINI
# bağlamalı (eksik yuva koyu palete sessiz geri düşerdi).
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

HEADER = """/*
 * design-system/stripe/theme.css — GENERATED, DO NOT EDIT.
 *
 * Stripe HDS tabanlı tema varyantı: `:root[data-theme="stripe"]` altında
 * pano/landing'in repo semantik yuvalarını (`--bg`, `--fg`, `--accent`, …)
 * design-system/stripe/tokens.css aynasındaki --hds-* token'larına bağlar.
 *
 * Üretici: scripts/generate_stripe_theme.py
 *   python3 design-system/stripe/scripts/generate_stripe_theme.py
 *   python3 design-system/stripe/scripts/generate_stripe_theme.py --check
 *
 * İçerik: (1) SLOT_MAP'in referans verdiği --hds-* token'larının transitif
 * kapanışı aynadan birebir, (2) 32 renk yuvasının tamamı için eşleme.
 * Elle düzenleme drift sayılır: check-design-tokens contract 9 fail-closed
 * bloke eder (yeniden üret → commit et).
 */

"""


def mirror_tokens() -> dict[str, str]:
    """Aynadan ilk-görülüm token haritası (değerler tek boşluğa normalize)."""
    text = MIRROR.read_text(encoding="utf-8")
    out: dict[str, str] = {}
    for name, value in PAIR.findall(text):
        out.setdefault(name, re.sub(r"\s+", " ", value).strip())
    hds = {k: v for k, v in out.items() if k.startswith("--hds-")}
    if not hds:
        raise SystemExit(f"HDS token bulunamadı: {MIRROR}")
    return hds


def referenced_hds() -> list[str]:
    """SLOT_MAP'te geçen --hds-* adları (deterministik sıra)."""
    names: set[str] = set()
    for value in SLOT_MAP.values():
        names.update(HDS_NAME.findall(value))
    return sorted(names)


def closure(names: list[str], hds: dict[str, str]) -> list[str]:
    """var() zincirlerini izleyerek transitif kapanışı tamamlar."""
    seen: set[str] = set()
    queue = list(names)
    missing: list[str] = []
    while queue:
        name = queue.pop(0)
        if name in seen:
            continue
        seen.add(name)
        value = hds.get(name)
        if value is None:
            missing.append(name)
            continue
        for dep in HDS_NAME.findall(value):
            if dep not in seen:
                queue.append(dep)
    if missing:
        raise SystemExit(
            "SLOT_MAP aynada olmayan HDS token'ına referans veriyor: "
            + ", ".join(sorted(missing)))
    return sorted(seen)


def render() -> str:
    hds = mirror_tokens()
    absent = sorted(set(REQUIRED_SLOTS) - set(SLOT_MAP))
    if absent:
        raise SystemExit(
            "REQUIRED_SLOTS eşlemesi eksik (koyu palete sessiz geri düşme): "
            + ", ".join(absent))
    extra = sorted(set(SLOT_MAP) - set(REQUIRED_SLOTS))
    if extra:
        raise SystemExit(
            "SLOT_MAP kanonik renk yüzeyi dışında yuva taşıyor: "
            + ", ".join(extra))

    lines = [HEADER, f"{SCOPE} {{"]
    lines.append("  /* ── HDS ön-koşulları (ayna: stripe/tokens.css, birebir) ── */")
    for name in closure(referenced_hds(), hds):
        lines.append(f"  {name}: {hds[name]};")
    lines.append("")
    lines.append("  /* ── repo semantiği → HDS ── */")
    for slot, value in SLOT_MAP.items():
        if value.startswith("--"):
            rendered = f"var({value})"
        else:
            rendered = re.sub(
                r"\{(" + HDS_NAME.pattern + r")\}", r"var(\1)", value)
        lines.append(f"  {slot}: {rendered};")
    lines.append("}")
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Stripe HDS tema varyantını üret (GENERATED)")
    ap.add_argument("--check", action="store_true",
                    help="yazmadan karşılaştır; drift varsa rc 1")
    args = ap.parse_args(argv)

    rendered = render()
    if args.check:
        current = OUT.read_text(encoding="utf-8") if OUT.is_file() else ""
        if current != rendered:
            print("STRIPE THEME DRIFT: design-system/stripe/theme.css "
                  "jeneratörle birebir değil — yeniden üret:\n"
                  "  python3 design-system/stripe/scripts/"
                  "generate_stripe_theme.py", file=sys.stderr)
            return 1
        hds_count = len(closure(referenced_hds(), mirror_tokens()))
        print(f"OK — stripe tema varyantı jeneratörle birebir "
              f"({len(SLOT_MAP)} yuva, {hds_count} HDS token)")
        return 0

    OUT.write_text(rendered, encoding="utf-8")
    print(f"yazıldı: {OUT.relative_to(REPO)} "
          f"({len(rendered)} B, {len(SLOT_MAP)} yuva)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
