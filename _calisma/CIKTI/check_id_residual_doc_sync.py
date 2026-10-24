#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_id_residual_doc_sync.py — §4 teslim satırı ↔ donmuş kayıt senkron kapısı.

Neden
-----
`docs/ID_RESIDUAL_ACCEPTANCE.md` §4'teki "Teslim sidecar'ı geçiş kaydı"
tablosunun tectonic-era satırı teslim PDF'i için üç hash taşır: **ham**,
**metadata-stripped** ve **/ID-kanonik**. Bu satır elle yazılmaz (üretici:
`gen_id_residual_acceptance.py`), ama yine de gözden kaçabilir: donmuş kayıt
(sidecar) yenilenip defter satırı eski kalırsa (ya da tersi) doküman sessizce
yanlış bir kaydı determinizm kanıtı olarak gösterir. `test_id_residual_
acceptance_doc.py` bu değerleri **sabit literal** olarak pinler; yani
"defter ↔ kayıt" senkronunu değil, "defter ↔ bir zamanlar yazılmış literal"i
denetler. Bu kapı o boşluğu kapatır.

Tek kaynak: donmuş kayıt
------------------------
Kayıt = `ingiliz_empirizmi_v3.pdf.metadata.sha256` (PDF'in yanında, commit'li):

    <stripped-sha>  ingiliz_empirizmi_v3.pdf.metadata
    # raw: <raw-sha>  ingiliz_empirizmi_v3.pdf
    # canonical: <canonical-sha>  ingiliz_empirizmi_v3.pdf   (yenilemede eklenir)

  * ham      → `check_seal_hash.parse_frozen_raw` (aynı satır, aynı ayrıştırıcı)
  * stripped → ilk veri satırı (`<64hex>  <pdf>.metadata`)
  * kanonik  → `id_canonical.sidecar_canonical` (yoksa None)

Kural: defter satırının "Ham PDF (bilgi)" hücresi kaydın `# raw:` değerine,
"Metadata-stripped" hücresi kaydın stripped değerine eşit olmalı. "Kanonik"
hücresi kayıtta `# canonical:` VARSA eşleşmeli (P0); YOKSA defterdeki kanonik
NOT olarak raporlanır — bugünkü tectonic-era sidecar iki satırlıdır ve
`ID_RESIDUAL_ACCEPTANCE.md` §6 bu durumu bilgi düzeyi sayar.

Fail-closed: defter/satır/tablo/hücre yok, kayıt yok, satır biçimi bozuk ya da
kayıt başka bir dosyayı imzalıyorsa bulgu üretilir (exit 1). Sessiz PASS yok.

Kullanım:
  python3 check_id_residual_doc_sync.py                 # denetle
  python3 check_id_residual_doc_sync.py --json          # makine-okur
  python3 check_id_residual_doc_sync.py --root DIR      # fixture kökü
  python3 check_id_residual_doc_sync.py --doc P --sidecar S

Exit: 0 = senkron, 1 = bulgu (fail-closed), 2 = kullanım hatası.
stdlib-only, OFFLINE.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import check_seal_hash as seal  # noqa: E402  (donmuş kayıt ayrıştırıcısı)
import id_canonical  # noqa: E402  (kanonik satır ayrıştırıcısı)

REPO_ROOT = Path(__file__).resolve().parents[2]
DOC_REL = Path("docs") / "ID_RESIDUAL_ACCEPTANCE.md"

HASH64_RE = re.compile(r"(?<![0-9a-fA-F])([0-9a-fA-F]{64})(?![0-9a-fA-F])")
# §4 alt-tablosunun başlığı: "| Dönem | Ham PDF (bilgi) | Metadata-stripped | ..."
TABLE_HEADER_RE = re.compile(
    r"^\|\s*Dönem\s*\|.*Metadata-stripped", re.M)
# Teslim satırı: "| tectonic-era teslim (V5l; mevcut) | ... |"
ROW_LABEL_RE = re.compile(r"^\|\s*tectonic-era\s+teslim\b", re.I | re.M)

# Hücre adı (küçük harf öneki) → sözlük anahtarı.
COLUMN_KEYS = (
    ("ham pdf", "raw"),
    ("metadata-stripped", "stripped"),
    ("kanonik", "canonical"),
)


def _normalize_cell(text):
    return re.sub(r"\s+", " ", text or "").strip().lower()


def _cell_hash(cell):
    """Hücredeki 64-hex değeri döndürür; `—` / boş → None."""
    match = HASH64_RE.search(cell or "")
    return match.group(1).lower() if match else None


def parse_doc_row(doc_text):
    """§4 teslim satırını sütun adlarına göre ayrıştırır.

    Döndürür: `(values, findings)` — `values` `{"raw":…, "stripped":…,
    "canonical":…}` (bulunamayan → None). Sütun sırası başlıktan okunur;
    sabit pozisyon varsayılmaz (tablo yeniden düzenlenirse kapı körleşmesin).
    """
    findings = []
    header = TABLE_HEADER_RE.search(doc_text)
    if not header:
        findings.append({
            "kind": "doc_table_missing",
            "detail": "§4 'Teslim sidecar'ı geçiş kaydı' alt-tablosunun "
                      "başlığı bulunamadı (Dönem | Ham PDF | Metadata-stripped)",
        })
        return {}, findings

    header_line = doc_text[header.start():doc_text.find("\n", header.start())]
    header_cells = [c.strip() for c in header_line.strip().strip("|").split("|")]
    index = {}
    for pos, cell in enumerate(header_cells):
        norm = _normalize_cell(cell)
        for prefix, key in COLUMN_KEYS:
            if norm.startswith(prefix):
                index[key] = pos
                break
    missing_cols = [k for _p, k in COLUMN_KEYS if k not in index]
    if missing_cols:
        findings.append({
            "kind": "doc_columns_missing",
            "detail": "§4 alt-tablosunda beklenen sütun(lar) yok: %s"
                      % ", ".join(missing_cols),
        })
        return {}, findings

    rows = []
    for match in ROW_LABEL_RE.finditer(doc_text):
        line = doc_text[match.start():doc_text.find("\n", match.start())]
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        rows.append(cells)
    if not rows:
        findings.append({
            "kind": "doc_row_missing",
            "detail": "§4 tablosunda 'tectonic-era teslim … mevcut' satırı yok",
        })
        return {}, findings
    if len(rows) > 1:
        findings.append({
            "kind": "doc_row_ambiguous",
            "detail": "§4 tablosunda birden çok tectonic-era teslim satırı var "
                      "(%d) — hangisinin yürürlükte olduğu belirsiz" % len(rows),
        })
        return {}, findings

    cells = rows[0]
    values = {}
    for key, pos in index.items():
        values[key] = _cell_hash(cells[pos]) if pos < len(cells) else None
    return values, findings


def parse_frozen_record(sidecar_text, pdf_name):
    """Donmuş kaydı `{"raw", "stripped", "canonical"}` olarak ayrıştırır.

    Döndürür: `(record, findings)`. Fail-closed: eksik/bozuk satır bulgudur.
    """
    findings = []
    record = {"raw": None, "stripped": None, "canonical": None}

    for line in sidecar_text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        token = stripped.split()[0]
        if not re.fullmatch(r"[0-9a-fA-F]{64}", token):
            findings.append({
                "kind": "stripped_malformed",
                "detail": "kaydın ilk veri satırı '<64hex>  <pdf>.metadata' "
                          "biçiminde değil: %r" % line[:80],
            })
            break
        record["stripped"] = token.lower()
        name = stripped.split()[1] if len(stripped.split()) > 1 else ""
        expected = pdf_name + ".metadata"
        if name != expected:
            findings.append({
                "kind": "stripped_name_mismatch",
                "detail": "stripped satırı başka dosyayı imzalıyor: %r "
                          "(beklenen %r)" % (name, expected),
            })
        break
    if record["stripped"] is None and not findings:
        findings.append({
            "kind": "stripped_missing",
            "detail": "kayıtta stripped hash satırı yok",
        })

    raw, raw_name = seal.parse_frozen_raw(sidecar_text)
    if raw is None:
        findings.append({
            "kind": "frozen_record_malformed",
            "detail": "kayıtta `# raw: <64 hex>  <name>` satırı yok",
        })
    else:
        record["raw"] = raw
        if raw_name != pdf_name:
            findings.append({
                "kind": "frozen_record_name_mismatch",
                "detail": "`# raw:` satırı başka dosyayı imzalıyor: %r "
                          "(beklenen %r)" % (raw_name, pdf_name),
            })

    # `# canonical:` satırı dosya yolundan okunur (parse_record_file).
    return record, findings


def parse_record_file(sidecar_path, pdf_name):
    """Dosyadan donmuş kaydı ayrıştırır (canonical satırı dahil)."""
    text = sidecar_path.read_text(encoding="utf-8", errors="replace")
    record, findings = parse_frozen_record(text, pdf_name)
    record["canonical"] = id_canonical.sidecar_canonical(str(sidecar_path))
    return record, findings


def _finding(kind, detail, priority="P0", **extra):
    item = {"kind": kind, "detail": detail, "priority": priority}
    item.update(extra)
    return item


def check(doc_path, sidecar_path, pdf_name):
    """Defter satırı ↔ donmuş kayıt karşılaştırması.

    Döndürür: `(findings, notes, facts)`. `findings` bloklar (exit 1),
    `notes` yalnız bilgi (kanonik kayıtta yokken defterde olması gibi).
    """
    findings = []
    notes = []
    facts = {
        "doc": str(doc_path),
        "sidecar": str(sidecar_path),
        "pdf": pdf_name,
        "doc_hashes": {},
        "record": {},
    }

    doc_values = {}
    if not doc_path.is_file():
        findings.append(_finding(
            "doc_missing", "kabul defteri yok: %s" % doc_path))
    else:
        doc_values, doc_findings = parse_doc_row(
            doc_path.read_text(encoding="utf-8", errors="replace"))
        findings.extend(doc_findings)
    facts["doc_hashes"] = doc_values

    record = {"raw": None, "stripped": None, "canonical": None}
    if not sidecar_path.is_file():
        findings.append(_finding(
            "frozen_record_missing", "donmuş kayıt yok: %s" % sidecar_path))
    else:
        record, record_findings = parse_record_file(sidecar_path, pdf_name)
        findings.extend(record_findings)
    facts["record"] = record

    # ── karşılaştırma (yalnız iki taraf da okunabildiyse anlamlı) ─────────
    for key, label in (("raw", "ham PDF"), ("stripped", "metadata-stripped")):
        doc_value = doc_values.get(key)
        rec_value = record.get(key)
        if rec_value is not None and doc_value is None:
            findings.append(_finding(
                "doc_hash_missing",
                "defter satırında %s hash'i yok (kayıt %s… diyor)"
                % (label, rec_value[:12]), column=key))
        elif doc_value is not None and rec_value is not None \
                and doc_value != rec_value:
            findings.append(_finding(
                "doc_value_mismatch",
                "defter %s hash'i donmuş kayıtla uyuşmuyor" % label,
                column=key, doc=doc_value, record=rec_value))
        elif doc_value is not None and rec_value is None:
            # Kayıt okunamadıysa zaten bulgu var; burada ikinci bulgu üretme.
            pass

    doc_canonical = doc_values.get("canonical")
    rec_canonical = record.get("canonical")
    if rec_canonical is not None and doc_canonical is not None \
            and doc_canonical != rec_canonical:
        findings.append(_finding(
            "doc_value_mismatch",
            "defter kanonik hash'i donmuş kayıtla uyuşmuyor",
            column="canonical", doc=doc_canonical, record=rec_canonical))
    elif rec_canonical is not None and doc_canonical is None:
        findings.append(_finding(
            "doc_hash_missing",
            "kayıt `# canonical:` taşıyor ama defter satırında kanonik hash "
            "yok", column="canonical"))
    elif rec_canonical is None and doc_canonical is not None:
        notes.append({
            "kind": "canonical_not_in_record",
            "detail": "defterde kanonik hash var (%s…), kayıtta `# canonical:` "
                      "satırı yok — yenilemede eklenecek (§6: bilgi düzeyi)"
                      % doc_canonical[:12],
        })

    return findings, notes, facts


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=REPO_ROOT,
                        help="repository root (varsayılan: script'ten türetilir)")
    parser.add_argument("--doc", type=Path, default=None,
                        help="kabul defteri yolu (varsayılan: --root altında)")
    parser.add_argument("--sidecar", type=Path, default=None,
                        help="donmuş kayıt yolu (varsayılan: <pdf>.metadata.sha256)")
    parser.add_argument("--pdf", type=Path, default=None,
                        help="teslim PDF yolu (yalnız adı kullanılır)")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--out", type=Path,
                        help="JSON raporunu bu yola da yaz")
    args = parser.parse_args(argv)

    root = args.root.expanduser().resolve()
    if not root.is_dir():
        print("HATA: --root bir dizin değil: %s" % root, file=sys.stderr)
        return 2

    doc = args.doc.expanduser() if args.doc else root / DOC_REL
    pdf = args.pdf.expanduser() if args.pdf else root / seal.PDF_REL
    sidecar = (args.sidecar.expanduser() if args.sidecar
               else pdf.with_name(pdf.name + seal.SIDECAR_SUFFIX))

    findings, notes, facts = check(doc, sidecar, pdf.name)
    report = {
        "ok": not findings,
        "findings": findings,
        "notes": notes,
        "hashes": {
            "doc_raw": facts["doc_hashes"].get("raw"),
            "doc_stripped": facts["doc_hashes"].get("stripped"),
            "doc_canonical": facts["doc_hashes"].get("canonical"),
            "record_raw": facts["record"].get("raw"),
            "record_stripped": facts["record"].get("stripped"),
            "record_canonical": facts["record"].get("canonical"),
        },
        "paths": {"doc": facts["doc"], "sidecar": facts["sidecar"],
                  "pdf": facts["pdf"]},
    }
    encoded = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(encoded, encoding="utf-8")

    if args.json:
        print(encoded, end="")
    else:
        hashes = report["hashes"]
        print("check-id-residual-doc-sync: %s §4 ↔ %s"
              % (doc.name, Path(facts["sidecar"]).name))
        print("  defter ham      : %s" % hashes["doc_raw"])
        print("  kayıt ham       : %s" % hashes["record_raw"])
        print("  defter stripped : %s" % hashes["doc_stripped"])
        print("  kayıt stripped  : %s" % hashes["record_stripped"])
        print("  defter kanonik  : %s" % hashes["doc_canonical"])
        print("  kayıt kanonik   : %s" % hashes["record_canonical"])
        for item in notes:
            print("  NOT — %s" % item["detail"])
        for item in findings:
            print("  %s — %s" % (item["kind"].upper(), item["detail"]))
        print("SONUÇ: temiz (defter donmuş kayıtla senkron)"
              if not findings
              else "SONUÇ: %d bulgu — fail-closed" % len(findings))
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
