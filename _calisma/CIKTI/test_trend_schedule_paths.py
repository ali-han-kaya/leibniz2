#!/usr/bin/env python3
"""test_trend_schedule_paths.py — Pazartesi schedule koşumunun yol sözleşmesi.

Gelecek Pazartesi (2026-10-05) 03:17 UTC'de `determinism-trend` cron'u iki
kez daha ateşlenecek. O koşumda ölçümün nereye gideceği WORKFLOW'A bağlı:
workflow'tan bir satır çıkarılırsa ölçüm kaybolur veya yanlış yere gider,
ama koşum yeşil kalır. Bu test o yolları simüle ederek pinler.

İki kanıtlanmış yol (ikisi de repo yorumlarında run id'leriyle kayıtlı):

  * **TREND_BRANCH push** — main'e bare push branch-protection'a takılır
    (GH006, koşum 35580855610: deney PASS, push FAIL). Bu yüzden kayıt
    `chore/determinism-trend-record` dalına `--force` push edilir ve PR
    duvarından geçer. Test: push HEDEFİ main olamaz.
  * **policy-fallback** — `gh pr create` Actions izni kapalıysa GraphQL
    hata verir (koşum 35590265995). O hâlde adım çökmez: ölçüm bot dalında
    güvende kalır, yönerge yazılır ve adım YEŞİL biter. Test: bu yol
    çalıştığında exit 0 ve yönerge satırları görünür.

Ayrıca fail-closed: `--update` hiçbir şey eklemediyse stage boş kalır ve
adım 1 ile düşer (sessiz yeşil ölçüm yok).

Simülasyon: step'in `run:` betiği YAML'dan ÇIKARILIR ve geçici bir git
repo'sunda stub `git`/`gh` ile gerçekten koşturulur. Betiği kopyalamak
değil, workflow'taki metni çalıştırmak esastır — kopyalanırsa workflow
değiştiğinde test eski metni sınar ve sessizce yeşil kalır.

OFFLINE: gerçek git remote'u, gerçek GitHub API'si, gerçek push yok.
"""
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
WORKFLOW = ROOT / ".github" / "workflows" / "determinism-trend.yml"
TREND_FILE = "docs/determinism_trend/determinism_trend.jsonl"

EXPECTED_CRON = "17 3 * * 1"
EXPECTED_TREND_BRANCH = "chore/determinism-trend-record"
NEXT_MONDAY = "2026-10-05"


def load_yaml():
    try:
        import yaml
    except ImportError:  # pragma: no cover
        raise unittest.SkipTest("PyYAML gerekli")
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def step_script(name="Commit trend record"):
    """Workflow'tan adı verilen step'in `run:` betiğini döndürür."""
    data = load_yaml()
    for job in data["jobs"].values():
        for step in job.get("steps", []):
            if step.get("name") == name:
                return step["run"], step.get("env", {})
    raise AssertionError("step bulunamadı: %s" % name)


class Sandbox:
    """Stub `git`/`gh` olan geçici repo — push/PR yollarını gerçekten yürütür."""

    def __init__(self, *, gh_create_ok, gh_pr_exists=None, gh_auto_ok=True,
                 stage_empty=False):
        self.dir = Path(tempfile.mkdtemp())
        self.bin = self.dir / "bin"
        self.bin.mkdir()
        self.calls = self.dir / "calls.log"
        # stub git: gerçek git değil — çağrı günlüğüne yazar, `diff --cached`
        # çıkış kodu senaryoya göre belirlenir.
        # `git diff --cached --quiet`: 0 = fark yok (stage boş) -> workflow
        # FAIL alır; 1 = fark var -> normal push yolu. Semantik ters yazılırsa
        # fail-closed muhafızı ters çalışır ve test kendini yanıltır.
        stage_rc = 0 if stage_empty else 1
        self._stub("git",
                   '#!/bin/sh\n'
                   'echo "git $*" >> "$CALLS"\n'
                   'if [ "$1" = "diff" ]; then exit %d; fi\n'
                   'exit 0\n' % stage_rc)
        self._stub("gh",
                   '#!/bin/sh\n'
                   'echo "gh $*" >> "$CALLS"\n'
                   'if [ "$2" = "list" ]; then echo "%s"; exit 0; fi\n'
                   'if [ "$2" = "create" ]; then\n'
                   '  if [ "%d" = "1" ]; then echo "https://gh/pr/1"; exit 0; fi\n'
                   '  echo "GraphQL: Resource not accessible by integration" >&2\n'
                   '  exit 1\n'
                   'fi\n'
                   'if [ "$2" = "merge" ]; then\n'
                   '  if [ "%d" = "1" ]; then exit 0; fi\n'
                   '  echo "auto-merge kuyruğa alınamadı — PR açık kalır, elle incelenir"\n'
                   '  exit 1\n'
                   'fi\n'
                   'exit 0\n'
                   % (gh_pr_exists or "", 1 if gh_create_ok else 0,
                      1 if gh_auto_ok else 0))
        (self.dir / "env.sh").write_text(
            'CALLS=%s\nexport CALLS\n' % self.calls, encoding="utf-8")

    def _stub(self, name, body):
        p = self.bin / name
        p.write_text(body, encoding="utf-8")
        p.chmod(0o755)

    def run(self):
        script, env = step_script()
        # GitHub ifadeleri bash'ta bad substitution verir; koşum anında
        # çözülürler — burada gerçekçi bir placeholder'a indirgenir.
        script = re.sub(r"\$\{\{[^}]*\}\}", "gha-placeholder", script)
        cmd = ". %s/env.sh\n" % self.dir
        for k, v in (env or {}).items():
            # env degerleri de ifade icerebilir (${{ github.token }})
            cmd += "export %s=%s\n" % (
                k, re.sub(r"\$\{\{[^}]*\}\}", "gha-placeholder", str(v)))
        cmd += script
        return subprocess.run(["bash", "-c", cmd], cwd=str(self.dir),
                              capture_output=True, text=True, env={
                                  "PATH": "%s:/usr/bin:/bin" % self.bin,
                                  "CALLS": str(self.calls),
                                  "GITHUB_RUN_ID": "999",
                              })

    def log(self):
        if not self.calls.exists():
            return []
        return [l for l in self.calls.read_text(encoding="utf-8").splitlines() if l]

    def cleanup(self):
        shutil.rmtree(self.dir, ignore_errors=True)


class TestScheduleArmed(unittest.TestCase):
    """Pazartesi koşumunun workflow'ta hâlâ durduğu."""

    def setUp(self):
        self.data = load_yaml()
        self.on = self.data[True] if True in self.data else self.data.get("on")

    def test_weekly_monday_cron_is_intact(self):
        self.assertIn(EXPECTED_CRON, str(self.on),
                      "Pazartesi cron kaydı workflow'ta yok: %r" % (self.on,))

    def test_trigger_is_schedule_not_only_dispatch(self):
        self.assertIn("schedule", self.on)

    def test_next_monday_is_the_named_one(self):
        # 2026-10-05 Pazartesi; bu test dosyasındaki NEXT_MONDAY kaydın
        # "gelecek Pazartesi" dediği günle aynı olmalı.
        import datetime
        d = datetime.date.fromisoformat(NEXT_MONDAY)
        self.assertEqual(d.weekday(), 0, "%s Pazartesi değil" % NEXT_MONDAY)

    def test_write_permissions_are_declared(self):
        perms = self.data["permissions"]
        self.assertEqual(perms.get("contents"), "write")
        self.assertEqual(perms.get("pull-requests"), "write")


class TestTrendBranchPushPath(unittest.TestCase):
    """Kayıt main'e değil, TREND_BRANCH'e gitmeli (branch-policy nedeniyle)."""

    def setUp(self):
        self.sb = Sandbox(gh_create_ok=False)

    def tearDown(self):
        self.sb.cleanup()

    def test_push_target_is_the_trend_branch_not_main(self):
        r = self.sb.run()
        log = self.sb.log()
        pushes = [l for l in log if l.startswith("git push")]
        self.assertTrue(pushes, "hiç push çağrısı yapılmadı")
        for p in pushes:
            self.assertIn("HEAD:%s" % EXPECTED_TREND_BRANCH, p,
                          "push hedefi trend dalı değil: %s" % p)
            self.assertNotIn("origin HEAD:main", p)
            self.assertNotIn(":main ", p)

    def test_push_uses_force_so_repeat_runs_dont_clash(self):
        r = self.sb.run()
        self.assertTrue(any(l.startswith("git push --force")
                            for l in self.sb.log()),
                        "push --force değil — haftalık iki kayıt çakışır")

    def test_trend_branch_constant_matches_env_block(self):
        _script, env = step_script()
        self.assertEqual(env.get("TREND_BRANCH"), EXPECTED_TREND_BRANCH)

    def test_recording_step_fails_closed_on_empty_stage(self):
        sb = Sandbox(gh_create_ok=False, stage_empty=True)
        try:
            r = sb.run()
            self.assertNotEqual(r.returncode, 0,
                                "stage boşken adım yeşil kaldı — ölçüm kaybolur")
            self.assertIn("stage", r.stdout.lower())
            self.assertFalse([l for l in sb.log() if l.startswith("git push")],
                             "boş stage'de yine de push yapıldı")
        finally:
            sb.cleanup()


class TestPolicyFallbackPath(unittest.TestCase):
    """gh pr create bloklanınca ölçüm kaybolmaz, adım yeşil biter."""

    def setUp(self):
        self.sb = Sandbox(gh_create_ok=False)
        self.r = self.sb.run()

    def tearDown(self):
        self.sb.cleanup()

    def test_step_stays_green_when_pr_create_is_blocked(self):
        self.assertEqual(self.r.returncode, 0,
                         "policy blokunda adım kırmızı — ölçüm kaybı: %s"
                         % self.r.stderr[-300:])

    def test_fallback_prints_manual_pr_instructions(self):
        out = self.r.stdout
        self.assertIn("bot-PR oluşturulamadı", out)
        self.assertIn("bot dalında güvende", out)
        self.assertIn("gh pr create", out)

    def test_measurement_still_pushed_to_the_bot_branch(self):
        self.assertTrue(any("HEAD:%s" % EXPECTED_TREND_BRANCH in l
                            for l in self.sb.log()),
                        "fallback'te dal push'u yapılmadı — ölçüm kaybolur")

    def test_merge_is_never_forced_directly_to_main(self):
        # Doğrudan main'e push/merge yasak; PR duvarı korunmalı.
        script, _ = step_script()
        self.assertNotIn("git push origin HEAD:main", script)
        self.assertIn("--base main", script)


class TestPrLifecyclePaths(unittest.TestCase):
    def test_new_pr_queues_auto_merge(self):
        sb = Sandbox(gh_create_ok=True, gh_auto_ok=True)
        try:
            r = sb.run()
            self.assertEqual(r.returncode, 0)
            log = sb.log()
            self.assertTrue(any(l.startswith("gh pr create") for l in log))
            self.assertTrue(any("pr merge" in l and "--auto" in l for l in log),
                            "auto-merge kuyruğa alınmadı: %r" % log)
        finally:
            sb.cleanup()

    def test_existing_pr_is_commented_not_duplicated(self):
        sb = Sandbox(gh_create_ok=True, gh_pr_exists="77")
        try:
            r = sb.run()
            self.assertEqual(r.returncode, 0)
            log = sb.log()
            self.assertFalse(any(l.startswith("gh pr create") for l in log),
                             "açık PR varken ikinci PR açıldı")
            self.assertTrue(any("pr comment" in l for l in log))
        finally:
            sb.cleanup()

    def test_auto_merge_failure_does_not_fail_the_step(self):
        sb = Sandbox(gh_create_ok=True, gh_auto_ok=False)
        try:
            r = sb.run()
            self.assertEqual(r.returncode, 0)
            self.assertIn("kuyruğa alınamadı", r.stdout)
        finally:
            sb.cleanup()


if __name__ == "__main__":
    unittest.main()
