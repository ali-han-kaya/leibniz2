#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_branch_cleanup_advisor.py — dal temizlik önerisi kapısı.

Gerçek geçici git depoları kullanılır (ağ yok, gh yok): kapsam kanıtı ancak
gerçek blob/commit karşılaştırmasıyla ölçülebilir. Sözleşmeler:

  1) ANCESTOR      — fast-forward merge edilmiş dal → DELETE.
  2) CONTENT       — squash sonrası içerik main'de birebir aynı → DELETE
                     (dal ucu main'in atası DEĞİL; commit soyu yetmez).
  3) PATCH_ID      — içerik sonradan değişmiş ama yamalar base'de eşleşiyor
                     (`git cherry` '-' ) → DELETE.
  3b) MERGE        — içerik tam eşleşmiyor ve dalda merge commit'i var;
                     `git cherry` merge'leri listelemediği için yama eşleşmesi
                     kapsam kanıtı sayılmaz → REVIEW.
  4) PARTIAL       — dosyaların bir kısmı aynı → REVIEW (silme önerilmez).
  5) UNIQUE        — base'de karşılığı olmayan dosya → KEEP.
  6) EMPTY         — dal ucu base ile aynı → DELETE (taşınan commit yok).
  7) Araç SALT-OKUNUR: koşum sonrası repo temiz kalır, hiçbir dal silinmez.
  8) `--json` TEK doküman; `--commands` yalnız DELETE dalar için komut üretir.
  9) Base çözülemezse rc=2 (sessiz "silebilirsin" yok).
"""
import contextlib
import io
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

CIKTI = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(CIKTI))

import branch_cleanup_advisor as bca  # noqa: E402


def _git(repo, *args, check=True):
    proc = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True)
    if check and proc.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} başarısız: {proc.stderr}")
    return proc


def _write(repo, name, content):
    path = os.path.join(repo, name)
    os.makedirs(os.path.dirname(path), exist_ok=True) if os.path.dirname(name) else None
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def _commit(repo, name, content, message):
    _write(repo, name, content)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", message)


class RepoCase(unittest.TestCase):
    """Ortak geçici depo: main + senaryo dalları."""

    def setUp(self):
        self.repo = tempfile.mkdtemp(prefix="bca-")
        self.addCleanup(shutil.rmtree, self.repo, True)
        _git(self.repo, "init", "-q", "-b", "main")
        _git(self.repo, "config", "user.email", "t@example.invalid")
        _git(self.repo, "config", "user.name", "t")
        _commit(self.repo, "README.md", "base\n", "init")

        # 1) fast-forward edilmiş dal (ata)
        _git(self.repo, "checkout", "-q", "-b", "merged-ff")
        _commit(self.repo, "a.txt", "a\n", "add a")
        _git(self.repo, "checkout", "-q", "main")
        _git(self.repo, "merge", "-q", "--ff-only", "merged-ff")

        # 2) squash edilmiş dal: içerik main'de aynı, commit farklı
        _git(self.repo, "checkout", "-q", "-b", "squashed", "main")
        _commit(self.repo, "b.txt", "b\n", "add b")
        _git(self.repo, "checkout", "-q", "main")
        _commit(self.repo, "b.txt", "b\n", "squash b from branch")

        # 3) kısmi kapsama: iki dosyadan biri main'e girmiş
        _git(self.repo, "checkout", "-q", "-b", "partial", "main")
        _commit(self.repo, "c.txt", "c\n", "add c")
        _commit(self.repo, "d.txt", "d\n", "add d")
        _git(self.repo, "checkout", "-q", "main")
        _commit(self.repo, "c.txt", "c\n", "take c only")

        # 4) yalnız dalda olan içerik
        _git(self.repo, "checkout", "-q", "-b", "unique", "main")
        _commit(self.repo, "e.txt", "e\n", "add e unique")
        _git(self.repo, "checkout", "-q", "main")

        # 5) boş dal (uç = main) — setUp sonunda, main'in son hâline bağlanır.
        # 6) yaması base'de olan ama içeriği sonradan değişmiş dal
        _git(self.repo, "checkout", "-q", "-b", "picked", "main")
        _commit(self.repo, "f.txt", "f\n", "add f")
        _git(self.repo, "checkout", "-q", "main")
        # `-x` ile mesaj farklılaşır → commit sha'sı farklı (aynı yama);
        # ardından main dosyayı düzenler: içerik artık eşleşmez, patch eşleşir.
        _git(self.repo, "cherry-pick", "-x", "picked")
        _commit(self.repo, "f.txt", "f-changed\n", "edit f after cherry-pick")

        # 7) merge ile çözülen benzersiz içerik: commit'lerin yaması base'de
        # eşleşir ama içerik YALNIZ merge commit'inde yaşar → REVIEW.
        _git(self.repo, "checkout", "-q", "-b", "merge-res", "main")
        _commit(self.repo, "g.txt", "g\n", "add g")
        _git(self.repo, "checkout", "-q", "main")
        _git(self.repo, "cherry-pick", "-x", "merge-res")
        _commit(self.repo, "g.txt", "main-g\n", "edit g on main")
        _git(self.repo, "checkout", "-q", "merge-res")
        _git(self.repo, "merge", "main", check=False)  # çakışma beklenir
        _commit(self.repo, "g.txt", "merged-only\n", "resolve merge uniquely")

        _git(self.repo, "checkout", "-q", "main")
        # 5) boş dal: uç BİREBİR main (taşınan commit yok)
        _git(self.repo, "branch", "empty", "main")

    def rows(self):
        _, rows = bca.analyze(self.repo, "main", "origin")
        # origin uzak dalı yok: yerel dallar için base=main, remote=origin
        # kullanılamaz → bu yardımcı yerel refs üzerinden okur.
        return {r["branch"]: r for r in rows}

    def by_branch(self):
        """Yerel dalları uzak gibi sunan sarmalayıcı (refs/heads)."""
        rows = {}
        for name in _git(self.repo, "for-each-ref", "--format=%(refname:short)",
                         "refs/heads").stdout.split():
            if name == "main":
                continue
            sha = _git(self.repo, "rev-parse", name).stdout.strip()
            date = _git(self.repo, "log", "-1", "--format=%cI", name).stdout.strip()
            rows[name] = bca.analyze_branch(
                self.repo, {"branch": name, "sha": sha, "date": date},
                _git(self.repo, "rev-parse", "main").stdout.strip())
        return rows


class EvidenceTests(RepoCase):
    def test_fast_forward_branch_is_ancestor_delete(self):
        row = self.by_branch()["merged-ff"]
        self.assertEqual(row["evidence"], "ANCESTOR")
        self.assertEqual(row["recommend"], "DELETE")

    def test_squash_landed_content_is_delete(self):
        row = self.by_branch()["squashed"]
        self.assertEqual(row["evidence"], "CONTENT")
        self.assertEqual(row["recommend"], "DELETE")
        self.assertEqual(row["files_identical"], row["files_total"])
        self.assertGreater(row["ahead"], 0)  # commit soyu main'de DEĞİL
        self.assertGreater(row["behind"], 0)

    def test_patch_id_fallback_after_content_drift(self):
        row = self.by_branch()["picked"]
        self.assertEqual(row["evidence"], "PATCH_ID")
        self.assertEqual(row["recommend"], "DELETE")
        self.assertEqual(row["unique_commits"], 0)
        self.assertGreaterEqual(row["upstream_commits"], 1)

    def test_merge_resolution_content_is_not_delete(self):
        # Yamalar eşleşse de merge çözümünde doğan içerik yalnız dalda:
        # DELETE önerilirse gerçek iş kaybolur.
        row = self.by_branch()["merge-res"]
        self.assertEqual(row["evidence"], "MERGE")
        self.assertEqual(row["recommend"], "REVIEW")
        self.assertEqual(row["files_identical"], 0)

    def test_partial_coverage_is_review(self):
        row = self.by_branch()["partial"]
        self.assertEqual(row["evidence"], "PARTIAL")
        self.assertEqual(row["recommend"], "REVIEW")
        self.assertEqual(row["files_total"], 2)
        self.assertEqual(row["files_identical"], 1)
        self.assertEqual(row["files_missing_in_base"], 1)

    def test_unique_content_is_keep(self):
        row = self.by_branch()["unique"]
        self.assertEqual(row["evidence"], "UNIQUE")
        self.assertEqual(row["recommend"], "KEEP")
        self.assertIn("e.txt", row["sample_paths"])

    def test_empty_branch_is_delete(self):
        row = self.by_branch()["empty"]
        self.assertEqual(row["evidence"], "EMPTY")
        self.assertEqual(row["recommend"], "DELETE")
        self.assertEqual(row["ahead"], 0)


class CliTests(RepoCase):
    def _run(self, argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            with self.assertRaises(SystemExit) as cm:
                bca.main(argv)
        return cm.exception.code, out.getvalue(), err.getvalue()

    def test_json_is_single_document_with_summary(self):
        # Uzak dal yok → 0 dal; yine de tek doküman ve özet sözleşmesi.
        code, out, err = self._run(["--repo", self.repo, "--base", "main", "--json"])
        payload = json.loads(out)  # stdout TEK doküman olmalı
        self.assertEqual(code, 0)
        self.assertEqual(payload["total_branches"], 0)
        self.assertEqual(payload["summary"], {"delete": 0, "review": 0, "keep": 0})
        self.assertEqual(payload["delete_commands"], [])
        self.assertEqual(payload["verdict"], "OK")
        # Teşhis satırı stderr'de: JSON stdout'u bozulmaz.
        self.assertIn("0 DELETE", err)
        self.assertNotIn("dal temizlik", out)

    def test_json_commands_only_for_delete(self):
        payload = bca.build_payload(
            self.repo, "main", "origin", "0" * 40,
            [{"branch": "x", "recommend": "DELETE"},
             {"branch": "y", "recommend": "REVIEW"},
             {"branch": "z", "recommend": "KEEP"}],
            with_commands=True)
        self.assertEqual(payload["delete_commands"],
                         ["git push origin --delete x"])
        self.assertEqual(payload["summary"],
                         {"delete": 1, "review": 1, "keep": 1})

    def test_missing_base_exits_two(self):
        code, out, err = self._run(["--repo", self.repo, "--base", "origin/main",
                                    "--json"])
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(out)["verdict"], "ERROR")
        self.assertIn("HATA", err)

    def test_invalid_base_expression_rejected(self):
        code, out, _ = self._run(["--repo", self.repo, "--base", "main;rm -rf",
                                  "--json"])
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(out)["verdict"], "ERROR")

    def test_text_report_marks_recommendation(self):
        code, out, _ = self._run(["--repo", self.repo, "--base", "main"])
        self.assertEqual(code, 0)
        self.assertIn("dal temizlik önerisi", out)
        self.assertIn("Özet:", out)


class ReadOnlyTests(RepoCase):
    def test_analysis_does_not_touch_repo_or_branches(self):
        before = _git(self.repo, "for-each-ref", "--format=%(refname)")
        before_status = _git(self.repo, "status", "--porcelain").stdout
        _git(self.repo, "checkout", "-q", "main")
        bca.analyze(self.repo, "main", "origin")
        bca.analyze(self.repo, "main", "origin")
        after = _git(self.repo, "for-each-ref", "--format=%(refname)")
        self.assertEqual(before.stdout, after.stdout)
        self.assertEqual(before_status,
                         _git(self.repo, "status", "--porcelain").stdout)


class RemoteListingTests(unittest.TestCase):
    def test_list_branches_skips_base_and_head(self):
        repo = tempfile.mkdtemp(prefix="bca-remote-")
        self.addCleanup(shutil.rmtree, repo, True)
        _git(repo, "init", "-q", "-b", "main")
        _git(repo, "config", "user.email", "t@example.invalid")
        _git(repo, "config", "user.name", "t")
        _commit(repo, "README.md", "base\n", "init")
        _git(repo, "update-ref", "refs/remotes/origin/main",
             _git(repo, "rev-parse", "main").stdout.strip())
        _git(repo, "update-ref", "refs/remotes/origin/HEAD",
             _git(repo, "rev-parse", "main").stdout.strip())
        _git(repo, "update-ref", "refs/remotes/origin/feat/x",
             _git(repo, "rev-parse", "main").stdout.strip())
        names = [r["branch"] for r in bca.list_branches(repo, "origin", "origin/main")]
        self.assertEqual(names, ["feat/x"])


if __name__ == "__main__":
    unittest.main()
