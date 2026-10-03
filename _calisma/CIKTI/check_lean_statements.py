#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_lean_statements.py — K9 statement-safety kontrolü (fail-closed).

Content.lean'daki 8 teoremin imzasını (ad + sözde-ifade) MAP.md'deki
makine-okunur STATEMENT CONTRACT listesiyle karşılaştırır. Amaç: Z3↔Lean
eşleşme sözleşmesinin (MAP.md) kodla birlikte sürüklenmemesi — teorem adı
veya ifadesi değişirse K9 derlemeye gitmeden P0 üretir.

İmza çıkarımı: `theorem NAME :` satırından ilk `:=`'e kadar olan metin,
whitespace normalize edilerek alınır (çok satırlı ifadeler tek satıra
indirgenir; yorumlar atlanır). MAP.md'deki sözleşme aynı formatta:

    ## STATEMENT CONTRACT
    NAME : ifade

Frozen liste MAP.md'de TEK KAYNAKTIR; bu script yalnızca doğrular.

AYNA BÜTÜNLÜĞÜ (2026-10-03 ölçümü): 8 teorem çekirdeği İKİ kopyada
duruyor — `Content.lean` (shim; bu kapı ve `lean Content.lean` bunu okur)
ve `Leibniz2Reduct/Content.lean` (lake target'ı; `lake build --wfail`
BUNU derler). `lakefile.toml` srcDir="." düzeninde yalnızca kitaplık
adı altındaki modülleri derdiği için shim lake target'ı DEĞİLDİR. İki
kopya byte-eşit olmadığında sözleşme kapısı derlenmeyen dosyayı
doğrular, derlenen dosya ise denetimsiz kalır — ÖLÇÜLDÜ: kütüphane
kopyasına enjekte edilen bir sapma `check_lean_statements`,
`check_lean_axioms`, `lake build --wfail` ve `verify_lean.sh`
kapılarının DÖRDÜ DE yeşil kaldı. Bu yüzden ayna özdeşliği de
fail-closed denetlenir.

Exit: 0 = uyumlu / 1 = drift (eksik/fazla/değişmiş teorem ya da ayna
sapması) / 2 = hata.
Kullanım:
    python3 check_lean_statements.py [--lean-file PATH] [--map PATH]
                                     [--twin-file PATH] [--no-twin] [--json]
"""
import argparse
import hashlib
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
LEAN_DIR = os.path.normpath(os.path.join(HERE, "..", "lean_reduct"))
DEFAULT_LEAN = os.path.join(LEAN_DIR, "Content.lean")
DEFAULT_MAP = os.path.join(LEAN_DIR, "MAP.md")
# lake build'ın derlediği ikinci kopya (shim'in aynası).
DEFAULT_TWIN = os.path.join(LEAN_DIR, "Leibniz2Reduct", "Content.lean")

# STATEMENT CONTRACT başlığı (MAP.md'deki makine-okunur bölüm).
CONTRACT_HEADER = "## STATEMENT CONTRACT"

_THEOREM_RE = re.compile(r"^theorem\s+([A-Za-z0-9_]+)\s*:")
_LINE_COMMENT = re.compile(r"--")


def _strip_line_comment(line):
    """Satır yorumunu (`--`) kes; string'lerdeki `--` korunur (basit maskeleme)."""
    # Lean string literal'leri "..." — içlerindeki `--` yorum değildir.
    out = []
    in_str = False
    i = 0
    while i < len(line):
        ch = line[i]
        if ch == '"':
            in_str = not in_str
            out.append(ch)
        elif ch == "-" and i + 1 < len(line) and line[i + 1] == "-" and not in_str:
            break
        else:
            out.append(ch)
        i += 1
    return "".join(out)


def extract_signatures(lean_text):
    """Content.lean metninden {ad: normalize_ifade} sözlüğü çıkarır.

    `theorem NAME :` satırından ilk `:=`'e kadar (blok yorum atlanarak) toplanır.
    """
    sigs = {}
    lines = lean_text.splitlines()
    i = 0
    while i < len(lines):
        line = _strip_line_comment(lines[i])
        m = _THEOREM_RE.match(line)
        if not m:
            i += 1
            continue
        name = m.group(1)
        # `:` sonrası aynı satırdan başla; `:=`'e kadar devam et.
        stmt = line[m.end():]
        in_block = False
        while i < len(lines):
            # Blok yorum `/- ... -/` atla (çok satırlı).
            if in_block:
                if "-/" in lines[i]:
                    in_block = False
                    # Satırın kalanı ifadeye devam edebilir — basitçe atla.
                i += 1
                continue
            # `:=` dışarıda bulunursa imza bitti.
            if ":=" in stmt:
                stmt = stmt.split(":=", 1)[0]
                break
            if "/-" in stmt:
                # Blok yorum başlangıcı — `-/` yoksa devam satırlarını yut.
                if "-/" not in stmt[stmt.index("/-"):]:
                    stmt = stmt[:stmt.index("/-")]
                    in_block = True
                    i += 1
                    continue
                stmt = re.sub(r"/-.*?-/", " ", stmt, flags=re.S)
            # Satır bitti ama `:=` yoksa sonraki satıra geç.
            if i + 1 < len(lines):
                i += 1
                stmt += " " + _strip_line_comment(lines[i])
            else:
                break
        norm = re.sub(r"\s+", " ", stmt).strip()
        sigs[name] = norm
        i += 1
    return sigs


def parse_contract(map_text):
    """MAP.md'deki STATEMENT CONTRACT bölümünü {ad: ifade} olarak ayrıştırır."""
    if CONTRACT_HEADER not in map_text:
        return None
    body = map_text.split(CONTRACT_HEADER, 1)[1]
    # Sonraki `## ` başlığına kadar (başlıksız biterse dosya sonu).
    if "\n## " in body:
        body = body.split("\n## ", 1)[0]
    contract = {}
    for ln in body.splitlines():
        ln = ln.strip()
        if not ln or ln.startswith("#") or ln.startswith("|") or ln.startswith("```"):
            continue
        if ": " in ln and not ln.startswith("-"):
            name, expr = ln.split(": ", 1)
            name = name.strip()
            if re.match(r"^[A-Za-z0-9_]+$", name):
                contract[name] = expr.strip()
    return contract


def check_twin(lean_file, twin_file):
    """Shim ile lake target kopyası byte-eşit mi? Döndürür (ok, findings).

    İki kopya aynı anda kaynak olduğu için ayrışmaları sessizce iki
    farklı kaynak gerçeği yaratır: sözleşme kapısı birini, lake build
    diğerini derler. Bayt eşitliği aranır (satır sonu/boşluk farkı da
    drift sayılır — kaynaklar birebir aynı olmalıdır).
    """
    findings = []
    digests = {}
    for label, path in (("shim", lean_file), ("twin", twin_file)):
        try:
            with open(path, "rb") as f:
                digests[label] = hashlib.sha256(f.read()).hexdigest()
        except OSError as e:
            return False, [{"kind": "twin_unreadable", "name": label,
                            "detail": f"{label} okunamadı: {path} ({e})"}]
    if digests["shim"] != digests["twin"]:
        findings.append({
            "kind": "twin_drift", "name": "Content.lean",
            "detail": (f"shim ve lake target kopyası byte-eşit değil — "
                       f"sözleşme kapısı derlenmeyen dosyayı doğruluyor\n"
                       f"  shim ({lean_file}): {digests['shim']}\n"
                       f"  twin ({twin_file}): {digests['twin']}")})
    return not findings, findings


def check_statements(lean_file, map_file):
    """İmzaları karşılaştır. Döndürür (ok: bool, findings: list[dict])."""
    findings = []
    with open(lean_file, encoding="utf-8") as f:
        lean_text = f.read()
    with open(map_file, encoding="utf-8") as f:
        map_text = f.read()

    contract = parse_contract(map_text)
    if contract is None:
        return False, [{"kind": "contract_missing",
                        "detail": f"MAP.md'de {CONTRACT_HEADER} bölümü yok"}]

    sigs = extract_signatures(lean_text)
    # Eksik teorem: MAP.md'de var, Content.lean'da yok.
    for name, expr in sorted(contract.items()):
        if name not in sigs:
            findings.append({"kind": "missing", "name": name,
                             "detail": f"teorem Content.lean'da yok: {name}"})
            continue
        if sigs[name] != expr:
            findings.append({"kind": "changed", "name": name,
                             "detail": (f"imza değişti: {name}\n"
                                        f"  Content.lean: {sigs[name]}\n"
                                        f"  MAP.md      : {expr}")})
    # Fazla teorem: Content.lean'da var ama sözleşmede yok (kapsam genişledi).
    for name in sorted(sigs):
        if name not in contract:
            findings.append({"kind": "extra", "name": name,
                             "detail": f"fazla teorem (sözleşmede yok): {name}"})
    return not findings, findings


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--lean-file", default=DEFAULT_LEAN)
    ap.add_argument("--map", default=DEFAULT_MAP)
    ap.add_argument("--twin-file", default=DEFAULT_TWIN,
                    help="lake target kopyası (shim ile byte-eşit olmalı)")
    ap.add_argument("--no-twin", action="store_true",
                    help="ayna bütünlüğü denetimini atla (test/alt-kopya)")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--exit-0", action="store_true",
                    help="drift olsa bile exit 0 (advisory)")
    args = ap.parse_args(argv)

    if not os.path.isfile(args.lean_file) or not os.path.isfile(args.map):
        print("HATA: Content.lean veya MAP.md yok", file=sys.stderr)
        return 2

    ok, findings = check_statements(args.lean_file, args.map)
    twin_state = None
    if not args.no_twin:
        twin_ok, twin_findings = check_twin(args.lean_file, args.twin_file)
        twin_state = "PASS" if twin_ok else "FAIL"
        findings = findings + twin_findings
        ok = ok and twin_ok
    if args.json:
        print(json.dumps({"ok": ok, "findings": findings,
                          "lean_file": args.lean_file,
                          "map_file": args.map,
                          "twin_file": None if args.no_twin else args.twin_file,
                          "twin_state": twin_state}, ensure_ascii=False))
    else:
        print(f"check-lean-statements: {args.lean_file}")
        for f in findings:
            print(f"  {f['kind'].upper()} {f.get('name', '')} — {f['detail']}")
        if findings:
            print(f"SONUÇ: {len(findings)} drift — fail-closed")
        else:
            print("SONUÇ: uyumlu — 8 teorem imzası MAP.md sözleşmesiyle birebir")
        if twin_state is not None:
            print(f"AYNA: {twin_state} — shim ile lake target kopyası "
                  f"{'byte-eşit' if twin_state == 'PASS' else 'AYRIŞTI'}")
    if findings and not args.exit_0:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
