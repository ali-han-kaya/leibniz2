#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_check_prettier_format.py — prettier kapısının SÖZLEŞMESİ.

Kapı iki farklı çağırana hizmet ediyor ve ikisinin davranışı ZIT olmalı:

  * pre-commit (`check-prettier-format`): ortam-bağımlı. Prettier yoksa
    SKIP (rc=0) — ortamı olmayan bir geliştiriciyi bloke etmemeli.
  * haftalık `prettier-drift.yml` (--all-tracked --require-prettier):
    fail-closed. Prettier yoksa rc=2 — kurulmamış bir CI job'ı yeşil
    görünüp HİÇBİR ŞEY ölçmemeli.

Bu ayrım test edilmezse tek bir semantik sürüklenme ("ikisi de SKIP olsun")
hapşırıkla değil, ancak aylar sonra job'ın hep yeşil olduğu fark edilerek
anlaşılır. Ayrıca kapsamın hook'un `files:`/`exclude:` filtresiyle aynı
kalması gerekir: kapsam sessizce daralırsa tarama yapar görünür ama
dosyaları atlar.

Testler ÇEVRİMDIŞI ve ortamdan bağımsızdır: sahte prettier ikilisi kullanılır,
gerçek prettier'ın kurulu olması GEREKMEZ (CI'da node_modules yok).
"""
import contextlib
import io
import json
import os
import pathlib
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import check_prettier_format as cpf  # noqa: E402

# Sahte prettier: FAKE_PW_RC ile çıkış kodu, her argüman için `[warn]` basar.
FAKE_PRETTIER = r'''#!/usr/bin/env python3
import os, sys
rc = int(os.environ.get("FAKE_PW_RC", "0"))
paths = [a for a in sys.argv[1:] if not a.startswith("-")]
if rc != 0:
    for p in paths:
        sys.stderr.write("[warn] %s\n" % p)
    sys.stderr.write("[warn] Code style issues found in %d files. Run "
                     "Prettier with --write to fix.\n" % len(paths))
    sys.exit(rc)
print("All matched files use Prettier code style!")
'''


def _write_fake_prettier(td):
    p = pathlib.Path(td) / "fake_prettier"
    p.write_text(FAKE_PRETTIER, encoding="utf-8")
    p.chmod(p.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return p


class TrackedTargetsTests(unittest.TestCase):
    """`--all-tracked` kapsamı = hook'un files:/exclude: filtresiyle AYNI."""

    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.repo = pathlib.Path(self._td.name)
        self.addCleanup(self._td.cleanup)
        subprocess.run(["git", "init", "-q"], cwd=str(self.repo), check=True)

    def _add(self, *names):
        for name in names:
            p = self.repo / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("x\n", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=str(self.repo), check=True)

    def test_only_js_ts_json_are_in_scope(self):
        self._add("a.js", "b.tsx", "c.json", "d.ts", "e.jsx",
                  "skip.py", "skip.md", "skip.yml", "skip.css")
        got = cpf.tracked_targets(self.repo)
        self.assertEqual(got, ["a.js", "b.tsx", "c.json", "d.ts", "e.jsx"],
                         "kapsam hook'un files: filtresinden kaydı")

    def test_package_lock_is_excluded_but_a_real_lock_file_is_not_proof(self):
        """package-lock.json hariç; ama dosya GERÇEKTEN orada olmalı.

        Aksi hâlde test vacuous olurdu (dışlama hiçbir şey yapmıyor olabilirdi).
        """
        self._add("package-lock.json", "other-lock.json")
        self.assertTrue((self.repo / "package-lock.json").is_file())
        got = cpf.tracked_targets(self.repo)
        self.assertNotIn("package-lock.json", got)
        self.assertIn("other-lock.json", got)

    def test_nested_paths_are_relative_and_unsorted_input_is_sorted(self):
        self._add("z/z.js", "a/a.js")
        self.assertEqual(cpf.tracked_targets(self.repo), ["a/a.js", "z/z.js"])

    def test_non_ascii_names_survive_unescaped(self):
        """`git ls-files -z`: quotePath açıkken düz `ls-files` adı kaçışlar.

        Kaçışlanmış bir ad `is_file()`/prettier çağrısında var olmayan bir
        yola dönüşür ve dosya sessizce taranmaz.
        """
        self._add("gölge-thumb.js")
        self.assertEqual(cpf.tracked_targets(self.repo), ["gölge-thumb.js"])

    def test_brute_scope_matches_the_hook_filter(self):
        """Kapsam deseni hook'unkinden türetilmeli (tek kaynak iddiası)."""
        self.assertEqual(cpf.INCLUDED_SUFFIXES,
                         (".js", ".jsx", ".ts", ".tsx", ".json"))
        self.assertEqual(cpf.EXCLUDED_NAMES, ("package-lock.json",))


class ResolvePrettierTests(unittest.TestCase):
    def test_env_override_wins(self):
        with tempfile.TemporaryDirectory() as td:
            fake = _write_fake_prettier(td)
            self.assertEqual(cpf.resolve_prettier({"PRETTIER_BIN": str(fake)}),
                             fake)

    def test_missing_override_yields_none_not_fallback(self):
        """Var olmayan bir override, repo varsayılanına DÜŞMEZ.

        Düşseydi CI'da yanlış kurulum sessizce yerel ikiliyle 'doğrulanır'
        ve pin kaydı anlamsızlaşırdı.
        """
        self.assertIsNone(cpf.resolve_prettier({"PRETTIER_BIN": "/nonexistent"}))

    def test_blank_override_is_ignored(self):
        with tempfile.TemporaryDirectory() as td:
            fake = _write_fake_prettier(td)
            got = cpf.resolve_prettier({"PRETTIER_BIN": "   "})
            self.assertTrue(got is None or got == cpf.PRETTIER)


class MainModeTests(unittest.TestCase):
    """İki çağıranın ZIT davranışı: SKIP (hook) vs fail-closed (CI)."""

    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.td = pathlib.Path(self._td.name)
        self.addCleanup(self._td.cleanup)
        self.fake = _write_fake_prettier(self.td)
        self.target = self.td / "drift.js"
        self.target.write_text("let x=1\n", encoding="utf-8")

    def _run(self, argv, rc=0, env=None):
        base = {"PRETTIER_BIN": str(self.fake), "FAKE_PW_RC": str(rc)}
        base.update(env or {})
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.dict(os.environ, base, clear=False):
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = cpf.main(argv)
        return code, out.getvalue(), err.getvalue()

    # ---- hook semantiği -----------------------------------------------------
    def test_missing_prettier_skips_in_hook_mode(self):
        code, out, _ = self._run(["drift.js"], env={"PRETTIER_BIN": "/nonexistent"})
        self.assertEqual(code, 0, "hook modu ortam yokken bloke etmemeli")
        self.assertIn("SKIP", out)

    def test_no_files_skips(self):
        code, out, _ = self._run(["/nonexistent/dosya.js"])
        self.assertEqual(code, 0)
        self.assertIn("SKIP", out)

    def test_clean_file_passes(self):
        code, out, _ = self._run([str(self.target)], rc=0)
        self.assertEqual(code, 0)
        self.assertIn("OK", out)

    def test_drifting_file_fails_and_is_named(self):
        code, out, _ = self._run([str(self.target)], rc=1)
        self.assertEqual(code, 1)
        self.assertIn(self.target.name, out,
                      "biçim-uyumsuz dosya adı raporlanmalı")

    def test_summary_line_is_not_reported_as_a_file(self):
        """`Code style issues found in N files…` bir DOSYA DEĞİL.

        Bu filtre olmasa kapı 'sorunlu dosya' diye prettier'ın özet satırını
        listeler ve sayı uydururdu.
        """
        code, out, _ = self._run([str(self.target)], rc=1)
        self.assertEqual(code, 1)
        self.assertNotIn("Code style issues", out)

    # ---- CI semantiği -------------------------------------------------------
    def test_require_prettier_is_fail_closed(self):
        code, _, err = self._run(["--all-tracked", "--require-prettier"],
                                 env={"PRETTIER_BIN": "/nonexistent"})
        self.assertEqual(code, 2,
                         "prettier kurulmadan CI job'ı yeşil görünmemeli")
        self.assertIn("fail-closed", err)

    def test_require_prettier_is_not_a_no_op_when_prettier_exists(self):
        """Bayrak, prettier VARSA sonucu değiştirmemeli (aksi hâlde her hafta
        kırmızı üretir ve kimse bakmaz)."""
        with mock.patch.object(cpf, "tracked_targets", return_value=["drift.js"]):
            with mock.patch.dict(os.environ, {"FAKE_PW_RC": "0"}, clear=False):
                code, out, _ = self._run(["--all-tracked", "--require-prettier"],
                                         rc=0)
        self.assertEqual(code, 0)
        self.assertIn("OK", out)

    def test_empty_all_tracked_is_fail_closed(self):
        """Takipli liste boş dönerse '0 dosya temiz' DEMEK YASAK.

        (git okunamadı / desen bozuldu demektir; sessiz yeşil olurdu.)
        """
        with mock.patch.object(cpf, "tracked_targets", return_value=[]):
            code, _, err = self._run(["--all-tracked"])
        self.assertEqual(code, 2)
        self.assertIn("BOŞ", err)

    def test_all_tracked_covers_files_the_hook_would_never_see(self):
        """Asıl amaç: dokunulmayan bir dosya da taranmalı.

        `tracked_targets`'ın döndürdüğü her dosya prettier'a gider — yani
        'commit edilmiş ama hiç dokunulmamış' dosya artık görünmez değil.
        """
        seen = []

        def spy(prettier, files, repo=None):
            seen.extend(files)
            return 0, []

        with mock.patch.object(cpf, "tracked_targets",
                               return_value=["untouched/a.js", "untouched/b.ts"]):
            with mock.patch.object(cpf, "run_check", side_effect=spy):
                code, _, _ = self._run(["--all-tracked"])
        self.assertEqual(code, 0)
        self.assertEqual(seen, ["untouched/a.js", "untouched/b.ts"])


class WorkflowWiringTests(unittest.TestCase):
    """Job, kapıyı gerçekten ve doğru bayraklarla çağırıyor mu (statik)."""

    def setUp(self):
        self.wf = (cpf.REPO / ".github" / "workflows"
                   / "prettier-drift.yml")
        if not self.wf.is_file():
            self.skipTest("prettier-drift.yml yok")

    def test_job_is_scheduled_weekly_and_manual(self):
        text = self.wf.read_text(encoding="utf-8")
        self.assertIn("schedule:", text)
        self.assertIn("workflow_dispatch:", text)

    def test_job_invokes_the_gate_with_both_flags(self):
        text = self.wf.read_text(encoding="utf-8")
        self.assertIn("check_prettier_format.py", text)
        self.assertIn("--all-tracked", text)
        self.assertIn("--require-prettier", text)

    def test_prettier_version_comes_from_the_lockfile(self):
        """Sürüm elle yazılırsa ikinci bir kopya doğar ve kayar."""
        text = self.wf.read_text(encoding="utf-8")
        self.assertIn("package-lock.json", text)
        lock = (cpf.REPO / "apps" / "dashboard-next" / "package-lock.json")
        if lock.is_file():
            data = json.loads(lock.read_text(encoding="utf-8"))
            ver = data.get("packages", {}).get("node_modules/prettier", {}) \
                      .get("version")
            self.assertTrue(ver, "lock'ta prettier girdisi olmalı")
            self.assertIn("node_modules/prettier", text,
                          "workflow lock'taki girdiyi okumuyor")

    def test_ignore_file_exists_for_the_vendor_exclusion(self):
        """Muafiyet `.prettierignore`'dan gelir (tek kaynak).

        Prettier onu hem glob hem AÇIK argüman için uygular — yani hook ile
        CI aynı muafiyeti görür; kapı içine ikinci bir liste gömülmez.
        """
        ign = cpf.REPO / ".prettierignore"
        self.assertTrue(ign.is_file(), ".prettierignore yok")
        text = ign.read_text(encoding="utf-8")
        self.assertIn("_calisma/CIKTI/vendor/axe.min.js", text)
        # Gerekçe yazılı olmalı: gerekçesiz muafiyet sessiz kapsam kaybıdır.
        self.assertIn("sha256", text)


if __name__ == "__main__":
    unittest.main()
