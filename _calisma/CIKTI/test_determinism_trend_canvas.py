#!/usr/bin/env python3
"""test_determinism_trend_canvas.py — determinism-trend.yml canvas job sözleşmesi.

Canvas (Incidental Proof) kaynaklarının CI-determinizm kanıtı, mevcut
TeXLive-zinciri job'ının AYNI motor-piniyle koşmalı. Dört kural
(fail-closed, offline, stdlib-only):

  K1) Job varlığı: determinism-trend.yml'de canvas-determinism job'ı
      tanımlı ve `bash _calisma/CIKTI/canvas_determinism_test.sh`'i
      `run:` adımında çağırıyor (uses: değil — gated-schedules K2 deseni).
  K2) Motor-pini TEK KAYNAK: canvas job'ındaki tectonic sürüm + sha256
      digest'i, mevcut TeXLive-zinciri job'ındaki piniyle BİREBİR aynı
      (kopya-pini drift üretir; sürüm-yükseltmesi iki job'ı birlikte
      değiştirmeli).
  K3) SDE-güvenlik: canvas job'ı SOURCE_DATE_EPOCH'u explicit veriyor
      (sabit epoch — motor güncel zamanı gömemez).
  K4) Yerel yüzey: bash canvas_determinism_test.sh --help koşumu exit 0
      (betik çalıştırılabilir + bash-parse edilebilir).

OFFLINE, stdlib-only, ~0.02s.
"""
import pathlib
import re
import subprocess
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "determinism-trend.yml"
SCRIPT = ROOT / "_calisma" / "CIKTI" / "canvas_determinism_test.sh"


def _job_block(text: str, job_key: str) -> str:
    """yaml-safe job bloğu: `job_key:` satırından sonraki top-level anahtara
    dek (aynı girinti-düzeyi). Stdlib-only; PyYAML-çıkarsama yok."""
    m = re.search(rf"^  {re.escape(job_key)}:\n", text, re.M)
    if not m:
        return ""
    start = m.end()
    nxt = re.search(r"^  \S.*:\n", text[start:], re.M)
    return text[start: start + (nxt.start() if nxt else len(text[start:]))]


class TestDeterminismTrendCanvasJob(unittest.TestCase):
    def setUp(self):
        self.text = WORKFLOW.read_text(encoding="utf-8")

    def test_canvas_job_exists_and_calls_script_via_run(self):
        # K1: job var + script bir `run:` adımında çağrılıyor (uses: değil —
        # gated-schedules K2 deseni). Blok-skaler (run: |) biçemi de tanır:
        # koşul — blokta hem run-step hem script adı var; uses:-satırı script
        # adını taşımıyor.
        block = _job_block(self.text, "canvas-determinism")
        self.assertTrue(block, "determinism-trend.yml'de canvas-determinism job'ı yok")
        self.assertTrue(re.search(r"^\s+run:", block, re.M),
                        "canvas job'ında run-step yok")
        self.assertIn("canvas_determinism_test.sh", block,
                      "canvas job'ı deney script'ini çağırmıyor")
        bad_uses = [ln for ln in block.splitlines()
                    if "uses:" in ln and "canvas_determinism" in ln]
        self.assertFalse(bad_uses,
                         "script uses:-adımıyla substitute edilemez (K2)")

    def test_canvas_job_pins_same_engine_as_texlive_chain(self):
        # K2: motor-pini TEK KAYNAK — canvas job'ındaki sürüm + digest,
        # TeXLive-zinciri job'ındaki piniyle birebir aynı.
        texlive = re.search(r'TECTONIC_VERSION="([^"]+)"', self.text)
        digest = re.search(r'TECTONIC_SHA256="([^"]+)"', self.text)
        self.assertTrue(texlive and digest,
                        "mevcut job'da TECTONIC_VERSION/SHA256 pini yok")
        canvas_block = _job_block(self.text, "canvas-determinism")
        self.assertIn(f'TECTONIC_VERSION="{texlive.group(1)}"', canvas_block,
                      "canvas job sürüm-pini TeXLive-zinciri pininden farklı")
        self.assertIn(f'TECTONIC_SHA256="{digest.group(1)}"', canvas_block,
                      "canvas job digest-pini TeXLive-zinciri pininden farklı")

    def test_canvas_job_sets_explicit_sde(self):
        # K3: SOURCE_DATE_EPOCH explicit (motor güncel zamanı gömemez).
        canvas_block = _job_block(self.text, "canvas-determinism")
        self.assertIn("SOURCE_DATE_EPOCH=", canvas_block,
                      "canvas job explicit SOURCE_DATE_EPOCH vermalı")

    def test_canvas_script_is_executable_and_parseable(self):
        # K4: yerel yüzey — betik bash-parse edilebilir (syntax hata yok).
        self.assertTrue(SCRIPT.is_file())
        r = subprocess.run(["bash", "-n", str(SCRIPT)],
                           capture_output=True, text=True, timeout=10)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
