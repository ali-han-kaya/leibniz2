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
      --index budget/index.json --out-dir budget \
      --version-out budget/cli_overrides_version.json

Davranış:
  - config yoksa / okunamıyorsa: UYARI yazar, exit 0 (advisory; bütçe kapısı
    budget aşımıdır, bu betik denetim izi sağlar).
  - override yoksa: "override yok" kaydı yazar (denetim izi her zaman tam).
  - override varsa: her parametre için file_value → effective kaydı yazar ve
    index.json'a cli_overrides.warning=true işaretler.
  - --version-out verilirse refs-online/run-history deseninde bir VERSION
    JSON yazar (tool/date/ts + warning + overrides + summary) — her run'da
    override trendini makine-okur takip etmek için (CI artifact sidecar).
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
    ap.add_argument("--config", default=None,
                    help="effective_config.json yolu (--cross-check ile gerekmez)")
    ap.add_argument("--index", default="budget/index.json",
                    help="güncellenecek budget/index.json yolu")
    ap.add_argument("--out-dir", default="budget",
                    help="cli_overrides_warning.txt çıktı dizini")
    ap.add_argument("--version-out", default=None,
                    help="VERSION JSON sidecar yolu (refs-online/run-history "
                         "deseninde; her run'da override trendi için)")
    ap.add_argument("--cross-check", nargs=2, metavar=("INDEX", "VERSION"),
                    default=None,
                    help="İki override kaynağını aynı anda okuyup tutarlılığı "
                         "doğrula: budget/index.json + cli_overrides_version.json. "
                         "Tutarsızlık → exit 2 (advisory); yok → exit 0")
    args = ap.parse_args(argv)

    if args.cross_check is not None:
        # --cross-check: ek yazma davranışı yok, yalnızca denetim.
        # exit 0 = tutarlı, exit 2 = tutarsızlık (advisory, CI'ı kırmaz).
        index_path, version_path = args.cross_check
        ok, detail, problems = cross_check(index_path, version_path)
        if ok:
            print(f"[CLI-OVERRIDE] cross-check: PASS — "
                  f"{index_path} ↔ {version_path} tutarlı")
        else:
            print(f"[CLI-OVERRIDE] cross-check: FAIL — {detail}")
            for p in problems:
                print(f"  - {p}")
        return 0 if ok else 2

    cfg = None
    if args.config and os.path.isfile(args.config):
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

    # 3) VERSION JSON sidecar (refs-online/run-history deseni) — her run'da
    # override trendini makine-okur izle: ts + warning + overrides + özet.
    if args.version_out:
        os.makedirs(os.path.dirname(os.path.abspath(args.version_out)),
                    exist_ok=True)
        version = {
            "tool": "check_cli_overrides.py — CLI override denetimi "
                    "(effective_config.json cli_overrides)",
            "ts": __import__("datetime").datetime.now(
                __import__("datetime").timezone.utc).isoformat(),
            "warning": warning,
            "override_count": len(overrides),
            "overrides": overrides,
            "config_read": cfg is not None,
            # refs-online/run-history trend'lerinde kullanılan özet alanlar:
            "summary": "CLI override TESPİT EDİLDİ (%d parametre)" % len(overrides)
                        if overrides else "CLI override YOK",
        }
        try:
            with open(args.version_out, "w", encoding="utf-8") as f:
                json.dump(version, f, indent=2, ensure_ascii=False)
            print(f"[CLI-OVERRIDE] VERSION JSON yazıldı: "
                  f"{args.version_out} (override={len(overrides)})")
        except OSError as e:
            print(f"UYARI: VERSION JSON yazılamadı ({args.version_out}): {e}",
                  file=sys.stderr)

    return 0


def cross_check(index_path, version_path):
    """İki override kaynağını aynı anda okuyup tutarlılığı doğrular.

    budget/index.json'daki cli_overrides alanı ile cli_overrides_version.json
    (VERSION JSON sidecar) aynı veriyi taşımalıdır — ikisi de
    check_cli_overrides.py tarafından yazılır. Tutarsızlık → pipeline drift.

    Döndürür (ok: bool, detail: str, problems: list[str]).
    """
    problems = []

    # 1) İki dosyayı oku (biri eksikse tutarlılık denetlenemez — atla).
    index_data = None
    if os.path.isfile(index_path):
        try:
            with open(index_path, encoding="utf-8") as f:
                index_data = json.load(f)
        except (OSError, ValueError) as e:
            problems.append(f"index.json okunamadı: {e}")
            return False, "index.json bozuk", problems
    else:
        # index yok — ama version'da override varsa veri kaybı şüphesi.
        problems.append(f"index.json yok: {index_path}")
        version_data = None
        if os.path.isfile(version_path):
            try:
                with open(version_path, encoding="utf-8") as f:
                    version_data = json.load(f)
            except (OSError, ValueError):
                pass
        if version_data and version_data.get("overrides"):
            problems.append(
                f"VERSION JSON {len(version_data['overrides'])} override "
                "kaydederken index.json yok — veri kaybı şüphesi")
        return False, "index.json bulunamadı", problems

    version_data = None
    if os.path.isfile(version_path):
        try:
            with open(version_path, encoding="utf-8") as f:
                version_data = json.load(f)
        except (OSError, ValueError) as e:
            problems.append(f"version.json okunamadı: {e}")
            return False, "version.json bozuk", problems
    else:
        problems.append(f"version.json yok: {version_path}")
        return False, "version.json bulunamadı", problems

    # 2) index.json'dan cli_overrides bloğunu çıkar.
    idx_cov = index_data.get("cli_overrides")
    if not isinstance(idx_cov, dict):
        problems.append("index.json'da cli_overrides dict değil/yok")
        # version'da override varsa ciddi tutarsızlık.
        ver_ov = version_data.get("overrides", [])
        if ver_ov:
            problems.append(
                f"VERSION JSON {len(ver_ov)} override kaydederken "
                "index.json'da cli_overrides yok — veri kaybı şüphesi")
        return not problems, "; ".join(problems) if problems else "PASS", problems

    # 3) warning bayrağı eşleşmeli.
    idx_warn = idx_cov.get("warning", False)
    ver_warn = version_data.get("warning", False)
    if idx_warn != ver_warn:
        problems.append(
            f"warning bayrağı uyuşmuyor: index={idx_warn}, version={ver_warn}")

    # 4) override_count eşleşmeli.
    idx_count = len(idx_cov.get("overrides", []))
    ver_count = version_data.get("override_count", 0)
    if idx_count != ver_count:
        problems.append(
            f"override sayısı uyuşmuyor: index={idx_count}, version={ver_count}")

    # 5) Her override kaydı birebir eşleşmeli (key → {file_value, effective}).
    idx_map = {
        o.get("key"): {"file_value": o.get("file_value"),
                       "effective": o.get("effective")}
        for o in idx_cov.get("overrides", [])
    }
    ver_map = {
        o.get("key"): {"file_value": o.get("file_value"),
                       "effective": o.get("effective")}
        for o in version_data.get("overrides", [])
    }
    all_keys = sorted(set(idx_map) | set(ver_map))
    for key in all_keys:
        if key not in idx_map:
            problems.append(f"{key}: index'te yok, version'da var")
        elif key not in ver_map:
            problems.append(f"{key}: index'te var, version'da yok")
        else:
            if idx_map[key] != ver_map[key]:
                problems.append(
                    f"{key}: uyuşmaz index={idx_map[key]}, version={ver_map[key]}")

    ok = not problems
    detail = "PASS" if ok else "; ".join(problems)
    return ok, detail, problems


if __name__ == "__main__":
    sys.exit(main())
