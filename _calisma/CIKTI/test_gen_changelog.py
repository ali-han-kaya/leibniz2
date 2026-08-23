#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_gen_changelog.py — gen_changelog.py birim testleri.

Kapsam:
  - conventional-commit ayrıştırma (feat/fix/ci/docs/refs/publish/history/teslim)
  - non-conventional prefix ayrıştırma (V5h:, Add ..., Basic ...)
  - find_missing_commits: yalnızca tablodaki en yeni tarihten sonraki commit'ler
  - find_stale_hashes: tabloda olup git log'da olmayan hash'ler
  - format_readme_row / format_pub_row: tablo satırı üretimi
  - --print / --check / --update modları
"""

import os
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest.mock import patch

# Import the module under test
sys.path.insert(0, str(Path(__file__).parent))
import gen_changelog as gc


class TestParseCommit(unittest.TestCase):
    """Conventional-commit mesajı ayrıştırma."""

    def test_feat_with_scope(self):
        cat, desc = gc.parse_commit("feat(ci): add precheck-report to manifest")
        self.assertEqual(cat, "feat")
        self.assertEqual(desc, "(ci) add precheck-report to manifest")

    def test_fix_no_scope(self):
        cat, desc = gc.parse_commit("fix: remove local keyword")
        self.assertEqual(cat, "fix")
        self.assertEqual(desc, "remove local keyword")

    def test_docs(self):
        cat, desc = gc.parse_commit("docs: add changelog to README")
        self.assertEqual(cat, "docs")
        self.assertEqual(desc, "add changelog to README")

    def test_refs(self):
        cat, desc = gc.parse_commit("refs: add OCLC numbers to 5 sources")
        self.assertEqual(cat, "refs")
        self.assertEqual(desc, "add OCLC numbers to 5 sources")

    def test_publish(self):
        cat, desc = gc.parse_commit("publish: branch protection setup")
        self.assertEqual(cat, "publish")
        self.assertEqual(desc, "branch protection setup")

    def test_history(self):
        cat, desc = gc.parse_commit("history: squash test markers")
        self.assertEqual(cat, "history")
        self.assertEqual(desc, "squash test markers")

    def test_teslim(self):
        cat, desc = gc.parse_commit("teslim: ilk V5 teslimi")
        self.assertEqual(cat, "teslim")
        self.assertEqual(desc, "ilk V5 teslimi")

    def test_ispat(self):
        cat, desc = gc.parse_commit("ispat: Z3 sembolik ispat 12/12")
        self.assertEqual(cat, "ispat")
        self.assertEqual(desc, "Z3 sembolik ispat 12/12")

    def test_v5_prefix(self):
        cat, desc = gc.parse_commit("V5h: fix Beth 1953 references in .tex")
        self.assertEqual(cat, "teslim")
        self.assertEqual(desc, "fix Beth 1953 references in .tex")

    def test_add_prefix(self):
        cat, desc = gc.parse_commit("Add GitHub publish runbook")
        self.assertEqual(cat, "feat")
        self.assertEqual(desc, "GitHub publish runbook")

    def test_basic_prefix(self):
        cat, desc = gc.parse_commit("Basic bos kopyalari ignore et")
        self.assertEqual(cat, "chore")
        self.assertEqual(desc, "bos kopyalari ignore et")

    def test_fallback_other(self):
        cat, desc = gc.parse_commit("Some random commit message")
        self.assertEqual(cat, "other")
        self.assertEqual(desc, "Some random commit message")

    def test_long_description_truncation(self):
        """Uzun açıklamalar 80 karaktere kısaltılır (format satırında)."""
        long_desc = "x" * 100
        ci = gc.CommitInfo("abc1234", "abc1234full", "2026-08-21",
                           f"feat: {long_desc}", "feat", f"feat: {long_desc}")
        row = gc.format_readme_row(ci)
        # Satır 80+3=83 karakterden uzun açıklama içermemeli
        # | 2026-08-21 | feat | xxx... | `abc1234` |
        parts = row.split("|")
        desc_part = parts[3].strip()
        self.assertLessEqual(len(desc_part), 80)


class TestFindMissingCommits(unittest.TestCase):
    """find_missing_commits: yalnızca en yeni tarihten sonraki commit'ler."""

    def _ci(self, short, date, subject="feat: test"):
        cat, desc = gc.parse_commit(subject)
        return gc.CommitInfo(short, short + "full", date, subject, cat, desc)

    def test_no_missing_when_all_present(self):
        commits = [self._ci("aaa1111", "2026-08-21"),
                   self._ci("bbb2222", "2026-08-20"),
                   self._ci("ccc3333", "2026-08-19")]
        existing = {"aaa1111", "bbb2222", "ccc3333"}
        missing = gc.find_missing_commits(commits, existing)
        self.assertEqual(missing, [])

    def test_finds_newer_commit(self):
        """Tablodaki en yeni = bbb2222; aaa1111 ondan daha yeni → eksik."""
        commits = [self._ci("aaa1111", "2026-08-21"),  # newer
                   self._ci("bbb2222", "2026-08-20"),  # in table (newest)
                   self._ci("ccc3333", "2026-08-19")]  # in table
        existing = {"bbb2222", "ccc3333"}
        missing = gc.find_missing_commits(commits, existing)
        self.assertEqual(len(missing), 1)
        self.assertEqual(missing[0].short_hash, "aaa1111")

    def test_does_not_report_old_missing(self):
        """ccc3333 git log'da yok (eski commit) → missing'e girmemeli.

        bbb2222 tabloda ve git log'da var → newest_idx = 0 (bbb2222).
        aaa1111 bbb2222'den yeni → eksik olmALI (1 tane).
        Ama ccc3333 (git log'da yok) eksik olarak raporlanMAMALI.
        """
        commits = [self._ci("aaa1111", "2026-08-21"),
                   self._ci("bbb2222", "2026-08-20")]
        existing = {"bbb2222", "ccc3333"}  # ccc3333 git log'da yok
        missing = gc.find_missing_commits(commits, existing)
        # aaa1111 is newer than bbb2222 → 1 missing
        self.assertEqual(len(missing), 1)
        self.assertEqual(missing[0].short_hash, "aaa1111")
        # ccc3333 should NOT appear in missing (it's stale, not missing)
        for ci in missing:
            self.assertNotEqual(ci.short_hash, "ccc3333")

    def test_empty_existing_returns_all(self):
        commits = [self._ci("aaa1111", "2026-08-21"),
                   self._ci("bbb2222", "2026-08-20")]
        existing = set()
        missing = gc.find_missing_commits(commits, existing)
        self.assertEqual(len(missing), 2)

    def test_no_match_returns_empty(self):
        """Hiçbir hash git log'da yok (rebase olmuş olabilir)."""
        commits = [self._ci("aaa1111", "2026-08-21")]
        existing = {"xxx9999"}  # git log'da yok
        missing = gc.find_missing_commits(commits, existing)
        self.assertEqual(missing, [])


class TestFindStaleHashes(unittest.TestCase):
    """find_stale_hashes: tabloda olup git log'da olmayan hash'ler."""

    def _ci(self, short, date="2026-08-21", subject="feat: test"):
        cat, desc = gc.parse_commit(subject)
        return gc.CommitInfo(short, short + "full", date, subject, cat, desc)

    def test_no_stale(self):
        commits = [self._ci("aaa1111"), self._ci("bbb2222")]
        existing = {"aaa1111", "bbb2222"}
        stale = gc.find_stale_hashes(commits, existing)
        self.assertEqual(stale, set())

    def test_finds_stale(self):
        commits = [self._ci("aaa1111")]
        existing = {"aaa1111", "xxx9999"}  # xxx9999 git log'da yok
        stale = gc.find_stale_hashes(commits, existing)
        self.assertEqual(stale, {"xxx9999"})


class TestFormatRow(unittest.TestCase):
    """Tablo satırı üretimi."""

    def test_readme_row_format(self):
        ci = gc.CommitInfo("abc1234", "abc1234full", "2026-08-21",
                           "feat(ci): add X", "feat", "(ci) add X")
        row = gc.format_readme_row(ci)
        self.assertIn("2026-08-21", row)
        self.assertIn("feat", row)
        self.assertIn("(ci) add X", row)
        self.assertIn("`abc1234`", row)

    def test_pub_row_format(self):
        ci = gc.CommitInfo("def5678", "def5678full", "2026-08-20",
                           "fix: bug Y", "fix", "bug Y")
        row = gc.format_pub_row(ci)
        self.assertIn("2026-08-20", row)
        self.assertIn("fix", row)
        self.assertIn("bug Y", row)
        self.assertIn("`def5678`", row)


class TestTagRegexFilter(unittest.TestCase):
    """filter_commits: --tag-regex kategori filtreleme."""

    def _ci(self, short, subject="feat: test"):
        cat, desc = gc.parse_commit(subject)
        return gc.CommitInfo(short, short + "full", "2026-08-21", subject, cat, desc)

    def test_none_returns_all(self):
        commits = [self._ci("aaa1111", "feat: A"),
                   self._ci("bbb2222", "docs: B")]
        out = gc.filter_commits(commits, None)
        self.assertEqual(len(out), 2)

    def test_empty_returns_all(self):
        commits = [self._ci("aaa1111", "feat: A")]
        out = gc.filter_commits(commits, "")
        self.assertEqual(len(out), 1)

    def test_feat_fix_refs_filter(self):
        """Yalnızca feat/fix/refs kategorileri kalır; docs/test/chore elenir."""
        commits = [
            self._ci("aaa1111", "feat: A"),
            self._ci("bbb2222", "fix: B"),
            self._ci("ccc3333", "refs: C"),
            self._ci("ddd4444", "docs: D"),
            self._ci("eee5555", "test: E"),
            self._ci("fff6666", "chore: F"),
        ]
        out = gc.filter_commits(commits, "feat|fix|refs")
        cats = [ci.category for ci in out]
        self.assertEqual(cats, ["feat", "fix", "refs"])

    def test_case_insensitive(self):
        commits = [self._ci("aaa1111", "FIX: A"),
                   self._ci("bbb2222", "docs: B")]
        out = gc.filter_commits(commits, "FIX")
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0].short_hash, "aaa1111")

    def test_scope_category(self):
        """Kategori filtresi scope'lu commit'leri de yakalar (kategori 'feat')."""
        commits = [self._ci("aaa1111", "feat(ci): A"),
                   self._ci("bbb2222", "docs: B")]
        out = gc.filter_commits(commits, "feat")
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0].short_hash, "aaa1111")

    def test_invalid_regex_raises(self):
        commits = [self._ci("aaa1111", "feat: A")]
        with self.assertRaises(ValueError):
            gc.filter_commits(commits, "(feat|fix")

    def test_v_prefix_maps_to_teslim_not_feat(self):
        """V5h: prefix'leri 'teslim' kategorisine eşlenir — 'feat' filtreye girmez."""
        commits = [self._ci("aaa1111", "V5h: fix Beth refs")]
        out = gc.filter_commits(commits, "feat")
        self.assertEqual(out, [])
        out2 = gc.filter_commits(commits, "teslim")
        self.assertEqual(len(out2), 1)

    def test_missing_uses_filter_but_stale_does_not(self):
        """check_file_changelog: missing filtreli, stale tam listeden.

        Tabloda yalnızca bbb2222 (fix) var. Filtre 'feat|fix|refs':
          - aaa1111 (feat, yeni) → missing
          - ddd4444 (docs, tabloda değil) → missing DEĞİL (filtre dışı)
          - eee5555 (test, tabloda, git log'da yok) → stale (filtre dışı ama raporlanır)
        """
        commits = [
            gc.CommitInfo("aaa1111", "a", "2026-08-22", "feat: A", "feat", "A"),
            gc.CommitInfo("bbb2222", "b", "2026-08-21", "fix: B", "fix", "B"),
            gc.CommitInfo("ccc3333", "c", "2026-08-20", "refs: C", "refs", "C"),
        ]
        content = textwrap.dedent("""\
            # Test

            ## Değişiklik Geçmişi

            | Tarih | Kategori | Değişiklik | Commit |
            |---|---|---|---|
            | 2026-08-21 | fix | B | `bbb2222` |
            | 2026-08-19 | test | E | `eee5555` |
            """)
        with tempfile.TemporaryDirectory() as td:
            readme = Path(td, "README.md")
            readme.write_text(content)
            filtered = gc.filter_commits(commits, "feat|fix|refs")
            missing, stale = gc.check_file_changelog(
                readme, "## Değişiklik Geçmişi", gc._README_ROW_RE, filtered,
                all_commits=commits)
        # missing: aaa1111 (feat) — ccc3333 (refs, eski, tabloda yok) DEĞİL
        self.assertEqual(missing, ["aaa1111"])
        # stale: eee5555 (test — filtre dışı ama tam listeden raporlanır)
        self.assertEqual(stale, ["eee5555"])


class TestCheckMode(unittest.TestCase):
    """--check modu: README ve PUBLISH_SCENARIO drift tespiti."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.readme = Path(self.tmpdir, "README.md")
        self.pub = Path(self.tmpdir, "PUBLISH_SCENARIO.md")

    def test_check_no_drift(self):
        """Tüm commit'ler tablolarda → PASS."""
        commits = [
            gc.CommitInfo("aaa1111", "a", "2026-08-21", "feat: X", "feat", "X"),
            gc.CommitInfo("bbb2222", "b", "2026-08-20", "fix: Y", "fix", "Y"),
        ]
        readme_content = textwrap.dedent("""\
            # Test

            ## Değişiklik Geçmişi

            | Tarih | Kategori | Değişiklik | Commit |
            |---|---|---|---|
            | 2026-08-21 | feat | X | `aaa1111` |
            | 2026-08-20 | fix | Y | `bbb2222` |
            """)
        self.readme.write_text(readme_content)
        self.pub.write_text(readme_content)

        readme_missing, readme_stale = gc.check_file_changelog(
            self.readme, "## Değişiklik Geçmişi", gc._README_ROW_RE, commits)
        self.assertEqual(readme_missing, [])
        self.assertEqual(readme_stale, [])

    def test_check_detects_missing(self):
        """Yeni commit var ama tabloda yok → missing detected."""
        commits = [
            gc.CommitInfo("aaa1111", "a", "2026-08-21", "feat: X", "feat", "X"),
            gc.CommitInfo("bbb2222", "b", "2026-08-20", "fix: Y", "fix", "Y"),
        ]
        readme_content = textwrap.dedent("""\
            # Test

            ## Değişiklik Geçmişi

            | Tarih | Kategori | Değişiklik | Commit |
            |---|---|---|---|
            | 2026-08-20 | fix | Y | `bbb2222` |
            """)
        self.readme.write_text(readme_content)

        missing, stale = gc.check_file_changelog(
            self.readme, "## Değişiklik Geçmişi", gc._README_ROW_RE, commits)
        self.assertEqual(len(missing), 1)
        self.assertEqual(missing[0], "aaa1111")

    def test_check_detects_stale(self):
        """Tabloda olup git log'da olmayan hash → stale detected."""
        commits = [
            gc.CommitInfo("aaa1111", "a", "2026-08-21", "feat: X", "feat", "X"),
        ]
        readme_content = textwrap.dedent("""\
            # Test

            ## Değişiklik Geçmişi

            | Tarih | Kategori | Değişiklik | Commit |
            |---|---|---|---|
            | 2026-08-21 | feat | X | `aaa1111` |
            | 2026-08-19 | fix | Z | `dead999` |

            ### Regresyon
            """)
        self.readme.write_text(readme_content)

        missing, stale = gc.check_file_changelog(
            self.readme, "## Değişiklik Geçmişi", gc._README_ROW_RE, commits)
        self.assertIn("dead999", stale)


class TestUpdateMode(unittest.TestCase):
    """--update modu: yeni satırları tabloya ekle."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.readme = Path(self.tmpdir, "README.md")

    def test_update_adds_new_row(self):
        commits = [
            gc.CommitInfo("aaa1111", "a", "2026-08-21", "feat: X", "feat", "X"),
            gc.CommitInfo("bbb2222", "b", "2026-08-20", "fix: Y", "fix", "Y"),
        ]
        readme_content = textwrap.dedent("""\
            # Test

            ## Değişiklik Geçmişi

            | Tarih | Kategori | Değişiklik | Commit |
            |---|---|---|---|
            | 2026-08-20 | fix | Y | `bbb2222` |

            ### Regresyon notları

            | ID | Tarih | Kırılma |
            |---|---|---|
            | R1 | 2026-08-19 | YAML |
            """)
        self.readme.write_text(readme_content)

        added, stale = gc.update_file_changelog(
            self.readme, "## Değişiklik Geçmişi", gc._README_ROW_RE,
            gc.format_readme_row, commits)

        self.assertEqual(len(added), 1)
        self.assertEqual(added[0], "aaa1111")

        # Verify file updated
        content = self.readme.read_text()
        self.assertIn("`aaa1111`", content)
        # Verify existing rows preserved
        self.assertIn("`bbb2222`", content)
        # Verify regression section preserved
        self.assertIn("### Regresyon", content)
        self.assertIn("| R1 |", content)

    def test_update_no_new_commits(self):
        """Tüm commit'ler zaten tabloda → değişiklik yok."""
        commits = [
            gc.CommitInfo("aaa1111", "a", "2026-08-21", "feat: X", "feat", "X"),
        ]
        readme_content = textwrap.dedent("""\
            # Test

            ## Değişiklik Geçmişi

            | Tarih | Kategori | Değişiklik | Commit |
            |---|---|---|---|
            | 2026-08-21 | feat | X | `aaa1111` |
            """)
        self.readme.write_text(readme_content)

        added, stale = gc.update_file_changelog(
            self.readme, "## Değişiklik Geçmişi", gc._README_ROW_RE,
            gc.format_readme_row, commits)
        self.assertEqual(added, [])


class TestMainTagRegex(unittest.TestCase):
    """main() --tag-regex: --print ve --update davranışı."""

    def _commits(self):
        return [
            gc.CommitInfo("aaa1111", "a", "2026-08-22", "feat: A", "feat", "A"),
            gc.CommitInfo("bbb2222", "b", "2026-08-21", "docs: B", "docs", "B"),
            gc.CommitInfo("ccc3333", "c", "2026-08-20", "refs: C", "refs", "C"),
        ]

    def test_print_filters_by_tag_regex(self):
        """--print --tag-regex 'feat|refs' → docs satırı çıktıda yok."""
        import contextlib
        import io
        buf = io.StringIO()
        with patch.object(gc, "get_git_log", return_value=self._commits()), \
             patch.object(sys, "argv", ["gen_changelog.py", "--print",
                                        "--tag-regex", "feat|refs"]), \
             contextlib.redirect_stdout(buf):
            gc.main()
        out = buf.getvalue()
        self.assertIn("`aaa1111`", out)
        self.assertIn("`ccc3333`", out)
        self.assertNotIn("`bbb2222`", out)

    def test_invalid_regex_exits_2(self):
        import contextlib
        import io
        err = io.StringIO()
        with patch.object(gc, "get_git_log", return_value=self._commits()), \
             patch.object(sys, "argv", ["gen_changelog.py", "--print",
                                        "--tag-regex", "(feat|fix"]), \
             contextlib.redirect_stderr(err), \
             self.assertRaises(SystemExit) as cm:
            gc.main()
        self.assertEqual(cm.exception.code, 2)
        self.assertIn("HATA", err.getvalue())

    def test_update_skips_non_matching_new_commits(self):
        """--update --tag-regex 'feat|refs': docs commit'i tabloya eklenmez.

        Tablo refs (ccc3333, eşleşen çapa) + docs (bbb2222) içerir.
        Filtreli listede çapa ccc3333 → aaa1111 (feat, daha yeni) eklenir;
        docs commit'i (filtre dışı) eklenmez, stale de raporlanmaz.
        """
        readme_content = textwrap.dedent("""\
            # Test

            ## Değişiklik Geçmişi

            | Tarih | Kategori | Değişiklik | Commit |
            |---|---|---|---|
            | 2026-08-21 | docs | B | `bbb2222` |
            | 2026-08-20 | refs | C | `ccc3333` |
            """)
        with tempfile.TemporaryDirectory() as td:
            readme = Path(td, "README.md")
            readme.write_text(readme_content)
            filtered = gc.filter_commits(self._commits(), "feat|refs")
            added, stale = gc.update_file_changelog(
                readme, "## Değişiklik Geçmişi", gc._README_ROW_RE,
                gc.format_readme_row, filtered, all_commits=self._commits())
            content = readme.read_text()
        # Yalnızca feat (aaa1111) eklendi; refs çapa olarak tabloda zaten var
        self.assertEqual(added, ["aaa1111"])
        self.assertIn("`aaa1111`", content)
        self.assertIn("`ccc3333`", content)
        self.assertIn("`bbb2222`", content)
        self.assertEqual(stale, [])


class TestRegexPatterns(unittest.TestCase):
    """Tablo satırı regex'leri."""

    def test_readme_row_re_matches(self):
        line = "| 2026-08-21 | feat | add X | `abc1234` |"
        m = gc._README_ROW_RE.match(line)
        self.assertIsNotNone(m)
        self.assertEqual(m.group("date"), "2026-08-21")
        self.assertEqual(m.group("cat"), "feat")
        self.assertEqual(m.group("desc"), "add X")
        self.assertEqual(m.group("hash"), "abc1234")

    def test_pub_row_re_matches(self):
        line = "| 2026-08-21 | AŞAMA 0 | precheck added | `def5678` |"
        m = gc._PUB_ROW_RE.match(line)
        self.assertIsNotNone(m)
        self.assertEqual(m.group("section"), "AŞAMA 0")

    def test_readme_row_re_does_not_match_regresyon(self):
        line = "| R1 | 2026-08-19 | CI 0s | YAML | satır | `d57a60c` |"
        m = gc._README_ROW_RE.match(line)
        self.assertIsNone(m)


if __name__ == "__main__":
    unittest.main(verbosity=2)
