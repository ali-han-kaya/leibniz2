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
  5) Araç zinciri fallback: pdflatex→tectonic, convert→pdftoppm→sips
     sırası (Method 1 yedekliliği); gerçek derleme yalnızca araç varsa
     (skip — CI'da TeX motoru olmayabilir).
  6) Motor seçimi fail-closed: pdflatex kuruluyken tectonic'e DÜŞÜLMEZ,
     seçim `Araçlar: LaTeX=...` satırında log'lanır, hiç motor yoksa rc=2.
     Kanıt KALICI: `TestEngineSelectionMutationGuard` her koşumda
     render_z3_slides.py'nin geçici kopyasına sıra-ters / pdflatex-düşür /
     fail-open / log-sil mutasyonlarını uygular ve bekçinin KIRMIZI
     düştüğünü doğrular (mutation_guard.py). Mutasyon kaçarsa test fail —
     sessiz motor kayması geri gelemez.
"""
import contextlib
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import mutation_guard  # noqa: E402
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


# ---------------------------------------------------------------------------
# Motor seçimi: fail-closed bekçi + KALICI mutasyon kanıtı
# ---------------------------------------------------------------------------
def _stub_bin(root, names):
    """Sahte araç dizini: her isim için çalıştırılabilir stub (exit 1)."""
    d = pathlib.Path(root) / ("bin_" + ("_".join(names) if names else "empty"))
    d.mkdir(parents=True, exist_ok=True)
    for name in names:
        p = d / name
        p.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
        p.chmod(0o755)
    return d


@contextlib.contextmanager
def _only_path(path):
    """os.environ PATH'ini geçici olarak tek dizine indir (sonra geri koy)."""
    old = os.environ.get("PATH", "")
    os.environ["PATH"] = str(path)
    try:
        yield
    finally:
        os.environ["PATH"] = old


def _engine_violations(module, script_path):
    """Motor-seçimi bekçisinin gördüğü ihlaller ([] = sağlıklı).

    Aynı fonksiyon gerçek modülde ve MUTANT kopyalarda koşar; mutant bir
    ihlal üretmiyorsa mutasyon testi kırmızı olur (kanıt kaçmaz).
    """
    out = []
    with tempfile.TemporaryDirectory(prefix="z3eng_") as td:
        full = _stub_bin(td, ["latex", "pdflatex", "tectonic"])
        no_pdflatex = _stub_bin(td, ["latex", "tectonic"])
        tectonic_only = _stub_bin(td, ["tectonic"])
        empty = _stub_bin(td, [])
        for path, expected, label in (
                (full, "pdflatex", "pdflatex kuruluyken"),
                (no_pdflatex, "latex", "pdflatex yokken"),
                (tectonic_only, "tectonic", "yalnız tectonic varken")):
            with _only_path(path):
                got = module.find_tex_engine()
            if got != expected:
                out.append(f"{label} {expected} seçilmeliydi, {got!r} seçildi")
        with _only_path(empty):
            if module.find_tex_engine() is not None:
                out.append("hiç motor yokken None dönmeli")

        # Gerçek CLI yüzeyi: motorsuz koşum fail-closed; motor varken seçim log'da.
        base_env = dict(os.environ)
        no_engine = subprocess.run(
            [sys.executable, str(script_path)],
            env=dict(base_env, PATH=str(empty)),
            capture_output=True, text=True, timeout=60)
        if no_engine.returncode != 2:
            out.append("motorsuz koşum rc=2 vermeliydi (rc=%d)" % no_engine.returncode)
        if "HATA" not in no_engine.stdout + no_engine.stderr:
            out.append("motorsuz koşum HATA yazmalıydı (sessiz fail-open)")

        with_bin = _stub_bin(td, ["pdflatex", "pdftoppm"])
        logged = subprocess.run(
            [sys.executable, str(script_path), "--only", "P1-a",
             "--out", str(pathlib.Path(td) / "out")],
            env=dict(base_env, PATH=str(with_bin)),
            capture_output=True, text=True, timeout=60)
        if "Araçlar: LaTeX=pdflatex" not in logged.stdout:
            out.append("motor seçimi stdout'a yazılmıyor (Araçlar: LaTeX=...)")
    return out


class TestEngineSelection(unittest.TestCase):
    """Gerçek motor seçimi fail-closed sözleşmesi (bu makineden bağımsız)."""

    def test_real_module_passes_the_guard(self):
        self.assertEqual(
            _engine_violations(rz, HERE / "render_z3_slides.py"), [])


class TestEngineSelectionMutationGuard(unittest.TestCase):
    """Kanıt kalıcı: mutasyon bekçiyi KIRMIZIYA düşürmeli."""

    ENGINE_BLOCK = (
        "    if not engine:\n"
        '        print("HATA: pdflatex/tectonic yok (TeX motoru bulunamadı)", '
        "file=sys.stderr)\n"
        "        return 2")

    def _assert_caught(self, label, mutations):
        with tempfile.TemporaryDirectory(prefix="z3mut_") as td:
            copy = mutation_guard.mutated_copy(
                HERE / "render_z3_slides.py", td, mutations)
            module_name = "rz_mutant_" + label
            try:
                mutant = mutation_guard.load_copy(copy, module_name)
                violations = _engine_violations(mutant, copy)
            finally:
                mutation_guard.unload(module_name)
        self.assertTrue(
            violations,
            "mutasyon KAÇTI (%s) — bekçi sapmayı görmedi" % label)

    def test_reversed_preference_order_is_caught(self):
        self._assert_caught("order", [(
            'for cand in ("pdflatex", "latex", "tectonic"):',
            'for cand in ("tectonic", "latex", "pdflatex"):')])

    def test_removed_pdflatex_preference_is_caught(self):
        self._assert_caught("no_pdflatex", [(
            'for cand in ("pdflatex", "latex", "tectonic"):',
            'for cand in ("latex", "tectonic"):')])

    def test_fail_open_mutation_is_caught(self):
        self._assert_caught("fail_open", [(
            self.ENGINE_BLOCK, self.ENGINE_BLOCK.replace("return 2", "return 0"))])

    def test_selection_log_removal_is_caught(self):
        self._assert_caught("no_log", [(
            "Araçlar: LaTeX={engine}", "Araclar: LaTeX={engine}")])


if __name__ == "__main__":
    unittest.main()
