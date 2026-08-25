#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_lake_evidence_smoke.py — LEAN_ISPAT_RAPORU §6.3 kanıtının canlı yeniden üretimi.

§6.3 "lake build kanıtı" bölümündeki çıktı tek bir komutla üretilir:

    cd _calisma/lean_reduct && lake clean && lake build --wfail   # exit 0

Bu smoke testi aynı zinciri HER COMMITTE gerçekten koşarak raporun
kanıdının bayatlamadığını doğrular (fail-closed):

  1. Rapor sabitleri: §6.3'te kanonik komut satırı + "Build completed
     successfully." transcript'i ve v4.14.0 aracı satırı BULUNMALI
     (rapor format drift'i yakalanır).
  2. Tek kaynak: lean-toolchain dosyası vd.LEAN_TOOLCHAIN ile birebir
     aynı olmalı (test_lean_lake.TestK9Combined ile aynı sözleşme).
  3. Canlı üretim: lake clean + lake build --wfail gerçekten koşulur;
     exit 0 değilse veya beklenen derleme çıktısı yoksa commit bloke olur.

Ortam notu: lean/lake kurulu değilse testler DÜRÜSTÇE SKIP edilir —
kapı yalnızca aracın var olduğu ortamda iddia üretir (verify_lean.sh ve
TestFindTool.skipTest deseni). Gerçek lean'siz CI koruması K9-LAKE
(--full) ve verify.yml elan adımındadır.
"""
import os
import pathlib
import shutil
import subprocess
import sys
import unittest

CIKTI = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(CIKTI))

import verify_delivery as vd  # noqa: E402

REDUCT_DIR = CIKTI.parent / "lean_reduct"
REPORT = REDUCT_DIR / "LEAN_ISPAT_RAPORU.md"

CANONICAL_CMD = "$ cd _calisma/lean_reduct && lake clean && lake build --wfail"
BUILD_OK_MARK = "Build completed successfully"


def _tool_available(name):
    """Aracın GERÇEKTEN çalıştırılabilir olduğunu doğrula (find_tool + which)."""
    cmd = vd.find_tool(name)
    return os.path.isfile(cmd) or shutil.which(cmd) is not None


class TestLakeEvidenceSmoke(unittest.TestCase):
    """§6.3 lake build kanıtı: rapor sabitleri + canlı yeniden üretim."""

    @classmethod
    def setUpClass(cls):
        if not _tool_available("lake"):
            raise unittest.SkipTest(
                "lake yok — §6.3 kanıtı bu ortamda yeniden üretilemez "
                "(brew install elan-init)")
        if not _tool_available("lean"):
            raise unittest.SkipTest(
                "lean yok — lake build toolchain indiremez; SKIP")

    def test_report_pins_canonical_transcript(self):
        """§6.3 kanonik komutu + başarı işaretini taşımalı (format kapısı)."""
        text = REPORT.read_text(encoding="utf-8")
        sec = text.split("### 6.3", 1)
        self.assertEqual(len(sec), 2, "§6.3 bölümü kayboldu")
        body = sec[1].split("###", 1)[0]  # sonraki başlığa kadar
        self.assertIn(CANONICAL_CMD, body)
        self.assertIn(BUILD_OK_MARK, body)

    def test_toolchain_single_source(self):
        """lean-toolchain ↔ kod sabiti ↔ rapor üçlüsü senkron olmalı."""
        tc = REDUCT_DIR / "lean-toolchain"
        self.assertEqual(tc.read_text(encoding="utf-8").strip(),
                         vd.LEAN_TOOLCHAIN)
        self.assertIn(vd.LEAN_TOOLCHAIN,
                      REPORT.read_text(encoding="utf-8"))

    def test_reproduce_section_6_3_evidence(self):
        """§6.3'ün kendisini canlı üret: lake clean && lake build --wfail."""
        lake = vd.find_tool("lake")
        for args, timeout in ((["clean"], 120),
                              (["build", "--wfail"], 600)):
            r = subprocess.run([lake, *args], capture_output=True,
                               text=True, timeout=timeout,
                               cwd=str(REDUCT_DIR))
            self.assertEqual(
                r.returncode, 0,
                f"lake {args[-1]} FAILED rc={r.returncode}\n"
                f"{(r.stdout or '')[-800:]}\n{(r.stderr or '')[-800:]}")
            if args[0] == "build":
                out = (r.stdout or "") + (r.stderr or "")
                # §6.3 transcript'iyle aynı başarı işareti:
                self.assertTrue(
                    BUILD_OK_MARK in out or "✔ [" in out,
                    f"beklenen derleme çıktısı yok:\n{out[-800:]}")


if __name__ == "__main__":
    unittest.main()
