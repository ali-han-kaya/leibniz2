#!/usr/bin/env python3
"""build_landing.py — landing_src.html -> landing.html derleyicisi.

image-to-code akışının son halkası. Yapılanlar:
  1. design-system/tokens.css dosya içeriğini @import satırının yerine gömer
     (tek-kaynak sözleşmesi: landing'te sıfır uydurma renk; tüketim
     tokens.css'ten, embed yalnız taşıma).
  2. Mühür placeholder'larını GERÇEK veriyle doldurur:
       {{SEAL_RING}}   -> VERIFIED • <raw sha ilk 12 hex, büyük> •
                          (donmuş kayıt: qpdf_determinism_output.txt raw SHA-256)
       {{SEAL_CENTER}} -> ilk 6 hex + "…"
     Kaynak yolu git grep ile bulunamazsa build BAŞARISIZ biter — uydurma
     hash basılmaz (fail-closed, dashboard'un a11y kapısıyla aynı ilke).
  3. Z3 plakalarını assets/ altına kopyalar ve yolları yeniden yazar
     (self-contained preview: served-root dışı göreceli yollar 404 olur).
  4. Çıktıyı yaz ve basit tutarlılık kontrollerinden geçir.
"""
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = Path(__file__).resolve().parent / "landing_src.html"
OUT = Path(__file__).resolve().parent / "landing.html"
ASSETS = Path(__file__).resolve().parent / "assets"
SLIDES = ROOT / "_calisma" / "CIKTI" / "slides_z3"
PLATES = ["P1-a.png", "P2.png", "P3-a.png"]
TOKENS = ROOT / "design-system" / "tokens.css"
DETERMINISM_RECORD = (
    ROOT / "_calisma" / "V5_ICERIK" / "TESLIM_V5_FINAL_2026-08-17"
    / "stoic_hume_package" / "Stoic_Hume_Formal_Section_2026-08-17"
    / "qpdf_determinism_output.txt"
)


def die(msg):
    print(f"BUILD FAIL: {msg}", file=sys.stderr)
    sys.exit(1)


def main():
    src = SRC.read_text(encoding="utf-8")
    tokens = TOKENS.read_text(encoding="utf-8")

    # 1) token gömme — @import satırını dosya içeriğiyle değiştir
    imp = '<style>@import "../../design-system/tokens.css";</style>'
    if imp not in src:
        die("@import satırı kaynakta bulunamadı — dosya değişti mi?")
    src = src.replace(imp, "<style>\n" + tokens + "\n</style>")

    # 2) gerçek hash — donmuş kayıttan raw SHA-256 (fail-closed)
    rec = DETERMINISM_RECORD.read_text(encoding="utf-8")
    m = re.search(r"raw SHA-256\s*:\s*([0-9a-f]{64})", rec)
    if not m:
        die("donmuş kayıtta raw SHA-256 bulunamadı — mühür uydurulmaz")
    sha = m.group(1).upper()

    src = src.replace("{{SEAL_RING}}", f"VERIFIED • {sha[:12]} •")
    src = src.replace("{{SEAL_CENTER}}", sha[:6] + "…")

    # 3) plakalar: self-contained kopya + yol yeniden yazımı
    ASSETS.mkdir(exist_ok=True)
    for plate in PLATES:
        srcp = SLIDES / plate
        if not srcp.is_file():
            die(f"plaka bulunamadı: {srcp}")
        shutil.copyfile(srcp, ASSETS / plate)
        src = src.replace(f"../../CIKTI/slides_z3/{plate}", f"assets/{plate}")

    # 4) tutarlılık kontrolleri
    leftover = re.findall(r"\{\{[A-Z_]+\}\}", src)
    if leftover:
        die(f"doldurulmamış placeholder: {leftover}")
    for banned in ("F4F1EA", "#000000", "quantumly", "nexus", "acme"):
        if banned.lower() in src.lower():
            die(f"yasaklı değer/klise: {banned}")
    if "--on-accent" not in src:
        die("btn-primary kontrast token'ı kayıp")
    if "../../CIKTI/slides_z3" in src:
        die("plaka yolu yeniden yazılamadı — self-contained değil")

    OUT.write_text(src, encoding="utf-8")
    print(f"OK: {OUT.name} ({OUT.stat().st_size} bayt) — mühür {sha[:12]}")


if __name__ == "__main__":
    main()
