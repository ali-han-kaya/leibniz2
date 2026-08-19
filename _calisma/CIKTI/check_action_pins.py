#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_action_pins.py — workflow action major sürümlerini pin'le (downgrade kapısı).

pre-commit hook'u: action_pins.json'daki minimum major sürümleri denetler.
Bir action daha ESKİ bir major'a düşürülürse (ör. actions/checkout@v7 → v6)
commit'i BLOKE eder. Lokal ve OFFLINE'dir — ağ çağrısı ve PyYAML YOKTUR
(yalnızca stdlib + hafif regex ile workflow'daki `uses:` satırları okunur).
Ağ bağımlısı node24 runtime denetimi (check_action_runtimes.py) CI'da ayrı
koşar; bu hook onun commit-öncesi, hızlı tamamlayıcısıdır.

Kurallar (fail-closed):
  - action pin'li VE major < pin   → FAIL  (downgrade — commit bloke edilir)
  - action pin'siz (yeni action)    → FAIL  (pin zorunlu; --update ile ekle)
  - action pin'li VE major == pin  → PASS
  - action pin'li VE major > pin   → WARN  (pin yükseltilebilir — --update)
  - lokal action (./...)            → SKIP  (markette değil)

Kullanım:
  python3 check_action_pins.py                 # denetle (exit 0/1)
  python3 check_action_pins.py --update        # mevcut major'ları pin dosyasına yaz
  python3 check_action_pins.py --json          # makine-okur JSON

Exit: 0 = pin'ler karşılandı; 1 = FAIL var (downgrade/pin'siz); 2 = kullanım hatası.
"""
import argparse
import json
import re
import sys

DEFAULT_WORKFLOW = ".github/workflows/verify.yml"
DEFAULT_PINS = "_calisma/CIKTI/action_pins.json"

# Yalnızca kendi satırında `uses:` anahtarı olan satırlar yakalanır; hem
# `- uses: ...` (liste öğesi) hem `        uses: ...` (ayrı satır) biçimini
# yakalar. Değer boşluk/#/tırnakla sınırlanır ki heredoc içi JS/string'ler
# yanlış pozitif üretmesin.
_USES_RE = re.compile(r'^\s*(?:-\s*)?uses:\s*["\']?([^\s"\'#]+)')
_REF_RE = re.compile(r"^v(\d+)$")


def extract_uses(workflow_text):
    """workflow metninden unique `uses:` değerlerini çıkar (görünüm sırasıyla).

    PyYAML gerektirmez; yalnızca satır-başı `uses:` anahtarlarına güvenir.
    """
    seen = set()
    out = []
    for line in workflow_text.splitlines():
        m = _USES_RE.match(line)
        if m:
            value = m.group(1).strip()
            if value and value not in seen:
                seen.add(value)
                out.append(value)
    return out


def split_action(action):
    """'actions/checkout@v7' → (owner_repo, ref, major|None)."""
    if "@" not in action:
        return action, "", None
    owner_repo, ref = action.rsplit("@", 1)
    m = _REF_RE.match(ref or "")
    major = int(m.group(1)) if m else None
    return owner_repo, ref, major


def load_pins(path):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"pin dosyası sözlük olmalı: {path}")
    return data


def check(workflow_text, pins):
    """Denetle. Döndürür finding listesi (verdict: PASS|FAIL|WARN|SKIP)."""
    findings = []
    for action in extract_uses(workflow_text):
        if action.startswith("./") or action.startswith("../"):
            findings.append({"action": action, "major": None, "pinned": None,
                             "verdict": "SKIP",
                             "note": "lokal action (markette değil)"})
            continue
        owner_repo, ref, major = split_action(action)
        if owner_repo in pins:
            pinned = pins[owner_repo]
            if major is None:
                findings.append({"action": action, "major": None, "pinned": pinned,
                                 "verdict": "FAIL",
                                 "note": f"major ayrıştırılamadı (ref='{ref}') — vN bekleniyor"})
            elif major < pinned:
                findings.append({"action": action, "major": major, "pinned": pinned,
                                 "verdict": "FAIL",
                                 "note": f"downgrade: v{major} < pin v{pinned}"})
            elif major > pinned:
                findings.append({"action": action, "major": major, "pinned": pinned,
                                 "verdict": "WARN",
                                 "note": f"pin yükseltilebilir: v{major} > v{pinned} (--update)"})
            else:
                findings.append({"action": action, "major": major, "pinned": pinned,
                                 "verdict": "PASS", "note": f"v{major} == pin"})
        else:
            findings.append({"action": action, "major": major, "pinned": None,
                             "verdict": "FAIL",
                             "note": "pin yok — yeni action action_pins.json'a eklenmeli (--update)"})
    return findings


def collect_pins(workflow_text):
    """Mevcut vN major'ları pin sözlüğü olarak topla (--update için).

    vN biçimli ref'i olmayan (ör. @main/@latest) action'lar atlanır — böylece
    --update asla ayrıştırılamayan bir pin yazmaz (o action sonraki check'te
    "pin yok" FAIL üretir, fail-closed).
    """
    pins = {}
    for action in extract_uses(workflow_text):
        if action.startswith("./") or action.startswith("../"):
            continue
        owner_repo, _ref, major = split_action(action)
        if owner_repo and major is not None:
            pins[owner_repo] = major
    return pins


def main(argv=None):
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--workflow", default=DEFAULT_WORKFLOW,
                    help=f"workflow dosyası (varsayılan: {DEFAULT_WORKFLOW})")
    ap.add_argument("--pins", default=DEFAULT_PINS,
                    help=f"pin dosyası (varsayılan: {DEFAULT_PINS})")
    ap.add_argument("--update", action="store_true",
                    help="mevcut major'ları pin dosyasına yaz")
    ap.add_argument("--json", action="store_true",
                    help="makine-okur JSON çıktısı")
    args = ap.parse_args(argv)

    try:
        with open(args.workflow, encoding="utf-8") as f:
            wf = f.read()
    except OSError as e:
        print(f"HATA: workflow okunamadı ({args.workflow}): {e}", file=sys.stderr)
        return 2

    if args.update:
        pins = collect_pins(wf)
        try:
            with open(args.pins, "w", encoding="utf-8") as f:
                json.dump(pins, f, indent=2, ensure_ascii=False, sort_keys=True)
                f.write("\n")
        except OSError as e:
            print(f"HATA: pin dosyası yazılamadı ({args.pins}): {e}", file=sys.stderr)
            return 2
        print(f"pin dosyası güncellendi: {args.pins}")
        for k in sorted(pins):
            print(f"  {k}: v{pins[k]}")
        return 0

    try:
        pins = load_pins(args.pins)
    except (OSError, ValueError) as e:
        print(f"HATA: pin dosyası okunamadı ({args.pins}): {e}", file=sys.stderr)
        return 2

    findings = check(wf, pins)
    fails = [f for f in findings if f["verdict"] == "FAIL"]
    warns = [f for f in findings if f["verdict"] == "WARN"]

    if args.json:
        print(json.dumps({"workflow": args.workflow, "pins": pins,
                          "findings": findings}, indent=2, ensure_ascii=False))
    else:
        print(f"Action pin denetimi (kaynak: {args.workflow})")
        for f in findings:
            tag = {"PASS": "OK  ", "FAIL": "FAIL", "WARN": "WARN",
                   "SKIP": "SKIP"}[f["verdict"]]
            print(f"  [{tag}] {f['action']:<28} {f['note']}")
        print(f"\nSONUÇ: {'FAIL' if fails else 'PASS'} — "
              f"{sum(1 for f in findings if f['verdict'] == 'PASS')} PASS, "
              f"{len(fails)} FAIL, {len(warns)} WARN, "
              f"{sum(1 for f in findings if f['verdict'] == 'SKIP')} SKIP")
        if warns:
            print("Not: WARN bloke etmez; pin'i yükseltmek için `--update` çalıştırın.")
        if fails:
            print("Downgrade/pin'siz action commit'i bloke eder. "
                  "Gerekirse `--update` ile pin'i yeniden üret (önce sürümü doğrula).")

    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
