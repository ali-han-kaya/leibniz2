#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""pdf_id_canonical.py — PDF trailer /ID kanonik hash (TEK uygulama).

Neden var: pdfTeX her koşumda trailer'a rastgele 64 baytlık /ID yazar;
SOURCE_DATE_EPOCH /CreationDate ve /ModDate'yi sabitler, /ID'yi
sabitlemez. Ölçülen tek fark bu /ID satırıdır (docs/ID_RESIDUAL_ACCEPTANCE.md
§1-2). Kanonik görünüm /ID çiftini sabit değere indirger; içerik birebir
aynıysa kanonik hash eşit.

Bu modül TEK uygulamadır. İki tüketici vardır ve ikisi de buradan
okur (regex'in iki kopyası = iki gerçeklik):
  1. _calisma/CIKTI/texlive_determinism_test.sh → canonical_sha()
  2. _calisma/CIKTI/verify_delivery.py (K6-DETERM) → kanonik karşılaştırma

Fail-safe (ölçülmüş tasarım kararı): /ID deseni eşleşmezse kanonik
görünüm ham baytlara düşer, yani canonical == raw. Böylece "temiz
sayılan" ama gerçekte farklı iki dosya asla eşit sayılmaz — ölçülen
hiçbir fark gizlenmez. Desenin tutmaması ayrıca `id_found=False`
olarak raporlanır ki kapı "kanonik" dediğinde /ID'nin gerçekten
nötrlendiğini kanıtlayabilsin.

stdlib-only, OFFLINE. Python 3.9 uyumlu (tuple[...] tipleri yok).
"""
import hashlib
import re

# /ID [<32-hex> <32-hex>] — whitespace toleranslı, büyük/küçük hex kabul.
ID_PAIR_RE = re.compile(rb"/ID\s*\[\s*<[0-9a-fA-F]{32}>\s*<[0-9a-fA-F]{32}>\s*\]")

# Nötrleştirilmiş /ID: iki sıfır çifti. Uzunluk birebir korunur ki
# değiştirme dosya boyutunu kaydırmasın (hash yalnız içerik görünümü).
ID_NEUTRAL = b"/ID [<00000000000000000000000000000000><00000000000000000000000000000000>]"

ZERO64 = "0" * 64


def canonical_bytes(data):
    """Ham baytları kanonik görünüme indirger (bytes → bytes)."""
    return ID_PAIR_RE.sub(ID_NEUTRAL, data)


def id_pair(data):
    """Gerçek /ID çiftini döner (kanıt satırı için), yoksa None."""
    m = ID_PAIR_RE.search(data)
    return m.group(0).decode("ascii", "replace") if m else None


def canonical_sha256_bytes(data):
    """(canonical_hex, id_found) — /ID nötrlenmiş SHA-256."""
    normalized = canonical_bytes(data)
    return hashlib.sha256(normalized).hexdigest(), ID_PAIR_RE.search(data) is not None


def canonical_sha256_path(path):
    """Dosya için (canonical_hex, id_found). Okunamazsa (None, False)."""
    try:
        with open(path, "rb") as fh:
            data = fh.read()
    except OSError:
        return None, False
    return canonical_sha256_bytes(data)


FULL_HASH_RE = re.compile(r"\b[0-9a-f]{64}\b")


def ledger_hashes(doc_text):
    """Eski genel toplayıcı: dokümandaki TÜM 64-hex token'lar.

    Kural: yalnız TAM 64 haneli hex (kısaltılmış `…` önekleri dışarıda).
    Daraltılmış karşılaştırma için aşağıdaki
    `ledger_canonical_hashes` kullanılmalı — bu fonksiyon ham/hacim
    sütunlarını da içerir.
    """
    return set(FULL_HASH_RE.findall(doc_text))


def _table_rows(lines):
    """Markdown tablo satırlarını (başlık + ayraç + veri) listeler."""
    rows = []
    for line in lines:
        s = line.strip()
        if s.startswith("|") and s.count("|") >= 2:
            cells = [c.strip() for c in s.strip("|").split("|")]
            if all(set(c) <= set("-: ") for c in cells if c):
                continue  # ayraç satırı (|---|---|)
            rows.append(cells)
    return rows


def ledger_canonical_hashes(doc_text):
    """Kabul defterindeki ÖLÇÜLMÜŞ TAM kanonik hash kümesi.

    Kural katmanları:
      1) Yalnız "Kanonik" başlıklı sütun okunur — ham (bilgi) ve
         metadata-stripped sütunları kabul sayılmaz; onlar teslim
         sidecar'ının çıktısıdır, karşılaştırma yüzeyi değil.
      2) Yalnız TAM 64-hex hücreler kabul edilir. Kısaltılmış önek
         (`47681218…`, "donmuş önek") kümede olmaz.
      3) Böyle bir tablo yoksa küme BOŞ döner; çağıran taraf bunu
         P1'e çevirir (fail-closed) — sessiz geçiş yok.
    """
    for idx, line in enumerate(doc_text.splitlines()):
        if "Kanonik" not in line or not line.strip().startswith("|"):
            continue
        header = [c.strip() for c in line.strip().strip("|").split("|")]
        col = None
        for i, cell in enumerate(header):
            if "kanonik" in cell.lower():
                col = i
                break
        if col is None:
            continue
        found = set()
        for cells in _table_rows(doc_text.splitlines()[idx + 1:]):
            if col < len(cells):
                found |= set(FULL_HASH_RE.findall(cells[col]))
        if found:
            return found
    return set()


if __name__ == "__main__":  # CLI: pdf_id_canonical.py FILE.pdf
    import sys

    if len(sys.argv) != 2:
        print("KULLANIM: pdf_id_canonical.py <pdf.pdf>", file=sys.stderr)
        raise SystemExit(2)
    hexdigest, found = canonical_sha256_path(sys.argv[1])
    if hexdigest is None:
        print("HATA: okunamadı: %s" % sys.argv[1], file=sys.stderr)
        raise SystemExit(2)
    print(hexdigest)
    print("id_found=%s" % ("true" if found else "false"))
