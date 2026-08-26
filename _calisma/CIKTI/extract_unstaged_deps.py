#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""extract_unstaged_deps.py — precommit.log'dan unstaged-deps uyarılarını çıkarır.

`pre-commit run --all-files` çıktısındaki unstaged-deps ön-kontrol bloklarını
(advisory `⚠️` veya strict `⛔` marker'ları) ayrıştırır ve makine-okunur JSON
sidecar'ına yazar. CI pre-commit adımında koşulur: uyarı varsa precommit-logs
artifact'ına (logs/ dizini) görünür biçimde girer — advisory (build'i bloke
etmez; hook'ların kendi `--strict` davranışı zaten CI'da fail-closed değildir,
çünkü checkout temizdir).

Kullanım:
    python3 extract_unstaged_deps.py --log logs/precommit.log \\
        --out-json logs/unstaged_deps_findings.json \\
        [--out-txt logs/unstaged_deps_findings.txt]

Çıktı şeması (JSON):
    {
      "found": bool,          # en az bir uyarı var mı?
      "count": int,           # uyarı bloğu sayısı (hook başına 1)
      "files": [rel, ...],    # kirli bağımlılık dosyaları (benzersiz)
      "hooks": [              # hook başına bir blok
        {"hook": str, "strict": bool, "files": [{rel, status}]}
      ]
    }

Advisory: script her zaman exit 0 döner (bulgu yoksa da).
"""
import argparse
import json
import os
import re
import sys

# Marker'lar hook_unstaged_deps.py ile birebir:
#   print_warning: "⚠️  {hook} ÖN-KONTROL: bağımlılık dosyası STAGE EDİLMEMİŞ"
#   block_strict:  "⛔  {hook} ÖN-KONTROL (--strict): bağımlılık dosyası
#                  STAGE EDİLMEMİŞ — HOOK BLOKE"
#   satır:         "    • {rel}  ({status})"
HEAD_RE = re.compile(
    r"(?P<mark>[⛔\u26a0])\ufe0f?\s+"
    r"(?P<hook>[A-Za-z0-9_.-]+)\s+ÖN-KONTROL.*?STAGE EDİLMEMİŞ.*")
FILE_RE = re.compile(r"^\s*•\s+(?P<rel>\S+)\s+\((?P<status>.*)\)\s*$")

STRICT_MARK = "\u26d4"   # ⛔
WARN_MARK = "\u26a0\ufe0f"  # ⚠️


def parse_log(text):
    """precommit.log metnini ayrıştır → uyarı blokları listesi.

    Her blok: {"hook": str, "strict": bool, "files": [{rel, status}]}
    """
    blocks = []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        m = HEAD_RE.match(line)
        if m:
            strict = m.group("mark") == "\u26d4"
            hook = m.group("hook")
            files = []
            j = i + 1
            while j < len(lines):
                fm = FILE_RE.match(lines[j])
                if fm:
                    files.append({"rel": fm.group("rel").rstrip(","),
                                  "status": fm.group("status").rstrip(",")})
                    j += 1
                else:
                    break
            blocks.append({"hook": hook, "strict": strict, "files": files})
            i = j
        else:
            i += 1
    return blocks


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--log", required=True, help="precommit.log yolu")
    ap.add_argument("--out-json", required=True,
                    help="JSON sidecar çıktı yolu (logs/ içine)")
    ap.add_argument("--out-txt", default=None,
                    help="İnsan-okur txt çıktı yolu (opsiyonel)")
    args = ap.parse_args(argv)

    if not os.path.isfile(args.log):
        # Log yoksa (pre-commit adımı koşmadıysa) dürüst boş rapor yaz.
        report = {"found": False, "count": 0, "files": [], "hooks": [],
                  "log": args.log, "error": "log dosyası yok"}
    else:
        with open(args.log, encoding="utf-8", errors="replace") as f:
            blocks = parse_log(f.read())
        files = sorted({ff["rel"] for b in blocks for ff in b["files"]})
        report = {"found": bool(blocks), "count": len(blocks),
                  "files": files, "hooks": blocks, "log": args.log}

    os.makedirs(os.path.dirname(os.path.abspath(args.out_json)),
                exist_ok=True)
    with open(args.out_json, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    if args.out_txt:
        with open(args.out_txt, "w", encoding="utf-8") as f:
            if not report["found"]:
                f.write("unstaged-deps uyarısı yok (checkout temiz)\n")
            else:
                f.write(f"{report['count']} unstaged-deps uyarısı bulundu:\n\n")
                for b in report["hooks"]:
                    mode = "STRICT (--strict)" if b["strict"] else "advisory"
                    f.write(f"• {b['hook']} [{mode}]\n")
                    for ff in b["files"]:
                        f.write(f"    - {ff['rel']}  ({ff['status']})\n")
                f.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
