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
import contextlib
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
GATE = ROOT / "_calisma" / "CIKTI" / "check_prettier_format.py"
sys.path.insert(0, str(GATE.parent))

import check_prettier_format as gate  # noqa: E402

# `git commit`, pre-commit hook'una GIT_DIR + GIT_INDEX_FILE export EDER
# (git'in local_repo_env'i — ölçüldü: <common>/.git/worktrees/<wt> ve
# .../worktrees/<wt>/index). Alt süreçler bunu MİRAS ALIR ve
# `git -C <geçici depo>` çağrıları çalıştırıldıkları depoyu değil,
# o değişkenlerin işaret ettiği depoyu kullanır. Test bu yüzden kendi
# git ortamını SIFIRLAR; aksi hâlde batarya yalnız `git commit` içinde
# kırılır — ölçülen ayrım: `pre-commit run` PASS, `git commit` FAIL.
_GIT_IDENTITY = {
    "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",
    "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid",
}


def hermetic_git_env():
    """GIT_* mirası olmayan, yalnız commit kimliği taşıyan ortam."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(_GIT_IDENTITY)
    return env


@contextlib.contextmanager
def scrubbed_git_env():
    """Süreç ortamından TÜM GIT_* değişkenlerini süreli kaldırır."""
    saved = {k: v for k, v in os.environ.items() if k.startswith("GIT_")}
    for k in saved:
        del os.environ[k]
    try:
        yield
    finally:
        for k in [k for k in os.environ if k.startswith("GIT_")]:
            del os.environ[k]
        os.environ.update(saved)


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


class TestDiffModeCollectsBranchSurface(unittest.TestCase):
    """--diff: değişim farkı yüzeyi, yalnız stage değil.

    Ölçülen boşluk: `files:` filtresi yalnız O AN stage'li dosyayı görür.
    Dalın önceki commit'inde bozulmuş ama şu anda stage'lenmemiş bir dosya
    sessizce geçer. --diff yüzeyi genişletir:

        U ∪ B = (şu an stage'li) ∪ (merge-base..HEAD arası değişen)

    Birlestirme iki yönlüdür: stage commit anını, dal farkı commit'leri
    kapsar. Gerçek bir temp git deposunda ölçülür (mock yok).
    """

    @classmethod
    def setUpClass(cls):
        import subprocess as sp
        cls.tmp = tempfile.mkdtemp(prefix="prettier-diff-")
        # GIT_* ortamı TAMAMEN sıfırlanmalı. `git commit`, pre-commit
        # hook'una GIT_DIR + GIT_INDEX_FILE export EDER (ölçüldü:
        # .git/worktrees/<wt> ve .git/worktrees/<wt>/index) ve alt süreçler
        # bunu miras alır; `git -C tmp …` çalıştırıldığı depoyu değil o
        # değişkenlerin işaret ettiği depoyu kullanır. Sızarsa kurulum
        # GERÇEK repo üzerinde koşar: add -A leibniz2'nin bütün ağacını
        # izole indekse yazar, `git diff --cached` 63 dosyalık gerçek yüzeyi
        # döner ve fixture iddiaları (kept.js dışarıda kalmalı) yanlış yere
        # bağlanır. Test bu yüzden hangi ortamda koşarsa koşsun aynı depoyu
        # görmek zorundadır: yalnız commit kimliği taşınır.
        env = hermetic_git_env()

        def run(*args):
            return sp.run(["git", "-C", cls.tmp] + list(args), env=env,
                          capture_output=True, text=True, timeout=30)

        run("init", "-q", "-b", "main")
        # base commit: kept.js base'den sonra HİÇ değişmeyecek (dokunulmamış
        # temiz referans); staged.js ve touched.js temiz başlar.
        for f in ("kept.js", "staged.js", "touched.js"):
            with open(os.path.join(cls.tmp, f), "w") as fh:
                fh.write("const a = 1;\n")
        run("add", "-A")
        run("commit", "-qm", "base")
        # feature commit: (a) boz dosya ekle — commit anında stage OLMAYACAK,
        # (b) touched.js'i değiştir. kept.js bilerek dokunulmaz.
        with open(os.path.join(cls.tmp, "borrowed.js"), "w") as fh:
            fh.write("const b=2\n")
        with open(os.path.join(cls.tmp, "touched.js"), "w") as fh:
            fh.write("const a = 2;\n")
        run("add", "-A")
        run("commit", "-qm", "feature: debt + change")
        # çalışma ağacında SADECE staged.js değişik (borrowed.js dokunulmadı)
        with open(os.path.join(cls.tmp, "staged.js"), "w") as fh:
            fh.write("const a = 3;\n")
        run("add", "staged.js")
        cls.run_git = staticmethod(run)

    def _collect(self, base="HEAD~1"):
        import importlib
        gate = importlib.import_module("check_prettier_format")
        orig = gate.REPO
        gate.REPO = pathlib.Path(self.tmp)
        # gate._git_lines os.environ'u miras alır. Ambient GIT_DIR alt süreci
        # geçici depodan GERÇEK repoya yönlendirir (fark hesabı yanlış yerde
        # koşar, git hatayla boş döner); GIT_INDEX_FILE ise indeksin hangi
        # dosyayı okuyacağını değiştirir. İkisi de temizlenir: git yalnız
        # REPO'yu keşfeder, yani geçici deponun kendi .git'ini.
        try:
            with scrubbed_git_env():
                return set(gate.collect_diff_files(base))
        finally:
            gate.REPO = orig

    def test_diff_mode_includes_files_changed_on_branch(self):
        self.assertIn("borrowed.js", self._collect(),
                      "onceki commit'te degisen dosya --diff yuzeyinde olmali")

    def test_diff_mode_includes_touched_file(self):
        self.assertIn("touched.js", self._collect(),
                      "feature commit'inde degisen dosya kapsamda olmali")

    def test_diff_mode_includes_staged_file(self):
        self.assertIn("staged.js", self._collect(),
                      "su an stage'li dosya da kapsamda olmali")

    def test_diff_mode_excludes_untouched_clean_file(self):
        self.assertNotIn("kept.js", self._collect(),
                         "bu dosya base'den beri ayni -> kapsam disi")

    def test_diff_mode_is_deterministic(self):
        self.assertEqual(self._collect(), self._collect(),
                         "iki tarama ayni sonucu vermeli")

    def test_diff_mode_on_empty_diff_returns_empty(self):
        # Index'i boşalt: stage tarafı katkısız kalsın, yalnız dal farkı
        # (HEAD...HEAD = boş) ölçülsün.
        self.run_git("reset", "-q")
        try:
            self.assertEqual(self._collect(base="HEAD"), set(),
                             "HEAD..HEAD farki bos olmali")
        finally:
            self.run_git("add", "staged.js")

    def test_diff_mode_respects_prettierignore(self):
        # Muaf desen kapsam dışı kalmalı (kod/veri ayrımı bozulmaz).
        ignore = os.path.join(self.tmp, ".prettierignore")
        with open(ignore, "w") as fh:
            fh.write("borrowed.js\n")
        try:
            self.assertNotIn("borrowed.js", self._collect())
        finally:
            os.remove(ignore)

    def test_collect_is_immune_to_ambient_git_env(self):
        """Ölçülen kırılma: `git commit` hook ortamı GIT_DIR/GIT_INDEX_FILE
        export eder; bunlar miras alınırsa fark hesabı GERÇEK repo üzerinde
        koşar ve temp deponun yüzeyi hiç görünmez. Kanıt: ambient GIT_DIR'yi
        KASITLI olarak geçersiz bir değere ayarla — temp deponun yüzeyi yine
        de doğru dönmeli. Miras alınan kod burada kırılır, temizlenen kod
        geçer.
        """
        ambient = {
            "GIT_DIR": os.path.join(self.tmp, "..", "yok-boyle-bir-depo"),
            "GIT_INDEX_FILE": os.path.join(self.tmp, ".yanlis-indeks"),
        }
        saved = {k: os.environ.get(k) for k in ambient}
        os.environ.update(ambient)
        try:
            got = self._collect()
        finally:
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
        self.assertIn("borrowed.js", got,
                      "ambient GIT_DIR temp deponun yuzeyini gostermemeli")
        self.assertIn("staged.js", got, "stage'li dosya da gorunmeli")
        self.assertNotIn("kept.js", got, "dokunulmamis temiz dosya disarida")

    def test_hook_is_diff_aware_and_always_runs(self):
        cfg = (ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8")
        block = cfg.split("- id: check-prettier-format\n", 1)[1]
        block = block.split("\n      - id:", 1)[0]
        self.assertIn("--diff", block, "ana hook --diff kullanmali")
        self.assertIn("always_run: true", block, "hook her commit'te kosmali")
        self.assertIn("pass_filenames: false", block,
                      "dosya listesi pre-commit'ten degil kapidan gelmeli")

    def test_diff_mode_exists_in_gate_source(self):
        src = GATE.read_text(encoding="utf-8")
        self.assertIn("def collect_diff_files", src)
        self.assertIn("--diff", src)


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