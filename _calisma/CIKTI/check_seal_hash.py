#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_seal_hash.py — fail-closed: landing mühür halkası ↔ committed PDF.

Ne kanıtlar
-----------
`_calisma/landing/landing.html`'deki verdict mühürü, `{{SEAL_RING}}` ve
`{{SEAL_CENTER}}` placeholder'larının basılmış hâlidir: halkada
`VERIFIED • <12 hex> •`, merkezde `<6 hex>…`. Bu dosya o hash'in ÜÇ bağımsız
kaynakta AYNI olduğunu doğrular:

  1. **Basılmış mühür** — `landing.html` içindeki `class="seal-big"` SVG'si.
  2. **Donmuş kayıt** — `ingiliz_empirizmi_v3.pdf.metadata.sha256` sidecar'ının
     `# raw: <64 hex>  <name>` satırı (`reproducible_pdf_skill.py` sözleşmesi).
  3. **Committed PDF'in gerçek baytları** — `sha256sum ingiliz_empirizmi_v3.pdf`.

Yani "mühürde yazan hash" ile "repoda duran PDF" arasındaki bağ, build anındaki
snapshot'a değil, **repodaki baytlara** dayanır.

Neden ayrı bir kapı
-------------------
`build_landing.py` mühür hash'ini KOŞUM ANINDAKİ preview snapshot'ından alır ve
kendi yorumunda bunu açıkça söyler ("donmuş kayıt yok"). `test_build_landing.py`
*derleyiciyi* doğrular; bu kapı ise **basılmış artifact'ı** doğrular. Aradaki
boşluk gerçektir: PDF build'den sonra yeniden paketlenir ama landing yeniden
derlenmezse mühür kanıtladığı şeyi kanıtlamayı bırakır — kimse fark etmez.
Bu kapı o boşluğu kapatır: üç kaynak ayrışırsa commit fail-closed kapanır.

Kapsam sınırı: bu kapı mühür hash'ini **bağlar**, üretmez. Yeniden mühürlemek
`build_landing.py`'nin işidir ve taze bir PASS snapshot'ı gerektirir.

Exit codes: 0 = temiz, 1 = bulgu (fail-closed), 2 = çağrı/kaynak hatası.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

LANDING_REL = Path("_calisma") / "landing" / "landing.html"
PDF_REL = (Path("_calisma") / "V5_ICERIK" / "TESLIM_V5_FINAL_2026-08-17"
           / "stoic_hume_package" / "Stoic_Hume_Formal_Section_2026-08-17"
           / "ingiliz_empirizmi_v3.pdf")
# qpdf determinizm kaydı; `# raw:` satırı mühürün kullandığı ham PDF hash'idir.
SIDECAR_SUFFIX = ".metadata.sha256"

# Mühür halkasında en az bu kadar hex olmalı. build_landing.py sha[:12] basar;
# kapı uzunluğu dayatmaz (tasarım değişebilir) ama 12'nin altındaki bir önek
# kanıt sayılmaz — bu yüzden taban aranır.
MIN_RING_HEX = 12

SEAL_SVG_RE = re.compile(
    r'<svg[^>]*\bclass="seal-big"[^>]*>(?P<body>.*?)</svg>', re.S)
SEAL_RING_RE = re.compile(
    r"<textPath[^>]*>\s*VERIFIED\s*•\s*(?P<hex>[0-9A-Fa-f]{6,64})\s*•", re.S)
# Mühür SVG'si içindeki tek `…` ile biten metin merkezdir.
SEAL_CENTER_RE = re.compile(
    r">\s*(?P<hex>[0-9A-Fa-f]{6,64})\s*…\s*</text>", re.S)
PLACEHOLDER_RE = re.compile(r"\{\{\s*SEAL_(?:RING|CENTER)\s*\}\}")
FROZEN_RAW_RE = re.compile(
    r"^\s*#\s*raw:\s*(?P<hex>[0-9a-fA-F]{64})\s+(?P<name>\S+)\s*$", re.M)


def sha256_file(path: Path) -> str:
    """Dosya baytlarının SHA-256'sı (parçalı okuma; büyük PDF'ler için)."""
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_seal(html_text: str) -> dict:
    """Mühür SVG'sinden halka/merkez hex'lerini çıkarır.

    SVG bulunamazsa `seal_svg_found=False`; hex'ler bulunamazsa `None`.
    """
    match = SEAL_SVG_RE.search(html_text)
    body = match.group("body") if match else ""
    ring = SEAL_RING_RE.search(body)
    center = SEAL_CENTER_RE.search(body)
    return {
        "seal_svg_found": match is not None,
        "ring": ring.group("hex").lower() if ring else None,
        "center": center.group("hex").lower() if center else None,
    }


def parse_frozen_raw(sidecar_text: str):
    """Sidecar'daki `# raw: <hex64>  <name>` satırını (hex, name) olarak döndürür."""
    match = FROZEN_RAW_RE.search(sidecar_text)
    if not match:
        return None, None
    return match.group("hex").lower(), match.group("name")


def _finding(kind: str, detail: str, **extra) -> dict:
    item = {"kind": kind, "detail": detail}
    item.update(extra)
    return item


def check(landing_path: Path, pdf_path: Path, sidecar_path: Path):
    """Üç kaynağı karşılaştırır; (findings, facts) döndürür.

    Fail-closed: beklenen bir artifact eksikse bu bulgu sayılır (sessiz geçilmez).
    """
    findings: list[dict] = []
    facts: dict = {
        "landing": str(landing_path),
        "pdf": str(pdf_path),
        "sidecar": str(sidecar_path),
    }

    # ── 1) basılmış mühür ────────────────────────────────────────────────
    seal = {"seal_svg_found": False, "ring": None, "center": None}
    if not landing_path.is_file():
        findings.append(_finding(
            "landing_missing", "mühür artifact'ı yok: %s" % landing_path))
    else:
        html = landing_path.read_text(encoding="utf-8", errors="replace")
        if PLACEHOLDER_RE.search(html):
            findings.append(_finding(
                "seal_placeholder",
                "landing derlenmemiş: {{SEAL_RING}}/{{SEAL_CENTER}} "
                "placeholder'ı hâlâ duruyor"))
        seal = parse_seal(html)
        if not seal["seal_svg_found"]:
            findings.append(_finding(
                "seal_svg_missing",
                'mühür SVG\'si yok (class="seal-big" bulunamadı)'))
        else:
            if seal["ring"] is None:
                findings.append(_finding(
                    "seal_ring_missing",
                    "mühür halkasında `VERIFIED • <hex> •` deseni yok"))
            if seal["center"] is None:
                findings.append(_finding(
                    "seal_center_missing",
                    "mühür merkezinde `<hex>…` deseni yok"))
    facts["seal"] = seal

    # ── 2) committed PDF'in gerçek baytları ──────────────────────────────
    pdf_sha = None
    if not pdf_path.is_file():
        findings.append(_finding(
            "pdf_missing", "committed PDF yok: %s" % pdf_path))
    else:
        pdf_sha = sha256_file(pdf_path)
    facts["pdf_sha256"] = pdf_sha

    # ── 3) donmuş kayıt (sidecar) ────────────────────────────────────────
    frozen_raw = None
    if not sidecar_path.is_file():
        findings.append(_finding(
            "frozen_record_missing", "donmuş kayıt yok: %s" % sidecar_path))
    else:
        frozen_raw, frozen_name = parse_frozen_raw(
            sidecar_path.read_text(encoding="utf-8", errors="replace"))
        if frozen_raw is None:
            findings.append(_finding(
                "frozen_record_malformed",
                "donmuş kayıtta `# raw: <64 hex>  <name>` satırı yok"))
        elif frozen_name != pdf_path.name:
            findings.append(_finding(
                "frozen_record_name_mismatch",
                "donmuş kayıt başka bir dosyayı imzalar: %r (beklenen %r)"
                % (frozen_name, pdf_path.name)))
        elif pdf_sha is not None and frozen_raw != pdf_sha:
            findings.append(_finding(
                "frozen_record_mismatch",
                "donmuş kayıt ile committed PDF ayrışıyor",
                expected=frozen_raw, actual=pdf_sha))
    facts["frozen_raw"] = frozen_raw

    # ── 4) mühür ↔ PDF: asıl iddia ───────────────────────────────────────
    if pdf_sha is not None:
        ring = seal["ring"]
        if ring is not None:
            if len(ring) < MIN_RING_HEX:
                findings.append(_finding(
                    "seal_ring_too_short",
                    "mühür halkasındaki önek kanıt için çok kısa "
                    "(<%d hex)" % MIN_RING_HEX, ring=ring))
            elif not pdf_sha.startswith(ring):
                findings.append(_finding(
                    "seal_ring_mismatch",
                    "mühür halkası committed PDF ile eşleşmiyor",
                    ring=ring, pdf_sha256=pdf_sha))
        center = seal["center"]
        if center is not None and not pdf_sha.startswith(center):
            findings.append(_finding(
                "seal_center_mismatch",
                "mühür merkezi committed PDF ile eşleşmiyor",
                center=center, pdf_sha256=pdf_sha))
    # Halka ile merkez birbirini tutmalı (aynı hash'in iki farklı kırpması).
    if seal["ring"] and seal["center"] and \
            not seal["ring"].startswith(seal["center"]):
        findings.append(_finding(
            "seal_internal_inconsistency",
            "halka ile merkez aynı hash'i göstermiyor",
            ring=seal["ring"], center=seal["center"]))

    return findings, facts


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=REPO_ROOT,
                        help="repository root (varsayılan: script'ten türetilir)")
    parser.add_argument("--landing", type=Path, default=None,
                        help="landing.html yolu (varsayılan: --root altında)")
    parser.add_argument("--pdf", type=Path, default=None,
                        help="committed PDF yolu (varsayılan: --root altında)")
    parser.add_argument("--sidecar", type=Path, default=None,
                        help="donmuş kayıt yolu (varsayılan: <pdf>.metadata.sha256)")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--out", type=Path,
                        help="JSON raporunu bu yola da yaz")
    args = parser.parse_args(argv)

    root = args.root.expanduser().resolve()
    if not root.is_dir():
        print("HATA: --root bir dizin değil: %s" % root, file=sys.stderr)
        return 2

    landing = args.landing.expanduser() if args.landing else root / LANDING_REL
    pdf = args.pdf.expanduser() if args.pdf else root / PDF_REL
    sidecar = (args.sidecar.expanduser() if args.sidecar
               else pdf.with_name(pdf.name + SIDECAR_SUFFIX))

    findings, facts = check(landing, pdf, sidecar)
    report = {
        "ok": not findings,
        "findings": findings,
        "root": str(root),
        "hashes": {
            "seal_ring": facts["seal"]["ring"],
            "seal_center": facts["seal"]["center"],
            "pdf_sha256": facts["pdf_sha256"],
            "frozen_raw": facts["frozen_raw"],
        },
        "paths": {
            "landing": facts["landing"],
            "pdf": facts["pdf"],
            "sidecar": facts["sidecar"],
        },
    }
    encoded = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(encoded, encoding="utf-8")
    if args.json:
        print(encoded, end="")
    else:
        hashes = report["hashes"]
        print("check-seal-hash: mühür ↔ %s" % pdf.name)
        print("  mühür halkası : %s" % hashes["seal_ring"])
        print("  committed PDF : %s" % hashes["pdf_sha256"])
        print("  donmuş kayıt  : %s" % hashes["frozen_raw"])
        for item in findings:
            print("  %s — %s" % (item["kind"].upper(), item["detail"]))
        print("SONUÇ: temiz (mühür committed PDF'i doğruluyor)"
              if not findings
              else "SONUÇ: %d bulgu — fail-closed" % len(findings))
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
