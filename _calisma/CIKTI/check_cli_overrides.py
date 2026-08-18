#!/usr/bin/env python3
"""check_cli_overrides.py — effective_config.json'daki CLI override'larını
bütçe raporu artifact'ına uyarı olarak yaz.

verify.yml'deki budget job'u bu betiği, verify job'unun --config-out ile
ürettiği effective_config.json üzerinde çalıştırır. effective_config'in
cli_overrides.<param>.override==true olması, bütçe kalkanının dosyadaki
değerle DEĞİL CLI'dan verilen değerle koştuğu anlamına gelir (ör. `--budget
25` veya `--budget-method universal`). Bu, tekrarlanabilirlik denetimi için
kayda değer bir sapmadır; advisory uyarı olarak budget/index.json'a
(cli_overrides alanı) ve budget/cli_overrides_warning.txt'ye yazılır.

Kullanım:
  python3 check_cli_overrides.py --config effective_config.json \
      --index budget/index.json --out-dir budget

Davranış:
  - config yoksa / okunamıyorsa: UYARI yazar, exit 0 (advisory; bütçe kapısı
    budget aşımıdır, bu betik denetim izi sağlar).
  - override yoksa: "override yok" kaydı yazar (denetim izi her zaman tam).
  - override varsa: her parametre için file_value → effective kaydı yazar ve
    index.json'a cli_overrides.warning=true işaretler.
"""
import argparse
import json
import os
import sys


def collect_overrides(cfg):
    """cli_overrides dict'inden override==true olan kayıtları döndür.

    Döndürür: (overrides: list[dict], raw: dict). raw, cfg'deki cli_overrides
    bloğunun kendisidir (yoksa {}).
    """
    raw = cfg.get("cli_overrides", {})
    if not isinstance(raw, dict):
        return [], {}
    overrides = []
    for key, rec in raw.items():
        if not isinstance(rec, dict):
            continue
        if rec.get("override"):
            overrides.append({
                "key": key,
                "cli_value": rec.get("cli_value"),
                "file_value": rec.get("file_value"),
                "effective": rec.get("effective"),
            })
    return overrides, raw


def render_lines(overrides, cfg):
    lines = []
    if not overrides:
        lines.append("CLI override YOK — bütçe, dosya config değerleriyle koştu.")
        return lines
    lines.append(f"CLI override TESPİT EDİLDİ ({len(overrides)} parametre):")
    for o in overrides:
        lines.append(
            f"  {o['key']}: {o['file_value']!r} → {o['effective']!r} "
            f"(CLI verildi)"
        )
    lines.append(
        "Bütçe kalkanı yukarıdaki parametrelerde DOSYA değeriyle DEĞİL, "
        "CLI değeriyle koştu — tekrarlanabilirlik denetiminde dikkate alın."
    )
    return lines


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True, help="effective_config.json yolu")
    ap.add_argument("--index", default="budget/index.json",
                    help="güncellenecek budget/index.json yolu")
    ap.add_argument("--out-dir", default="budget",
                    help="cli_overrides_warning.txt çıktı dizini")
    args = ap.parse_args(argv)

    cfg = None
    if os.path.isfile(args.config):
        try:
            with open(args.config, encoding="utf-8") as f:
                cfg = json.load(f)
        except (OSError, ValueError) as e:
            print(f"UYARI: effective_config okunamadı ({args.config}): {e}",
                  file=sys.stderr)

    if cfg is None:
        overrides, raw = [], {}
        lines = ["effective_config.json bulunamadı/okunamadı — "
                 "CLI override denetimi yapılamadı."]
        warning = False
    else:
        overrides, raw = collect_overrides(cfg)
        lines = render_lines(overrides, cfg)
        warning = bool(overrides)

    # 1) İnsan-okur uyarı dosyası (her zaman yazılır — denetim izi tam).
    os.makedirs(args.out_dir, exist_ok=True)
    txt_path = os.path.join(args.out_dir, "cli_overrides_warning.txt")
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"[CLI-OVERRIDE] warning={warning} → {txt_path}")

    # 2) budget/index.json'a cli_overrides alanı ekle (varsa).
    if not os.path.isfile(args.index):
        print(f"UYARI: index yok ({args.index}) — yalnızca txt yazıldı.",
              file=sys.stderr)
    else:
        try:
            with open(args.index, encoding="utf-8") as f:
                index = json.load(f)
        except (OSError, ValueError) as e:
            print(f"UYARI: index okunamadı ({args.index}): {e}", file=sys.stderr)
            index = None
        if index is not None:
            index["cli_overrides"] = {
                "warning": warning,
                "overrides": overrides,
                "raw": raw,
            }
            with open(args.index, "w", encoding="utf-8") as f:
                json.dump(index, f, indent=2, ensure_ascii=False)
            print(f"[CLI-OVERRIDE] index.json güncellendi: {args.index}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
