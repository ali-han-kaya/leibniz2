#!/usr/bin/env python3
import hashlib
import importlib.util
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "_calisma" / "CIKTI" / "render_z3_slides.py"


def _load_render_module():
    """render_z3_slides.py'yi dosya yolundan yükle.

    __import__("render_z3_slides") yalnızca CWD = _calisma/CIKTI iken
    çözülür; pre-commit hook'u (entry: python3 -m unittest ...) repo kökünden
    çalıştırır ve CIKTI sys.path'te DEĞİLDİR → clean checkout'ta
    ModuleNotFoundError. Path-based import CWD'den bağımsızdır.
    """
    spec = importlib.util.spec_from_file_location("render_z3_slides", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestZ3SlideReproducibility(unittest.TestCase):
    def test_same_inputs_produce_identical_png_hashes(self):
        if not shutil.which("tectonic"):
            self.skipTest("tectonic yok")
        converter = next((x for x in ("convert", "magick", "pdftoppm", "sips")
                          if shutil.which(x)), None)
        if not converter:
            self.skipTest("PDF→PNG aracı yok")
        with tempfile.TemporaryDirectory(prefix="z3-repro-") as td:
            first, second = Path(td, "first"), Path(td, "second")
            for out in (first, second):
                result = subprocess.run(
                    ["python3", str(SCRIPT), "--out", str(out), "--with-label"],
                    cwd=str(ROOT), capture_output=True, text=True, timeout=600,
                )
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            def hashes(directory):
                return {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                        for p in sorted(directory.glob("*.png"))}
            left, right = hashes(first), hashes(second)
            expected = {f"{t[0]}.png" for t in _load_render_module().THEOREMS}
            self.assertEqual(set(left), expected)
            self.assertEqual(left, right)


if __name__ == "__main__":
    unittest.main()
