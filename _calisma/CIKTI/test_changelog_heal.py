#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_changelog_heal.py — squash-merge'in bıraktığı ÖLÜ changelog hash
döngüsünün ve yapısal LAG-ONE eksiğinin kapandığını doğrular.

Sözleşme dört parçalıdır ve dördü birlikte anlamlıdır:
  1. `heal_changelog.py` ölü satırı GATE ile aynı ölçütle bulur
     (`origin/main` ∪ `HEAD` erişilebilirliği) ve ölçemezse sessiz "temiz"
     demez (exit 2).
  2. `heal_changelog.py` eksik (lag-one) satırı `gen_changelog`
     `find_missing_commits` sözleşmesiyle bulur ve `--apply` bunu `--prune` ile
     ekler; heal botunun kendi commit'i (`chore(changelog): [bot]`) META
     sayılır — yoksa her bot PR'ı yeni bir eksik üretir (sonsuz döngü).
  3. `.github/workflows/changelog-heal.yml` main'e her inişte ölçer, ölü/eksik
     satır varsa prune+append eder — main branch-protection'lı olduğu için
     çıktı bot dalı + PR (auto-merge) ile döner, bare push ile DEĞİL.
  4. Prune/append gerçekten tabloyu düzeltir (uçtan uca: README yazılır, ölü
     satır gider, canlı/eksik satır doğru yere gelir).

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
            # Tablo temiz olmalı: satırı olmayan commit de "eksik" sayılır
            # (lag-one ölçümü), bu yüzden canlı satır yazılır.
            readme.write_text(_readme([
                "| 2026-10-01 | feat | init | `%s` |" % live]), encoding="utf-8")
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


class MissingRowTests(unittest.TestCase):
    """heal_changelog.missing_hashes + --apply append — lag-one kapanışı."""

    def test_missing_row_after_newest_table_row_is_reported(self):
        """Tablodaki en yeni satırdan SONRA gelen commit eksik sayılır.

        Gerçek lag-one: tabloyu yazan hook satırı commit'ten önce üretir, yani
        en yeni commit her zaman tablonun bir adım önündedir.
        """
        with tempfile.TemporaryDirectory() as td:
            repo = _init_repo(td)
            readme = repo / "README.md"
            first = _commit(repo, readme, _readme([]), "feat: birinci")
            head = _commit(repo, readme, _readme([]) + "\nx\n", "fix: ikinci")
            _set_origin_main(repo)
            readme.write_text(_readme([
                "| 2026-10-01 | feat | birinci | `%s` |" % first]), encoding="utf-8")
            self.assertEqual(hc.missing_hashes(repo, readme), [head])
            self.assertEqual(hc.main(["--check", "--repo", str(repo)]), 1)

    def test_apply_appends_missing_row_end_to_end(self):
        """--apply: gen_changelog --prune eksik satırı ekler, --check 0'a düşer."""
        with tempfile.TemporaryDirectory() as td:
            repo = _init_repo(td)
            readme = repo / "README.md"
            first = _commit(repo, readme, _readme([]), "feat: birinci")
            head = _commit(repo, readme, _readme([]) + "\nx\n", "fix: ikinci")
            _set_origin_main(repo)
            readme.write_text(_readme([
                "| 2026-10-01 | feat | birinci | `%s` |" % first]), encoding="utf-8")
            rc = hc.main(["--apply", "--repo", str(repo), "--json"])
            self.assertEqual(rc, 0, "append sonrası hâlâ eksik satır var")
            text = readme.read_text(encoding="utf-8")
            self.assertIn(head, text)
            self.assertIn(first, text)  # canlı satır korunur
            self.assertEqual(hc.main(["--check", "--repo", str(repo)]), 0)

    def test_bot_meta_commit_does_not_reopen_the_loop(self):
        """Heal botunun kendi commit'i eksik sayılmamalı — döngü kırıcı.

        Gerçek akış: bot PR'ı merge olur, main'e `chore(changelog): [bot]`
        commit'i iner. O commit kendi satırını taşıyamaz. META sayılmazsa heal
        her push'ta yeni bir eksik görüp sonsuza dek PR açar.
        """
        with tempfile.TemporaryDirectory() as td:
            repo = _init_repo(td)
            readme = repo / "README.md"
            first = _commit(repo, readme, _readme([]), "feat: birinci")
            _commit(repo, readme, _readme([
                "| 2026-10-01 | feat | birinci | `%s` |" % first]),
                "chore(changelog): [bot] olu hash prune + eksik satir ekle")
            _set_origin_main(repo)
            self.assertEqual(hc.missing_hashes(repo, readme), [])
            self.assertEqual(hc.main(["--check", "--repo", str(repo)]), 0)

    def test_dead_and_missing_are_measured_together(self):
        """Tek turda hem ölü satır silinir hem eksik satır eklenir."""
        with tempfile.TemporaryDirectory() as td:
            repo = _init_repo(td)
            readme = repo / "README.md"
            live = _commit(repo, readme, _readme([]), "feat: canlı")
            head = _commit(repo, readme, _readme([]) + "\nx\n", "fix: yeni")
            _set_origin_main(repo)
            readme.write_text(_readme([
                "| 2026-10-01 | feat | canlı satır | `%s` |" % live,
                "| 2026-10-02 | fix | ölü satır | `%s` |" % FAKE,
            ]), encoding="utf-8")
            self.assertEqual(hc.dead_hashes(repo, readme), [FAKE])
            self.assertEqual(hc.missing_hashes(repo, readme), [head])
            rc = hc.main(["--apply", "--repo", str(repo), "--json"])
            self.assertEqual(rc, 0)
            text = readme.read_text(encoding="utf-8")
            self.assertNotIn(FAKE, text)
            self.assertIn(live, text)
            self.assertIn(head, text)


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
        # Bot dalında check tetiklemek için `gh workflow run` -> actions: write.
        self.assertEqual(perms["actions"], "write")

    def test_bot_pr_runs_are_approved(self):
        """Bot PR'ının koşumları ONAYLANIR — yoksa check hiç raporlanmaz.

        Ölçüldü (#136, #138): `GITHUB_TOKEN` ile açılan PR'da pull_request
        koşumları `action_required` (onay bekliyor) doğar → 0 check →
        required context'ler yok → `--auto` sonsuza dek BLOCKED. Onaylamak
        check'leri PR'a BAĞLAR (#138: onay sonrası checks=10);
        `workflow_dispatch` ise PR'a bağlanmayan ayrı bir koşum üretir, bu
        yüzden kullanılmaz.
        """
        text = self.text
        self.assertIn("/actions/runs/$id/approve", text)
        self.assertIn('select(.conclusion=="action_required")', text)
        # Dispatch yanlış çözümdü: PR'a bağlanmaz, boşa koşum üretir.
        self.assertNotIn("gh workflow run", text)
        # Onay, PR açıldıktan SONRA.
        self.assertGreater(text.index("/actions/runs/$id/approve"),
                           text.index("gh pr create"))
        # Onaylanacak koşum yoksa sessiz kalınmaz: satır kırmızı biter.
        idx = text.index("/actions/runs/$id/approve")
        self.assertIn("exit 1", text[idx:idx + 900])

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
        apply = next(s for s in steps
                     if s.get("name") == "Heal changelog rows (prune + append)")
        self.assertNotIn("continue-on-error", apply)

    def test_apply_only_when_drift_found(self):
        """rc=1 hem ölü hem eksik satırı kapsar; tek --apply ikisini de düzeltir."""
        steps = self.doc["jobs"]["heal"]["steps"]
        apply = next(s for s in steps
                     if s.get("name") == "Heal changelog rows (prune + append)")
        self.assertIn("steps.probe.outputs.rc == '1'", apply["if"])
        self.assertIn("heal_changelog.py --apply", apply["run"])

    def test_probe_measures_missing_rows_too(self):
        """Ölçüm yalnız ölü satırı değil eksik (lag-one) satırı da raporlar."""
        steps = self.doc["jobs"]["heal"]["steps"]
        probe = next(s for s in steps if s.get("id") == "probe")
        self.assertIn("dead + missing rows", probe["name"])

    def test_bot_commit_carries_meta_prefix(self):
        """Döngü kırıcının sözleşmesi: commit subject `chore(changelog): [bot]`.

        `gen_changelog.find_missing_commits` bu prefix'i META sayar; workflow
        başka bir subject yazarsa heal kendi commit'ini eksik görüp sonsuz PR
        açar. Prefix `chore(changelog)` olduğu için kanıt-boşluğu muafiyeti de
        korunur (`deploy_evidence.DEFAULT_GAP_EXEMPT`).
        """
        self.assertIn("chore(changelog): [bot]", self.text)
        self.assertIn("git commit -F /tmp/heal_msg.txt", self.text)

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
