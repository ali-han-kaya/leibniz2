#!/usr/bin/env python3
"""id_canonical.py — `/ID`-kanonik PDF determinizm referansı (TEK KAYNAK).

Faz 4 (docs/TEXLIVE_MIGRATION_PLAN.md) sözleşmesinin ortak çekirdeği:
pdfTeX `SOURCE_DATE_EPOCH` ile deterministiktir; iki bağımsız koşum arasındaki
tek fark trailer'daki rastgele `/ID` satırıdır (ölçüm:
`docs/ID_RESIDUAL_ACCEPTANCE.md` §1-2). Dolayısıyla determinizm referansı
`/ID`-nötrlenmiş hash'tir ve bu referans **kabul defterinde** kayıtlı olmalıdır.

Bu modülü kullanan üç yer (hepsi AYNI normalizasyonu ve AYNI defter
çözümlemesini uygular — kopya regex/defter mantığı yok):

  - `verify_delivery.py` K6-DETERM — strict modda teslim PDF'inin kanonik
    hash'ini defterde arar (P1 + remedy).
  - `repack_delivery.py` — motor-geçişinde sidecar'ı bilinçli yenilerken
    `# canonical:` satırını yazar ve yeni kanoniği defterde doğrular
    (repack determinizm kapısı).
  - `check_zip_lineage_drift.py` (K14) — sidecar'daki kanonik referans ↔
    defter tutarlılığını commit anında denetler.

Defter çözümleme sırası (ilk okunabilen kazanır):
  1. `ID_RESIDUAL_LEDGER` ortam değişkeni (açık yol; CI/özel düzen)
  2. `<repo>/docs/ID_RESIDUAL_ACCEPTANCE.md` (normal checkout)
  3. `<script dizini>/ID_RESIDUAL_ACCEPTANCE.md` (TCC-safe mirror drop —
     `sync_verify_mirror.sh` defteri verify mirror'a düz adla bırakır)

stdlib-only, OFFLINE.
"""
import hashlib
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(HERE))

# Repo-göreli tek kaynak yol (dokümanlarda bu yol anılır).
LEDGER_DOC = "docs/ID_RESIDUAL_ACCEPTANCE.md"
# Mirror drop adı: sync_verify_mirror.sh defteri bu adla script yanına kopyalar.
LEDGER_FLAT_NAME = "ID_RESIDUAL_ACCEPTANCE.md"
# Açık override (yol verilmezse yukarıdaki sıra kullanılır).
LEDGER_ENV = "ID_RESIDUAL_LEDGER"

# /ID [<32 hex> <32 hex>] — pdfTeX'in rastgele belge kimliği.
_ID_TRAILER_PATTERN = re.compile(
    rb"/ID\s*\[\s*<[0-9a-fA-F]{32}>\s*<[0-9a-fA-F]{32}>\s*\]")
_ID_TRAILER_NEUTRAL = (b"/ID [<00000000000000000000000000000000>"
                       b"<00000000000000000000000000000000>]")
HASH64_PATTERN = re.compile(r"[0-9a-fA-F]{64}")


def canonical_pdf_sha256(pdf_path):
    """PDF'in `/ID`-nötrlenmiş SHA-256'si; okunamayan dosyada None.

    `/ID` çifti sabit değere indirgenir (tek kanonik görünüm) ve içerik
    farkları GİZLENMEZ. Desen yoksa ham hash döner (fail-safe).
    """
    try:
        with open(pdf_path, "rb") as fh:
            data = fh.read()
    except OSError:
        return None
    if _ID_TRAILER_PATTERN.search(data):
        data = _ID_TRAILER_PATTERN.sub(_ID_TRAILER_NEUTRAL, data)
    return hashlib.sha256(data).hexdigest()


def ledger_candidates():
    """Defter adayları (sıralı): env → repo docs → mirror drop."""
    out = []
    env = os.environ.get(LEDGER_ENV)
    if env:
        out.append(env)
    out.append(os.path.join(REPO_ROOT, LEDGER_DOC))
    out.append(os.path.join(HERE, LEDGER_FLAT_NAME))
    return out


def ledger_tokens(path=None):
    """Kabul defterindeki 64-hex hash kümesi.

    Döndürür: `(tokens, error, source)`. Açık `path` verilirse yalnız o
    denenir; verilmezse `ledger_candidates()` sırası. Hiçbiri okunamazsa
    boş küme + hata metni (çağıran fail-closed karar verir).
    """
    candidates = [path] if path else ledger_candidates()
    for cand in candidates:
        try:
            with open(cand, encoding="utf-8") as fh:
                text = fh.read()
        except OSError:
            continue
        return {m.lower() for m in HASH64_PATTERN.findall(text)}, "", cand
    return set(), "aranan yollar okunamadı: " + ", ".join(candidates), None


def has_canonical(canonical, tokens):
    """Kanonik hash defterde kayıtlı mı (None → False)."""
    return canonical is not None and canonical in tokens


def sidecar_canonical(sidecar_path):
    """Sidecar'daki `# canonical: <sha>` satırını okur (yoksa None).

    Sidecar formatı (repack yazar):
        <stripped-sha>  ingiliz_empirizmi_v3.pdf.metadata
        # raw: <sha>  ingiliz_empirizmi_v3.pdf
        # canonical: <sha>  ingiliz_empirizmi_v3.pdf
        # renewal: <ISO tarih> — <gerekçe>
    """
    try:
        with open(sidecar_path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if line.startswith("# canonical:"):
                    parts = line.split()
                    if len(parts) >= 3:
                        return parts[2].lower()
    except OSError:
        return None
    return None


if __name__ == "__main__":  # küçük CLI: denetim/elle doğrulama için
    import sys
    if len(sys.argv) != 2:
        print("kullanım: id_canonical.py <pdf>", file=sys.stderr)
        raise SystemExit(2)
    canon = canonical_pdf_sha256(sys.argv[1])
    tokens, err, src = ledger_tokens()
    print(f"canonical={canon}")
    print(f"ledger={src or '—'} ({len(tokens)} hash) hata={err or '—'}")
    print(f"kayıtlı={'EVET' if has_canonical(canon, tokens) else 'HAYIR'}")
