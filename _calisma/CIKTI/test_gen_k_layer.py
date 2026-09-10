#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_gen_k_layer.py — gen_k_layer.py (verify-chain skill K-katmanı üreticisi) testleri.

Skill prosedürü adım 5 (SKILL.md "Adding a new K-layer"): üreticinin
deterministik olduğunu, K numarasını tek kaynaktan (LAYER_LABELS) türettiğini,
tüm anchor'ları bulduğunu, üretilen test şablonunun derlenebilir ve koşulabilir
olduğunu ve --dry-run'ın hiçbir dosyaya dokunmadığını doğrular (fail-closed).
"""
import importlib.util
import os
import pathlib
import py_compile
import subprocess
import sys
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent.parent
GKL = REPO / "skills" / "verify-chain" / "gen_k_layer.py"
VD = REPO / "_calisma" / "CIKTI" / "verify_delivery.py"


def _load_gkl():
    spec = importlib.util.spec_from_file_location("gen_k_layer", GKL)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


gkl = _load_gkl()

# Gerçek verify_delivery.py LAYER_LABELS — K sayısı tek kaynak.
VD_TEXT = VD.read_text(encoding="utf-8")
VD_SKILL = (REPO / "skills" / "verify-chain" / "SKILL.md").read_text(encoding="utf-8")


class TestNextK(unittest.TestCase):
    def test_next_k_is_max_plus_one(self):
        # K21 şu an en büyük → 22.
        self.assertEqual(gkl.next_k(VD_TEXT), 22)

    def test_next_k_deterministic(self):
        self.assertEqual(gkl.next_k(VD_TEXT), gkl.next_k(VD_TEXT))

    def test_next_k_no_labels_raises(self):
        with self.assertRaises(SystemExit):
            gkl.next_k("no labels here")

    def test_next_k_ignores_non_numeric_keys(self):
        self.assertEqual(gkl.next_k('"K1": "a", "foo": 1, "K3": "c"'), 4)


class TestBuildBlocks(unittest.TestCase):
    def test_all_anchors_present_in_real_files(self):
        k = gkl.next_k(VD_TEXT)
        blocks = gkl.build_blocks(k, "check_demo", "Demo katmanı", True)
        for label, (anchor, _block) in blocks.items():
            hay = VD_TEXT if label != "skill" else VD_SKILL
            self.assertIn(anchor, hay,
                          f"{label}: anchor {anchor!r} gerçek dosyada yok")

    def test_deterministic(self):
        b1 = gkl.build_blocks(22, "check_demo", "Demo", True)
        b2 = gkl.build_blocks(22, "check_demo", "Demo", True)
        self.assertEqual(b1, b2)

    def test_flag_dash_conversion(self):
        blocks = gkl.build_blocks(22, "check_demo_layer", "Demo", False)
        # argparse anchor blokta --check-demo-layer (alt çizgi → tire)
        self.assertIn("--check-demo-layer", blocks["argparse"][1])
        # attribute ise alt çizgili kalır
        self.assertIn("lambda a: a.check_demo_layer", blocks["optional"][1])

    def test_core_mode_keeps_only_docstring_labels(self):
        blocks = gkl.build_blocks(22, "check_demo", "Demo", False)
        core = {l: b for l, b in blocks.items() if l in ("docstring", "labels")}
        self.assertEqual(set(core), {"docstring", "labels"})

    def test_skill_row_full_column(self):
        blocks = gkl.build_blocks(22, "check_demo", "Demo", True)
        self.assertIn("| K22 | Demo | `--check-demo` | yes |", blocks["skill"][1])
        blocks = gkl.build_blocks(22, "check_demo", "Demo", False)
        self.assertIn("| K22 | Demo | `--check-demo` | no |", blocks["skill"][1])


class TestTemplate(unittest.TestCase):
    def _tpl_compiles(self, full):
        tpl = gkl.gen_test_template(22, "check_demo", "Demo katmanı", full)
        with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
            f.write(tpl)
            p = f.name
        try:
            py_compile.compile(p, doraise=True)
        finally:
            os.unlink(p)
        return tpl

    def test_template_compiles_full(self):
        self._tpl_compiles(True)

    def test_template_compiles_independent(self):
        self._tpl_compiles(False)

    def test_template_runs_pass(self):
        # Gerçek uçtan uca: üreticinin enjeksiyonu (check_demo iskeleti dahil)
        # + test şablonu BİRLİKTE koşunca PASS vermeli (exit 0, OK).
        k = gkl.next_k(VD_TEXT)
        blocks = gkl.build_blocks(k, "check_demo", "Demo", False)
        new_vd, _new_sk, changes = gkl.apply(blocks, VD_TEXT, VD_SKILL, True)
        self.assertNotIn("!! ", "".join(changes), "anchor atlanmamalı")
        tpl = gkl.gen_test_template(k, "check_demo", "Demo", False)
        with tempfile.TemporaryDirectory() as td:
            pathlib.Path(td, "verify_delivery.py").write_text(
                new_vd, encoding="utf-8")
            pathlib.Path(td, "test_check_demo.py").write_text(
                tpl, encoding="utf-8")
            # verify_delivery'nin yan importları (battery, check_lean_axioms…)
            # CIKTI'dan çözülmeli.
            env = dict(os.environ)
            env["PYTHONPATH"] = str(HERE) + os.pathsep + env.get(
                "PYTHONPATH", "")
            r = subprocess.run(
                [sys.executable, "-m", "unittest", "discover", "-s", td,
                 "-p", "test_check_demo.py"],
                capture_output=True, text=True, env=env, cwd=td)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            # unittest özeti stderr'e yazar.
            self.assertIn("OK", r.stdout + r.stderr)

    def test_injected_vd_compiles(self):
        # Enjeksiyon sonrası verify_delivery.py SÖZDİZİMSEL GEÇERLİ olmalı
        # (anchor'lar ifade bölmezse) ve import edilebilmeli.
        k = gkl.next_k(VD_TEXT)
        blocks = gkl.build_blocks(k, "check_demo", "Demo", False)
        new_vd, _new_sk, changes = gkl.apply(blocks, VD_TEXT, VD_SKILL, True)
        self.assertNotIn("!! ", "".join(changes))
        with tempfile.TemporaryDirectory() as td:
            vd_p = pathlib.Path(td, "verify_delivery.py")
            vd_p.write_text(new_vd, encoding="utf-8")
            # Import: yan modüller CIKTI'dan; import sırasında fonksiyon
            # tanımları değerlendirilir — sözdizimi hatası burada patlar.
            env = dict(os.environ)
            env["PYTHONPATH"] = str(HERE) + os.pathsep + env.get(
                "PYTHONPATH", "")
            r = subprocess.run(
                [sys.executable, "-c", "import verify_delivery; "
                 "assert 'K%d' in verify_delivery.LAYER_LABELS; "
                 "assert verify_delivery._OPTIONAL_LAYERS['K%d']("
                 "type('A', (), {'check_demo': True})())" % (k, k)],
                capture_output=True, text=True, env=env, cwd=td)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_template_full_block_contains_full_test(self):
        tpl_full = self._tpl_compiles(True)
        tpl_no = self._tpl_compiles(False)
        self.assertIn("test_full_enables", tpl_full)
        self.assertNotIn("test_full_enables", tpl_no)

    def test_template_uses_underscore_attribute(self):
        tpl = self._tpl_compiles(False)
        self.assertIn("check_demo=False", tpl)
        self.assertNotIn("check-demo=False", tpl)


class TestApplyAndDryRun(unittest.TestCase):
    def test_dry_run_touches_nothing(self):
        with tempfile.TemporaryDirectory() as td:
            vd_p = pathlib.Path(td, "vd.py")
            sk_p = pathlib.Path(td, "SKILL.md")
            vd_p.write_text(VD_TEXT, encoding="utf-8")
            sk_p.write_text(VD_SKILL, encoding="utf-8")
            before_vd = vd_p.read_bytes()
            before_sk = sk_p.read_bytes()
            r = subprocess.run(
                [sys.executable, str(GKL), "--name", "check_demo",
                 "--label", "Demo", "--full", "--dry-run",
                 "--vd-path", str(vd_p), "--skill-path", str(sk_p)],
                capture_output=True, text=True, cwd=REPO)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertEqual(vd_p.read_bytes(), before_vd, "dry-run vd değiştirdi")
            self.assertEqual(sk_p.read_bytes(), before_sk, "dry-run skill değiştirdi")
            # Test şablonu da üretilmemeli.
            self.assertFalse((REPO / "_calisma" / "CIKTI" / "test_check_demo.py").exists())

    def test_apply_inserts_all_blocks(self):
        k = gkl.next_k(VD_TEXT)
        blocks = gkl.build_blocks(k, "check_demo", "Demo", False)
        new_vd, new_sk, changes = gkl.apply(blocks, VD_TEXT, VD_SKILL, True)
        self.assertNotIn("!! ", "".join(changes), "anchor atlanmamalı")
        self.assertIn(f'"K{k}": "Demo",', new_vd)
        self.assertIn(f'lambda a: a.check_demo,', new_vd)
        self.assertIn("def check_demo(add):", new_vd)
        self.assertIn(f"| K{k} | Demo | `--check-demo` | no |", new_sk)

    def test_missing_anchor_reports_and_skips(self):
        blocks = gkl.build_blocks(22, "check_demo", "Demo", False)
        # Anchor'u bozuk metinle çağır — skill bloğu atlanmalı ama vd işlenmeli.
        new_vd, new_sk, changes = gkl.apply(blocks, VD_TEXT, "no anchor here", True)
        self.assertTrue(any("!! skill" in c for c in changes))
        self.assertIn('"K22": "Demo",', new_vd)


class TestMainGates(unittest.TestCase):
    def test_name_must_start_check(self):
        with self.assertRaises(SystemExit):
            gkl.main(["--name", "demo", "--label", "x", "--dry-run"])

    def test_core_and_full_conflict(self):
        with self.assertRaises(SystemExit):
            gkl.main(["--name", "check_demo", "--label", "x",
                      "--core", "--full", "--dry-run"])


if __name__ == "__main__":
    unittest.main()
