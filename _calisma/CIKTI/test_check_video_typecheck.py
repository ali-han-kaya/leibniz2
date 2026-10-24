#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_check_video_typecheck.py — check_video_typecheck.sh regresyon testleri.

Sözleşme (check_dashboard_typecheck.sh ile birebir aynı):
  - node_modules/.bin/tsc veya tsconfig.json yoksa SKIP → exit 0
  - ikisi de varsa `tsc --noEmit` çalışır; tip hatası → exit 1
  - temiz tip → exit 0

Gerçek node kurulumu gerektirmemesi için sahte bir `tsc` sarmalayıcısı ile
sözleşmenin ÜÇ dalı da geçici dizinde ölçülür; ardından canlı repo
sözleşmesi (gerçek script, gerçek çalışma ağacı) de koşulur.
"""

import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
GATE = os.path.join(HERE, "check_video_typecheck.sh")
REPO = os.path.dirname(os.path.dirname(HERE))


def _fake_repo(tmp, tsc_body=None, with_tsc=True, with_tsconfig=True):
    """Sahte repo ağacı: _calisma/CIKTI/<gate> + _calisma/video/{tsconfig,tsc}."""
    cikti = os.path.join(tmp, "_calisma", "CIKTI")
    video = os.path.join(tmp, "_calisma", "video")
    os.makedirs(cikti, exist_ok=True)
    os.makedirs(video, exist_ok=True)
    shutil.copy2(GATE, os.path.join(cikti, "check_video_typecheck.sh"))
    if with_tsconfig:
        with open(os.path.join(video, "tsconfig.json"), "w", encoding="utf-8") as f:
            f.write("{}\n")
    if with_tsc:
        binp = os.path.join(video, "node_modules", ".bin")
        os.makedirs(binp, exist_ok=True)
        tsc = os.path.join(binp, "tsc")
        with open(tsc, "w", encoding="utf-8") as f:
            f.write("#!/usr/bin/env bash\n" + (tsc_body or 'echo "tsc --noEmit"\nexit 0\n'))
        os.chmod(tsc, 0o755)
    return tmp


def _run(root):
    return subprocess.run(
        ["bash", os.path.join(root, "_calisma", "CIKTI", "check_video_typecheck.sh")],
        capture_output=True,
        text=True,
    )


class TestVideoTypecheckGate(unittest.TestCase):
    def test_skip_without_node_modules(self):
        """tsconfig var, node_modules yok → SKIP, exit 0 (kapı blokelemez)."""
        with tempfile.TemporaryDirectory() as tmp:
            root = _fake_repo(tmp, with_tsc=False)
            r = _run(root)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("SKIP", r.stdout)

    def test_skip_without_tsconfig(self):
        """node_modules var, tsconfig yok → SKIP, exit 0."""
        with tempfile.TemporaryDirectory() as tmp:
            root = _fake_repo(tmp, with_tsconfig=False)
            r = _run(root)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("SKIP", r.stdout)

    def test_clean_typecheck_passes(self):
        """tsc temiz → exit 0 ve OK yazılır."""
        with tempfile.TemporaryDirectory() as tmp:
            root = _fake_repo(tmp)
            r = _run(root)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("OK", r.stdout)
            self.assertIn("tsc --noEmit", r.stdout)

    def test_type_error_is_fail_closed(self):
        """tsc tip hatası döndürürse exit 1 — kapı fail-closed."""
        with tempfile.TemporaryDirectory() as tmp:
            root = _fake_repo(
                tmp, tsc_body='echo "src/x.ts(3,5): error TS2322" >&2\nexit 2\n'
            )
            r = _run(root)
            self.assertEqual(r.returncode, 2, r.stdout)
            self.assertNotIn("SKIP", r.stdout)

    def test_gate_does_not_emit(self):
        """READ-ONLY sözleşmesi: kapı --noEmit dışında bir bayrak geçirmez."""
        with tempfile.TemporaryDirectory() as tmp:
            root = _fake_repo(tmp)
            _run(root)
            src = open(GATE, encoding="utf-8").read()
            self.assertIn("--noEmit", src)
            self.assertNotIn("tsconfig.tsbuildinfo", src)

    def test_live_repo_gate(self):
        """Canlı repo sözleşmesi: gerçek script gerçek ağaçta SKIP veya OK verir.

        Kurulum varsa gerçek tip kapısı koşar (fail-closed), yoksa SKIP.
        İkisi de kabul: çıkış kodu 0 olmalı, çökme olmamalı.
        """
        r = subprocess.run(["bash", GATE], capture_output=True, text=True, cwd=REPO)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue("SKIP" in r.stdout or "OK" in r.stdout, r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
