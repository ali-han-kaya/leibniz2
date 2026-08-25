#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_refs_table_sync.py — REFERANS_KANIT_DENETIMI §2 tablosu ↔ kod listeleri senkronu.

REFERANS_KANIT_DENETIMI.md §2'deki 64 satırlık ana tabloyu (Kaynak sütunu)
verify_delivery.py'deki REFERENCE_* listelerinin `key` alanlarıyla birebir
karşılaştırır. Drift: koda yeni referans eklenir ama tabloya satır eklenmez
(veya tersi) → sessiz kapsam kaybı / tablo-kod tutarsızlığı → fail-closed.

Eşleştirme stratejisi:
  1. Çapa (anchor) bulucu: her tablo satırından (soyad, yıl) çıkarılır —
     aksan-duyarsız (Lagrée ↔ Lagree), ilk sözcük soyad, ilk 4 haneli yıl.
     Bu, 64 satırın 54'ünü tek anlamlı eşler.
  2. Kalan 10 satır için AÇIK eşleme tablosu (TABLE_OVERRIDES): Hume
     edisyonları (Norton&Norton 2000 = Treatise, Beauchamp 1999 = Enquiry),
     Leibniz Monadologie §32 = 1714, Locke Nidditch 1975 = Essay 1689,
     SEP girdileri, Sextus Loeb Bury. Bu eşlemeler bibliyografik olarak
     birebir doğrudur (kod anahtarıyla aynı eser).
  3. Çift yönlü bijection doğrulaması: her tablo satırı bir kod anahtarına,
     her kod anahtarı bir tablo satırına eşlenmeli; sayılar eşit olmalı.

Kullanım:
  python3 check_refs_table_sync.py            # denetle (exit 0/1)
  python3 check_refs_table_sync.py --json     # makine-okur JSON

Exit: 0 = senkron; 1 = drift (FAIL) veya parse hatası; 2 = kullanım hatası.
"""

import argparse
import json
import pathlib
import re
import sys
import unicodedata

CIKTI = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(CIKTI))

import verify_delivery as vd  # noqa: E402

DEFAULT_MD = CIKTI / "REFERANS_KANIT_DENETIMI.md"

# Kodu çapaladığımız tüm REFERENCE_* listeleri (K6 çevrimiçi + sabit).
REFERENCE_LISTS = (
    "REFERENCE_CROSSREF", "REFERENCE_SEP", "REFERENCE_KNOWN",
    "REFERENCE_OPENLIBRARY", "REFERENCE_ARCHIVE", "REFERENCE_URL",
    "REFERENCE_PERSEUS",
)

# Açık (bibliyografik) eşleme: tablo satır numarası → kod anahtarı.
# Çapa bulucunun tek anlamlı eşleyemediği 10 satır (farklı yazım/edisyon).
TABLE_OVERRIDES = {
    28: "Hume 1739-40 Treatise",       # Norton & Norton 2000 = Treatise (OUP)
    29: "Hume 1748 Enquiry",           # Beauchamp 1999 = Enquiry (OUP)
    30: "Hume (Selby-Bigge/Nidditch) 1975",
    34: "Leibniz 1714",                # Monadologie §32 → 1714
    37: "Locke 1689",                  # Locke, Nidditch 1975 = Essay (1689)
    50: "Rosker SEP",
    51: "Baltzly SEP",
    52: "Bolyard SEP",
    53: "Papy SEP",
    62: "Sextus Loeb Bury",
}


def _fold(s):
    """Aksan-duyarsız + küçük harf + boşluk tekilleştirme."""
    s = unicodedata.normalize("NFD", str(s))
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", s).strip().lower()


def _anchor(text):
    """Tablo satırı/kod anahtarından (soyad, yıl) çıkar."""
    t = _fold(text)
    yr = None
    m = re.search(r"\b(1[5-9]\d\d|20\d\d)\b", t)
    if m:
        yr = m.group(1)
    words = t.split()
    return (words[0] if words else ""), yr


def extract_code_keys():
    """verify_delivery.py REFERENCE_* listelerindeki tüm key'ler."""
    keys = {}
    for name in REFERENCE_LISTS:
        lst = getattr(vd, name, None)
        if lst is None:
            raise RuntimeError(f"verify_delivery.py'de {name} listesi yok")
        for r in lst:
            k = r["key"]
            keys.setdefault(k, name)
    return keys


def extract_table_rows(md_text):
    """§2 tablosunu (satır_no, kaynak, sonuç, kanıt) demetlerine ayrıştır."""
    m = re.search(r"## 2\. Tam tablo.*?\n(.*?)\n---", md_text, re.S)
    if not m:
        raise RuntimeError("§2 'Tam tablo' bölümü bulunamadı")
    rows = []
    for line in m.group(1).splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if cells[0] in ("#", "") or cells[0].startswith("---"):
            continue
        rows.append((int(cells[0]), cells[1], cells[2], cells[3]))
    return rows


def build_mapping(table_rows, code_keys):
    """Tablo satırını kod anahtarına eşle; (mapping, findings) döndür."""
    findings = []
    mapping = {}  # satır_no → key

    # Çapa indexi: (soyad, yıl) → [key]
    by_anchor = {}
    for k in code_keys:
        by_anchor.setdefault(_anchor(k), []).append(k)

    for num, kaynak, sonuc, kanit in table_rows:
        # 1) Açık eşleme
        if num in TABLE_OVERRIDES:
            key = TABLE_OVERRIDES[num]
            if key not in code_keys:
                findings.append({
                    "kind": "override_key_missing",
                    "row": num, "kaynak": kaynak, "key": key,
                    "msg": f"satır {num} override'ı '{key}' kodda yok",
                })
                continue
            mapping[num] = key
            continue

        # 2) Çapa eşlemesi
        s, y = _anchor(kaynak)
        cands = by_anchor.get((s, y), [])
        if len(cands) == 1:
            mapping[num] = cands[0]
            continue
        if len(cands) == 0:
            findings.append({
                "kind": "no_match", "row": num, "kaynak": kaynak,
                "msg": f"satır {num} ({kaynak}) hiçbir kod anahtarına eşleşmedi",
            })
        else:
            findings.append({
                "kind": "ambiguous", "row": num, "kaynak": kaynak,
                "cands": cands,
                "msg": f"satır {num} ({kaynak}) birden çok anahtara eşleşti: {cands}",
            })

    # 3) Ters yön: eşlenmemiş kod anahtarları (orphan)
    matched = set(mapping.values())
    for k in sorted(code_keys):
        if k not in matched:
            findings.append({
                "kind": "orphan_key", "key": k,
                "msg": f"kod anahtarı '{k}' tabloda hiçbir satıra eşlenmedi",
            })

    return mapping, findings


def check(md_text=None):
    """Tam denetim. (ok: bool, findings: list, meta: dict) döndür."""
    md_text = md_text if md_text is not None else DEFAULT_MD.read_text(
        encoding="utf-8")
    code_keys = extract_code_keys()
    table_rows = extract_table_rows(md_text)
    mapping, findings = build_mapping(table_rows, code_keys)

    meta = {
        "table_rows": len(table_rows),
        "code_keys": len(code_keys),
        "mapped": len(mapping),
        "overrides": len(TABLE_OVERRIDES),
    }
    ok = (not findings and meta["table_rows"] == meta["code_keys"]
          and meta["mapped"] == meta["table_rows"])
    return ok, findings, meta


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", action="store_true",
                    help="makine-okur JSON çıktısı")
    args = ap.parse_args(argv)

    try:
        ok, findings, meta = check()
    except Exception as e:  # parse/import hatası → fail-closed
        if args.json:
            print(json.dumps({"ok": False, "error": str(e),
                              "findings": []}, ensure_ascii=False))
        else:
            print(f"HATA: {e}")
        return 1

    if args.json:
        print(json.dumps({"ok": ok, "meta": meta, "findings": findings},
                         ensure_ascii=False, indent=2))
    else:
        print(f"REFERANS_KANIT_DENETIMI §2 tablo ↔ kod listeleri senkronu:")
        print(f"  tablo satırı: {meta['table_rows']} | kod anahtarı: "
              f"{meta['code_keys']} | eşlenen: {meta['mapped']} "
              f"| override: {meta['overrides']}")
        if ok:
            print("PASS — tablo-kod birebir senkron.")
        else:
            print("FAIL — tablo-kod drift'i:")
            for f in findings:
                print(f"  ✗ {f['msg']}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
