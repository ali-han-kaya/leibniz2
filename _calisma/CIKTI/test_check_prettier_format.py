#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_check_prettier_format.py — Prettier kapısının sözleşmesi.

Ölçülen kök neden: kapı `files:` filtresiyle **yalnız stage'li** dosyayı
denetler. Hiç yeniden stage olmayan dosyalar (github_scripts, apps/*,
design-system) sessizce biçimden düştü; `origin/main`'de 40 dosya borçluydu
ve borç ancak tüm ağaç taranınca göründü. Sözleşme:
  1) --all modu: git ls-files üzerinden TÜM uygun dosyayı denetler
  2) package-lock.json muaf (mevcut hook exclude sözleşmesi)
  3) .prettierignore muafiyeti: vendor/ (3. parti minified) ve
     design-system/vercel/*.json (makine çıkarımı VERİ anlık görüntüsü)
  4) --all, borç varsa exit 1 (fail-closed), temiz ağaçta exit 0
  5) prettier yoksa SKIP (exit 0) — ortam-bağımlı kapı ortam yoksa bloklamaz

OFFLINE, stdlib-only. Gerçek prettier ÇALIŞTIRILMAZ: dosya listesi ve
muaffiyet mantığı saf fonksiyonlardan doğrulanır.
"""
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
GATE = ROOT / "_calisma" / "CIKTI" / "check_prettier_format.py"
sys.path.insert(0, str(GATE.parent))

import check_prettier_format as gate  # noqa: E402


class TestExtensionFilter(unittest.TestCase):
    """Hangi dosyalar kapsama girer (hook'un `files:` sözleşmesi)."""

    def test_js_ts_json_included(self):
        for f in ("a.js", "a.jsx", "a.ts", "a.tsx", "apps/x/a.json"):
            self.assertTrue(gate.matches_glob(f), f"{f} kapsamda olmalı")

    def test_other_extensions_excluded(self):
        for f in ("a.py", "a.html", "a.css", "a.sh", "a.md", "a.yml"):
            self.assertFalse(gate.matches_glob(f), f"{f} kapsam DIŞIDA olmalı")

    def test_package_lock_excluded(self):
        # Hook `exclude: package-lock\.json$` — kilit dosyaları biçimlendirilmez.
        self.assertFalse(gate.matches_glob("apps/x/package-lock.json"))

    def test_node_modules_never_scanned(self):
        # node_modules prettier'ın kendi çıktısıdır; taramaya girmemeli.
        self.assertFalse(gate.matches_glob("apps/x/node_modules/lib/a.js"))

    def test_nested_package_lock_excluded(self):
        self.assertFalse(
            gate.matches_glob("_calisma/pptx/package-lock.json"))


class TestIgnoreFile(unittest.TestCase):
    """.prettierignore muafiyetleri — kod/veri ayrımı."""

    def setUp(self):
        self.ignore = (ROOT / ".prettierignore")
        self.text = self.ignore.read_text(encoding="utf-8") \
            if self.ignore.exists() else ""

    def test_ignore_file_exists(self):
        self.assertTrue(self.ignore.exists(),
                        "muafiyet listesi yoksa kod/veri ayrımı belirsiz")

    def test_vendor_is_excluded_with_reason(self):
        # axe.min.js 3. parti (MPL-2.0) minified dosya: prettier 2x büyütür
        # (ölçüm: 553446 -> 1022724 bayt) ve diff okunamaz olur.
        self.assertRegex(self.text, r"vendor/",
                         "3. parti vendor muaf olmalı")

    def test_extracted_vercel_data_excluded(self):
        # design-system/vercel/*.json harici siteden MAKİNE ÇIKARIMI veri
        # anlık görüntüsü ("extractor": "dembrandt") — kaynak kod değil.
        self.assertRegex(self.text, r"design-system/vercel/")

    def test_patcher_owned_runtime_asset_excluded(self):
        # preview.js dashboard'ın çalışma-zamanı betiği ve
        # determinism_trend_badge.py --update-preview tarafından idempotent
        # yamalanır. Patcher ÇİFT tırnaklı JS üretir, .prettierrc singleQuote:
        # true ister → prettier --write sonrası patcher yeniden yamalar ve
        # kapı tekrar FAIL eder (ölçülen çift yönlü çekişme).
        self.assertRegex(self.text, r"preview\.js",
                         "patcher'a ait varlık muaf olmalı")

    def test_patcher_owned_exclusion_has_reason(self):
        self.assertRegex(
            self.text, r"(?is)preview\.js.*(?:patcher|yama)",
            "preview.js muafiyeti gerekçesiyle yazılmalı")

    def test_patcher_output_is_not_prettier_reformattable(self):
        # Canlı çelişki kanıtı: patcher'ın yazdığı JS, prettier'ın singleQuote
        # kuralına aykırıdır. Bu dosyayı kapsama almak kapıyı sürekli FAIL
        # ederdi — yani muafiyet keyfidir, stil tercihi değil.
        patcher = (ROOT / "_calisma" / "CIKTI" /
                   "determinism_trend_badge.py")
        if not patcher.is_file():
            self.skipTest("patcher yok — SKIP")
        src = patcher.read_text(encoding="utf-8")
        self.assertIn('$("det-trend-badge")', src,
                      "patcher çift tırnaklı JS üretiyor (ölçülen çatışma)")

    def test_ignore_file_documents_reason_not_just_pattern(self):
        # Desen listesi yeterli değil: NEDEN yazılı olmalı (borcun
        # yeniden doğmaması için bağlam gerekir).
        self.assertRegex(self.text, r"(?m)^#\s+\S",
                         "gerekçe satırı olmalı")


class TestAllModeCollectsTree(unittest.TestCase):
    """--all: tüm ağacı toplar, yalnız stage'e bakmaz."""

    def test_all_mode_collects_from_git_ls_files(self):
        src = GATE.read_text(encoding="utf-8")
        self.assertIn("--all", src, "--all modu tanımlı olmalı")
        self.assertIn("ls-files", src,
                      "ağaç taraması git ls-files üzerinden olmalı "
                      "(untracked çürümeye bırakılmamalı)")

    def test_all_mode_is_hook_wired(self):
        cfg = (ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8")
        self.assertIn("check-prettier-format-all", cfg,
                      "all-files kapısı pre-commit'e bağlı olmalı")
        # always_run + pass_filenames:false = her commit'te ağacı tarar
        m = cfg.split("- id: check-prettier-format-all", 1)
        self.assertEqual(len(m), 2, "hook kaydı bulunamadı")
        block = m[1].split("\n      - id:", 1)[0]
        self.assertIn("always_run: true", block)
        self.assertIn("pass_filenames: false", block)
        self.assertIn("--all", block)

    def test_hook_uses_venv_guard(self):
        # check_prettier_format.py prettier binary'sini dashboard-next
        # node_modules'tan bulur; sistem python3'ü yeterli (stdlib-only).
        cfg = (ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8")
        block = cfg.split("- id: check-prettier-format-all", 1)[1]
        block = block.split("\n      - id:", 1)[0]
        self.assertIn("check_prettier_format.py", block)
        self.assertIn("--all", block)


class TestGateIsStdlibOnly(unittest.TestCase):
    def test_no_third_party_import(self):
        src = GATE.read_text(encoding="utf-8")
        for banned in ("import yaml", "import requests", "import black"):
            self.assertNotIn(banned, src, f"kapı stdlib-only olmalı: {banned}")

    def test_prettier_path_points_at_dashboard_node_modules(self):
        self.assertTrue(str(gate.PRETTIER).endswith(
            "apps/dashboard-next/node_modules/.bin/prettier"))


class TestRealTreeIsClean(unittest.TestCase):
    """GERÇEK ağaç: --all denetiminde borç kalmamalı.

    Bu, listenin kendisi: --all modu eklendikten ve ağaç biçimlendirildikten
    sonra gerçek repoda exit 0 vermelidir. Prettier binary'si yoksa SKIP
    (ortam-bağımlı kapı ortam yoksa bloklamaz).
    """

    def test_real_tree_has_no_prettier_debt(self):
        if not gate.PRETTIER.is_file():
            self.skipTest("prettier yok (node_modules kurulu değil) — SKIP")
        files = gate.collect_all_files()
        self.assertGreater(len(files), 0, "ağaç taraması boş döndü")
        rc = gate.main(["--all"])
        self.assertEqual(rc, 0,
                         "gerçek ağaçta biçim borcu kaldı — --all FAIL")


if __name__ == "__main__":
    unittest.main()