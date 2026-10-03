#!/usr/bin/env python3
"""test_precommit_hooks_source.py — hook panelinin veri kaynagi kapisi.

Dashboard'da "Pre-commit ... ⏳ hook verisi bekleniyor…" paneli takili kaliyordu.
Kok neden IKI kaynak arasindaki asimetri:

  * `_refresh_precommit_hooks_bg` (preview_server.py) `result.stderr or
    result.stdout` diyor — dogru.
  * `_finalize_run` ise YALNIZ `stderr`'a bakiyordu; fallback'i de yalnizca
    `logs/PRECOMMIT_RAPORU.json` sidecar'ini aramakla sinirliydi.

Olcum (2026-10-02, bu degerin kendi pre-commit ciktisi):

  * `pre_commit run --all-files --show-diff-on-failure` -> 52 hook satiri
    **stdout**'ta, **stderr 0 bayt** (hook'lar basarisiz olsa bile).
  *Uc sidecar adayinin hicbiri dosyada degil.
  => `parse(stderr)` = 0 hook, `parse(stdout)` = 52 hook. Panel takili kalirdi.

Bu test, kaynagin ikisini de okudugunu ve gercek pre-commit bicimini
ayristirdigini sabitler. OFFLINE, stdlib-only.
"""
import importlib.util
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
SERVER = ROOT / "_calisma" / "CIKTI" / "preview_server.py"
PREVIEW_JS = ROOT / "_calisma" / "CIKTI" / "preview.js"


def load_server():
    spec = importlib.util.spec_from_file_location("pvs_under_test", SERVER)
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except SystemExit:
        pass
    return mod


class TestHookSourceInFinalize(unittest.TestCase):
    """_finalize_run hook'lari stdout'tan da okumali."""

    @classmethod
    def setUpClass(cls):
        cls.src = SERVER.read_text(encoding="utf-8")

    def test_finalize_reads_stdout_fallback(self):
        self.assertIn(
            "_parse_precommit_hooks(stderr) or _parse_precommit_hooks(stdout)",
            self.src,
            "_finalize_run stdout'a bakmiyor — panel stdout'ta bekliyor",
        )

    def test_background_path_and_finalize_use_the_same_sources(self):
        # Asimetrinin kendisi regresyona donusmesin: iki yol ayni kaynagi
        # gostermeli. Ikisi de once stderr, sonra stdout.
        self.assertRegex(self.src, r"result\.stderr or result\.stdout")
        self.assertRegex(self.src,
                         r"_parse_precommit_hooks\(stderr\) or "
                         r"_parse_precommit_hooks\(stdout\)")

    def test_sidecar_fallback_is_still_present(self):
        # Sidecar yolu silinmemeli; stdout eklendi, ikisi birbirinin yerine
        # gecmemeli (stderr doluysa sidecar hic aranmamaliydi — degil).
        self.assertIn("PRECOMMIT_RAPORU.json", self.src)


class TestHookParserRealOutput(unittest.TestCase):
    """Gercek pre-commit bicimi ayristirilabilmeli."""

    @classmethod
    def setUpClass(cls):
        cls.mod = load_server()

    def test_parses_passed_and_failed_hooks(self):
        blob = ("Verify Stoic-Hume V5 delivery (fail-closed)"
                "....................Passed\n"
                "Budget shield............................Failed\n")
        hooks = self.mod._parse_precommit_hooks(blob)
        self.assertEqual(len(hooks), 2)
        self.assertEqual(hooks[0]["status"], "Passed")
        self.assertEqual(hooks[1]["status"], "Failed")

    def test_parses_hook_ids_with_colons_and_parens(self):
        # Gercek isimler'de iki nokta ust uste ve parantez var; gözdesi
        # olmayan bir desen burada sessizce 0 dondurur.
        name = "Sync config from package content (gen_config.py)"
        hooks = self.mod._parse_precommit_hooks(name + "....Passed\n")
        self.assertEqual(len(hooks), 1)
        self.assertEqual(hooks[0]["name"], name)

    def test_returns_none_for_empty_output(self):
        self.assertIsNone(self.mod._parse_precommit_hooks(""))
        self.assertIsNone(self.mod._parse_precommit_hooks(None))

    def test_panel_text_is_the_stuck_placeholder(self):
        # Panelin takili kaldigi metin: duzeltilmemis hali bu yaziyi
        # gosteriyordu.
        self.assertIn("hook verisi bekleniyor",
                      PREVIEW_JS.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
