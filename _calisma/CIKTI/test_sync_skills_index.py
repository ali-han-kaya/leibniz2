#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_sync_skills_index.py — sync_skills_index.py kontrat kapısı.

Amaç: README "## Skills" tablosunu `skills/*/SKILL.md` frontmatter'ından
ÜRETEN yazarı (auto-sync) ve onun fail-rolled `--check` yüzeyini ölçümle
sabitler. Testler iki katmanlıdır:

  1) SAF (sandbox): geçici bir skills/ + README üretilir; araç hem içeride
     (import) hem CLI (subprocess) olarak koşar. Canlı repo'ya dokunulmaz.
  2) CANLI: gerçek repo'nun README'si drift'siz olmalıdır (`check() == 0`) —
     bu, CI'ın full-discover adımında fail-closed çalışan yüzeydir.

Kritik tasarım kuralı (kayıp yok): Yazar, frontmatter'dan TÜRETİLEN
açıklamayı mevcut satırların üzerine YAZMAZ. README'deki insan eliyle
kurulmuş Türkçe özetler ve satır sırası korunur; yalnızca:
  - skills/'e eklenen skill'ler tabloya eklenir (alfabetik, sona),
  - skills/'ten silinen skill satırları düşer,
  - blok işaretçileri (skills-index:start/end) yoksa eklenir.
Bu, gen_changelog.py --update ile aynı desendir ("mevcut insan özetleri
korunur").

stdlib unittest — ek bağımlılık yok (PyYAML yok: frontmatter elle ayrıştırılır).
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
sys.path.insert(0, str(CIKTI))

import sync_skills_index as sync  # noqa: E402

REAL_REPO_ROOT = CIKTI.parents[1]


def fm(name, description, extra=""):
    return ("---\n"
            "name: %s\n"
            "description: \"%s\"\n"
            "%s"
            "---\n\n"
            "# %s\n\nGövde.\n") % (name, description, extra, name)


def block(*rows):
    head = sync.START_MARKER + "\n" + sync.TABLE_HEADER + "\n" + sync.TABLE_SEP + "\n"
    body = "".join("| `skills/%s/SKILL.md` | %s |\n" % (n, d) for n, d in rows)
    return head + body + sync.END_MARKER + "\n"


class SandboxCase(unittest.TestCase):
    """Her testte taze geçici skills/ + README."""

    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="sync_skills_"))
        (self.tmp / "skills").mkdir()
        self.skills = self.tmp / "skills"
        self.readme = self.tmp / "README.md"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def add_skill(self, name, description, extra=""):
        d = self.skills / name
        d.mkdir(parents=True, exist_ok=True)
        (d / "SKILL.md").write_text(fm(name, description, extra), encoding="utf-8")
        return d

    def write_readme(self, index_block):
        self.readme.write_text(
            "# Repo\n\n## Skills\n\nProse.\n\n" + index_block + "\n## Sonraki\n\nx\n",
            encoding="utf-8")

    def check_rc(self):
        return sync.check(readme_text=self.readme.read_text(encoding="utf-8"),
                          skills_dir=str(self.skills))

    def update(self):
        return sync.update(readme_path=str(self.readme),
                           skills_dir=str(self.skills), stage=False)


# ────────────────────────────────────────────────────────────────────────────
class TestFrontmatter(SandboxCase):
    """Frontmatter ayrıştırma: üst düzey skaler alanlar, iç içe bloklar atlanır."""

    def test_parses_quoted_and_unquoted(self):
        d = self.add_skill("a-skill", "Kısa açıklama.")
        md = fm("a-skill", "Kısa açıklama.")
        (d / "SKILL.md").write_text(md, encoding="utf-8")
        meta = sync.parse_frontmatter(d / "SKILL.md")
        self.assertEqual(meta["name"], "a-skill")
        self.assertEqual(meta["description"], "Kısa açıklama.")

        d2 = self.skills / "b-skill"
        d2.mkdir()
        (d2 / "SKILL.md").write_text(
            "---\nname: b-skill\ndescription: Tırnaksız açıklama.\n---\n\n# b\n",
            encoding="utf-8")
        self.assertEqual(
            sync.parse_frontmatter(d2 / "SKILL.md")["description"],
            "Tırnaksız açıklama.")

    def test_nested_metadata_block_is_skipped(self):
        d = self.skills / "verify-chain"
        d.mkdir()
        (d / "SKILL.md").write_text(fm(
            "verify-chain", "Fail-closed zincir.",
            extra='metadata:\n  openclaw:\n    emoji: "⛓️"\n    source: "leibniz2"\n'),
            encoding="utf-8")
        meta = sync.parse_frontmatter(d / "SKILL.md")
        self.assertEqual(meta["description"], "Fail-closed zincir.")
        self.assertNotIn("metadata", meta)
        self.assertNotIn("emoji", meta)

    def test_missing_frontmatter_or_name_fails_closed(self):
        d = self.skills / "no-name"
        d.mkdir()
        (d / "SKILL.md").write_text("# Başlık\n", encoding="utf-8")
        with self.assertRaises(sync.SkillError):
            sync.load_skills(str(self.skills))


# ────────────────────────────────────────────────────────────────────────────
class TestRenderBlock(SandboxCase):
    """Blok üretimi: insan özetleri ve sıra korunur, yeniler alfabetik eklenir."""

    def test_preserves_curated_description_and_order(self):
        # Var olan skill'in İNSAN özeti korunur, frontmatter üzerine yazılmaz;
        # satır sırası da (zeta, alpha — alfabetik DEĞİL) aynen kalır.
        self.add_skill("zeta-skill", "Frontmatter zeta.")
        self.add_skill("alpha-skill", "Frontmatter alpha.")
        existing = block(("zeta-skill", "Elle yazılmış özet."),
                         ("alpha-skill", "Kısa özet."))
        out = sync.render_block(existing, sync.load_skills(str(self.skills)))
        self.assertIn("Elle yazılmış özet.", out)
        self.assertIn("Kısa özet.", out)
        self.assertNotIn("Frontmatter zeta.", out)
        rows = [ln for ln in out.splitlines() if ln.startswith("| `skills/")]
        self.assertEqual([r.split("/")[1] for r in rows],
                         ["zeta-skill", "alpha-skill"])

    def test_new_skills_appended_alphabetically(self):
        self.add_skill("kept-skill", "Kısa özet.")
        self.add_skill("new-b", "Yeni B.")
        self.add_skill("new-a", "Yeni A.")
        existing = block(("kept-skill", "Elle yazılmış özet."))
        out = sync.render_block(existing, sync.load_skills(str(self.skills)))
        rows = [ln for ln in out.splitlines() if ln.startswith("| `skills/")]
        self.assertEqual([r.split("/")[1] for r in rows],
                         ["kept-skill", "new-a", "new-b"])
        self.assertIn("Elle yazılmış özet.", out)
        self.assertIn("Yeni A.", out)

    def test_rows_of_deleted_skills_are_dropped(self):
        self.add_skill("kept-skill", "Kısa özet.")
        existing = block(("kept-skill", "Korunsun."),
                         ("gone-skill", "Silinecek."))
        out = sync.render_block(existing, sync.load_skills(str(self.skills)))
        self.assertIn("Korunsun.", out)
        self.assertNotIn("gone-skill", out)
        self.assertNotIn("Silinecek.", out)

    def test_frontmatter_description_is_escaped_and_capped(self):
        self.add_skill("pipey", "A | B " + ("çok " * 60) + "uzun.")
        out = sync.render_block("", sync.load_skills(str(self.skills)))
        row = [ln for ln in out.splitlines() if "pipey" in ln][0]
        # Boru escape'lenir → hücre sayısı bozulmaz (Skill | Açıklama = 4 boru).
        self.assertIn("A \\| B", row)
        cells = re.split(r"(?<!\\)\|", row)
        self.assertEqual(len(cells), 4,
                         "escape'li boru hücre bölmemeli (3 sınır + boş)")
        desc = cells[2].strip()
        self.assertLessEqual(len(desc), sync.MAX_DESC)
        self.assertTrue(desc.endswith("…"), desc)


# ────────────────────────────────────────────────────────────────────────────
class TestCheckUpdateRoundTrip(SandboxCase):
    """--check fail-closed, --update onarır ve idempotenttir."""

    def _seed_synced(self):
        self.add_skill("alpha", "Alpha özeti.")
        self.add_skill("beta", "Beta özeti.")
        self.write_readme(block(("alpha", "Elle alpha."), ("beta", "Elle beta.")))
        self.assertEqual(self.check_rc(), 0)

    def test_synced_readme_passes(self):
        self._seed_synced()

    def test_missing_marker_is_drift(self):
        self.add_skill("alpha", "A.")
        self.write_readme("| Skill | Açıklama |\n|---|---|\n"
                          "| `skills/alpha/SKILL.md` | Elle alpha. |\n")
        self.assertEqual(self.check_rc(), 1, "işaretçisiz tablo drift'tir")

    def test_missing_and_stale_rows_are_drift(self):
        self._seed_synced()
        self.add_skill("gamma", "G.")
        self.assertEqual(self.check_rc(), 1, "yeni skill satırı yok")
        shutil.rmtree(str(self.skills / "beta"))
        self.assertEqual(self.check_rc(), 1, "silinen skill satırı kalmış")

    def test_unmanaged_row_outside_block_is_drift(self):
        self._seed_synced()
        text = self.readme.read_text(encoding="utf-8").replace(
            "\n## Sonraki", "\n| `skills/alpha/SKILL.md` | Elle alpha. |\n\n## Sonraki")
        self.readme.write_text(text, encoding="utf-8")
        self.assertEqual(self.check_rc(), 1, "blok dışı satır yönetilemez")

    def test_update_fixes_every_drift_and_is_idempotent(self):
        self.add_skill("alpha", "Alpha ham açıklama.")
        self.write_readme("| Skill | Açıklama |\n|---|---|\n"
                          "| `skills/alpha/SKILL.md` | Elle alpha. |\n"
                          "| `skills/ghost/SKILL.md` | Hayalet. |\n")
        self.assertEqual(self.check_rc(), 1)

        self.assertTrue(self.update(), "--update drift'i onarmalı")
        self.assertEqual(self.check_rc(), 0, "onarım sonrası drift kalmamalı")
        text = self.readme.read_text(encoding="utf-8")
        self.assertIn(sync.START_MARKER, text)
        self.assertIn(sync.END_MARKER, text)
        self.assertIn("Elle alpha.", text, "insan özeti korunmalı")
        self.assertNotIn("Hayalet.", text, "hayalet satır düşmeli")

        first = text
        self.assertFalse(self.update(), "ikinci koşum değişmemeli (idempotent)")
        self.assertEqual(self.readme.read_text(encoding="utf-8"), first)

    def test_new_skill_row_uses_frontmatter_description(self):
        self.add_skill("brand-new", "Frontmatter'dan türetilen açıklama.")
        self.write_readme(block())
        self.assertTrue(self.update())
        self.assertIn("Frontmatter'dan türetilen açıklama.",
                      self.readme.read_text(encoding="utf-8"))

    def test_name_directory_mismatch_fails_closed(self):
        d = self.skills / "dir-adı"
        d.mkdir()
        (d / "SKILL.md").write_text(fm("baska-ad", "X."), encoding="utf-8")
        self.write_readme(block())
        self.assertEqual(self.check_rc(), 1, "isim/dizin uyuşmazlığı drift")
        with self.assertRaises(sync.SkillError):
            self.update()

    def test_missing_description_fails_closed(self):
        d = self.skills / "no-desc"
        d.mkdir()
        (d / "SKILL.md").write_text("---\nname: no-desc\n---\n\n# x\n", encoding="utf-8")
        self.write_readme(block())
        self.assertEqual(self.check_rc(), 1, "description yoksa üretilemez")


# ────────────────────────────────────────────────────────────────────────────
class TestCliAndStaging(SandboxCase):
    """CLI yüzeyi: --check/--update/--list ve gerçek `git add` (sandbox repo)."""

    def setUp(self):
        super().setUp()
        for args in (("init", "-q"), ("config", "user.email", "t@example.com"),
                     ("config", "user.name", "t")):
            subprocess.run(["git", *args], cwd=str(self.tmp), check=True,
                           capture_output=True)

    def _run(self, *args):
        return subprocess.run(
            [sys.executable, str(CIKTI / "sync_skills_index.py"),
             "--skills", str(self.skills), "--readme", str(self.readme), *args],
            cwd=str(self.tmp), capture_output=True, text=True)

    def test_cli_check_then_update_then_staged(self):
        self.add_skill("alpha", "Alpha.")
        self.write_readme(block(("alpha", "Elle alpha.")))
        r = self._run("--check")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

        self.add_skill("beta", "Beta.")
        r = self._run("--check")
        self.assertEqual(r.returncode, 1, "yeni skill görülmeli")
        self.assertIn("beta", r.stdout)

        r = self._run("--update")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        staged = subprocess.run(["git", "diff", "--cached", "--name-only"],
                                cwd=str(self.tmp), capture_output=True,
                                text=True, check=True).stdout.split()
        self.assertIn("README.md", staged, "--update README'i stage etmeli")

        self.assertEqual(self._run("--check").returncode, 0)

    def test_cli_verify_blocks_when_update_cannot_converge(self):
        d = self.skills / "broken"
        d.mkdir()
        (d / "SKILL.md").write_text("# frontmatter yok\n", encoding="utf-8")
        self.write_readme(block())
        r = self._run("--verify")
        self.assertEqual(r.returncode, 1, "yakınsayamayan yazar bloklamalı")
        self.assertIn("HATA", r.stdout + r.stderr)

    def test_cli_list_prints_names(self):
        self.add_skill("alpha", "Alpha.")
        self.write_readme(block(("alpha", "Elle."),))
        r = self._run("--list")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("alpha", r.stdout)


# ────────────────────────────────────────────────────────────────────────────
class TestRealRepoIsDriftFree(unittest.TestCase):
    """CANLI yüzey: gerçek README, gerçek skills/ ile senkron olmalı."""

    def test_real_repo_has_no_drift(self):
        rc = sync.check(readme_path=str(REAL_REPO_ROOT / "README.md"),
                        skills_dir=str(REAL_REPO_ROOT / "skills"))
        self.assertEqual(rc, 0, "canlı README skills index'i drift'siz olmalı")

    def test_real_skills_frontmatter_names_match_directories(self):
        for skill in sync.load_skills(str(REAL_REPO_ROOT / "skills")):
            self.assertEqual(skill.name, skill.path.parent.name)

    def test_descriptions_are_single_line_and_pipe_free(self):
        for skill in sync.load_skills(str(REAL_REPO_ROOT / "skills")):
            self.assertNotIn("\n", skill.description)
            self.assertNotIn("|", skill.description)


# ────────────────────────────────────────────────────────────────────────────
class TestHookWiring(unittest.TestCase):
    """Hook, aracın YAZAR + fail-closed modunu birlikte koşmalı (--verify).

    `--update` tek başına "sessiz onarım" olurdu (yazar düzelttikten sonra
    kapı yeşil görünür ama yakınsadığını kimse kanıtlamaz); `--check` tek
    başına ise D2'de ölçülen chicken-and-egg'dir (yeni skill eklemek için
    önce tabloyu elle yazmak gerekir). `--verify` ikisini birleştirir:
    önce dener, sonra KENDİ DOĞRULAMASI yapar ve yakınsamazsa bloklar.
    """

    def _hook_entry(self):
        cfg = (REAL_REPO_ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8")
        for block in re.split(r"\n      - id: ", cfg)[1:]:
            if block.split("\n", 1)[0].strip() == "check-skills-index":
                m = re.search(r"^\s+entry:\s*(.+)$", block, re.M)
                return m.group(1).strip() if m else None
        return None

    def test_hook_entry_runs_verify(self):
        entry = self._hook_entry()
        self.assertIsNotNone(entry, "check-skills-index hook'u bulunamadı")
        self.assertIn("sync_skills_index.py", entry)
        self.assertIn("--verify", entry,
                      "hook auto-sync + fail-closed doğrulamayı birlikte "
                      "koşmalı (--verify): %s" % entry)

    def test_tool_still_offers_standalone_check(self):
        """--check yüzeyi tek başına da kullanılabilir (elle denetim/CI)."""
        self.assertIn("--check", pathlib.Path(CIKTI / "sync_skills_index.py")
                      .read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()