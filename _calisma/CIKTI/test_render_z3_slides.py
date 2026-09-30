#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_render_z3_slides.py — render_z3_slides.py denetimi.

tex-render-guide Method 1 (standalone LaTeX → PDF → yüksek DPI PNG) ile
12 Z3 teoremini PNG'ye çeviren script'in kural sabitlemesi:

  1) THEOREMS ↔ symbolic_proof_z3.py record() ID'leri birebir (12/12)
  2) Drift fail-closed: tabloya yabancı teorem eklenirse / kod ID'si
     çıkarılırsa --check-sync exit 1 üretir (üretimle senkron kapısı)
  3) Beklenen sonuç tutarlılığı: aynı ID'nin verdict'i kodla eşleşmeli
     (ör. P4-b SAT, P4-d UNSAT — yanlış beklenen → drift)
  4) _latex_doc: geçerli standalone doküman üretir (preamble + teorem)
  5) Araç zinciri fallback: pdflatex→latex→tectonic, convert→pdftoppm→sips
     sırası (Method 1 yedekliliği); gerçek derleme yalnızca araç varsa
     (skip — CI'da TeX motoru olmayabilir).
  6) MOTOR SEÇİMİ koruyucu sözleşmesi (TestEngineSelection): öncelik
     pdflatex > latex > tectonic; pdflatex kuruluyken tectonic'e DÜŞÜLMEZ ve
     seçim 'Araçlar: LaTeX=...' satırında log'lanır; motor yoksa fail-closed.
  7) Bu koruyucunun kendisi mutasyonla sınanır (TestEngineSelectionMutation
     Guard): sıra ters / latex düşürülmüş / fail-open mutasyonlarının 4'ü de
     yakalanmalı (plan Faz 2 kanıtı '4/4' kalıcı hale getirildi).
"""
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import render_z3_slides as rz

THEOREM_IDS = ["P1-a", "P1-b", "P2", "P3-a", "P3-b",
               "P4-a", "P4-b", "P4-c", "P4-d", "P4-e", "P5", "P5-note"]


def _code_record_ids(src):
    """symbolic_proof_z3.py record() çağrılarındaki ID'ler."""
    import re
    return set(re.findall(r'record\("([^"]+)"', src))


class TestSyncCheck(unittest.TestCase):
    def test_twelve_theorems(self):
        """Tam 12 teorem, kaynak koddaki record() ID'leriyle birebir."""
        self.assertEqual(len(rz.THEOREMS), 12)
        self.assertEqual({t[0] for t in rz.THEOREMS}, set(THEOREM_IDS))

    def test_check_sync_passes_on_real_code(self):
        """Gerçek symbolic_proof_z3.py ile --check-sync exit 0."""
        self.assertEqual(rz.check_sync(), 0)

    def test_drift_extra_theorem_fails(self):
        """Tabloya kodda olmayan teorem eklenirse exit 1 (fail-closed)."""
        orig = rz.THEOREMS
        try:
            rz.THEOREMS = list(orig) + [("XX-1", r"x", "SAT", "sahte")]
            self.assertEqual(rz.check_sync(), 1)
        finally:
            rz.THEOREMS = orig

    def test_drift_missing_theorem_fails(self):
        """Kodda var ama tabloda yok → exit 1."""
        import re as _re
        orig = rz.THEOREMS
        try:
            # Tablodan P4-e'yi çıkar (kodda var) → drift
            rz.THEOREMS = [t for t in orig if t[0] != "P4-e"]
            self.assertEqual(rz.check_sync(), 1)
        finally:
            rz.THEOREMS = orig

    def test_drift_verdict_mismatch_fails(self):
        """Aynı ID'nin beklenen sonucu kodla çelişirse exit 1."""
        orig = rz.THEOREMS
        try:
            # P4-b kodda SAT — tabloda UNSAT yap → drift yakalanmalı
            rz.THEOREMS = [
                (t[0], t[1], "UNSAT" if t[0] == "P4-b" else t[2], t[3])
                for t in orig]
            self.assertEqual(rz.check_sync(), 1)
        finally:
            rz.THEOREMS = orig

    def test_code_ids_are_superset_of_table(self):
        """Koddaki 12 ID, tablo ID'lerini tam kapsar (kaynak tek)."""
        src = rz.Z3_SRC.read_text(encoding="utf-8")
        code_ids = _code_record_ids(src)
        self.assertEqual(code_ids, set(THEOREM_IDS))


class TestLatexDoc(unittest.TestCase):
    def test_doc_has_standalone_preamble(self):
        doc = rz._latex_doc(rz.THEOREMS[0], 4, False)
        self.assertIn(r"\documentclass[border=4pt]{standalone}", doc)
        self.assertIn(r"\usepackage{amsmath,amssymb}", doc)
        self.assertIn(r"\begin{document}", doc)
        self.assertIn(r"\end{document}", doc)

    def test_doc_contains_formula(self):
        tid, tex, _v, _n = rz.THEOREMS[0]
        doc = rz._latex_doc(rz.THEOREMS[0], 4, False)
        self.assertIn(tex, doc)
        self.assertNotIn(tid + r" \;·\;", doc)  # label yokken etiket basılmaz

    def test_doc_with_label(self):
        doc = rz._latex_doc(rz.THEOREMS[0], 4, True)
        self.assertIn(r"\texttt{P1-a}", doc)
        self.assertIn(r"\text{UNSAT}", doc)

    def test_all_theorems_produce_valid_doc(self):
        """Her teorem derlenebilir standalone doküman üretir."""
        for th in rz.THEOREMS:
            doc = rz._latex_doc(th, 4, False)
            self.assertTrue(doc.startswith(r"\documentclass[border=4pt]{standalone}"))
            self.assertTrue(doc.rstrip().endswith(r"\end{document}"))


class TestToolchain(unittest.TestCase):
    def test_find_tex_engine_returns_string_or_none(self):
        e = rz.find_tex_engine()
        if e is not None:
            self.assertIn(e, ("pdflatex", "latex", "tectonic"))

    def test_find_pdf_to_png_returns_string_or_none(self):
        c = rz.find_pdf_to_png()
        if c is not None:
            self.assertIn(c, ("convert", "magick", "pdftoppm", "sips"))


class _FakeShutil:
    """shutil.which yerine: yalnız verilen araç kümesini 'kurulu' sayar.

    Gerçek makinenin kurulumundan bağımsız, deterministik öncelik ölçümü için
    (stdlib shutil modülü DEĞİŞTİRİLMEZ — rz.shutil namespace'i yamanır).
    """

    def __init__(self, available):
        self.available = set(available)

    def which(self, candidate):
        return f"/fake/bin/{candidate}" if candidate in self.available else None


class TestEngineSelection(unittest.TestCase):
    """Motor seçimi koruyucu sözleşmesi (Faz 2).

    Neden: göç sonrası makinede hem pdflatex (TeXLive) hem tectonic kurulu
    olabilir. Seçim sessizce tectonic'e düşerse slaytlar farklı bir motorla
    (farklı font/ligatür) üretilir ve bu ancak gözle fark edilirdi. Sözleşme:
      - öncelik pdflatex > latex > tectonic (Method 1 sırası korunur)
      - pdflatex VARSA tectonic'e düşülmez
      - seçilen motor log'da görünür ('Araçlar: LaTeX=<motor>')
      - motor yoksa fail-closed (rc=2)
    """

    SCRIPT = HERE / "render_z3_slides.py"

    def _engine_for(self, available):
        with mock.patch.object(rz, "shutil", _FakeShutil(available)):
            return rz.find_tex_engine()

    # ── öncelik (deterministik; makine kurulumundan bağımsız) ─────────────
    def test_priority_pdflatex_first(self):
        self.assertEqual(self._engine_for({"pdflatex", "latex", "tectonic"}),
                         "pdflatex")

    def test_no_tectonic_fallback_when_pdflatex_present(self):
        self.assertEqual(self._engine_for({"pdflatex", "tectonic"}), "pdflatex",
                         "pdflatex varken tectonic'e düşülmemeli")

    def test_latex_between_pdflatex_and_tectonic(self):
        self.assertEqual(self._engine_for({"latex", "tectonic"}), "latex")

    def test_tectonic_is_last_resort(self):
        self.assertEqual(self._engine_for({"tectonic"}), "tectonic")

    def test_none_when_no_engine(self):
        self.assertIsNone(self._engine_for(set()))

    # ── log görünürlüğü + fail-closed (gerçek main() koşumu) ──────────────
    def _fake_bin(self, root, tools):
        """Sahte bin/: yalnız verilen araçlar 'kurulu' (çalıştırılmazlar
        — --only eşleşmeyen ID ile döngü hiç dönmez)."""
        b = root / "bin"
        b.mkdir()
        for tool in tools:
            p = b / tool
            p.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            p.chmod(0o755)
        return b

    def _run_main(self, bin_dir, out_dir):
        env = dict(os.environ, PATH=str(bin_dir))
        return subprocess.run(
            [sys.executable, str(self.SCRIPT), "--out", str(out_dir),
             "--only", "__hicbir_id__"],
            capture_output=True, text=True, env=env, timeout=120)

    def test_log_shows_pdflatex_and_never_tectonic(self):
        """pdflatex kuruluyken log pdflatex der; tectonic seçilmez."""
        with tempfile.TemporaryDirectory(prefix="z3-engine-") as td:
            root = pathlib.Path(td)
            r = self._run_main(self._fake_bin(root, ("pdflatex", "pdftoppm")),
                               root / "out")
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("LaTeX=pdflatex", r.stdout)
            self.assertNotIn("LaTeX=tectonic", r.stdout)

    def test_log_shows_tectonic_when_pdflatex_absent(self):
        """pdflatex yokken yedek zincir çalışır ve seçim log'da görünür."""
        with tempfile.TemporaryDirectory(prefix="z3-engine-") as td:
            root = pathlib.Path(td)
            r = self._run_main(self._fake_bin(root, ("tectonic", "pdftoppm")),
                               root / "out")
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("LaTeX=tectonic", r.stdout)

    def test_missing_engine_is_fail_closed(self):
        """Hiç motor yoksa rc=2 + açık hata (sessiz geçiş yok)."""
        with tempfile.TemporaryDirectory(prefix="z3-engine-") as td:
            root = pathlib.Path(td)
            r = self._run_main(self._fake_bin(root, ("pdftoppm",)), root / "out")
            self.assertEqual(r.returncode, 2)
            self.assertIn("TeX motoru bulunamadı", r.stderr)

    def test_missing_converter_is_fail_closed(self):
        """Motor var, PDF→PNG aracı yok → rc=2."""
        with tempfile.TemporaryDirectory(prefix="z3-engine-") as td:
            root = pathlib.Path(td)
            r = self._run_main(self._fake_bin(root, ("pdflatex",)), root / "out")
            self.assertEqual(r.returncode, 2)
            self.assertIn("PDF→PNG aracı bulunamadı", r.stderr)


class TestEngineSelectionMutationGuard(unittest.TestCase):
    """Koruyucu sözleşmenin KENDİSİNİ sınar (plan Faz 2 kanıtı kalıcı).

    Planın kanıtı "4 mutasyonun 4'ü yakalandı" idi ama kanıt dışarıda
    (elle) üretiliyordu. Bu sınıf onu YENİDEN ÜRETİLEBİLİR yapar:
    `render_z3_slides.py`'nin geçici bir kopyasına her mutasyon uygulanır ve
    `TestEngineSelection`'ın KIRMIZI düştüğü görülür. Bir mutasyon KAÇARSA
    koruyucu test zayıftır (sessiz motor kayması geri gelebilir) → fail.
    """

    SRC = HERE / "render_z3_slides.py"
    TEST = HERE / "test_render_z3_slides.py"
    # (ad, çapa, mutasyon) — çapalar kısa ve kararlı seçildi.
    MUTATIONS = (
        ("motor sırası ters (tectonic başa)",
         '("pdflatex", "latex", "tectonic")',
         '("tectonic", "latex", "pdflatex")'),
        ("laTeX zincirden çıkarıldı",
         '("pdflatex", "latex", "tectonic")',
         '("pdflatex", "tectonic")'),
        ("motor yokluğu fail-open",
         "if not engine:", "if False:"),
        ("PDF→PNG yokluğu fail-open",
         "if not converter:", "if False:"),
    )

    def _run_guard(self, td, source):
        (td / "render_z3_slides.py").write_text(source, encoding="utf-8")
        shutil.copy2(self.TEST, td / "test_render_z3_slides.py")
        return subprocess.run(
            [sys.executable, "-m", "unittest",
             "test_render_z3_slides.TestEngineSelection"],
            cwd=str(td), capture_output=True, text=True, timeout=300)

    def test_baseline_is_green(self):
        src = self.SRC.read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory(prefix="z3-mut-") as td:
            r = self._run_guard(pathlib.Path(td), src)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_every_mutation_is_caught(self):
        src = self.SRC.read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory(prefix="z3-mut-") as td:
            tdp = pathlib.Path(td)
            for name, old, new in self.MUTATIONS:
                with self.subTest(mutation=name):
                    self.assertIn(old, src,
                                  f"mutasyon çapası kaynakta yok: {name}")
                    r = self._run_guard(tdp, src.replace(old, new))
                    self.assertNotEqual(
                        r.returncode, 0,
                        f"mutasyon YAKALANMADI ({name}) — koruyucu test zayıf")


if __name__ == "__main__":
    unittest.main()
