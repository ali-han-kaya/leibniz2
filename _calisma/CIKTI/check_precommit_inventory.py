#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_precommit_inventory.py — pre-commit doc envanteri ↔ gerçek config.

Neden: `.pre-commit-config.yaml` zincirin TEK gerçeğidir. Zinciri ANLATAN
dokümanlar elle güncellenir ve sessizce bayatlar — ölçüldü (2026-09-28):
`skills/verify-chain/SKILL.md` "Existing hook inventory" bloğu 19 hook
sayarken config'te 60 hook var; 41 kapı belgesiz kalmış. Bayat envanter
ölçümü değil, ANLATIYI bozar: okuyucu (ve ajan) zincirin yarısını görmez.

Sözleşme (seam = kapı CLI'si):
- GERÇEK küme: `.pre-commit-config.yaml` `repos:` bölümündeki `- id:` satırları.
  stdlib-only ayrıştırma (regex) — hook ortamında PyYAML olmayabilir; YAML
  yükleyicisi kapıyı ortam-bağımlı yapardı.
- ENVANTER kümesi: hedef dokümanda "hook inventory" işaretinden (büyük/küçük
  harf duyarsız) SONRAKİ ilk kod bloğu; her satırın `#` öncesi ilk token'ı
  (`id  # açıklama` biçimi). Sıra ve yorumlar serbesttir.
- İKİ YÖNLÜ fark:
    * fazla  (phantom) — dokümanda adı geçen, config'te OLMAYAN hook:
      kaldırılmış/yeniden adlandırılmıştır → envanter KESİN bayat.
    * eksik  (missing) — config'te olan, dokümanda belgesiz kapı: envanter
      tamamlanmamış (kapsam sessizce daralmış).
- Varsayılan ADVISORY — istek sözleşmesi "bayat-ise UYARI versin": fark
  bulunursa uyarı basılır ve exit 0 kalır (commit bloklanmaz; bayatlık bir
  belge-kalitesi sinyalidir, kod doğruluğu değil). `--strict` ile aynı fark
  exit 1 yapar (fail-closed; CI/pre-commit sıkı modu).
- ÖLÇÜM YAPILAMIYORSA exit 2: config yok/boş, "hook inventory" işareti yok,
  kod bloğu yok. Körleşen bir envanter kapısı sessiz PASS üretmemelidir —
  işaret/k blok yeniden adlandırıldıysa bu GÖRÜNÜR olmalıdır.

Exit: 0 = senkron (veya advisory modda bayat), 1 = --strict altında bayat,
2 = kullanım/ölçüm hatası.
--json: {ok, stale, strict, config_path, doc_path, config_count, doc_count,
         missing[], phantom[]} makine-okunur.
"""

import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))

DEFAULT_CONFIG = os.path.join(ROOT, ".pre-commit-config.yaml")
# Kanonik envanter yüzeyi: beceri dokümanındaki "Existing hook inventory" bloğu.
DEFAULT_DOC = os.path.join(ROOT, "skills", "verify-chain", "SKILL.md")

# Envanter işareti — bulunamazsa kapı körleşir (exit 2).
MARKER = "hook inventory"

# Config satırı: yalnız `repos:` bölümünde `- id: <ad>` (hook düzeyi).
_CONFIG_ID_RE = re.compile(r"^\s*-\s*id:\s*([A-Za-z0-9][A-Za-z0-9_.-]*)\s*$")
# Envanter token'ı: hook id alfabesi (küçük harf/digit/tire).
_DOC_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def config_hook_ids(text):
    """`repos:` bölümündeki hook id'lerini sıra korunarak döndürür.

    `repos:` yoksa None döner (ölçüm imkânsız — çağıran exit 2 raporlar).
    Tekrar eden id tekilleştirilir (sıra korunur): aynı hook iki kez
    tanımlanırsa küme hesabı yanıltıcı olmasın.
    """
    lines = text.splitlines()
    start = None
    for i, line in enumerate(lines):
        if line.strip() == "repos:":
            start = i
            break
    if start is None:
        return None
    ids = []
    for line in lines[start + 1:]:
        match = _CONFIG_ID_RE.match(line)
        if match:
            ids.append(match.group(1))
    return list(dict.fromkeys(ids))


def doc_inventory(text):
    """Envanter işaretinden sonraki ilk kod bloğundaki hook id'lerini döndürür.

    İşaret veya blok yoksa None (çağıran exit 2 raporlar).
    """
    lines = text.splitlines()
    marker = None
    for i, line in enumerate(lines):
        if MARKER in line.lower():
            marker = i
            break
    if marker is None:
        return None
    fence = None
    for j in range(marker + 1, len(lines)):
        if lines[j].strip().startswith("```"):
            fence = j
            break
    if fence is None:
        return None
    ids = []
    for j in range(fence + 1, len(lines)):
        if lines[j].strip().startswith("```"):
            break
        token = lines[j].split("#", 1)[0].strip()
        if token and _DOC_ID_RE.match(token):
            ids.append(token)
    return list(dict.fromkeys(ids))


def diff_doc(config_ids, doc_ids):
    """(missing, phantom) — config'te olup doc'ta olmayan / doc'ta olup config'te olmayan."""
    cfg, doc = set(config_ids), set(doc_ids)
    return sorted(cfg - doc), sorted(doc - cfg)


def run(config_path=DEFAULT_CONFIG, doc_path=DEFAULT_DOC):
    """Ölçüm. Döner (rc, report_dict). rc 0/1/2 — sözleşme modül başlığında."""
    report = {
        "config_path": config_path,
        "doc_path": doc_path,
        "config_count": 0,
        "doc_count": 0,
        "missing": [],
        "phantom": [],
        "stale": False,
        "ok": False,
    }
    try:
        config_text = _read(config_path)
    except OSError as exc:
        print(f"HATA: config okunamadı: {config_path} ({exc})")
        return 2, report
    config_ids = config_hook_ids(config_text)
    if not config_ids:
        print(f"HATA: `repos:` bölümü veya hook id'si bulunamadı: {config_path}")
        return 2, report
    report["config_count"] = len(config_ids)

    try:
        doc_text = _read(doc_path)
    except OSError as exc:
        print(f"HATA: envanter dokümanı okunamadı: {doc_path} ({exc})")
        return 2, report
    doc_ids = doc_inventory(doc_text)
    if not doc_ids:
        print(f"HATA: '{MARKER}' işareti veya ardındaki kod bloğu bulunamadı: "
              f"{doc_path} — kapı körleşti (işaret/blok yeniden adlandırıldı mı?)")
        return 2, report
    report["doc_count"] = len(doc_ids)

    missing, phantom = diff_doc(config_ids, doc_ids)
    report["missing"], report["phantom"] = missing, phantom
    report["stale"] = bool(missing or phantom)
    report["ok"] = not report["stale"]
    return (0 if report["ok"] else 1), report


def _display(path):
    """Kök-içi yolu göreli, kök-dışını mutlak gösterir (../../.. gürültüsü yok)."""
    rel = os.path.relpath(path, ROOT)
    return path if rel.startswith("..") else rel


def render(report):
    """İnsan-okunur çıktı satırları."""
    lines = []
    lines.append("PRE-COMMIT ENVANTERİ ↔ KONFİG (check-precommit-inventory)")
    lines.append(f"  config: {_display(report['config_path'])} "
                 f"→ {report['config_count']} hook (tek kaynak)")
    lines.append(f"  envanter: {_display(report['doc_path'])} "
                 f"→ {report['doc_count']} hook ('{MARKER}' bloğu)")
    if not report["stale"]:
        lines.append(f"PASS: envanter senkron ({report['config_count']} hook)")
        return lines
    lines.append("BAYAT: doküman envanteri config ile uyuşmuyor.")
    if report["missing"]:
        lines.append(f"  eksik ({len(report['missing'])} — config'te var, "
                     "envanterde YOK): " + ", ".join(report["missing"]))
    if report["phantom"]:
        lines.append(f"  fazla ({len(report['phantom'])} — envanterde var, "
                     "config'te YOK): " + ", ".join(report["phantom"]))
    lines.append("  çözüm: envanter bloğunu `.pre-commit-config.yaml` ile "
                 "hizala (kapı: python3 _calisma/CIKTI/check_precommit_inventory.py).")
    return lines


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="pre-commit doc envanteri ↔ .pre-commit-config.yaml hook "
                    "sayısı/kümesi denetimi (varsayılan: advisory uyarı)")
    ap.add_argument("--config", default=DEFAULT_CONFIG, help="pre-commit config yolu")
    ap.add_argument("--doc", default=DEFAULT_DOC, help="envanter dokümanı yolu")
    ap.add_argument("--strict", action="store_true",
                    help="bayatlıkta exit 1 (varsayılan: yalnız uyarı, exit 0)")
    ap.add_argument("--json", action="store_true", help="makine-okunur JSON")
    args = ap.parse_args(argv)

    rc, report = run(args.config, args.doc)
    report["strict"] = args.strict

    if args.json:
        payload = dict(report)
        payload["ok"] = report["ok"] and rc == 0
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return rc if rc == 2 else (rc if args.strict else 0)

    for line in render(report):
        print(line)
    if rc == 2:
        return 2
    if report["stale"]:
        if args.strict:
            print("SONUÇ: FAIL (--strict) — envanter bayat.")
            return 1
        print("UYARI: envanter bayat (advisory — commit bloklanmadı; "
              "sıkı mod için --strict).")
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
