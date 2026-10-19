#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_github_theme_layers.py — GitHub mirror'ının dark/light katman kapısı.

Kapı: design-system/github/scripts/check_github_tokens.py (iki tema katmanı).

Sözleşmeler (hepsi fail-closed):
  T1 İKİ KATMAN YEŞİL    : commit'li dosyalarla rc=0 ve İKİ `OK — N` satırı
                           (dark 304 + light 258).
  T2 LIGHT DRIFT         : `tokens.light.css`'te tek değer değişirse rc=1 ve
                           drift o token'ı adıyla gösterir.
  T3 TEMA KANITI ZORUNLU : `raw.light.json` `pageState.dataColorMode`
                           "dark" yapılırsa rc=1 — tema kanıtı olmayan light
                           katman kabul edilmez (yanlış temayı light diye
                           yazmak sessiz PASS olamaz).
  T4 ÇAPRAZ KATMAN       : light katman paylaşılan isimlerde dark değerlerini
                           tekrarlarsa rc=1 ("does not differ from the dark
                           layer") — kopya yakalama light değildir.
  T5 RAPOR SENKRONU      : canlı ağaçta `report_theme_diff.py --check` rc=0.

Test izolasyonu: T1-T4 kendi sahte repo ağacını kurar (kapı ROOT'u kendi
konumundan türetir), gerçek çalışma ağacına yazmaz. T5 gerçek ağaçta koşar.

Koşum: `python3 -m unittest _calisma.CIKTI.test_github_theme_layers`
"""
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent.parent
MIRROR = REPO / "design-system" / "github"
GATE = MIRROR / "scripts" / "check_github_tokens.py"
REPORT = MIRROR / "scripts" / "report_theme_diff.py"

DATA_FILES = (
    "raw.json",
    "raw.light.json",
    "tokens.css",
    "tokens.json",
    "tokens.light.css",
    "tokens.light.json",
)


def run_gate(gate_path, cwd, args=()):
    proc = subprocess.run(
        [sys.executable, str(gate_path)] + list(args),
        cwd=str(cwd),
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
    )
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


class ThemeLayerCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="gh-theme-")
        self.addCleanup(self._tmp.cleanup)
        self.root = pathlib.Path(self._tmp.name)
        self.github = self.root / "design-system" / "github"
        (self.github / "scripts").mkdir(parents=True)
        self.gate = self.github / "scripts" / "check_github_tokens.py"
        shutil.copy2(GATE, self.gate)
        for name in DATA_FILES:
            shutil.copy2(MIRROR / name, self.github / name)

    # ── T1 ────────────────────────────────────────────────────────────────
    def test_two_layers_pass_with_two_ok_lines(self):
        rc, out = run_gate(self.gate, self.root)
        self.assertEqual(rc, 0, out)
        self.assertIn("304 GitHub tokens", out)
        self.assertIn("258 GitHub light tokens", out)

    # ── T2 ────────────────────────────────────────────────────────────────
    def test_light_css_value_drift_blocks(self):
        css = self.github / "tokens.light.css"
        text = css.read_text(encoding="utf-8")
        drifted = text.replace(": #", ": #deadbe", 1)
        self.assertNotEqual(text, drifted, "fixture bulunamadı: : #")
        css.write_text(drifted, encoding="utf-8")
        rc, out = run_gate(self.gate, self.root)
        self.assertEqual(rc, 1, out)
        self.assertIn("GITHUB TOKEN DRIFT", out)
        self.assertIn("light layer", out)

    # ── T3 ────────────────────────────────────────────────────────────────
    def test_light_layer_without_light_page_state_blocks(self):
        raw_path = self.github / "raw.light.json"
        raw = json.loads(raw_path.read_text(encoding="utf-8"))
        raw["pageState"]["dataColorMode"] = "dark"
        raw_path.write_text(
            json.dumps(raw, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        rc, out = run_gate(self.gate, self.root, args=("--sync",))
        self.assertEqual(rc, 1, out)
        self.assertIn("dataColorMode", out)

    # ── T4 ────────────────────────────────────────────────────────────────
    def test_light_layer_repeating_dark_values_blocks(self):
        dark = json.loads((self.github / "raw.json").read_text(encoding="utf-8"))
        dark_vars = dark["colors"]["cssVariables"]
        raw_path = self.github / "raw.light.json"
        light = json.loads(raw_path.read_text(encoding="utf-8"))
        light_vars = light["colors"]["cssVariables"]
        copied = 0
        for name, meta in light_vars.items():
            if name in dark_vars:
                meta["value"] = dark_vars[name]["value"]
                copied += 1
        self.assertGreater(copied, 100, "paylaşılan isim beklendi")
        raw_path.write_text(
            json.dumps(light, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        rc, out = run_gate(self.gate, self.root, args=("--sync",))
        self.assertEqual(rc, 1, out)
        self.assertIn("does not differ from the dark layer", out)


class LiveTreeCase(unittest.TestCase):
    # ── T5 ────────────────────────────────────────────────────────────────
    def test_live_gate_and_report_are_in_sync(self):
        rc, out = run_gate(GATE, REPO)
        self.assertEqual(rc, 0, out)
        proc = subprocess.run(
            [sys.executable, str(REPORT), "--check"],
            cwd=str(REPO),
            capture_output=True,
            text=True,
            stdin=subprocess.DEVNULL,
        )
        self.assertEqual(
            proc.returncode, 0, (proc.stdout or "") + (proc.stderr or "")
        )


if __name__ == "__main__":
    unittest.main()
