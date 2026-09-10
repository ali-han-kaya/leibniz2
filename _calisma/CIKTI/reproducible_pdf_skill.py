#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""reproducible_pdf_skill.py — reproducible-pdf-build skill protokolünün test edilebilir çekirdeği.

skills/reproducible-pdf-build/SKILL.md prosedürünü saf/taşınabilir
fonksiyonlara indirger; birim testler (test_reproducible_pdf_skill.py) bu
fonksiyonları MOCK qpdf + mock PDF senaryosunda koşup skill kurallarını kanıtlar:

  1) RERUN kuralı (SKILL.md Step 1): aynı girdi üzerinde qpdf --remove-metadata
     N kez koşulur; distinct çıktı hash'i > 1 → NON-DETERMINISTIC (qpdf'nin
     gerçek davranışı — V5l bulgusu). 1 → DETERMINISTIC.
  2) REUSE kuralı (SKILL.md "Critical rule" + Step 3): metadata sidecar
     YALNIZCA PDF'in ham SHA-256'sı DEĞİŞTİĞİNDE yeniden üretilir; ham hash
     değişmediyse mevcut sidecar AYNEN korunur → ardışık repack'ler
     byte-identical. repack_delivery.py'nin üretim koduyla aynı karar
     (cached_raw == raw_hash → reuse).
  3) OPSİYONEL ARAÇ (SKILL.md Step 3/4): qpdf yoksa sidecar üretilmez,
     hata olmaz (skip, fail değil) — (raw, None) semantiği.

Sidecar formatı repack_delivery.py ile birebir:
    <stripped_sha256>  <name>.metadata
    # raw: <raw_sha256>  <name>
"""
import hashlib
import os
import subprocess
import tempfile


def sha256_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def find_qpdf(candidates=("qpdf", "/opt/homebrew/bin/qpdf")):
    """qpdf'i bul; yoksa None (opsiyonel araç — skip, fail değil)."""
    for cand in candidates:
        if shutil_which(cand) or os.path.isfile(cand):
            return cand if os.path.isfile(cand) else cand
    return None


def shutil_which(name):
    """PATH'te ara (shutil.which; import yükü olmadan)."""
    for d in os.environ.get("PATH", "").split(os.pathsep):
        p = os.path.join(d, name)
        if os.path.isfile(p) and os.access(p, os.X_OK):
            return p
    return None


def rerun_experiment(qpdf, pdf, runs=5, timeout=120):
    """SKILL.md Step 1 — aynı girdi üzerinde N canlı koşum.

    Döner: {"hashes": [str|None], "distinct": int, "verdict": str}.
    Verdict: DETERMINISTIC (distinct ≤ 1) / NON-DETERMINISTIC (distinct > 1).
    """
    raw = sha256_file(pdf)
    hashes = []
    for _ in range(runs):
        tmp = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as t:
                tmp = t.name
            r = subprocess.run([qpdf, "--remove-metadata", pdf, tmp],
                               capture_output=True, text=True, timeout=timeout)
            hashes.append(sha256_file(tmp) if r.returncode == 0 else None)
        finally:
            if tmp and os.path.isfile(tmp):
                os.unlink(tmp)
    distinct = len({h for h in hashes if h})
    return {
        "raw": raw,
        "hashes": hashes,
        "distinct": distinct,
        "verdict": ("DETERMINISTIC" if distinct <= 1
                    else "NON-DETERMINISTIC"),
    }


def read_cached_raw(sidecar_path):
    """Sidecar'daki '# raw: <hash>' satırını okur; yoksa None."""
    if not os.path.isfile(sidecar_path):
        return None
    with open(sidecar_path, encoding="utf-8", errors="ignore") as f:
        for line in f:
            if line.startswith("# raw:"):
                parts = line.split()
                return parts[2] if len(parts) >= 3 else None
    return None


def write_sidecar(sidecar_path, stripped_sha, raw_sha, name):
    """Sidecar'ı repack_delivery.py formatıyla yazar (tek satır hash + # raw)."""
    with open(sidecar_path, "w", encoding="utf-8") as f:
        f.write(f"{stripped_sha}  {name}.metadata\n")
        f.write(f"# raw: {raw_sha}  {name}\n")


def strip_metadata(qpdf, pdf, out_path, timeout=60):
    """qpdf --remove-metadata alt süreci; başarı bool döndürür."""
    if not qpdf:
        return False
    r = subprocess.run([qpdf, "--remove-metadata", pdf, out_path],
                       capture_output=True, text=True, timeout=timeout)
    return r.returncode == 0 and os.path.isfile(out_path)


def sync_sidecar(pdf, sidecar_path, name, qpdf=None):
    """SKILL.md REUSE kuralı — sidecar'ı ham hash'e göre senkronlar.

    Karar (repack_delivery.py ile birebir):
      - qpdf yok veya PDF yok            → sidecar üretilmez, ("skip", raw|None)
      - cached_raw == raw_hash           → sidecar AYNEN korunur ("reuse", raw)
      - cached_raw != raw_hash           → qpdf ile yeniden üretilir
                                          ("regenerate", raw)

    Döner: (karar: "reuse"|"regenerate"|"skip", raw_sha256: str|None).
    """
    raw = sha256_file(pdf) if os.path.isfile(pdf) else None
    if not qpdf or not raw:
        return ("skip", raw)
    cached = read_cached_raw(sidecar_path)
    if cached == raw:
        return ("reuse", raw)
    tmp = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as t:
            tmp = t.name
        if not strip_metadata(qpdf, pdf, tmp):
            return ("skip", raw)
        write_sidecar(sidecar_path, sha256_file(tmp), raw, name)
        return ("regenerate", raw)
    finally:
        if tmp and os.path.isfile(tmp):
            os.unlink(tmp)
