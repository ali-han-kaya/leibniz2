#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_changelog_heal.py — squash-merge'in bıraktığı ÖLÜ changelog hash
döngüsünün kapandığını doğrular.

Sözleşme üç parçalıdır ve üçü birlikte anlamlıdır:
  1. `heal_changelog.py` ölü satırı GATE ile aynı ölçütle bulur
     (`origin/main` ∪ `HEAD` erişilebilirliği) ve ölçemezse sessiz "temiz"
     demez (exit 2).
  2. `.github/workflows/changelog-heal.yml` main'e her inişte ölçer, ölü satır
     varsa prune eder — main branch-protection'lı olduğu için çıktı bot dalı +
     PR (auto-merge) ile döner, bare push ile DEĞİL.
  3. Prune gerçekten tabloyu temizler (uçtan uca: README yazılır, ölü satır
     gider, canlı satır kalır).

Ölçüm gerçek bir geçici git deposunda yapılır — mock yok.
"""

from __future__ import annotations

import pathlib
import subprocess
import sys
import tempfile
import unittest

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[2]
CIKTI = ROOT / "_calisma" / "CIKTI"
sys.path.insert(0, str(CIKTI))

import heal_changelog as hc  # noqa: E402

WORKFLOW = ROOT / ".github" / "workflows" / "changelog-heal.yml"

FAKE = "0000000"  # 7 hex karakter, hiçbir commit'e ait değil


# ─── geçici git deposu yardımcıları ─────────────────────────────────────


def _git(repo: pathlib.Path, *args: str) -> str:
    proc = subprocess.run(["git", *args], cwd=str(repo), capture_output=True,
                          text=True, check=False)
    if proc.returncode != 0:
        raise AssertionError("git %s başarısız: %s" % (" ".join(args), proc.stderr))
    return proc.stdout


def _init_repo(td: str) -> pathlib.Path:
    repo = pathlib.Path(td)
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "t")
    _git(repo, "config", "commit.gpgsign", "false")
    # gen_changelog --prune PUBLISH dosyasını da ister (tek kaynak işaretçisi).
    pub = repo / "docs" / "PUBLISH_SCENARIO.md"
    pub.parent.mkdir(parents=True, exist_ok=True)
    pub.write_text("# Publish\n\nChangelog: README.md ## Değişiklik Geçmişi\n",
                   encoding="utf-8")
    return repo


def _readme(rows: list[str]) -> str:
    head = [
        "# Test",
        "",
        "## Değişiklik Geçmişi",
        "",
        "| Tarih | Kategori | Değişiklik | Commit |",
        "|---|---|---|---|",
    ]
    return "\n".join(head + rows) + "\n\n## Sonraki Bölüm\n"


def _commit(repo: pathlib.Path, path: pathlib.Path, content: str, msg: str) -> str:
    path.write_text(content, encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", msg)
    return _git(repo, "rev-parse", "--short=7", "HEAD").strip()


def _set_origin_main(repo: pathlib.Path, rev: str = "HEAD") -> None:
    _git(repo, "update-ref", "refs/remotes/origin/main", rev)


class DeadHashMeasurementTests(unittest.TestCase):
    """heal_changelog.dead_hashes — gate ile aynı ölçüt."""

    def test_dead_hash_is_detected_and_live_hash_kept(self):
        with tempfile.TemporaryDirectory() as td:
            repo = _init_repo(td)
            readme = repo / "README.md"
            live = _commit(repo, readme, _readme([]), "feat: init")
            _set_origin_main(repo)
            readme.write_text(_readme([
                "| 2026-10-01 | feat | canlı satır | `%s` |" % live,
                "| 2026-10-02 | fix | ölü satır | `%s` |" % FAKE,
            ]), encoding="utf-8")
            self.assertEqual(hc.dead_hashes(repo, readme), [FAKE])

    def test_hash_only_on_origin_main_is_alive(self):
        """Squash-merge sonrası eski satırlar origin/main'de yaşamaya devam eder.

        Ölçüt iki ucun BİRLEŞİMİ olmazsa, main ilerledikçe tablodaki geçerli
        satırlar yanlışlıkla ölü sayılırdı.
        """
        with tempfile.TemporaryDirectory() as td:
            repo = _init_repo(td)
            readme = repo / "README.md"
            base = _commit(repo, readme, _readme([]), "feat: init")
            on_main = _commit(repo, readme, _readme([]) + "\nx\n", "fix: main only")
            _set_origin_main(repo, on_main)
            # HEAD'i base'e geri al: on_main artık yalnız origin/main'de erişilebilir.
            _git(repo, "reset", "-q", "--hard", base)
            readme.write_text(_readme([
                "| 2026-10-01 | fix | main'de yaşayan satır | `%s` |" % on_main,
                "| 2026-10-02 | fix | ölü satır | `%s` |" % FAKE,
            ]), encoding="utf-8")
            self.assertEqual(hc.dead_hashes(repo, readme), [FAKE])

    def test_unmeasurable_without_origin_main(self):
        """origin/main yoksa ölçüm yapılamaz — sessiz PASS YOK (exit 2)."""
        with tempfile.TemporaryDirectory() as td:
            repo = _init_repo(td)
            readme = repo / "README.md"
            _commit(repo, readme, _readme([]), "feat: init")
            self.assertIsNone(hc.dead_hashes(repo, readme))
            rc = hc.main(["--check", "--repo", str(repo), "--json"])
            self.assertEqual(rc, 2)

    def test_check_exit_codes(self):
        with tempfile.TemporaryDirectory() as td:
            repo = _init_repo(td)
            readme = repo / "README.md"
            live = _commit(repo, readme, _readme([]), "feat: init")
            _set_origin_main(repo)
            self.assertEqual(hc.main(["--check", "--repo", str(repo)]), 0)
            readme.write_text(_readme([
                "| 2026-10-02 | fix | ölü satır | `%s` |" % FAKE]), encoding="utf-8")
            self.assertEqual(hc.main(["--check", "--repo", str(repo)]), 1)

    def test_apply_prunes_end_to_end(self):
        """--apply: gerçek gen_changelog --prune → README temizlenir, canlı satır kalır."""
        with tempfile.TemporaryDirectory() as td:
            repo = _init_repo(td)
            readme = repo / "README.md"
            live = _commit(repo, readme, _readme([]), "feat: canlı iş")
            _set_origin_main(repo)
            readme.write_text(_readme([
                "| 2026-10-01 | feat | canlı satır | `%s` |" % live,
                "| 2026-10-02 | fix | ölü satır | `%s` |" % FAKE,
            ]), encoding="utf-8")
            rc = hc.main(["--apply", "--repo", str(repo), "--json"])
            self.assertEqual(rc, 0, "prune sonrası hâlâ ölü satır var")
            text = readme.read_text(encoding="utf-8")
            self.assertNotIn(FAKE, text)
            self.assertIn(live, text)


class HealWorkflowContractTests(unittest.TestCase):
    """.github/workflows/changelog-heal.yml — tetik/permissions/kayıt yolu."""

    @classmethod
    def setUpClass(cls):
        cls.text = WORKFLOW.read_text(encoding="utf-8")
        cls.doc = yaml.safe_load(cls.text)

    def _triggers(self) -> dict:
        # PyYAML 1.1 `on:`'ı boolean True olarak çözer; ikisini de kabul et.
        return self.doc.get("on") or self.doc.get(True) or {}

    def test_triggers_on_main_push_and_dispatch(self):
        trig = self._triggers()
        self.assertIn("push", trig)
        self.assertEqual(trig["push"]["branches"], ["main"])
        self.assertIn("workflow_dispatch", trig)

    def test_has_privileges_needed_for_bot_pr(self):
        perms = self.doc["permissions"]
        self.assertEqual(perms["contents"], "write")
        self.assertEqual(perms["pull-requests"], "write")

    def test_full_history_fetch_required_for_reachability(self):
        steps = self.doc["jobs"]["heal"]["steps"]
        checkout = next(s for s in steps if "checkout" in s.get("uses", ""))
        self.assertEqual(checkout["with"]["fetch-depth"], 0)

    def test_check_step_fails_closed_on_unmeasurable(self):
        steps = self.doc["jobs"]["heal"]["steps"]
        probe = next(s for s in steps if s.get("id") == "probe")
        run = probe["run"]
        self.assertIn("heal_changelog.py --check", run)
        self.assertIn("rc=$?", run)
        self.assertIn("-eq 2", run)
        self.assertIn("exit 1", run)
        self.assertNotIn("continue-on-error", probe)

    def test_probe_step_does_not_fail_when_dead_rows_exist(self):
        """rc=1 (ölü satır var) NORMAL durumdur — adım kırmızı olmamalı.

        Adım 1 ile biterse job fail olur ve varsayılan `if: success()`
        yüzünden prune/PR adımları atlanır: iyileştirme hiç çalışmaz. Bu yüzden
        adım her durumda 0 ile kapanır, karar `outputs.rc` üzerinden verilir.
        """
        steps = self.doc["jobs"]["heal"]["steps"]
        probe = next(s for s in steps if s.get("id") == "probe")
        self.assertTrue(probe["run"].rstrip().endswith("exit 0"),
                        "probe adımı 0 ile kapanmıyor — rc=1 job'ı kırar")
        apply = next(s for s in steps if s.get("name") == "Prune dead rows")
        self.assertNotIn("continue-on-error", apply)

    def test_apply_only_when_dead_rows_found(self):
        steps = self.doc["jobs"]["heal"]["steps"]
        apply = next(s for s in steps if s.get("name") == "Prune dead rows")
        self.assertIn("steps.probe.outputs.rc == '1'", apply["if"])
        self.assertIn("heal_changelog.py --apply", apply["run"])

    def test_commit_goes_to_bot_branch_not_bare_main(self):
        """main branch-protection'lı: bare push GH006; kayıt yolu bot dalı + PR."""
        text = self.text
        self.assertIn("git switch -c \"$HEAL_BRANCH\"", text)
        self.assertIn("git push --force origin \"HEAD:$HEAL_BRANCH\"", text)
        self.assertIn("gh pr create", text)
        self.assertIn("gh pr merge \"$PR\" --auto", text)
        # main'e doğrudan push yasak (dustu = döngü geri gelir).
        self.assertNotIn("HEAD:main", text)
        self.assertNotIn("push origin main", text)

    def test_commit_message_uses_file_not_inline_flag(self):
        """Apostroflu inline -m harness/tırnaklama ile bozulur — dosyadan oku."""
        self.assertIn("git commit -F /tmp/heal_msg.txt", self.text)

    def test_empty_change_is_a_failure_not_a_silent_pass(self):
        self.assertIn("git diff --quiet -- README.md", self.text)
        idx = self.text.index("git diff --quiet -- README.md")
        self.assertIn("exit 1", self.text[idx:idx + 400])


if __name__ == "__main__":
    unittest.main()
