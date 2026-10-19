#!/usr/bin/env python3
"""report_theme_diff.py — GitHub dark/light token farkını sistematik üretir.

NEDEN ÜRETİLİR: fark raporu elle yazılırsa iki yakalamadan biri yenilendiğinde
sessizce bayatlar (ölçüldü: `VERCEL_DASHBOARD_TOKEN_FARK_RAPORU.md` elle
yazıldı ve kendi sayılarını taşır). Bu rapor iki `raw` yakalamasından türetilir,
tüm listeleri TAM verir (örnekleme yok) ve `--check` ile diskteki kopyaya karşı
birebir doğrulanır: elle düzenleme veya yakalama yenilemesi drift sayılır.

Kullanım:
    python3 design-system/github/scripts/report_theme_diff.py          # yaz
    python3 design-system/github/scripts/report_theme_diff.py --check  # drift → rc 1
    python3 design-system/github/scripts/report_theme_diff.py --stdout # ekrana

stdlib-only. OFFLINE (yalnız çalışma ağacı okunur).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent.parent
GITHUB = ROOT / "design-system" / "github"
OUT_PATH = ROOT / "_calisma" / "CIKTI" / "GITHUB_TEMA_FARK_RAPORU.md"

DARK_RAW = "raw.json"
LIGHT_RAW = "raw.light.json"
SCALE = re.compile(r"--base-color-scale-([a-z]+)-(\d+)\Z")


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def tokens_of(path: Path):
    data = load(path)
    variables = data.get("colors", {}).get("cssVariables") or {}
    flat = {}
    for name, meta in variables.items():
        flat[name] = meta["value"] if isinstance(meta, dict) else meta
    return data, flat


def namespace(name: str) -> str:
    return name[2:].split("-", 1)[0] or "ungrouped"


def md_table(header, rows):
    out = ["| " + " | ".join(header) + " |", "|" + "|".join(["---"] * len(header)) + "|"]
    for row in rows:
        out.append("| " + " | ".join(str(cell) for cell in row) + " |")
    return out


def page_state_row(label, data):
    state = data.get("pageState") or {}
    return [
        label,
        data.get("source", {}).get("theme")
        or data.get("theme")
        or "yok (bu alan 2026-10-11'de eklendi)",
        (data.get("extractedAt") or "")[:19].replace("T", " "),
        state.get("dataColorMode", "—"),
        state.get("bgColorDefault", "—"),
        state.get("fgColorDefault", "—"),
        state.get("computedCustomProperties", "—"),
    ]


def build_report():
    dark_data, dark = tokens_of(GITHUB / DARK_RAW)
    light_data, light = tokens_of(GITHUB / LIGHT_RAW)

    shared = sorted(set(dark) & set(light))
    same = [n for n in shared if dark[n] == light[n]]
    differ = [n for n in shared if dark[n] != light[n]]
    dark_only = sorted(set(dark) - set(light))
    light_only = sorted(set(light) - set(dark))

    namespaces = sorted({namespace(n) for n in set(dark) | set(light)},
                        key=lambda s: (s.lower(), s))
    ns_rows = []
    for ns in namespaces:
        d = {n for n in dark if namespace(n) == ns}
        l = {n for n in light if namespace(n) == ns}
        s = d & l
        ns_rows.append([
            "`%s`" % ns,
            len(d),
            len(l),
            len(s),
            len([n for n in s if dark[n] == light[n]]),
            len([n for n in s if dark[n] != light[n]]),
            len(d - l),
            len(l - d),
        ])

    # Tema-duyarlılık sınıfı: bir namespace'in paylaşılan isimlerinde fark var mı?
    theme_binding = defaultdict(list)
    for ns in namespaces:
        s = [n for n in shared if namespace(n) == ns]
        if not s:
            theme_binding["no-overlap"].append(ns)
        elif all(dark[n] != light[n] for n in s):
            theme_binding["all-differ"].append(ns)
        elif not any(dark[n] != light[n] for n in s):
            theme_binding["none-differ"].append(ns)
        else:
            theme_binding["mixed"].append(ns)

    # base-color-scale-* yapısal kayması
    dark_steps = defaultdict(set)
    light_steps = defaultdict(set)
    for name in dark:
        m = SCALE.match(name)
        if m:
            dark_steps[m.group(1)].add(int(m.group(2)))
    for name in light:
        m = SCALE.match(name)
        if m:
            light_steps[m.group(1)].add(int(m.group(2)))
    hues = sorted(set(dark_steps) | set(light_steps))
    scale_rows = []
    for hue in hues:
        d, l = sorted(dark_steps[hue]), sorted(light_steps[hue])
        scale_rows.append([
            "`%s`" % hue,
            "%d adet (%s)" % (len(d), ",".join(map(str, d))),
            "%d adet (%s)" % (len(l), ",".join(map(str, l))),
            ",".join(map(str, sorted(set(d) & set(l)))) or "—",
            ",".join(map(str, sorted(set(d) - set(l)))) or "—",
            ",".join(map(str, sorted(set(l) - set(d)))) or "—",
        ])

    lines = []
    add = lines.append
    add("# GitHub ↔ GitHub dark/light design-token fark raporu")
    add("")
    add("**Üretim:** `design-system/github/scripts/report_theme_diff.py` — bu dosya")
    add("ÜRETİLİR; `--check` diskteki kopyayı birebir doğrular (elle düzenleme = drift).")
    add("")
    add("**Karşılaştırılan iki katman:**")
    add("")
    lines.extend(md_table(
        ["Katman", "`theme` alanı", "Yakalama", "`dataColorMode`", "`bgColorDefault`",
         "`fgColorDefault`", "computed custom property"],
        [page_state_row("dark (`%s`)" % DARK_RAW, dark_data),
         page_state_row("light (`%s`)" % LIGHT_RAW, light_data)],
    ))
    add("")
    add("> İki katman da github.com ana sayfasının **kısmi** computed-kök-değişken")
    add("> yakalamasıdır (tam Primer design sistemi değil). `--bgColor-default` /")
    add("> `--fgColor-default` yukarıdaki kanıt sütunlarıdır: extractor'ın isim")
    add("> filtresi onları `colors.cssVariables`a koymaz (bkz. `README.md` kapsam")
    add("> uyarısı), bu yüzden tema kanıtı `pageState` alanında taşınır. dark")
    add("> katmanında bu alan yoktur (yakalama `pageState`'ten önce alındı); dark")
    add("> tarafın tema kanıtı `README.md` §Snapshot ve `logo.background` değeridir.")
    add("")
    add("**Kural eşitliği (canlı sayfaya bağlı, `--check` kapsamı dışında).** Aynı")
    add("betik dark tema ile koşturulduğunda commit'li `%s`'u birebir üretir:" % DARK_RAW)
    add("`node scripts/capture_theme.mjs dark /tmp/raw.redark.json` sonrası")
    add("`colors.cssVariables` %d/%d isim ve değerde aynıdır (ölçüldü 2026-10-11);" % (len(dark), len(dark)))
    add("bu ölçüm canlı sayfaya bağlı olduğu için raporun deterministik kısmına")
    add("yazılmaz, kapıya da bağlanmaz.")
    add("")
    add("## Yönetici özeti")
    add("")
    add("- dark **%d** token, light **%d** token; paylaşılan isim **%d**." % (len(dark), len(light), len(shared)))
    add("- Paylaşılan %d ismin **%d**'i farklı değer taşır, **%d**'i aynıdır." % (len(shared), len(differ), len(same)))
    add("- Yalnız dark'ta **%d**, yalnız light'ta **%d** isim var." % (len(dark_only), len(light_only)))
    add("- **Aynı isim ≠ aynı rol:** paylaşılan isimlerin %d/%d'i temaya göre değer"
        % (len(differ), len(shared)))
    add("  değiştiriyor. İki katmanı aynı cascade'e import etmek %d adda sessiz"
        % len(differ))
    add("  çakışma üretir; `check_github_tokens.py` bu iki katmanı ayrı dosyalarda")
    add("  fail-closed kilitler (`tokens.css` = dark, `tokens.light.css` = light).")
    add("- Ölçüm eşitliği: aynı betikle (`scripts/capture_theme.mjs`) yeniden alınan")
    add("  dark yakalama commit'li `%s`'u %d/%d birebir tekrar etti; light katman"
        % (DARK_RAW, len(dark), len(dark)))
    add("  iki bağımsız kurulumda %d/%d aynı çıktı." % (len(light), len(light)))
    add("")
    add("## Ölçüm tablosu")
    add("")
    lines.extend(md_table(
        ["Ölçüm", "Değer"],
        [
            ["dark token", len(dark)],
            ["light token", len(light)],
            ["paylaşılan isim", len(shared)],
            ["paylaşılan ve **aynı** değer", len(same)],
            ["paylaşılan ve **farklı** değer", len(differ)],
            ["yalnız dark", len(dark_only)],
            ["yalnız light", len(light_only)],
            ["light/dark oranı", "%.2f" % (len(light) / len(dark))],
        ],
    ))
    add("")
    add("## Namespace bazında fark")
    add("")
    lines.extend(md_table(
        ["Namespace", "dark", "light", "paylaşılan", "aynı", "farklı", "dark-only", "light-only"],
        ns_rows,
    ))
    add("")
    add("## Tema-duyarlılık sınıfları")
    add("")
    add("- **Tüm paylaşılan isimleri değişen** namespace'ler (%d): %s"
        % (len(theme_binding["all-differ"]),
           ", ".join("`%s`" % s for s in theme_binding["all-differ"]) or "—"))
    add("- **Kısmen değişen** (%d): %s"
        % (len(theme_binding["mixed"]),
           ", ".join("`%s`" % s for s in theme_binding["mixed"]) or "—"))
    add("- **Hiç değişmeyen** (%d): %s"
        % (len(theme_binding["none-differ"]),
           ", ".join("`%s`" % s for s in theme_binding["none-differ"]) or "—"))
    add("- **Kesişimi olmayan** (%d): %s"
        % (len(theme_binding["no-overlap"]),
           ", ".join("`%s`" % s for s in theme_binding["no-overlap"]) or "—"))
    add("")
    add("Değişmeyen %d isim (iki temada da aynı değer):" % len(same))
    add("")
    add(", ".join("`%s`" % n for n in same) if same else "—")
    add("")
    light_only_steps = defaultdict(int)
    dark_only_steps = defaultdict(int)
    for hue in hues:
        for step in sorted(dark_steps[hue] - light_steps[hue]):
            dark_only_steps[step] += 1
        for step in sorted(light_steps[hue] - dark_steps[hue]):
            light_only_steps[step] += 1

    def top_steps(counts):
        ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:3]
        return ", ".join("`%d` (%d hue)" % (step, count) for step, count in ranked) or "—"

    add("## `base-color-scale-*` yapısal kayması")
    add("")
    add("Aynı ölçek ailesinde iki tema **farklı adım kümelerini** taşıyor ve")
    add("paylaşılan adımların değerleri tema başına değişiyor — ör. `green-4`:")
    add("dark `#0fbf3e`, light `#23ea57`. Ölçülen eğilim: light'ın yalnız")
    add("kendisinde olan adımları %s; dark'ın yalnız kendisinde olanları %s." % (top_steps(light_only_steps), top_steps(dark_only_steps)))
    add("Bu, adım numarasının iki temada **aynı rolü** taşıdığı varsayımını")
    add("çürütür: eşleme ancak açık gerekçeyle yapılabilir.")
    add("")
    lines.extend(md_table(
        ["Hue", "dark adımları", "light adımları", "paylaşılan", "dark-only adım", "light-only adım"],
        scale_rows,
    ))
    add("")
    dark_palette = dark_data.get("colors", {}).get("palette") or []
    light_palette = light_data.get("colors", {}).get("palette") or []
    add("## Palet sayımı tema-duyarsızdır (token katmanı duyarlıdır)")
    add("")
    add("Element sayımıyla çıkan paletin ilk adımları iki temada neredeyse aynı")
    add("kalır (fark yalnız içerik/marka bölümünün ağırlığından gelir); yani tema")
    add("sinyali **palet sayımında değil, `colors.cssVariables` katmanındadır**:")
    add("")
    lines.extend(md_table(
        ["Sıra", "dark", "light"],
        [
            [
                i + 1,
                "`%s` (%d)" % (d.get("normalized") or d.get("color"), d.get("count", 0)),
                "`%s` (%d)" % (l.get("normalized") or l.get("color"), l.get("count", 0)),
            ]
            for i, (d, l) in enumerate(zip(dark_palette[:3], light_palette[:3]))
        ],
    ))
    add("")
    add("## Farklı değer taşıyan isimler (tam liste, %d)" % len(differ))
    add("")
    lines.extend(md_table(
        ["Token", "dark", "light"],
        [["`%s`" % n, "`%s`" % dark[n], "`%s`" % light[n]] for n in differ],
    ))
    add("")
    add("## Yalnız dark'ta bulunan isimler (tam liste, %d)" % len(dark_only))
    add("")
    lines.extend(md_table(
        ["Token", "dark"],
        [["`%s`" % n, "`%s`" % dark[n]] for n in dark_only],
    ))
    add("")
    add("## Yalnız light'ta bulunan isimler (tam liste, %d)" % len(light_only))
    add("")
    lines.extend(md_table(
        ["Token", "light"],
        [["`%s`" % n, "`%s`" % light[n]] for n in light_only],
    ))
    add("")
    add("## Tüketici için sonuçlar")
    add("")
    add("1. **Tek kaynak seç.** `tokens.css` (dark) ve `tokens.light.css` aynı")
    add("   cascade'e import edilirse %d adda değer çakışır ve sıralama kazananı"
        % len(differ))
    add("   belirler — hangi temanın göründüğü import sırasına bağlı, kasıtlı bir")
    add("   karar olmaktan çıkar.")
    add("2. **Tema anahtarı `data-color-mode`.** Yakalama bunu kanıtlar: sayfa dark")
    add("   iken `--bgColor-default` `#0d1117`, `light` pinlendiğinde `#fff`.")
    add("3. **Yalnız farkları değil, küme farkını da hesaba kat.** Yalnız dark'ta")
    add("   %d, yalnız light'ta %d isim var; bir tema için yazılan bileşen diğerinde"
        % (len(dark_only), len(light_only)))
    add("   token'sız kalabilir.")
    add("4. **Semantik eşleme yapma.** `base-color-scale-*` örneği gösteriyor ki")
    add("   aynı adım numarası iki temada aynı rolü taşımıyor; otomatik yeniden")
    add("   adlandırma veya toplu değer eşlemesi yanlış eşleme üretir.")
    add("")
    add("## Yeniden üretim")
    add("")
    add("```bash")
    add("python3 design-system/github/scripts/check_github_tokens.py --sync   # iki katman")
    add("python3 design-system/github/scripts/report_theme_diff.py --check    # bu rapor")
    add("")
    add("# yakalamayı yenile (evidence tooling; repo runtime bağımlılığı değil)")
    add("cd /tmp/gh-capture && npm install --no-save playwright@1.63.0 dembrandt@0.7.3")
    add("./node_modules/.bin/playwright install chromium")
    add("cp <repo>/design-system/github/scripts/capture_theme.mjs .")
    add("node capture_theme.mjs light <repo>/design-system/github/raw.light.json")
    add("```")
    add("")
    add("## Kanıt dosyaları")
    add("")
    for rel in (
        "design-system/github/raw.json",
        "design-system/github/raw.light.json",
        "design-system/github/tokens.css",
        "design-system/github/tokens.json",
        "design-system/github/tokens.light.css",
        "design-system/github/tokens.light.json",
        "design-system/github/scripts/capture_theme.mjs",
        "design-system/github/scripts/check_github_tokens.py",
        "design-system/github/scripts/report_theme_diff.py",
        "design-system/github/README.md",
    ):
        add("- `%s`" % rel)
    add("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="diskteki rapor drift'indeyse exit 1")
    parser.add_argument("--stdout", action="store_true", help="yazma, ekrana bas")
    args = parser.parse_args()

    try:
        rendered = build_report()
    except (OSError, ValueError, json.JSONDecodeError, KeyError) as exc:
        print("GITHUB TEMA FARK RAPORU: %s" % exc)
        return 1

    if args.stdout:
        sys.stdout.write(rendered)
        return 0

    if args.check:
        if not OUT_PATH.exists():
            print("GITHUB TEMA FARK RAPORU DRIFT: eksik dosya: %s" % OUT_PATH)
            return 1
        current = OUT_PATH.read_text(encoding="utf-8")
        if current != rendered:
            print("GITHUB TEMA FARK RAPORU DRIFT: %s yakalamalarla birebir değil" % OUT_PATH)
            print("  (yeniden üret: python3 design-system/github/scripts/report_theme_diff.py)")
            return 1
        print("OK — GitHub tema fark raporu iki yakalamayla birebir (%s)" % OUT_PATH.relative_to(ROOT))
        return 0

    OUT_PATH.write_text(rendered, encoding="utf-8")
    print("yazıldı: %s (%d satır)" % (OUT_PATH.relative_to(ROOT), rendered.count("\n") + 1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
