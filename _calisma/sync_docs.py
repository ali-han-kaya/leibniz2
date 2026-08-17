#!/usr/bin/env python3
"""
sync_docs.py — iff skop düzeltmesi sonrası bayat sayı/hash'leri senkronlar.
preview.html manifest tablosu, README, TEMIZLIK, TESLIM_OZETI, TESLIM_KRONOLOJISI.
Hem dış (TESLIM/) hem iç (V5_ICERIK/) kopyaları günceller.
"""
import os
import re

ROOT = os.path.dirname(os.path.abspath(__file__))
OUTER = os.path.join(ROOT, "TESLIM", "Stoic-Hume-Final-V5_2026-08-17")
INNER = os.path.join(ROOT, "V5_ICERIK", "TESLIM_V5_FINAL_2026-08-17")
PKG = os.path.join(INNER, "stoic_hume_package", "Stoic_Hume_Formal_Section_2026-08-17")

# (dosya, boyut, md5) — taze hesaplanmış değerler
TABLE = [
    ("core_section.tex", 38600, "7528539906a42334ebd68d15f9203d4d"),
    ("L0_Lplus_spec.md", 12623, "c3232dc369ce72abefcfc94acc93e89a"),
    ("model_check_report.md", 7678, "330cf107fa1d0ec6d2f52a67c489b674"),
    ("core_formal_model_check.py", 8598, "bea016133582c0842199b9ad569a23c8"),
    ("encoding_sensitivity_check.py", 5287, "013d1e0f2752bc38b68cafdac6b18e22"),
    ("gate15_check.py", 6023, "347db78d2eabc88c1ba4de46fac84368"),
    ("test_output.txt", 835, "f279b2960983f79107c809baebc00f04"),
    ("encoding_sensitivity_output.txt", 1239, "ece0c79b00a5e4a16e5ea65acd5d8d13"),
    ("gate15_output.txt", 618, "10e4c756a176bb511aca7ab17234cade"),
    ("provenance2_supplement.md", 8981, "09476e318c6ad2147543141ccdf69c99"),
    ("requirements.txt", 600, "5834add8aa405dd4a87979001c999bef"),
    ("REPRODUCIBILITY.md", 9026, "99df28f4a6ea192a52552ac62056ca69"),
    ("INTEGRATION_NOTE.md", 15347, "724615c2f6e21afba975c123698b0fcc"),
    ("internal_review_report.md", 28664, "26196415ef8c4efd9e823a9eb83aca63"),
    ("original_manuscript.pdf", 117067, "51d3492177253069975306ff1b10b60c"),
    ("README.md", 10922, "904156a4ae836f2a4b8cbe24f871c152"),
    ("ingiliz_empirizmi_v3.tex", 76416, "406d3b77d82406a0ce7f2c0cc1898364"),
    ("ingiliz_empirizmi_v3.pdf", 214520, "3a9d8b1cc85ed1d68f52fbc1b04fe6a8"),
    ("TESLIM_NOTU.md", 2875, "ef4b8fc5c35aee30beafc760555d9d0a"),
    ("TEMIZLIK_KONTROL_LISTESI.md", 8969, "3f34cae5571acff38817a4122fce908d"),
]


def replace(path, old, new, must=True):
    with open(path, encoding="utf-8") as f:
        txt = f.read()
    if old not in txt:
        if must:
            raise SystemExit(f"BULUNAMADI in {path}: {old[:60]!r}")
        return
    with open(path, "w", encoding="utf-8") as f:
        f.write(txt.replace(old, new, 1))
    print(f"  güncellendi: {os.path.relpath(path, ROOT)}")


def update_preview(path):
    with open(path, encoding="utf-8") as f:
        txt = f.read()
    start = txt.index('<table class="manifest">')
    end = txt.index('</table>', start) + len('</table>')
    rows = "\n".join(
        f'    <tr><td>{fn}</td><td>{sz}</td><td>{md}</td></tr>' for fn, sz, md in TABLE
    )
    new_table = ('<table class="manifest">\n'
                 '    <tr><th class="l">File</th><th>Size (B)</th><th>MD5</th></tr>\n'
                 + rows + "\n  </table>")
    txt = txt[:start] + new_table + txt[end:]

    old_legend = ('core_section.tex (877 lines, 11 subsections) is \\input unchanged; the V5\n'
                  '    additions live in ingiliz_empirizmi_v3.tex and are compiled with tectonic.')
    new_legend = ('core_section.tex (885 lines, 11 subsections) is \\input with the V5g\n'
                  '    bridge-collapse scope fix; the V5 additions live in ingiliz_empirizmi_v3.tex\n'
                  '    and are compiled with tectonic.')
    if old_legend in txt:
        txt = txt.replace(old_legend, new_legend, 1)
    else:
        raise SystemExit(f"legend bulunamadı: {path}")

    with open(path, "w", encoding="utf-8") as f:
        f.write(txt)
    print(f"  güncellendi (tablo+legend): {os.path.relpath(path, ROOT)}")


# 1) preview.html (dış + iç)
update_preview(os.path.join(OUTER, "preview.html"))
update_preview(os.path.join(INNER, "preview.html"))

# 2) README.md (paket)
replace(os.path.join(PKG, "README.md"),
        "(877 lines, 11 subsections, 9 subsubsections); unchanged in V5",
        "(885 lines, 11 subsections, 9 subsubsections); V5g bridge-collapse scope fix applied")

# 3) TEMIZLIK_KONTROL_LISTESI.md (iç)
replace(os.path.join(INNER, "TEMIZLIK_KONTROL_LISTESI.md"),
        "paketteki V5 PDF: 213.335 B, MD5 `1e5161e2…`, 33 sayfa",
        "paketteki V5 PDF: 214.520 B, MD5 `3a9d8b1c…`, 33 sayfa")

# 4) TESLIM_OZETI.md (dış + iç)
ozet_edits = [
    ("ANA TAŞIMA BİRİMİ (508 KB — Dropbox klasörünün tamamı)",
     "ANA TAŞIMA BİRİMİ (492 KB — Dropbox klasörünün tamamı)"),
    ("iç zip: ana teslim (464 KB, 29 dosya içinde)",
     "iç zip: ana teslim (454 KB, 29 dosya içinde)"),
    ("teslim süreci kronolojisi (26 bölüm + NİHAİ DURUM)",
     "teslim süreci kronolojisi (27 bölüm + NİHAİ DURUM)"),
    ("`core_section.tex` (877 satır)", "`core_section.tex` (885 satır)"),
    ("Atıf denetimi (Tillemans 1999, Beauchamp, Nidditch, Bury).",
     "Atıf denetimi (Tillemans 1999, Beauchamp, Nidditch, Bury) · "
     "**V5g:** bridge-collapse karakterizasyonu skop düzeltmesi "
     "(çift düzeyi iff; global eşdeğerlik T₁∧M₀∧¬T₂ ⟺ T₁∧M₀∧(⋆), Z3-ile kanıtlı)."),
]
for p in (os.path.join(OUTER, "TESLIM_OZETI.md"), os.path.join(INNER, "TESLIM_OZETI.md")):
    for old, new in ozet_edits:
        replace(p, old, new)

# 5) TESLIM_KRONOLOJISI.md (dış + iç) — bölüm 27 + footer
section27 = """## 27. IFF SKOP DÜZELTMESİ (V5g — sembolik ispat sonrası)

- **Bulgu:** Z3 sembolik ispatı (`symbolic_proof_z3.py`), bridge-collapse
  karakterizasyonundaki \"a model separates T1 from T2 if and only if M ⊨ ⋆\"
  ifadesinin **yalnızca tek-çift düzeyinde** geçerli olduğunu; global yönde
  iff'in tek yönlü (`(T1∧M0∧¬T2) → ⋆`) olduğunu kanıtladı. `⋆` tek başına
  `T1`'i ima etmez (Z3 karşı-modeli).
- **Düzeltme:** `core_section.tex` bridge-collapse önermesi + kanıtı yeniden
  yazıldı — çift düzeyinde iff; global eşdeğerlik `T1∧M0∧¬T2 ⟺ T1∧M0∧(⋆)`
  (Z3 P4-d/P4-e UNSAT ile doğrulandı). `L0_Lplus_spec.md` §6 aynı biçimde
  düzeltildi; \"vacuous quantification\" cümlesi kaldırıldı.
- **PDF:** `tectonic 0.17.0` ile yeniden derlendi (33 sayfa, 214.520 B).
- **Zincir:** MANIFEST (18/18) + KLASOR_CHECKSUMLARI + iç/dış zip + sidecar
  yeniden üretildi; `verify_delivery.py` PASS (P0=0, P1=0).
- **Doğrulanabilir değerler:** sidecar'larda (self-reference). Makalenin tezi,
  teoremleri ve scriptleri değişmedi — yalnızca karakterizasyonun skopu
  düzeltildi.

## NİHAİ DURUM"""
for p in (os.path.join(OUTER, "TESLIM_KRONOLOJISI.md"), os.path.join(INNER, "TESLIM_KRONOLOJISI.md")):
    replace(p, "## NİHAİ DURUM", section27)
    replace(p,
            "Bu belge 26 bölüm + NİHAİ DURUM (27 başlık) ile teslim sürecinin tam kapanışını belgeler.",
            "Bu belge 27 bölüm + NİHAİ DURUM (28 başlık) ile teslim sürecinin tam kapanışını belgeler.")

print("Senkron tamamlandı.")
