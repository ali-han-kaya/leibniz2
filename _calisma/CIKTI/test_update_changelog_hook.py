#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_update_changelog_hook.py — update_changelog_hook.sh birim kapısı.

Hook'u izole bir sandbox git repo'sunda koşar: hook'un bir KOPYASI sandbox'a
kopyalanır (SCRIPT_DIR sandbox'a düşer → README/PUBLISH yolları sandbox içinde
kalır) ve yanına bir MOCK gen_changelog.py konur (gerçek gen_changelog'a,
git log'a veya canlı repo'ya bağımlılık yok).

Mock, ortam değişkenleriyle yönlendirilir:
  MOCK_GC_CHECK_EXIT     --check exit kodu (0 = drift yok, 1 = drift var)
  MOCK_GC_UPDATE_EXIT    --update exit kodu (0 = başarı, 1 = hata)
  MOCK_GC_UPDATE_TOUCH   "1" ise --update README/PUBLISH'a satır ekler
                         (gerçek tablo güncellemesini simüle → hook git add
                         tetiklenir)

Kapsanan dallar:
  drift yok        → --check exit 0 → hook dokunmaz, exit 0
  drift var+stage  → --check exit 1 → --update başarılı + tablolar değişti →
                     README/PUBLISH stage edilir, ℹ️ mesajı, exit 0
  gen_changelog hata → --update exit 1 → "HATA: ..." stderr + exit 1 (bloke)

İKİNCİ KATMAN — TestChangelogTwoWriterInvariant: changelog'in "iki yazan"
değişmezini ölçümle sabitler (aşağıya bak).

stdlib unittest — ek bağımlılık yok.
"""
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

CIKTI = pathlib.Path(__file__).resolve().parent
REPO_ROOT = CIKTI.parents[1]
REAL_HOOK = CIKTI / "update_changelog_hook.sh"
REAL_GEN = CIKTI / "gen_changelog.py"
PRECOMMIT_CONFIG = REPO_ROOT / ".pre-commit-config.yaml"
UNIT_TESTS_HOOK = CIKTI / "check_unit_tests_hook.sh"


def norm(text):
    """Karşılaştırma için ASCII indirgeme: Türkçe İ/ı/ş vb. 'i̇'ye
    düşmesin (assertIn'da görünmez kıyas hatası üretmesin)."""
    table = {"İ": "i", "I": "i", "ı": "i", "Ş": "s", "ş": "s",
             "Ğ": "g", "ğ": "g", "Ü": "u", "ü": "u", "Ö": "o", "ö": "o",
             "Ç": "c", "ç": "c", "’": "'"}
    return "".join(table.get(ch, ch) for ch in text).lower()

# Ölçüldü (origin/main): stage eden hook betiği olan YALNIZCA bu ikisi.
DECLARED_WRITERS = ("update-config", "check-changelog-sync")

MOCK_GEN_CHANGELOG = """#!/usr/bin/env python3
# Mock gen_changelog.py — gerçek git log/table mantığı yerine env ile yönlendirilir.
import os
import pathlib
import sys

mode = sys.argv[1] if len(sys.argv) > 1 else ""
if mode == "--check":
    sys.exit(int(os.environ.get("MOCK_GC_CHECK_EXIT", "0")))
if mode == "--update":
    if os.environ.get("MOCK_GC_UPDATE_TOUCH", "0") == "1":
        line = "| 2026-08-23 | fix | (test) mock update | `mockhash` |\\n"
        for rel in ("README.md", "docs/PUBLISH_SCENARIO.md"):
            with open(pathlib.Path(rel), "a", encoding="utf-8") as f:
                f.write(line)
    sys.exit(int(os.environ.get("MOCK_GC_UPDATE_EXIT", "0")))
sys.exit(0)
"""

BASE_TABLE = (
    "# test repo\\n\\n"
    "## Değişiklik Geçmişi\\n\\n"
    "| Tarih | Kategori | Değişiklik | Commit |\\n"
    "|---|---|---|---|\\n"
    "| 2026-08-23 | fix | (test) base | `aaaa1111` |\\n"
)


class UpdateChangelogHookTest(unittest.TestCase):
    """Her testte taze sandbox git repo + hook kopyası + mock gen_changelog."""

    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="changelog_hook_test_"))
        cikti = self.tmp / "_calisma" / "CIKTI"
        cikti.mkdir(parents=True)
        shutil.copy(REAL_HOOK, cikti / "update_changelog_hook.sh")
        (cikti / "gen_changelog.py").write_text(MOCK_GEN_CHANGELOG, encoding="utf-8")
        self._git("init", "-q")
        self._git("config", "user.email", "test@example.com")
        self._git("config", "user.name", "test")
        (self.tmp / "README.md").write_text(BASE_TABLE, encoding="utf-8")
        (self.tmp / "docs").mkdir()
        (self.tmp / "docs" / "PUBLISH_SCENARIO.md").write_text(
            BASE_TABLE, encoding="utf-8")
        self._git("add", "-A")
        self._git("commit", "-q", "-m", "test: base")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _git(self, *args):
        subprocess.run(["git", *args], cwd=str(self.tmp), check=True,
                       capture_output=True, text=True)

    def _run_hook(self, env=None):
        full_env = dict(os.environ)
        if env:
            full_env.update(env)
        return subprocess.run(
            ["bash", str(self.tmp / "_calisma" / "CIKTI" / "update_changelog_hook.sh")],
            cwd=str(self.tmp), env=full_env, capture_output=True, text=True)

    def _porcelain(self):
        return subprocess.run(
            ["git", "status", "--porcelain"], cwd=str(self.tmp),
            capture_output=True, text=True, check=True).stdout

    def test_no_drift_exits_0_without_touching(self):
        # --check exit 0 → hook dokunmadan exit 0; ℹ️ mesajı yok, stage yok.
        r = self._run_hook({"MOCK_GC_CHECK_EXIT": "0"})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("changelog tabloları", r.stdout)
        self.assertEqual(self._porcelain(), "")

    def test_drift_updates_and_stages_both_files(self):
        # --check exit 1 (drift) → --update başarılı + tabloları değiştirdi →
        # README + PUBLISH stage edilir, ℹ️ mesajı basılır, exit 0.
        r = self._run_hook({
            "MOCK_GC_CHECK_EXIT": "1",
            "MOCK_GC_UPDATE_EXIT": "0",
            "MOCK_GC_UPDATE_TOUCH": "1",
        })
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("changelog tabloları git log'a göre güncellendi", r.stdout)
        staged = subprocess.run(
            ["git", "diff", "--cached", "--name-only"], cwd=str(self.tmp),
            capture_output=True, text=True, check=True).stdout.splitlines()
        self.assertIn("README.md", staged)
        self.assertIn("docs/PUBLISH_SCENARIO.md", staged)
        # Mock güncellemesi gerçekten dosyalara işlendi.
        self.assertIn("mockhash", (self.tmp / "README.md").read_text(encoding="utf-8"))
        self.assertIn(
            "mockhash",
            (self.tmp / "docs" / "PUBLISH_SCENARIO.md").read_text(encoding="utf-8"))

    def test_drift_without_changes_stages_nothing(self):
        # Drift var ama --update hiçbir dosyayı değiştirmedi → stage yok,
        # ℹ️ mesajı yok, yine exit 0.
        r = self._run_hook({
            "MOCK_GC_CHECK_EXIT": "1",
            "MOCK_GC_UPDATE_EXIT": "0",
            "MOCK_GC_UPDATE_TOUCH": "0",
        })
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("changelog tabloları", r.stdout)
        self.assertEqual(self._porcelain(), "")

    def test_update_failure_blocks_with_hata(self):
        # --check exit 1 (drift) → --update exit 1 → "HATA: ..." stderr +
        # exit 1 (fail-closed — commit bloke).
        r = self._run_hook({
            "MOCK_GC_CHECK_EXIT": "1",
            "MOCK_GC_UPDATE_EXIT": "1",
        })
        self.assertEqual(r.returncode, 1)
        self.assertIn("HATA: gen_changelog --update başarısız", r.stderr)
        self.assertEqual(self._porcelain(), "")


class TestChangelogTwoWriterInvariant(unittest.TestCase):
    """"İki yazan" değişmezini ölçümle sabitler.

    Arka plan (ölçülmüş, iddia değil): changelog tablosu commit HASH'İYLE
    anahtarlanır ve bir commit'in kendi hash'i ancak o commit OLUŞTUKTAN
    SONRA bilinir. `gen_changelog.py --check` (find_missing_commits) ise
    "tablodaki en yeni satırdan DAHA YENİ commit'ler"i eksik sayar. Bu
    ikisi birleşince yapısal bir olgu çıkar: TABL0, HER commit'ten sonra
    tam olarak BİR commit geridedir — gecikmesi bir commit'in satırını
    yazması, o satır ancak bir sonraki commit'te oluşabileceği için.

    Ölçüm (geçici git repo + GERÇEK gen_changelog.py CLI'si + GERÇEK hook):
      1) hook (yazar) çalışır → eksik satırı ekler, README.md'yi stage eder,
         exit 0 → commit geçer (yazarın commit içi adımı).
      2) o commit'ten sonra `--check` KIRMIZIDIR ve eksik olarak TAM OLARAK
         HEAD'in hash'ini listeler → saf okuma kapısı HER commit'i bloklardı.
      3) bir sonraki commit'te hook aynı onarımı yapar → döngü kapanır,
         gecikme yine tam bir commit'te kalır.

    Sonuç: saf okuma-hook + remedy bu tabloda YAPISAL OLARAK İMKÂNSIZDIR —
    bloklayan satırın hash'i henüz var olmaz. Doğru model İKİ YAZAN'dır:
      (1) commit içinde onarım yazan `check-changelog-sync`,
      (2) gecikmeli (lag-one) kayıt yazan
          `chore(changelog): <hash> satırını tabloya ekle` commit'i.

    Ayrıca beyan↔gerçek eşleşmesi sabitlenir: config'te "TEK yazan" diyen
    satır yanlıştır (ölçüldü: iki hook betiği de `git add` yapıyor) ve
    değişmezin metni üç yerde de (config başlığı, yazar hook'u, kapı
    sarmalayıcısı) yazılı olmalıdır.
    """

    SANDBOX_README = "\n".join([
        "# sandbox",
        "",
        "## Değişiklik Geçmişi",
        "",
        "| Tarih | Kategori | Değişiklik | Commit |",
        "|---|---|---|---|",
        "",
    ])
    SANDBOX_PUBLISH = "\n".join([
        "# sandbox publish",
        "",
        "## Değişiklik Geçmişi",
        "",
        "Changelog tek kaynağı README.md'dir; burada tablo tutulmaz.",
        "",
    ])

    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="changelog_invariant_"))
        self._git("init", "-q")
        self._git("config", "user.email", "test@example.com")
        self._git("config", "user.name", "test")
        (self.tmp / "README.md").write_text(self.SANDBOX_README, encoding="utf-8")
        (self.tmp / "docs").mkdir()
        (self.tmp / "docs" / "PUBLISH_SCENARIO.md").write_text(
            self.SANDBOX_PUBLISH, encoding="utf-8")
        self._commit("feat: tablo baslangici")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _git(self, *args):
        r = subprocess.run(["git", *args], cwd=str(self.tmp), check=False,
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0,
                         "git %s: %s%s" % (" ".join(args), r.stderr, r.stdout))
        return r

    def _commit(self, msg):
        self._git("add", "-A")
        self._git("commit", "-q", "-m", msg)

    def _gen(self, *args):
        return subprocess.run(
            [sys.executable, str(REAL_GEN), *args], cwd=str(self.tmp),
            capture_output=True, text=True)

    # ── davranış kanıtı ────────────────────────────────────────────────
    def _run_real_hook(self):
        """Gerçek hook betiğini sandbox'ta koşur (gerçek gen_changelog ile).

        Hook kendi dizininden (SCRIPT_DIR) gen_changelog.py'i bulur; ikisi de
        sandbox'a kopyalanır → hiçbir yerde canlı repo'ya dokunulmaz.
        """
        cikti = self.tmp / "_calisma" / "CIKTI"
        cikti.mkdir(parents=True, exist_ok=True)
        shutil.copy(REAL_HOOK, cikti / "update_changelog_hook.sh")
        shutil.copy(REAL_GEN, cikti / "gen_changelog.py")
        return subprocess.run(
            ["bash", str(cikti / "update_changelog_hook.sh")],
            cwd=str(self.tmp), capture_output=True, text=True)

    def _head_full(self):
        return self._git("rev-parse", "HEAD").stdout.strip()

    def _assert_missing_is_exactly_head(self, check):
        """Eksik kümesi TAM OLARAK HEAD'dir (kısaltma uzunluğu önemsiz)."""
        missing = self._missing_hashes(check)
        self.assertEqual(len(missing), 1,
                         "gecikme tam BİR commit olmalı: %s" % missing)
        self.assertTrue(
            self._head_full().startswith(missing[0]),
            "eksik satır HEAD olmalı: %s != %s" % (missing[0], self._head_full()))

    def _missing_hashes(self, check):
        return [ln.strip().lstrip("+").strip()
                for ln in check.stdout.splitlines()
                if ln.strip().startswith("+ ")]

    def test_writer_closes_the_loop_and_lag_is_exactly_one_commit(self):
        """Yazar commit içinde onarır; gecikme tam bir commit'te sabit kalır.

        Ölçülen üç eylem tek testte: hook onarımı → stage → commit, sonra
        okuma tarafının TAM HEAD'i eksik saydığı, sonra bir sonraki commit'te
        hook'un kapatıp tekrar bir commit'e indirdiği.
        """
        # 1) Yazar (check-changelog-sync) çalışır: onarır + stage eder, exit 0.
        hook = self._run_real_hook()
        self.assertEqual(hook.returncode, 0, hook.stderr)
        staged = self._git("diff", "--cached", "--name-only").stdout.split()
        self.assertIn("README.md", staged,
                      "yazar hook README tablosunu stage etmeli: " + hook.stdout)

        # 2) O commit geçer → okuma tarafı tam olarak HEAD'i eksik sayar.
        self._commit("feat: yazar tarafindan onarildi")
        check = self._gen("--check")
        self.assertEqual(check.returncode, 1,
                         "gecikme bir commit → okuma tarafı kırmızı: " + check.stdout)
        self._assert_missing_is_exactly_head(check)

        # 3) Bir sonraki commit'te yazar aynı onarımı yapar → döngü kapanır.
        hook = self._run_real_hook()
        self.assertEqual(hook.returncode, 0, hook.stderr)
        self.assertIn("README.md",
                      self._git("diff", "--cached", "--name-only").stdout.split())
        self._commit("feat: ikinci onarim")
        check = self._gen("--check")
        self._assert_missing_is_exactly_head(check)

    # ── beyan ↔ gerçek ──────────────────────────────────────────────────
    def _hook_blocks(self):
        text = PRECOMMIT_CONFIG.read_text(encoding="utf-8")
        blocks = re.split(r"\n      - id: ", text)[1:]
        out = {}
        for b in blocks:
            hook_id = b.split("\n", 1)[0].strip()
            m = re.search(r"^\s+entry:\s*(.+)$", b, re.M)
            out[hook_id] = m.group(1).strip() if m else ""
        return out

    def test_writers_are_exactly_the_two_declared_hooks(self):
        """Stage eden hook betikleri tam olarak beyan edilen iki yazardır.

        KAPSAM NOTU: yazarlık `git add` ile ölçülür — `git update-index`
        gibi başka bir komutla stage eden ya da entry'si shell betiği olmayan
        (python inline) bir yazar bu denetimi görmez. Ölçüm bilinçli olarak
        dar: config'in kendi `entry` betiklerini tarar, hook listesini değil.
        """
        blocks = self._hook_blocks()
        writers = set()
        for hook_id, entry in blocks.items():
            for script in re.findall(r"_calisma/CIKTI/[A-Za-z0-9_.\-]+", entry):
                path = REPO_ROOT / script
                if not path.exists():
                    continue
                body = path.read_text(encoding="utf-8", errors="replace")
                if re.search(r"\bgit add\b", body):
                    writers.add(hook_id)
        self.assertEqual(
            writers, set(DECLARED_WRITERS),
            "yazar kümesi beyanla uyuşmuyor: yeni bir yazan hook eklendiyse "
            "config başlığındaki yazar beyanı da güncellenmeli")

    def _comment_blocks(self, text):
        """Yorum satırlarını boş satırla ayrılmış paragraflara gruplar."""
        blocks, current = [], []
        for line in text.splitlines():
            if line.lstrip().startswith("#"):
                current.append(line)
            elif not line.strip():
                if current:
                    blocks.append("\n".join(current))
                    current = []
            else:
                if current:
                    blocks.append("\n".join(current))
                    current = []
        if current:
            blocks.append("\n".join(current))
        return blocks

    def test_config_header_declares_both_writers(self):
        """Config başlığındaki yazar beyanı 'tek yazan' YANLIŞINI taşımaz.

        Ölçüm: stage eden hook betiği olanlar tam olarak
        (update-config, check-changelog-sync) → beyan paragrafının İKİSİNİ
        de sayması gerekir; satır kaydırması denetimi bozmaz (paragraf
        bazlı). Ayrıca hiçbir yerde "tek yazan" iddiası kalmamalı.
        """
        header = PRECOMMIT_CONFIG.read_text(encoding="utf-8").split("repos:", 1)[0]
        self.assertNotIn("tek yazan", header.lower())
        declaration = [b for b in self._comment_blocks(header) if "yazan" in b.lower()]
        self.assertTrue(declaration, "başlıkta yazar beyanı yok")
        for block in declaration:
            for hook_id in DECLARED_WRITERS:
                self.assertIn(
                    hook_id, block,
                    "yazar beyanı %s hook'unu saymıyor: %s"
                    % (hook_id, block[:120]))

    def test_lag_one_invariant_is_documented_in_all_three_sources(self):
        """Gecikmeli yazma değişmezi üç yerde de açıkça yazılıdır."""
        config_text = PRECOMMIT_CONFIG.read_text(encoding="utf-8")
        for label, text in (
            (".pre-commit-config.yaml", config_text),
            ("update_changelog_hook.sh",
             REAL_HOOK.read_text(encoding="utf-8")),
            ("check_unit_tests_hook.sh",
             UNIT_TESTS_HOOK.read_text(encoding="utf-8")),
        ):
            self.assertIn("gecikmeli", norm(text),
                          "%s: 'gecikmeli' (lag-one) değişmezi yazılı değil" % label)
        # Yazar kimliği iki yazılı olmalı (config + kapı sarmalayıcısı).
        self.assertIn("iki yazan", norm(config_text))
        self.assertIn("iki yazan",
                      norm(UNIT_TESTS_HOOK.read_text(encoding="utf-8")))

    def test_writer_hook_ids_still_point_at_writer_scripts(self):
        """Yazar hook id'leri yeniden adlandırılırsa yazarlık sessizce kaybolmaz."""
        blocks = self._hook_blocks()
        self.assertEqual(blocks.get("update-config"),
                         "bash _calisma/CIKTI/update_config_hook.sh")
        self.assertEqual(blocks.get("check-changelog-sync"),
                         "bash _calisma/CIKTI/update_changelog_hook.sh")


if __name__ == "__main__":
    unittest.main()
