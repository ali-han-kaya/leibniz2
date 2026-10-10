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

2026-10-08 — AİLELER: koşum artık canvas ailesini de ölçüp kaydeder
(canvas_determinism_test.sh → `--update --family canvas`). Kaynak MATRİSİ
step `env.CANVAS_SOURCES` listesidir (beş kaynak, tek job'da beş rapor;
`strategy.matrix` yerine döngü — tek job sözü). Eklenen sözleşmeler
(TestCanvasFamilyWiring): her adım mevcut ve SIRALI (iki ölçüm de `--check`
öncesinde — tazelik sıralamadan gelmeli), canvas adımı aile SDE sabitini
(1700000000) açıkça verir, tectonic kurulumu TEK adımda kalır (Makefile'ın
"motor pini tek kaynaktir" sözü).

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
        # Workflow'un kayıp-koruma adımı GERÇEK trend_record_merge.py'yi
        # çağırır. Sandbox yalnız git/gh'yi stub'lar; script'i kendisi
        # sağlamazsa `python3: can't open file ...` ile adım düşer ve
        # yol sözleşmesi testleri sessizce yanlış nedenle kırılır. Stub
        # YAZMA: dosyayı depodan kopyala, böylece kayıp korumasının kendisi
        # de uçtan uca sınanır.
        cikti = self.dir / "_calisma" / "CIKTI"
        cikti.mkdir(parents=True)
        shutil.copy2(ROOT / "_calisma" / "CIKTI" / "trend_record_merge.py",
                     cikti / "trend_record_merge.py")
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
                   # `gh pr list` statik DEĞİLDİR: gerçekte pr create'dan
                   # sonra çağrılan list yeni PR'ı döner. Workflow
                   # fail-closed olduğu için bu geçişin modellenmesi şart —
                   # statik stub her koşumda "hâlâ PR yok" deyip adımı
                   # meşru olmayan bir kırmızıya düşürür (test kendi
                   # varsayımını doğrulamış olurdu).
                   'STATE="$(dirname "$CALLS")/gh_pr_created"\n'
                   'if [ "$2" = "list" ]; then\n'
                   '  if [ -f "$STATE" ]; then echo "1"; exit 0; fi\n'
                   '  echo "%s"; exit 0\n'
                   'fi\n'
                   'if [ "$2" = "create" ]; then\n'
                   '  if [ "%d" = "1" ]; then\n'
                   '    touch "$STATE"; echo "https://gh/pr/1"; exit 0;\n'
                   '  fi\n'
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

    def test_blocked_pr_create_fails_closed(self):
        """PR yolu kurulamazsa adım KIRMIZIDIR.

        84db33b'de bilinçli olarak değişen sözleşme: eskiden `|| echo`
        ile yutulup yeşil bitiyordu — kayıt bot dalında sıkışıp bir sonraki
        --force push'ta siliniyordu (koşum 37297101317). "Ölçüm merge
        yolunda değil" başarı değildir."""
        self.assertEqual(self.r.returncode, 1,
                         "PR yolu kurulamazken adım yeşil çıktı — ölçüm "
                         "sessizce kaybolur: %s" % self.r.stderr[-300:])

    def test_failure_prints_manual_pr_instructions(self):
        """Kırmızı çıkarken insanın yapacağı yol yazılı kalmalı."""
        out = self.r.stdout
        self.assertIn("PR yolu kurulamadı", out)
        self.assertIn("bot-dalında GÜVENDE", out)
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

    def test_auto_merge_failure_fails_closed(self):
        """auto-merge kuyruğa alınamazsa da adım kırmızı (fail-closed).

        Ölçüm PR'da açıkta bekliyorsa bu bir "başarı" değil, merge bekleyen
        bir işdir; yeşil görünmemeli."""
        sb = Sandbox(gh_create_ok=True, gh_auto_ok=False)
        try:
            r = sb.run()
            self.assertEqual(r.returncode, 1,
                             "auto-merge başarısızken adım yeşil çıktı")
            self.assertIn("kuyruğa alınamadı", r.stdout)
        finally:
            sb.cleanup()


class TestCanvasFamilyWiring(unittest.TestCase):
    """Pazartesi koşumu canvas ailesini de ölçer, kaydeder, doğrular."""

    ORDER = ["Run determinism experiment (two independent SDE runs)",
             "Record trend measurement",
             "Run canvas determinism experiment (plate-book, 5 kaynak)",
             "Record canvas trend measurement",
             "Validate trend invariants"]
    CANVAS_SOURCES = ["incidental_proof_canvas.tex",
                      "incidental_proof_plate02.tex",
                      "incidental_proof_plate03.tex",
                      "incidental_proof_plate04.tex",
                      "incidental_proof_book.tex"]

    @classmethod
    def setUpClass(cls):
        data = load_yaml()
        cls.steps = [st.get("name") for job in data["jobs"].values()
                     for st in job.get("steps", [])]
        cls.text = WORKFLOW.read_text(encoding="utf-8")

    def test_steps_exist_and_keep_record_before_check(self):
        # Sıralama SÖZLEŞMEDİR: iki ailenin tazelliği kendi eklenen satırına
        # bağlıdır; `--check` bir aile tazelenmeden koşarsa kendi kendine
        # kırmızı olur (ve canvas linux kaydı CI'dan gelir).
        for name in self.ORDER:
            self.assertIn(name, self.steps, "step yok: %s" % name)
        idx = [self.steps.index(n) for n in self.ORDER]
        self.assertEqual(idx, sorted(idx),
                         "step sırası değişti: %r" % self.steps)

    def test_canvas_experiment_runs_the_harness_with_family_epoch(self):
        script, _env = step_script(
            "Run canvas determinism experiment (plate-book, 5 kaynak)")
        self.assertIn("canvas_determinism_test.sh", script)
        # Aile SDE sabiti bilinçli yazılı: SOURCE_DATE_EPOCH'tan türümez
        # (el yazması epoch'u levha PDF'lerini sessizce yeniden damgalar).
        self.assertIn('SOURCE_DATE_EPOCH="1700000000"', script)
        # Rapor yolu recorder'ın okuduğu yere yazılır (CANVAS_REPORT).
        self.assertIn("canvas_determinism", script)

    def test_source_matrix_is_env_parameter_and_loops(self):
        # Matris parametresi env'dedir; run onu DÖNGÜyle işler (strategy.matrix
        # yok: o kaynak başına ayrı job açardı — "tek job'da rapor" sözü kırılırdı).
        script, env = step_script(
            "Run canvas determinism experiment (plate-book, 5 kaynak)")
        listed = env.get("CANVAS_SOURCES", "").split()
        self.assertEqual(listed, self.CANVAS_SOURCES, "matris listesi")
        self.assertIn("for src in $CANVAS_SOURCES", script)
        self.assertIn('TEX_SOURCE="_calisma/CIKTI/canvas/$src"', script)
        # Yapısal kilit: metin taraması yerine PARSED YAML — yorumlarda
        # "strategy.matrix" geçebilir (neden kullanılmadığı yazılıdır);
        # önemli olan hiçbir job'ın strategy/matris'e dağıtılmaması.
        for job_name, job in load_yaml()["jobs"].items():
            self.assertNotIn(
                "strategy", job,
                "job %r matris işi: 'tek job\'da beş rapor' sözü kırılırdı"
                % job_name)

    def test_five_reports_are_fail_closed(self):
        # "Beş rapor" sözü adımın İÇİNDE denetlenir: her kaynak için rapor
        # dosyası var + verdict=PASS; yoksa job kırmızı.
        script, _env = step_script(
            "Run canvas determinism experiment (plate-book, 5 kaynak)")
        self.assertIn('test -f "$report"', script)
        self.assertIn("verdict=PASS", script)
        self.assertIn("rapor yok", script)
        self.assertIn("${src%.tex}.determinism.txt", script)

    def test_canvas_step_loop_actually_runs_harness_for_every_source(self):
        """Davranışsal: adımın `run` betiği GERÇEKTE koşturulur (stub harness).

        Metin varsayımları döngüyü bağlamaz (kanıtlandı: döngü silinince test
        yeşil kalıyordu). Bu test betiği scratch bir repo-kökünde çalıştırır:
        harness yerine stub, PATH'e dummy tectonic → 5 çağrı, doğru sıra,
        SDE aile sabiti, 5 rapor. Hiçbir dış araç gerekmez.
        """
        script, env = step_script(
            "Run canvas determinism experiment (plate-book, 5 kaynak)")
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            canvas_dir = root / "_calisma" / "CIKTI" / "canvas"
            canvas_dir.mkdir(parents=True)
            for src in self.CANVAS_SOURCES:
                (canvas_dir / src).write_text("% stub kaynak\n", encoding="utf-8")
            log = root / "calls.log"
            stub = root / "_calisma" / "CIKTI" / "canvas_determinism_test.sh"
            stub.write_text(
                "#!/usr/bin/env bash\n"
                "set -euo pipefail\n"
                "stem=$(basename \"${TEX_SOURCE%.tex}\")\n"
                "printf '%s %s\\n' \"$stem\" \"$SOURCE_DATE_EPOCH\" >> \"$LOG\"\n"
                "mkdir -p docs/ci_simulate/canvas_determinism\n"
                "printf 'source=%s\\nsource_date_epoch=%s\\nverdict=PASS\\n'" +
                " \"$TEX_SOURCE\" \"$SOURCE_DATE_EPOCH\"" +
                " > \"docs/ci_simulate/canvas_determinism/$stem.determinism.txt\"\n",
                encoding="utf-8")
            stub.chmod(0o755)
            bin_dir = root / "bin"
            bin_dir.mkdir()
            dummy = bin_dir / "tectonic"
            dummy.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            dummy.chmod(0o755)

            run_env = dict(os.environ)
            run_env.update({k: str(v) for k, v in (env or {}).items()})
            run_env["PATH"] = "%s:%s" % (bin_dir, run_env.get("PATH", ""))
            run_env["LOG"] = str(log)
            r = subprocess.run(["bash", "-c", script], cwd=str(root),
                               env=run_env, capture_output=True, text=True)
            self.assertEqual(r.returncode, 0,
                             "adım düştü:\n" + r.stdout[-1200:] + r.stderr[-1200:])
            calls = [ln.split() for ln in
                     log.read_text(encoding="utf-8").splitlines() if ln]
            self.assertEqual([c[0] for c in calls],
                             [src[:-4] for src in self.CANVAS_SOURCES],
                             "harness çağrısı kapsamı/sırası")
            self.assertTrue(all(c[1] == "1700000000" for c in calls),
                            "her çağrı aile SDE sabitiyle: %r" % calls)
            reports = sorted(x.name for x in
                             (root / "docs" / "ci_simulate" /
                              "canvas_determinism").glob("*.determinism.txt"))
            self.assertEqual(len(reports), 5, reports)

    def test_missing_report_fails_the_step(self):
        """"Beş rapor" sözü fail-closed: bir rapor hiç yazılmazsa adım düşer.

        Harness derleme hatasında raporu hiç yazmaz (döngü ilk hatada zaten
        kırmızı döner); burada ikinci denetimin kendisi sınanır — son kaynağın
        raporu üretilmezse `test -f` yakalamalı.
        """
        script, env = step_script(
            "Run canvas determinism experiment (plate-book, 5 kaynak)")
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            canvas_dir = root / "_calisma" / "CIKTI" / "canvas"
            canvas_dir.mkdir(parents=True)
            for src in self.CANVAS_SOURCES:
                (canvas_dir / src).write_text("% stub kaynak\n", encoding="utf-8")
            stub = root / "_calisma" / "CIKTI" / "canvas_determinism_test.sh"
            stub.write_text(
                "#!/usr/bin/env bash\n"
                "set -euo pipefail\n"
                "stem=$(basename \"${TEX_SOURCE%.tex}\")\n"
                "if [ \"$stem\" = \"incidental_proof_book\" ]; then exit 0; fi\n"
                "mkdir -p docs/ci_simulate/canvas_determinism\n"
                "printf 'source=%s\\nverdict=PASS\\n' \"$TEX_SOURCE\"" +
                " > \"docs/ci_simulate/canvas_determinism/$stem.determinism.txt\"\n",
                encoding="utf-8")
            stub.chmod(0o755)
            bin_dir = root / "bin"
            bin_dir.mkdir()
            dummy = bin_dir / "tectonic"
            dummy.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            dummy.chmod(0o755)
            run_env = dict(os.environ)
            run_env.update({k: str(v) for k, v in (env or {}).items()})
            run_env["PATH"] = "%s:%s" % (bin_dir, run_env.get("PATH", ""))
            r = subprocess.run(["bash", "-c", script], cwd=str(root),
                               env=run_env, capture_output=True, text=True)
            self.assertNotEqual(r.returncode, 0,
                                "rapor eksiken adım yeşil kaldı")
            self.assertIn("rapor yok", r.stdout + r.stderr)

    def test_source_list_matches_makefile_single_source_of_truth(self):
        # Anti-drift: CI listesi = Makefile PLATE_SOURCES + PLATE_BOOK.
        # Makefile'a kaynak eklenir, bu liste unutulursa KIRMIZI (iki ayrı
        # aile listesi yaşayamaz); aynı sınıf risk SDE sabiti için de kilitli.
        mk = (ROOT / "docs" / "Makefile.texlive").read_text(encoding="utf-8")
        make_names = sorted(set(re.findall(
            r"incidental_proof_\w+\.tex", mk)))
        self.assertEqual(make_names, sorted(self.CANVAS_SOURCES), make_names)
        _script, env = step_script(
            "Run canvas determinism experiment (plate-book, 5 kaynak)")
        self.assertEqual(sorted(env.get("CANVAS_SOURCES", "").split()),
                         make_names)

    def test_canvas_record_uses_family_flag(self):
        script, _env = step_script("Record canvas trend measurement")
        self.assertIn("record_determinism_trend.py", script)
        self.assertIn("--update --family canvas", script)

    def test_single_tectonic_install_is_shared(self):
        # Makefile sözü: "motor pini tek kaynaktir ve CI'dadir". İkinci bir
        # tectonic kurulumu/pini eklenirse ya da canvas adımı kendisi kurarsa
        # kırmızı — pin tek kaynaktan sarsılır.
        self.assertEqual(self.text.count('TECTONIC_SHA256="'), 1)
        installers = [n for n in self.steps
                      if n and n.startswith("Install tectonic")]
        self.assertEqual(len(installers), 1, installers)
        script, _env = step_script(
            "Run canvas determinism experiment (plate-book, 5 kaynak)")
        for bad in ("curl ", "apt-get", "tar -x"):
            self.assertNotIn(bad, script)


if __name__ == "__main__":
    unittest.main()
