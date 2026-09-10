#!/usr/bin/env python3
"""test_texlive_determinism_hook.py — texlive-determinism hook davranış kapısı.

texlive_determinism_hook.sh (pre-commit) SKIP/fail-closed sözleşmesini
deterministik doğrular:

  1) tectonic yoksa → SKIP (exit 0) — kapı aracın var olduğu ortamda iddia
     üretir (check-lake-evidence deseni).
  2) TeXLive pdflatex yoksa → SKIP (exit 0) — TEXLIVE_BIN env'i veya
     /usr/local/texlive keşfi boşsa deney koşulmaz.
  3) Her iki araç da varsa → texlive_determinism_test.sh gerçekten KOŞAR ve
     exit kodu aynen yayılır (fail-closed): stub tectonic PDF üretemezse
     deney exit 1 → hook da exit 1 (commit bloke).

Stub araçlarla (fake tectonic/pdflatex) çalışır — gerçek TeXLive derlemesi
yapmaz; yalnızca hook'un araç keşfi + skip + exit yayma mantığını sabitler.
Gerçek byte-determinism iddiası texlive_determinism_test.sh'in kendisindedir
(TeXLive kurulu ortamda hook onu koşar).

stdlib-only, OFFLINE.
"""
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
CIKTI = ROOT / "_calisma" / "CIKTI"
HOOK = CIKTI / "texlive_determinism_hook.sh"

EMPTY_PATH = "/usr/bin:/bin"  # tectonic/TeXLive içermeyen minimal PATH


def _write_stub(path: Path, body: str) -> Path:
    path.write_text(body, encoding="utf-8")
    path.chmod(0o755)
    return path


class TestTexliveDeterminismHook(unittest.TestCase):
    def _run(self, texlive_bin=None, path=EMPTY_PATH, tectonic_bin=None):
        env = dict(os.environ)
        if texlive_bin is not None:
            env["TEXLIVE_BIN"] = texlive_bin
        if tectonic_bin is not None:
            env["TECTONIC_BIN"] = tectonic_bin
        env["PATH"] = path
        return subprocess.run(["bash", str(HOOK)],
                              capture_output=True, text=True, env=env)

    def test_skip_when_tectonic_missing(self):
        # tectonic PATH'te ve TECTONIC_BIN'de yok → SKIP, exit 0.
        r = self._run()
        self.assertEqual(r.returncode, 0,
                         f"tectonic'siz ortam bloke etmemeli:\n{r.stdout}\n{r.stderr}")
        self.assertIn("SKIP", r.stdout + r.stderr)

    def test_skip_when_texlive_missing(self):
        # tectonic var (stub), TeXLive yok (TEXLIVE_BIN geçersiz) → SKIP, exit 0.
        with tempfile.TemporaryDirectory() as td:
            bin_dir = Path(td) / "bin"
            bin_dir.mkdir()
            _write_stub(bin_dir / "tectonic", "#!/bin/sh\nexit 0\n")
            r = self._run(texlive_bin="/nonexistent-texlive",
                          path=f"{bin_dir}:{EMPTY_PATH}")
        self.assertEqual(r.returncode, 0,
                         f"TeXLive'siz ortam bloke etmemeli:\n{r.stdout}\n{r.stderr}")
        self.assertIn("SKIP", r.stdout + r.stderr)

    def test_skip_when_texlive_discovery_empty(self):
        # TEXLIVE_BIN env'i yok ve /usr/local/texlive keşfi boşsa → SKIP.
        # Bu makinede gerçek TeXLive varsa (TEXLIVE_BIN boşken keşfedilir)
        # test SKIP yerine deneyi koşar — o yüzden TEXLIVE_BIN'i boş bırakıp
        # yalnızca tectonic stub'ı veririz; keşif dizinini de stub'layamayız,
        # dolayısıyla bu test yalnızca makinede TeXLive yoksa anlamlıdır.
        # (Gerçek TeXLive'lı makinelerde 3. test fail-closed yaymayı zaten
        #  stub'larla kanıtlar — bu test ortama bağımlıdır, atlanmaz.)
        import shutil
        if shutil.which("pdflatex") or any(
                Path("/usr/local/texlive").glob("*/bin/*/pdflatex")):
            self.skipTest("makinede TeXLive kurulu — keşif boş değil")
        with tempfile.TemporaryDirectory() as td:
            bin_dir = Path(td) / "bin"
            bin_dir.mkdir()
            _write_stub(bin_dir / "tectonic", "#!/bin/sh\nexit 0\n")
            r = self._run(path=f"{bin_dir}:{EMPTY_PATH}")
        self.assertEqual(r.returncode, 0)
        self.assertIn("SKIP", r.stdout + r.stderr)

    def test_fail_closed_when_tools_present(self):
        # Araçlar var: stub tectonic (PATH) + stub pdflatex (TEXLIVE_BIN).
        # Deney gerçekten koşar; stub tectonic PDF üretemez → deney exit 1 →
        # hook aynen yayar (fail-closed: commit bloke).
        with tempfile.TemporaryDirectory() as td:
            bin_dir = Path(td) / "bin"
            bin_dir.mkdir()
            _write_stub(bin_dir / "tectonic", "#!/bin/sh\nexit 1\n")
            tl = Path(td) / "texlive"
            tl.mkdir()
            _write_stub(tl / "pdflatex", "#!/bin/sh\nexit 0\n")
            r = self._run(texlive_bin=str(tl),
                          path=f"{bin_dir}:{EMPTY_PATH}")
        self.assertEqual(r.returncode, 1,
                         "araçlar varken deney exit'i yayılmalı (fail-closed)")
        self.assertIn("tectonic PDF üretemedi", r.stdout + r.stderr)

    def test_invokes_test_script_when_tools_present(self):
        # Deney koştuğunun kanıtı: test script'in başlık çıktısı görünür.
        with tempfile.TemporaryDirectory() as td:
            bin_dir = Path(td) / "bin"
            bin_dir.mkdir()
            _write_stub(bin_dir / "tectonic", "#!/bin/sh\nexit 1\n")
            tl = Path(td) / "texlive"
            tl.mkdir()
            _write_stub(tl / "pdflatex", "#!/bin/sh\nexit 0\n")
            r = self._run(texlive_bin=str(tl),
                          path=f"{bin_dir}:{EMPTY_PATH}")
        self.assertIn("TeXLive+SDE PDF determinism deneyi",
                      r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
