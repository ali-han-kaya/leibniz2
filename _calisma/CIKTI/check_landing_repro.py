#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_landing_repro.py — image-to-code kaynakları + landing build reproducibility (fail-closed).

Ne kanıtlar
-----------
`_calisma/landing/refs/` image-to-code akışının KAYNAK kanıtıdır: 4 comp
bölümü için ekran görüntüsü (`comp-N-*.png`), kompozisyon (`comp-N-*.html`)
ve ölçüm (`analysis.json`: piksel + DOM metrikleri). Bu kaynaklar elle
`landing_src.html`'e işlenir; `build_landing.py` de ondan `landing.html` ve
`assets/` çıktısını üretir. Bu kapı iki boşluğu kapatır:

  1. **Kaynak smoke**: `analysis.json` gerçekten o PNG'leri mi anlatıyor
     (kayıtlı boyut ↔ baytlardaki gerçek IHDR), 4 PNG/HTML çifti eksiksiz mi,
     `landing_src.html` build önkoşullarını (token @import marker'ı, mühür
     placeholder'ları, 3 plaka yolu) hâlâ taşıyor mu?
  2. **Reproducibility**: committed `landing.html` gerçekten bu kaynaklardan mı
     üretildi? `build_landing.py` iki kez koşar: iki çıktı birbirinin ve
     committed artifact'ın bayt-özdeşi olmalı; sahnelenen plakalar committed
     `assets/` kopyasıyla eşleşmeli, committed kopya da `slides_z3/`
     kaynağıyla eşleşmeli (yeniden render edilen plaka, kopya güncellenmeden
     commit edilirse bayat kopya yakalanır).

`check_seal_hash.py` yalnız mühür HASH'ini bağlar (mühür ↔ PDF ↔ sidecar);
bu kapı artifact'ın BAYT düzeyinde yeniden üretilebilirliğini ölçer — elle
düzenlenmiş ya da kaynak değişiminden sonra bayatlamış `landing.html` hash
kontrolünden geçse bile burada düşer.

Mühür hash'i bu ağaçta artık koşum anından değil DONMUŞ KAYITTAN gelir:
`build_landing.py` committed PDF'in yanındaki `<pdf>.metadata.sha256`
sidecar'ının `# raw:` satırını okur ve hash'i PDF'in gerçek baytlarıyla
çapraz doğrular (bkz. `check_seal_hash.py` — aynı sözleşme). Bu kapı bu
yüzden derlemeyi TAZE BİR PASS SNAPSHOT olmadan, yalnız repodaki
kayıtlarla koşar; PDF ya da kayıt yoksa fail-closed (uydurma mühür
basılmaz). Ortam: stdlib-only, OFFLINE.

Kapsam sınırı: bu kapı plakaları üretmez — yoklarsa `plates_missing` bulgusu
ile durur ve üretim komutunu söyler (render_z3_slides.py). Build iki koşu
arasında 120 sn'yi aşarsa `build_failed` (zaman aşımı) raporlanır.

Exit codes: 0 = temiz, 1 = bulgu (fail-closed), 2 = kullanım/ölçüm hatası.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT / "_calisma" / "CIKTI") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "_calisma" / "CIKTI"))

# Donmuş kayıt sözleşmesinin tek kaynağı: sidecar biçimi + committed PDF yolu
# (build_landing.py ve check_seal_hash.py ile aynı değerler buradan gelir).
import check_seal_hash as seal_record  # noqa: E402

LANDING_REL = Path("_calisma") / "landing"
REFS_REL = LANDING_REL / "refs"
SLIDES_REL = Path("_calisma") / "CIKTI" / "slides_z3"
PDF_REL = seal_record.PDF_REL
SIDECAR_SUFFIX = seal_record.SIDECAR_SUFFIX

# 4 comp bölümü: PNG (kaynak görüntü) + HTML (kompozisyon) çiftleri.
COMPS = ("comp-1-hero", "comp-2-chain", "comp-3-proof", "comp-4-cta")
# build_landing.py'nin sahnelediği plakalar (tek kaynak: oradaki PLATES).
PLATES = ("P1-a.png", "P2.png", "P3-a.png")
PLATE_SRC_TOKEN = "../../CIKTI/slides_z3/%s"
IMPORT_MARKER = '@import "../../design-system/tokens.css"'
SEAL_PLACEHOLDERS = ("{{SEAL_RING}}", "{{SEAL_CENTER}}")

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
BUILD_TIMEOUT_S = 120.0


def sha256_file(path: Path) -> str:
    """Dosya baytlarının SHA-256'sı (parçalı okuma)."""
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def png_dimensions(path: Path):
    """PNG IHDR'ından (gen, yük); gerçek PNG değilse/okunamıyorsa None."""
    try:
        with path.open("rb") as fh:
            head = fh.read(24)
    except OSError:
        return None
    if len(head) < 24 or head[:8] != PNG_MAGIC or head[12:16] != b"IHDR":
        return None
    width, height = struct.unpack(">II", head[16:24])
    if width <= 0 or height <= 0:
        return None
    return width, height


def _finding(kind: str, detail: str, **extra) -> dict:
    item = {"kind": kind, "detail": detail}
    item.update(extra)
    return item


def check_sources(root: Path):
    """A) image-to-code kaynak smoke'u (refs + landing_src önkoşulları)."""
    findings = []
    facts = {}
    refs = root / REFS_REL

    for comp in COMPS:
        for suffix in (".png", ".html"):
            path = refs / (comp + suffix)
            if not path.is_file():
                findings.append(_finding(
                    "refs_pair_missing",
                    "image-to-code kaynağı eksik: %s" % path))

    real_dims = {}
    for comp in COMPS:
        path = refs / (comp + ".png")
        if not path.is_file():
            continue
        dims = png_dimensions(path)
        if dims is None:
            findings.append(_finding(
                "refs_png_invalid",
                "PNG değil ya da IHDR okunamadı: %s" % path))
        else:
            real_dims[comp] = dims
    facts["png_dims"] = {"%s.png" % c: "%dx%d" % d
                         for c, d in sorted(real_dims.items())}

    analysis_path = refs / "analysis.json"
    analysis = None
    if not analysis_path.is_file():
        findings.append(_finding(
            "analysis_missing", "ölçüm dosyası yok: %s" % analysis_path))
    else:
        try:
            analysis = json.loads(analysis_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            findings.append(_finding(
                "analysis_malformed",
                "analysis.json çözülemedi: %s" % exc))
    if analysis is not None and not isinstance(analysis, dict):
        findings.append(_finding(
            "analysis_malformed", "analysis.json JSON object değil"))
        analysis = None

    if isinstance(analysis, dict):
        pixels = analysis.get("pixels")
        if not isinstance(pixels, list):
            findings.append(_finding(
                "analysis_malformed", "analysis.json `pixels` listesi yok"))
        else:
            recorded = {}
            for item in pixels:
                if isinstance(item, dict) and isinstance(item.get("file"), str):
                    recorded[item["file"]] = item
            for comp in COMPS:
                name = comp + ".png"
                item = recorded.get(name)
                if item is None:
                    findings.append(_finding(
                        "analysis_pixel_coverage_missing",
                        "analysis.json `pixels` kapsamıyor: %s" % name,
                        file=name))
                    continue
                if comp not in real_dims:
                    continue
                real = "%dx%d" % real_dims[comp]
                if item.get("size") != real:
                    findings.append(_finding(
                        "analysis_pixel_size_mismatch",
                        "analysis.json boyutu PNG baytlarıyla ayrışıyor: %s"
                        % name, file=name, recorded=item.get("size"),
                        actual=real))
        dom = analysis.get("dom")
        if not isinstance(dom, list):
            findings.append(_finding(
                "analysis_malformed", "analysis.json `dom` listesi yok"))
        else:
            dom_files = {item.get("file") for item in dom
                         if isinstance(item, dict)}
            for comp in COMPS:
                name = comp + ".html"
                if name not in dom_files:
                    findings.append(_finding(
                        "analysis_dom_coverage_missing",
                        "analysis.json `dom` kapsamıyor: %s" % name,
                        file=name))

    src_path = root / LANDING_REL / "landing_src.html"
    if not src_path.is_file():
        findings.append(_finding(
            "landing_src_missing", "kaynak HTML yok: %s" % src_path))
    else:
        src = src_path.read_text(encoding="utf-8", errors="replace")
        required = [IMPORT_MARKER] + list(SEAL_PLACEHOLDERS) + \
            [PLATE_SRC_TOKEN % plate for plate in PLATES]
        for token in required:
            if token not in src:
                findings.append(_finding(
                    "landing_src_precondition_missing",
                    "build önkoşulu kaynakta yok: %s" % token,
                    token=token))
    return findings, facts


def run_build(root: Path, frozen_record_path: Path, output: Path,
              assets_dir: Path):
    """build_landing.py'yi gerçek CLI'siyle koşar (rc + stderr döner).

    Mühür kaynağı DONMUŞ KAYITTIR: uydurma/sentetik snapshot üretilmez.
    """
    cmd = [sys.executable, str(root / LANDING_REL / "build_landing.py"),
           "--frozen-record", str(frozen_record_path),
           "--output", str(output),
           "--assets-dir", str(assets_dir)]
    try:
        proc = subprocess.run(cmd, cwd=str(root), capture_output=True,
                              text=True, timeout=BUILD_TIMEOUT_S)
        return proc.returncode, proc.stderr
    except subprocess.TimeoutExpired:
        return None, "zaman aşımı (%gs)" % BUILD_TIMEOUT_S
    except OSError as exc:
        return None, "koşulamadı: %s" % exc


def _keyed_hashes(directory: Path, names):
    """Dizin içindeki verilen adların sha256'sı; eksik ad None olur."""
    return {name: (sha256_file(directory / name)
                   if (directory / name).is_file() else None)
            for name in names}


def check_build(root: Path, pdf_path: Path):
    """B) build smoke + reproducibility (iki koşu + committed artifact)."""
    findings = []
    facts = {}
    landing = root / LANDING_REL / "landing.html"
    assets = root / LANDING_REL / "assets"
    slides = root / SLIDES_REL
    build_py = root / LANDING_REL / "build_landing.py"

    if not build_py.is_file():
        findings.append(_finding(
            "build_script_missing", "derleyici yok: %s" % build_py))
        return findings, facts
    if not landing.is_file():
        findings.append(_finding(
            "artifact_missing", "committed landing.html yok: %s" % landing))
    if not pdf_path.is_file():
        findings.append(_finding(
            "pdf_missing", "mühür hash kaynağı PDF yok: %s" % pdf_path))
        return findings, facts

    missing_plates = [plate for plate in PLATES
                      if not (slides / plate).is_file()]
    if missing_plates:
        findings.append(_finding(
            "plates_missing",
            "plakalar yok: %s — üret: python3 _calisma/CIKTI/"
            "render_z3_slides.py --out _calisma/CIKTI/slides_z3"
            % ", ".join(missing_plates), missing=missing_plates))
        return findings, facts

    sha = sha256_file(pdf_path)
    facts["pdf_sha256"] = sha
    # Mühür kaynağı: committed PDF'in yanındaki donmuş kayıt (sidecar).
    frozen_record = pdf_path.with_name(pdf_path.name + SIDECAR_SUFFIX)
    facts["frozen_record"] = str(frozen_record)
    if not frozen_record.is_file():
        findings.append(_finding(
            "frozen_record_missing",
            "donmuş kayıt yok: %s — mühür kaynağı repoda olmalı "
            "(reproducible-pdf-build sidecar'ı)" % frozen_record))
        return findings, facts

    with tempfile.TemporaryDirectory(prefix="landing-repro-") as work:
        work_path = Path(work)
        runs = []
        for index in (1, 2):
            out_dir = work_path / ("run%d" % index)
            rc, stderr = run_build(root, frozen_record,
                                   out_dir / "landing.html",
                                   out_dir / "assets")
            if rc != 0:
                findings.append(_finding(
                    "build_failed",
                    "build_landing.py koşu %d rc=%s" % (index, rc),
                    run=index, stderr=stderr.strip()[-500:]))
                return findings, facts
            runs.append(out_dir)

        first_html, second_html = (runs[0] / "landing.html",
                                   runs[1] / "landing.html")
        h1 = sha256_file(first_html)
        h2 = sha256_file(second_html)
        facts["rebuild_sha256"] = [h1, h2]
        if h1 != h2:
            findings.append(_finding(
                "build_nondeterministic",
                "iki derleme bayt-özdeş değil (derleyici deterministik değil)",
                first=h1, second=h2))
        if landing.is_file():
            committed = sha256_file(landing)
            facts["committed_sha256"] = committed
            if h1 != committed:
                findings.append(_finding(
                    "artifact_drift",
                    "yeniden derleme committed landing.html ile bayt-özdeş "
                    "değil — artifact elle düzenlenmiş ya da bayat",
                    rebuild=h1, committed=committed))

        # Provenance: kalıcı build provenance artifact'ı (mühürle aynı hash).
        # Yeniden derlemeler provenance da üretir (derleyici yazar); committed
        # kopya bayt-özdeş olmalı, committed mühür de provenance hash'ini
        # taşımalı (mühür↔provenance bağı).
        run_provs = [run_dir / "landing.provenance.json"
                     for run_dir in runs]
        for index, prov in enumerate(run_provs, 1):
            if not prov.is_file():
                findings.append(_finding(
                    "provenance_missing",
                    "koşu %d provenance artifact'ı üretmedi" % index,
                    run=index))
        if all(prov.is_file() for prov in run_provs):
            phashes = [sha256_file(prov) for prov in run_provs]
            facts["provenance_sha256"] = phashes
            if phashes[0] != phashes[1]:
                findings.append(_finding(
                    "build_nondeterministic",
                    "provenance artifact'ı koşular arasında farklı",
                    first=phashes[0], second=phashes[1]))
        committed_prov = landing.parent / "landing.provenance.json"
        if not committed_prov.is_file():
            findings.append(_finding(
                "provenance_missing",
                "committed provenance artifact'ı yok: %s" % committed_prov))
        elif all(prov.is_file() for prov in run_provs):
            if sha256_file(committed_prov) != sha256_file(run_provs[0]):
                findings.append(_finding(
                    "provenance_drift",
                    "yeniden derleme provenance'ı committed provenance ile "
                    "bayt-özdeş değil",
                    rebuild=sha256_file(run_provs[0]),
                    committed=sha256_file(committed_prov)))
            else:
                try:
                    prov_data = json.loads(
                        committed_prov.read_text(encoding="utf-8"))
                    prov_hash = prov_data.get("snapshot_hash", "")
                except (OSError, ValueError):
                    prov_hash = ""
                seal = ""
                if landing.is_file():
                    html = landing.read_text(encoding="utf-8")
                    marker = "VERIFIED • "
                    at = html.find(marker)
                    if at >= 0:
                        seal = html[at + len(marker):at + len(marker) + 12]
                if not prov_hash or \
                        seal.upper() != prov_hash[:12].upper():
                    findings.append(_finding(
                        "seal_provenance_mismatch",
                        "committed mühür provenance snapshot hash'ini "
                        "taşımıyor",
                        seal=seal, provenance_hash=prov_hash))

        for index, run_dir in enumerate(runs, 1):
            staged = sorted(p.name for p in (run_dir / "assets").iterdir()
                            if p.is_file())
            if staged != sorted(PLATES):
                findings.append(_finding(
                    "asset_drift",
                    "koşu %d sahnelenen plaka kümesi 3 plaka değil" % index,
                    run=index, staged=staged))
        for plate in PLATES:
            run1 = runs[0] / "assets" / plate
            run2 = runs[1] / "assets" / plate
            if not run1.is_file():
                findings.append(_finding(
                    "asset_drift", "koşu 1 sahnelenen plaka yok: %s" % plate,
                    plate=plate))
                continue
            h_plate = sha256_file(run1)
            if run2.is_file() and sha256_file(run2) != h_plate:
                findings.append(_finding(
                    "build_nondeterministic",
                    "plaka baytları koşular arasında farklı: %s" % plate,
                    plate=plate))
            for label, candidate in (("committed assets", assets / plate),
                                     ("slides_z3 kaynağı", slides / plate)):
                if candidate.is_file() and \
                        sha256_file(candidate) != h_plate:
                    findings.append(_finding(
                        "asset_drift",
                        "sahnelenen plaka %s ile eşleşmiyor: %s"
                        % (label, candidate), plate=plate,
                        source=(label.split()[0])))
            # Bayat kopya: committed assets ↔ slides_z3 doğrudan karşılaştırılır
            # (staged kopya her zaman slides ile aynıdır — o eşitlik kopya
            # sadakatini doğrular, drift'i değil).
            committed_plate = assets / plate
            slide_plate = slides / plate
            if committed_plate.is_file() and slide_plate.is_file() and \
                    sha256_file(committed_plate) != sha256_file(slide_plate):
                findings.append(_finding(
                    "asset_drift",
                    "committed assets kopyası slides_z3 kaynağıyla "
                    "eşleşmiyor (bayat kopya): %s" % committed_plate,
                    plate=plate, source="committed-vs-slides"))
        facts["assets"] = {
            "staged": sorted(p.name for p in (runs[0] / "assets").iterdir()
                             if p.is_file()),
            "committed": (sorted(p.name for p in assets.iterdir()
                                 if p.is_file())
                          if assets.is_dir() else []),
        }
    return findings, facts


def check(root: Path, pdf_path=None):
    """Tüm katmanlar; (findings, facts) döndürür."""
    pdf = Path(pdf_path) if pdf_path is not None else root / PDF_REL
    src_findings, src_facts = check_sources(root)
    build_findings, build_facts = check_build(root, pdf)
    facts = {"sources": src_facts, "build": build_facts}
    return src_findings + build_findings, facts


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=REPO_ROOT,
                        help="repository root (varsayılan: script'ten türetilir)")
    parser.add_argument("--pdf", type=Path, default=None,
                        help="mühür hash kaynağı PDF (varsayılan: --root altında)")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--out", type=Path, help="JSON raporunu bu yola da yaz")
    args = parser.parse_args(argv)

    root = args.root.expanduser().resolve()
    if not root.is_dir():
        print("HATA: --root bir dizin değil: %s" % root, file=sys.stderr)
        return 2

    pdf = args.pdf.expanduser() if args.pdf else None
    findings, facts = check(root, pdf_path=pdf)
    report = {
        "ok": not findings,
        "findings": findings,
        "root": str(root),
        "facts": facts,
    }
    encoded = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(encoded, encoding="utf-8")
    if args.json:
        print(encoded, end="")
    else:
        print("check-landing-repro: image-to-code kaynakları + landing build")
        build_facts = facts.get("build", {})
        if build_facts.get("rebuild_sha256"):
            print("  yeniden derleme : %s / %s"
                  % tuple(build_facts["rebuild_sha256"]))
        if build_facts.get("committed_sha256"):
            print("  committed       : %s" % build_facts["committed_sha256"])
        for item in findings:
            print("  %s — %s" % (item["kind"].upper(), item["detail"]))
        print("SONUÇ: temiz (kaynaklar smoke + derleme yeniden üretilebilir)"
              if not findings
              else "SONUÇ: %d bulgu — fail-closed" % len(findings))
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
