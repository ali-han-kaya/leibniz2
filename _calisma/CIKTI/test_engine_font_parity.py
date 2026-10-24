#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_engine_font_parity.py — tectonic (XeTeX) ↔ TeXLive (pdfTeX) tipografi.

Sözleşme (2026-10-19 ölçümü):
  * Metin: Latin Modern — tectonic varsayılanı; pdfTeX ise `lmodern` olmadan
    T1/CM-Super (SFRM/SFBX) kullanıyordu. CM-Super ↔ LM düşey metrikleri
    ~3pt kayıyor, sayfa 4 bir satır taşıyor ve TOC sayfa numaraları
    (p7↔p6, p25↔p24) zincirleme kayıyordu.
  * Matematik: klasik CM (CMMI/CMSY/CMEX) — `lmodern`'in `nomath` seçeneği
    pdfTeX'in math fontlarını değiştirmez; XeTeX'in LaTeX math setup'ı da
    zaten CM kullanır.
  * Sonuç: 33/33 sayfa, 760/760 prose satırı aynı metin ve aynı satır-sonu
    x'i (tolerans 0.5pt; ölçülen en büyük fark 0.043pt), TOC sayfa numaraları
    birebir. Kalan PDF byte farkı PFB vs CFF embedding'idir (konum değil).

Test iki katmanlıdır (repo kuralı: tarayıcı/araç yokken de kırmızıya
düşebilen statik katman):
  1) STATİK — preamble `\\usepackage[nomath]{lmodern}` taşımalı, engine'e
     özgü font anahtarı (fontspec/unicode-math/setmainfont) bulunmamalı.
  2) GERÇEK — tectonic + pdflatex + pdftotext varsa iki motor da gerçek
     kaynaktan derlenir; sayfa sayısı, prose satır sayısı ve her satırın
     **metni + sağ kenar x'i** birebir olmalı. Satır-sonu x'i, metin
     çıkarımındaki matematik/diakritik gürültüsünden bağımsız olarak
     hyphenation ve satır kırılımını ölçer: taşan kelime sağ kenardan sol
     kenara atlar. Araçlar yoksa yalnız bu katman atlanır (statik katman
     koşar).
"""
from __future__ import annotations

import html
import os
import re
import shutil
import subprocess
import tempfile
import unicodedata
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
PACKAGE = (ROOT / "_calisma" / "V5_ICERIK"
           / "TESLIM_V5_FINAL_2026-08-17" / "stoic_hume_package"
           / "Stoic_Hume_Formal_Section_2026-08-17")
TEX = PACKAGE / "ingiliz_empirizmi_v3.tex"
CORE = PACKAGE / "core_section.tex"

# Prose satırı eşikleri ölçümle sabitlendi: gerçek belgede 760 satır yakalar;
# denklem satırları, tablo hücreleri ve nokta liderli TOC satırları elenir.
PROSE_MIN_CHARS = 25
PROSE_MIN_WORDS = 4
PROSE_MIN_ALPHA = 0.80
LINE_X_TOLERANCE = 0.5  # pt — ölçülen en büyük fark 0.043pt (yuvarlama)

_LIGATURES = {
    "\ufb00": "ff", "\ufb01": "fi", "\ufb02": "fl",
    "\ufb03": "ffi", "\ufb04": "ffl",
}
# pdftotext bazı diakritikleri iki motorda farklı Unicode'a çözer
# (Dharmakīrti ↔ Dharmakı̄rti). Satır kırılımı aynıysa bu fark önemsizdir;
# NFKD + combining silme + dotless-i eşlemesi karşılaştırmayı harf
# kimliğinden bağımsız hale getirir.
_DOTLESS_I = str.maketrans({"ı": "i", "İ": "I"})
# Matematik/tabloya ait satırları dışlar; bu belirteçler prose satırında
# görünmez (metin içi `§2.5` gibi referanslar `§` ile gelir, `+`/`=` ile değil).
_MATH_TOKENS = set("=+∈∧→⊆¬∃∀□θφΓ∗⟨⟩∑∏√≤≥≠±×÷↾⊨⊢")


def normalize_line(value: str) -> str:
    value = "".join(_LIGATURES.get(ch, ch) for ch in value)
    value = unicodedata.normalize("NFKD", value)
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", value.translate(_DOTLESS_I)).strip()


def is_prose(line: str) -> bool:
    core = line.replace(" ", "")
    if len(core) < PROSE_MIN_CHARS or len(line.split()) < PROSE_MIN_WORDS:
        return False
    if any(ch in _MATH_TOKENS for ch in core):
        return False
    if "_" in line or "\\" in line or line[:1].isdigit():
        return False
    return sum(ch.isalpha() for ch in core) / len(core) >= PROSE_MIN_ALPHA


def pdf_pages(path: Path) -> int:
    out = subprocess.run(
        ["pdfinfo", str(path)], capture_output=True, check=True,
        encoding="utf-8", errors="replace",
    ).stdout
    match = re.search(r"^Pages:\s+(\d+)\s*$", out, re.M)
    if not match:
        raise AssertionError(f"pdfinfo Pages satırı yok: {path}")
    return int(match.group(1))


def pdf_prose_lines(path: Path) -> list[list[tuple[str, float]]]:
    """Sayfa başına (normalize metin, satır-sonu xMax) prose satırları.

    `-bbox-layout` PDF'in kendi glif konumlarını verir; `-layout` metninin
    satır gruplamasına bağlı değildir. xMax, satır kırılımının parmak izidir.
    """
    out = subprocess.run(
        ["pdftotext", "-bbox-layout", str(path), "-"],
        capture_output=True, check=True, encoding="utf-8", errors="replace",
    ).stdout
    pages = []
    for page in out.split("<page ")[1:]:
        lines = []
        for match in re.finditer(r"<line[^>]*>(.*?)</line>", page, re.S):
            words = [
                (float(word.group(1)), html.unescape(word.group(2)))
                for word in re.finditer(
                    r'<word xMin="[\d.]+" yMin="[\d.]+" '
                    r'xMax="([\d.]+)" yMax="[\d.]+">(.*?)</word>',
                    match.group(1),
                )
            ]
            if not words:
                continue
            text = normalize_line(" ".join(word for _, word in words))
            if text and is_prose(text):
                lines.append((text, words[-1][0]))
        pages.append(lines)
    return pages


class TestPreambleFontContract(unittest.TestCase):
    """Statik katman — motor/araç olmadan da koşar ve kırmızıya düşebilir."""

    def setUp(self):
        self.text = TEX.read_text(encoding="utf-8")

    def test_loads_latin_modern_without_replacing_cm_math(self):
        self.assertIn("\\usepackage[nomath]{lmodern}", self.text,
                      "engine parity: LM metin + klasik CM matematik şart")
        self.assertIn("\\usepackage[T1]{fontenc}", self.text)
        self.assertLess(
            self.text.index("\\usepackage[T1]{fontenc}"),
            self.text.index("\\usepackage[nomath]{lmodern}"),
            "lmodern fontenc'ten sonra yüklenmeli",
        )

    def test_no_engine_specific_font_override(self):
        # Bu anahtarlar bir motoru diğerinden ayırır; parity'yi bozar.
        for token in ("fontspec", "unicode-math", "\\setmainfont",
                      "\\setmathfont"):
            self.assertNotIn(token, self.text,
                             f"engine'e özgü font anahtarı parity'yi bozar: {token}")

    def test_core_input_still_present(self):
        self.assertIn("\\input{core_section.tex}", self.text)
        self.assertTrue(CORE.is_file(), f"core section yok: {CORE}")


@unittest.skipUnless(
    all(shutil.which(tool) for tool in ("tectonic", "pdflatex", "pdftotext", "pdfinfo")),
    "tectonic/pdflatex/pdftotext/pdfinfo yok — yalnız statik katman koştu",
)
class TestRealEngineParity(unittest.TestCase):
    """Gerçek iki motor derlemesi: sayfa + prose satır kırılımı."""

    @classmethod
    def setUpClass(cls):
        cls._td = tempfile.TemporaryDirectory(prefix="engine-parity-")
        cls.root = Path(cls._td.name)
        shutil.copy2(TEX, cls.root / TEX.name)
        shutil.copy2(CORE, cls.root / CORE.name)
        cls.tex = cls.root / TEX.name
        cls.tt_dir = cls.root / "tectonic"
        cls.tl_dir = cls.root / "texlive"
        cls.tt_dir.mkdir()
        cls.tl_dir.mkdir()

        tectonic = subprocess.run(
            ["tectonic", "--outdir", str(cls.tt_dir), str(cls.tex)],
            cwd=cls.root, capture_output=True, timeout=240,
            encoding="utf-8", errors="replace",
        )
        if tectonic.returncode != 0:
            raise AssertionError(
                "tectonic derlemesi başarısız:\n"
                + tectonic.stdout[-3000:] + tectonic.stderr[-3000:]
            )
        cls.tt_pdf = cls.tt_dir / f"{cls.tex.stem}.pdf"

        env = dict(os.environ, TEXINPUTS=f"{cls.root}//:")
        for _ in range(3):
            build = subprocess.run(
                ["pdflatex", "-interaction=nonstopmode", "-halt-on-error",
                 f"-output-directory={cls.tl_dir}", str(cls.tex)],
                cwd=cls.root, env=env, capture_output=True,
                timeout=240, encoding="utf-8", errors="replace",
            )
            if build.returncode != 0:
                raise AssertionError(
                    "pdflatex derlemesi başarısız:\n"
                    + build.stdout[-3000:] + build.stderr[-3000:]
                )
        cls.tl_pdf = cls.tl_dir / f"{cls.tex.stem}.pdf"

    @classmethod
    def tearDownClass(cls):
        cls._td.cleanup()

    def test_same_page_count(self):
        self.assertEqual(pdf_pages(self.tt_pdf), pdf_pages(self.tl_pdf))

    @unittest.skipUnless(shutil.which("pdffonts"), "pdffonts yok")
    def test_same_embedded_font_designs(self):
        """Embedding biçimi (CFF/PFB) farklı olabilir; font *tasarımı* aynı."""
        def base_fonts(pdf: Path) -> set[str]:
            out = subprocess.run(
                ["pdffonts", str(pdf)], capture_output=True, check=True,
                encoding="utf-8", errors="replace",
            ).stdout
            names = set()
            for line in out.splitlines()[2:]:
                parts = line.split()
                if parts:
                    names.add(re.sub(r"^[A-Z]{6}\+", "", parts[0]))
            return names

        tt = base_fonts(self.tt_pdf)
        tl = base_fonts(self.tl_pdf)
        self.assertEqual(tt, tl, f"gömülü font tasarımları farklı: {tt ^ tl}")
        self.assertTrue(any(name.startswith("LMRoman") for name in tt),
                        f"Latin Modern metin fontu yok: {sorted(tt)}")
        self.assertFalse({name for name in tt
                          if name.startswith(("SFRM", "SFBX"))},
                         f"CM-Super gömülü — parity bozuk: {sorted(tt)}")

    def test_same_prose_line_breaks(self):
        tt = pdf_prose_lines(self.tt_pdf)
        tl = pdf_prose_lines(self.tl_pdf)
        total = sum(len(page) for page in tt)
        self.assertGreater(total, 500,
                           "prose filtresi boş/oyuk — karşılaştırma anlamsız")
        self.assertEqual(len(tt), len(tl), "sayfa sayısı farklı")
        for index, (a, b) in enumerate(zip(tt, tl), start=1):
            if len(a) != len(b):
                self.fail(
                    f"sayfa {index}: prose satır sayısı farklı "
                    f"({len(a)} vs {len(b)}) — satır kırılımı kaydı"
                )
            for row, (line_a, line_b) in enumerate(zip(a, b), start=1):
                if line_a[0] == line_b[0] and abs(line_a[1] - line_b[1]) <= LINE_X_TOLERANCE:
                    continue
                self.fail(
                    f"sayfa {index} satır {row}: satır kırılımı farklı\n"
                    f"  tectonic: {line_a[0]!r} (xMax {line_a[1]:.3f}pt)\n"
                    f"  texlive : {line_b[0]!r} (xMax {line_b[1]:.3f}pt)"
                )


if __name__ == "__main__":
    unittest.main()
