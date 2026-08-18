#!/usr/bin/env python3
"""
diff_config_artifacts.py — config artifact'ları arası diff (advisory uyarı).

CI'da 'config' artifact bundle'ı iki dosya içerir:
  verify_delivery.config.json  — repo'daki ham config (commit'li)
  effective_config.json        — verify_delivery.py'nin çözümlediği etkin
                                  config (varsayılanlar + CLI override'ları)

Bu betik ikisini karşılaştırır; farklı alanları insan-okur ve makine-okur
çıktıya yazar. Fark bulunursa UYARI basar ama exit 0 döner (advisory —
bloke etmez; bloke eden kapı config-drift job'ıdır).

Fark nedenleri (deterministik sınıflandırma):
  cli_override   — effective_config.cli_overrides.<k>.override == true
  default        — raw config'te alan yok, etkin değer varsayılandan
  drift          — raw config'te alan var ama etkin değer farklı (CLI yok)
  (eşleşme)      — aynı değer; rapora yazılmaz

Çıktılar (--out-dir altına):
  config-diff.txt  — insan-okur tablo (field | raw | effective | neden)
  config-diff.json — makine-okur: {generated, changed, differences[]}

Kullanım:
  python3 diff_config_artifacts.py --config-dir config --out-dir config
  (CI'da verify job'ında 'Bundle config snapshot' adımından sonra çalışır)
"""
import argparse
import datetime
import json
import pathlib
import sys


# effective_config.json'da olup ham config'te olmayan meta alanlar — diff'e
# konmaz (bunlar çözümleme ürünü, "fark" değil).
META_KEYS = {
    "config_path", "source", "cli_overrides",
}
# Karşılaştırılan alanlar: ham config ile etkin config'te ortak anlamlı olanlar.
# cli_overrides anahtarları farklı adlandırılmış (budget_usd → budget);
# aşağıdaki eşleme classify()'te neden tespiti için kullanılır.
COMPARE_KEYS = [
    "budget_usd", "budget_method", "budget_ratios",
    "expected_pages", "expected_refs", "expected_manifest",
]
OVERRIDE_KEY = {
    "budget_usd": "budget",
    "budget_method": "budget_method",
}


def classify(field, raw_val, eff_val, effective):
    """Farkın nedenini belirle (deterministik)."""
    ov_key = OVERRIDE_KEY.get(field)
    ov = (effective.get("cli_overrides") or {}).get(ov_key) if ov_key else None
    if ov and ov.get("override"):
        return "cli_override"
    if raw_val is None:
        return "default"
    return "drift"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config-dir", default="config",
                    help="config artifact'larının bulunduğu dizin "
                         "(verify_delivery.config.json + effective_config.json)")
    ap.add_argument("--out-dir", default="config",
                    help="diff çıktı dizini (varsayılan: --config-dir)")
    args = ap.parse_args()

    cfg_dir = pathlib.Path(args.config_dir)
    raw_path = cfg_dir / "verify_delivery.config.json"
    eff_path = cfg_dir / "effective_config.json"

    missing = [p.name for p in (raw_path, eff_path) if not p.is_file()]
    if missing:
        print(f"UYARI: diff_config_artifacts — eksik dosya(lar): {missing} "
              f"(atlanıyor, advisory)", file=sys.stderr)
        return 0

    raw = json.loads(raw_path.read_text(encoding="utf-8"))
    effective = json.loads(eff_path.read_text(encoding="utf-8"))

    differences = []
    for field in COMPARE_KEYS:
        raw_val = raw.get(field)
        eff_val = effective.get(field)
        if raw_val == eff_val:
            continue
        differences.append({
            "field": field,
            "raw": raw_val,
            "effective": eff_val,
            "reason": classify(field, raw_val, eff_val, effective),
        })

    now = datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")
    out = {
        "tool": "diff_config_artifacts",
        "generated": now,
        "changed": bool(differences),
        "compared_fields": COMPARE_KEYS,
        "differences": differences,
    }

    out_dir = pathlib.Path(args.out_dir)
    out_dir.mkdir(exist_ok=True)

    lines = [
        "CONFIG DIFF (advisory) — raw (verify_delivery.config.json) vs "
        "effective (effective_config.json)",
        f"generated: {now}",
        "=" * 72,
        f"{'FIELD':<20} {'RAW':<22} {'EFFECTIVE':<22} NEDEN",
        "-" * 72,
    ]
    for d in differences:
        lines.append(
            f"{d['field']:<20} {str(d['raw']):<22} {str(d['effective']):<22} "
            f"{d['reason']}")
    lines += ["-" * 72]
    if differences:
        lines.append(f"UYARI: {len(differences)} fark bulundu — bloke etmez "
                     f"(advisory). Bloke eden kapı: config-drift job'ı.")
    else:
        lines.append("Fark yok: ham config ile etkin config aynı.")
    lines.append("=" * 72)
    lines.append("")

    (out_dir / "config-diff.txt").write_text("\n".join(lines), encoding="utf-8")
    (out_dir / "config-diff.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")

    if differences:
        print(f"[CONFIG-DIFF] UYARI: {len(differences)} fark bulundu → "
              f"{out_dir / 'config-diff.txt'} (advisory, bloke etmez)")
        for d in differences:
            print(f"  {d['field']}: {d['raw']!r} → {d['effective']!r} "
                  f"({d['reason']})")
    else:
        print(f"[CONFIG-DIFF] fark yok → {out_dir / 'config-diff.txt'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
