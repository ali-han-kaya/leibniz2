#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gen_precommit_inventory.py — pre-commit doc envanteri üreticisi.

Neden ÜRETİLİR (elle yazılmaz): `skills/verify-chain/SKILL.md`'de
"Existing hook inventory" bloğu `.pre-commit-config.yaml`'den üretilir.
Bu, `.pre-commit-config.yaml` TEK KAYNAKTUR — envanter elle yazılmaz;
doküman `python3 _calisma/CIKTI/gen_precommit_inventory.py` ile üretilir.

Kullanım:
    python3 _calisma/CIKTI/gen_precommit_inventory.py            # üret
    python3 _calisma/CIKTI/gen_precommit_inventory.py --check     # drift → rc 1
    python3 _calisma/CIKTI/gen_precommit_inventory.py --json      # veri

stdlib-only. OFFLINE (yalnız çalışma ağacı okunur).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
CIKTI = os.path.join(ROOT, "_calisma", "CIKTI")

sys.path.insert(0, ROOT)
from _calisma.CIKTI import check_precommit_inventory as gate  # noqa: E402

CONFIG_PATH = os.path.join(ROOT, ".pre-commit-config.yaml")
DOC_PATH = os.path.join(ROOT, "skills", "verify-chain", "SKILL.md")

# Envanter işareti — bulunamazsa kapı körleşir (exit 2).
MARKER = "Existing hook inventory"


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _yaml_hook_ids(text):
    """`repos:` bölümündeki hook id'lerini sıra korunarak döndürür."""
    lines = text.splitlines()
    start = None
    ids = []
    for i, line in enumerate(lines):
        if line.strip() == "repos:":
            start = i
            break
    if start is None:
        return []
    for line in lines[start + 1:]:
        match = re.match(r"^\s*-\s*id:\s*([A-Za-z0-9][A-Za-z0-9_.-]*)\s?$", line)
        if match:
            ids.append(match.group(1))
    # Tekilleştir (sıra korunur)
    seen = set()
    result = []
    for id_ in ids:
        if id_ not in seen:
            seen.add(id_)
            result.append(id_)
    return result


def _doc_inventory_block(text):
    """Dokümandaki 'Existing hook inventory' bloğunu ve satır numaralarını döndürür.

    Döner: (hook_ids_list, (marker_idx, fence_idx, end_fence))
    hook_ids_list: bloktan çıkarılan hook id'leri (sıra korunmuş, tekilleşmiş)
    marker_idx: "Existing hook inventory" satırı indeksi
    fence_idx: kod bloğu başlayan ``` satırı indeksi
    end_fence: kod bloğun sonundaki ``` satırı indeksi
    None, None: marker bulunamazsa
    """
    lines = text.splitlines()
    marker = None
    for i, line in enumerate(lines):
        if MARKER in line:
            marker = i
            break
    if marker is None:
        return None, None

    # İşaret sonrası ``` kod bloğunu bul
    fence = None
    for j in range(marker + 1, len(lines)):
        if lines[j].strip().startswith("```"):
            fence = j
            break
    if fence is None:
        return None, None

    # Kod bloğunun sonundaki ```'ı bul
    end_fence = None
    for j in range(fence + 1, len(lines)):
        if lines[j].strip() == "```":
            end_fence = j
            break
    if end_fence is None:
        return None, None

    # Kod bloğundaki satırları çıkar - sadece hook id'leri (ilk token)
    code_lines = lines[fence + 1:end_fence]
    hook_ids = []
    for line in code_lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        # İlk token'ı al (space'den önceki kelime)
        parts = stripped.split()
        if parts:
            hook_ids.append(parts[0])

    return hook_ids, (marker, fence, end_fence)


def _replace_hook_inventory_block(lines, hook_ids, marker_idx, fence_idx, end_fence):
    """SKILL.md içindeki Existing hook inventory bloğunu günceller.

    Bloğun formatı:
    ```
    Existing hook inventory:

    ```
    id1                  # comment
    id2                  # comment
    ```
    ```
    ```
    Returns the modified lines list.
    """
    # Yeni kod bloğunu oluştur - satırlar zaten yorumları içerir
    new_code_lines = []
    for hid in hook_ids:
        new_code_lines.append(f"  {hid}")

    # Bloğu değiştir: lines[marker_idx : end_fence + 1] ile yeni içerik
    # marker_idx: "Existing hook inventory:" satırı
    # end_fence: ``` son satırı

    # Yeni blok satırları
    new_block = [MARKER]
    new_block.extend(new_code_lines)
    new_block.append("```")

    # Eski bloğu sil, yeniyi yerleştir
    new_lines = lines[:marker_idx] + new_block + lines[end_fence + 1:]

    return new_lines


def build():
    """(markdown, veri) — doküman metni ve makine-okunur özet."""
    # Read config
    config_text = _read(CONFIG_PATH)
    hook_ids = _yaml_hook_ids(config_text)

    # Read doc
    doc_text = _read(DOC_PATH)

    # Check current state
    current_ids, block_info = _doc_inventory_block(doc_text)

    # Build new doc
    if block_info:
        new_lines = _replace_hook_inventory_block(
            doc_text.splitlines(), hook_ids, *block_info
        )
        new_doc = "\n".join(new_lines)
    else:
        # Bloğu yoksa dokümanı değiştirmeden döndür
        new_doc = doc_text

    # Generate summary data
    data = {
        "config_path": CONFIG_PATH,
        "doc_path": DOC_PATH,
        "config_count": len(hook_ids),
        "hook_ids": hook_ids,
        "ok": current_ids == hook_ids if current_ids else False,
        "current_ids": current_ids,
    }

    return new_doc, data


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true",
                    help="doküman bayalsa exit 1 (fail-closed)")
    ap.add_argument("--json", action="store_true", help="makine-okunur özet")
    ap.add_argument("--out", default=DOC_PATH,
                    help="hedef SKILL.md yolu")
    args = ap.parse_args(argv)

    text, data = build()

    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return 0 if data["ok"] else 1

    if args.check:
        try:
            with open(args.out, encoding="utf-8") as fh:
                on_disk = fh.read()
        except OSError as exc:
            print("FAIL: doküman okunamadı: %s (%s)" % (args.out, exc))
            return 1
        if on_disk != text:
            print("FAIL: %s BAYAT — yeniden üret: python3 %s"
                  % (os.path.relpath(args.out, ROOT),
                     os.path.join("_calisma", "CIKTI", "gen_precommit_inventory.py")))
            return 1
        print("PASS: envanter dokümanı güncel (%d hook)" % data["config_count"])
        return 0

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write(text)
    print("yazıldı: %s" % args.out)
    print("  %d hook · kapı %s" % (data["config_count"], "yeşil" if data["ok"] else "KIRMIZI"))
    return 0 if data["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())