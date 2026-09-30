#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_select_affected_tests.py — artımlı seçimin sözleşme testleri.

check-unit-tests artık commit'in dokunduğu testleri koşuyor. Bunun
doğru çalıştığını gösteren TEK bir kural var:

    hiçbir test, hiçbir değişiklikte sessizce koşulmaktan düşmemeli

Aşağıdaki testler o kuralın her kırılma yolunu kapatır: ulaşılamayan test,
stale glob, nokta ile başlayan yol, `--all-files` (CI) tam batarya garantisi,
kör kapı. Seçimin kendisi `test_coverage_report`'tedir (tek kaynak); burada
onun sözleşmesi ve `select_affected_tests` CLI'sı kilitlenir.
"""

import io
import contextlib
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

CIKTI = pathlib.Path(__file__).resolve().parent
ROOT = CIKTI.parents[1]
if str(CIKTI) not in sys.path:
    sys.path.insert(0, str(CIKTI))

import test_coverage_report as cov  # noqa: E402
import select_affected_tests as selector  # noqa: E402

HOOK_SH = CIKTI / "check_unit_tests_hook.sh"
CONFIG = ROOT / ".pre-commit-config.yaml"
WORKFLOW = ROOT / ".github" / "workflows" / "verify.yml"


def select(paths):
    return cov.affected_tests(paths)["selected"]


def text_of(path):
    return path.read_text(encoding="utf-8")


class TestReachabilityContract(unittest.TestCase):
    """TOPLAM ERİŞİLEBİLİRLİK: manifest'teki her test artımlı koşumda
    seçilebilmeli. Ulaşılamayan test = hiç koşmayan test."""

    @classmethod
    def setUpClass(cls):
        cls.reach = cov.reachable()

    def test_no_test_is_unreachable(self):
        self.assertEqual(
            self.reach["unreachable"], [],
            "artımlı koşumda hiç seçilemeyen test var: her biri ya "
            "ALWAYS_RUN'a ya da TEST_SOURCE_GLOBS'a girilmeli")

    def test_manifest_counts_add_up(self):
        total = (len(self.reach["always"]) + len(self.reach["reactive"])
                 + len(self.reach["unreachable"]))
        self.assertEqual(total, len(self.reach["manifest"]))

    def test_always_run_entries_are_in_the_manifest(self):
        for t in cov.ALWAYS_RUN:
            self.assertIn(t, self.reach["manifest"],
                          f"ALWAYS_RUN'daki test manifest'te yok: {t}")

    def test_glob_entries_are_in_the_manifest(self):
        for t in cov.TEST_SOURCE_GLOBS:
            self.assertIn(t, self.reach["manifest"],
                          f"TEST_SOURCE_GLOBS'taki test manifest'te yok: {t}")

    def test_no_stale_globs(self):
        stale = cov.stale_globs()
        self.assertEqual(stale, [],
                         "diskte hiçbir şeyi tutmayan glob: yeniden adlandırılmış "
                         "bağımlılık, sessizce ölmüş olabilir")

    def test_stale_basis_excludes_ignored_trees(self):
        """Stale denetiminin tabanı ÜRETİLMİŞ çıktıyı saymamalı.

        Ölçülen sahte-pozitif: `*lake-manifest.json` glob'u geliştiricinin
        ağacında ignored olan bir dosyaya tutunduğu için canlı görünüyordu.
        Oysa ignored dosya hiçbir commit listesinde bulunamaz → glob seçim
        üretemez. Taze worktree kanıtı (2026-09-29) bunu patlattı: kapı
        taze checkout'ta kırmızıydı, geliştirici ağacında yeşildi.
        """
        files = cov._selectable_files()
        if files is None:
            self.skipTest("git erişilemedi — taban kümesi düşüyor")
        self.assertIn("_calisma/dev_bootstrap.sh", files)
        self.assertFalse([f for f in files if f.startswith("node_modules/")],
                         "ignored ağaç taban kümede olmamalı")
        self.assertFalse([f for f in files if "/.next/" in f],
                         "üretilmiş derleme çıktısı taban kümede olmamalı")

    def test_untracked_but_committable_file_is_not_stale(self):
        """Commit'lenmemiş OLMAK bir dosyayı üretilmiş çıktı YAPMAZ. Yeni
        (untracked, ignored olmayan) bir kaynak dosyaya bağlanan glob,
        commit'e girene kadar "stale" görünmemeli."""
        files = cov._selectable_files()
        if files is None:
            self.skipTest("git erişilemedi")
        self.assertIn("_calisma/requirements-z3.txt", files,
                      "untracked ama ignored değil → seçilebilir olmalı")


class TestSelection(unittest.TestCase):
    def test_always_run_tests_always_selected(self):
        sel = select(["docs/UNCOMMITTED-INVENTORY.md"])
        for t in cov.ALWAYS_RUN:
            self.assertIn(t, sel)

    def test_edited_test_selects_itself(self):
        self.assertIn("test_workflow_triggers.py",
                      select(["_calisma/CIKTI/test_workflow_triggers.py"]))

    def test_import_derivation_selects_importer(self):
        """Türetilen eşleme: bir gate'i değiştirince onu test eden koşar."""
        sel = select(["_calisma/CIKTI/check_precommit_inventory.py"])
        self.assertIn("test_check_precommit_inventory.py", sel)

    def test_import_derivation_does_not_pull_in_everything(self):
        sel = select(["_calisma/CIKTI/check_precommit_inventory.py"])
        self.assertLess(len(sel), 60,
                        "türetilen eşleme tüm bataryayı çekiyor — glob "
                        "over-match'i var")

    def test_declared_glob_works(self):
        sel = select(["_calisma/dev_bootstrap.sh"])
        self.assertIn("test_dev_bootstrap.py", sel)

    def test_glob_on_a_quoted_filename_is_not_a_dependency(self):
        """REGRESYON: `test_k9_lean_files_sync` `lake-manifest.json`
        DOSYASINI OKUMAZ — `sync_verify_mirror.sh`'ta geçen
        `! -name "lake-manifest.json"` ifadesini arar. O dosyaya glob
        bağlamak üretilmiş bir artifact'a bağlamak demek; test gerçek
        kaynaklarından biri değiştiğinde seçilmiyordu."""
        sel = select(["_calisma/CIKTI/sync_verify_mirror.sh"])
        self.assertIn("test_k9_lean_files_sync.py", sel)
        sel = select(["_calisma/CIKTI/verify_delivery.py"])
        self.assertIn("test_k9_lean_files_sync.py", sel)
        for t, globs in cov.TEST_SOURCE_GLOBS.items():
            self.assertNotIn("*lake-manifest.json", globs,
                             f"{t}: üretilmiş artifact glob'u bildirilemez")

    def test_leading_dot_paths_are_matched(self):
        """REGRESYON: `lstrip("./")` `.github/workflows/verify.yml`'i
        `github/workflows/verify.yml` yapıyordu — nokta ile başlayan HER
        yol sessizce eşleşmez oluyordu."""
        self.assertEqual(cov.normalize_path("./a/b"), "a/b")
        self.assertEqual(cov.normalize_path(".github/workflows/verify.yml"),
                         ".github/workflows/verify.yml")
        self.assertEqual(cov.normalize_path("/abs/.p"), "abs/.p")
        sel = select([".github/workflows/verify.yml"])
        self.assertIn("test_workflow_triggers.py", sel)
        self.assertIn("test_doc_job_sync.py", sel)

    def test_unrelated_change_still_runs_always_run(self):
        sel = select(["docs/some/random/file.md"])
        self.assertTrue(cov.ALWAYS_RUN.issubset(set(sel)))

    def test_selection_is_never_empty(self):
        self.assertTrue(select(["docs/some/random/file.md"]))


class TestFullBatteryContract(unittest.TestCase):
    """'full batarya CI'da kalır' sözleşmesi — mekanik garanti."""

    def test_all_files_selects_the_whole_manifest(self):
        manifest = cov.read_manifest()
        sel = cov.affected_tests(cov._repo_files(), manifest=manifest)["selected"]
        self.assertEqual(sorted(sel), sorted(manifest),
                         "`--all-files` girdisinde seçim manifest'in tamamı "
                         "olmalı; olmuyorsa CI artık tam batarya koşmuyor")

    def test_cli_full_flag_returns_manifest(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = selector.main(["--full"])
        self.assertEqual(rc, 0)
        self.assertEqual(sorted(buf.getvalue().split()), sorted(cov.read_manifest()))

    def test_ci_workflow_still_runs_full_discover(self):
        """CI'ın fail-closed birim-test adımı bu script'ten GEÇMEZ; doğrudan
        `discover -p "test_*.py"` koşar. Artımlı hâle getirmek bu satırı
        sessizce daraltmamalı."""
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn('unittest discover -s _calisma/CIKTI -p "test_*.py"', text)

    def test_ci_advisory_step_uses_all_files(self):
        self.assertIn("pre-commit run check-unit-tests --all-files", text_of(WORKFLOW))


class TestCliContract(unittest.TestCase):
    def test_json_output_is_machine_readable(self):
        import json
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = selector.main(["--json", "README.md"])
        self.assertEqual(rc, 0)
        payload = json.loads(buf.getvalue())
        self.assertEqual(payload["mode"], "incremental")
        self.assertTrue(payload["selected"])

    def test_empty_manifest_is_a_blind_gate(self):
        backup = cov.read_manifest
        cov.read_manifest = lambda: []
        try:
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(io.StringIO()):
                rc = selector.main(["README.md"])
        finally:
            cov.read_manifest = backup
        self.assertEqual(rc, selector.BLIND)


class TestHookShellContract(unittest.TestCase):
    """Sarmalayıcının fail-safe davranışı yapısal olarak sabitlenir."""

    @classmethod
    def setUpClass(cls):
        cls.text = HOOK_SH.read_text(encoding="utf-8")

    def test_hook_takes_filenames(self):
        self.assertIn("pass_filenames: true", text_of(CONFIG))

    def test_selection_failure_falls_back_to_full(self):
        """Seçim üretilemezse TAM BATARYA düşülmeli. Boş seçim "0 test,
        commit geçti" olsaydı kapı tamamen işlevsiz olurdu."""
        self.assertIn('if [ "$FULL" -eq 0 ]', self.text)
        self.assertIn("SELECTED=()", self.text)
        self.assertIn("tam batarya", self.text)

    def test_no_args_means_full_battery(self):
        self.assertIn('[ "${#CHANGED[@]}" -gt 0 ]', self.text)

    def test_selector_is_the_single_source(self):
        self.assertIn("select_affected_tests.py", self.text)

    def test_hook_message_keeps_the_rca_signature(self):
        """`gh_run_rca.py` bu satırı "manifest-drift" olarak SINIFLANDIRIR
        (`RULES[0]` deseni: `manifest/HOOK_COVERAGE drift`). Mesaj kapsam
        notu ekleyince bu imza sessizce kırılır ve CI'daki hata "bilinmeyen"
        diye raporlanır. Ölülen hata: "glob-kapsam" kelimesi imzayı böldü.
        Yalnız `echo` satırına bakılır — yorum satırındaki alıntı yanlış
        pozitif üretmesin diye."""
        import gh_run_rca

        echo = re.search(r'echo "(check-unit-tests: [^"]+)" >&2', self.text)
        self.assertIsNotNone(echo, "hook'un block mesajı bulunamadı")
        self.assertRegex(echo.group(1), re.compile(gh_run_rca.RULES[0][1]))

    def test_sync_diagnostics_are_not_swallowed(self):
        """`--update` yalnız manifest/HOOK_COVERAGE drift'ini çözer; glob
        kapsamı drift'ini ÇÖZMEZ. Sebebi yutmadan tek remedy göstermek
        kullanıcıyı çalışmayan düzeltmeye gönderirdi."""
        self.assertIn("SYNC_OUT", self.text)
        self.assertNotIn("--check >/dev/null", self.text)

    def test_drift_gate_runs_before_tests(self):
        self.assertLess(self.text.index("sync_check_unit_tests.py --check"),
                        self.text.index("unittest discover"))


class TestDerivationSoundness(unittest.TestCase):
    def test_every_derived_glob_exists(self):
        """Türetilen glob'lar diskte gerçek dosyalardır; yanlış modül adı
        import edilseydi sessizce boşa düşerdi."""
        missing = []
        for t in cov.read_manifest():
            for g in cov.import_globs(t):
                if not (ROOT / g).is_file():
                    missing.append((t, g))
        self.assertEqual(missing, [])

    def test_derivation_is_hermetic(self):
        """Türetme diske bağımlı ama AĞ/ortam bağımlı değil; tekrarlanabilir."""
        a = cov.import_globs("test_check_precommit_inventory.py")
        b = cov.import_globs("test_check_precommit_inventory.py")
        self.assertEqual(a, b)
        self.assertTrue(a)


STUB_TEST = '"""Sandbox stub testi."""\nimport unittest\n\n\nclass T(unittest.TestCase):\n    def test_ok(self):\n        pass\n'
# Sandbox kapsam modülü: gerçek modülle AYNI sözleşme, 3 testlik küçük küme.
# Her testin bir eşlemesi VARDIR (aksi halde sync kapısı "ulaşılamayan test"
# der ve bloklar — ki bu doğru davranıştır). test_a ↔ `src/alpha*`,
# test_b ↔ `src/beta*`; kapsam modülünün kendisi ↔ manifest dosyası.
# Böylece `src/beta.py` değiştiğinde TAM OLARAK 1 test seçilir; hiçbir şeyin
# eşleşmediği bir yolda seçim boş kalır → sarmalayıcı tam bataryaya düşer.
SANDBOX_MANIFEST = ["test_a.py", "test_b.py", "test_coverage_report.py"]
SANDBOX_COV = '''"""Sandbox kapsam modülü (gerçek sözleşmenin küçük örneği)."""
import ast
import pathlib
import unittest

TEST_DIR = pathlib.Path(__file__).resolve().parent
HOOK_COVERAGE = {{"check-unit-tests": {manifest!r}}}
ALWAYS_RUN = frozenset()
TEST_SOURCE_GLOBS = {{
    "test_a.py": ["src/alpha*"],
    "test_b.py": ["src/beta*"],
    "test_coverage_report.py": ["_calisma/CIKTI/check_unit_tests.list"],
}}


def _local_module_path(mod):
    return None


def normalize_path(path):
    p = str(path).replace("\\\\", "/")
    while p.startswith("./"):
        p = p[2:]
    return p.lstrip("/")


def import_globs(test_file):
    return []


def effective_globs(test_file):
    return sorted(set(import_globs(test_file)) | set(TEST_SOURCE_GLOBS.get(test_file, [])))


def read_manifest():
    manifest = TEST_DIR / "check_unit_tests.list"
    return [ln.strip() for ln in manifest.read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.lstrip().startswith("#")]


def affected_tests(paths, manifest=None):
    """Gerçek `affected_tests` ile aynı sözleşme (bu testin konusu seçim
    MANTIĞI değil, KABUK + seçici zinciridir; mantığın kendisi
    TestSelection'da gerçek modüle karşı sınanır)."""
    import fnmatch

    manifest = list(manifest if manifest is not None else read_manifest())
    changed = [normalize_path(p) for p in paths]
    selected, reasons = [], {{}}
    for t in manifest:
        if t in ALWAYS_RUN:
            selected.append(t)
            reasons[t] = "always"
            continue
        own = f"_calisma/CIKTI/{{t}}"
        hit = own if own in changed else None
        if not hit:
            for p in changed:
                if any(fnmatch.fnmatch(p, g) for g in effective_globs(t)):
                    hit = p
                    break
        if hit:
            selected.append(t)
            reasons[t] = hit
    return {{"selected": selected, "reasons": reasons, "total": len(manifest),
            "changed": changed}}


def reachable(manifest=None):
    manifest = manifest if manifest is not None else read_manifest()
    always = [t for t in manifest if t in ALWAYS_RUN]
    reactive = [t for t in manifest if t not in ALWAYS_RUN and effective_globs(t)]
    unreachable = [t for t in manifest if t not in always and t not in reactive]
    return {{"manifest": manifest, "always": always, "reactive": reactive,
            "unreachable": unreachable}}


def stale_globs():
    return []


class T(unittest.TestCase):
    def test_ok(self):
        pass
'''.format(manifest=SANDBOX_MANIFEST)


class TestHookEndToEnd(unittest.TestCase):
    """GERÇEK kabuk + GERÇEK seçici, izole sandbox ağacında.

    Statik sözleşme testleri YEĞİN: `mapfile` bash 4 builtin'idir, macOS'un
    /bin/bash'i ise 3.2. Ölülen hata tam olarak bu: 3.2'de `mapfile`
    "command not found" ile düşer, seçim boş kalır, fail-safe DEVREYE
    GİRER ve tam batarya koşar. Yani kapı sağlıklı görünür ama artımlı
    hiç çalışmaz — 190/190, ~350 s, her commit. Bu test o sessiz
    düşüşü mekanik olarak yakalar (tek test koştuğunu kanıtlar).
    """

    def _sandbox(self):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        cikti = pathlib.Path(td.name) / "_calisma" / "CIKTI"
        cikti.mkdir(parents=True)
        for name in ("sync_check_unit_tests.py", "check_unit_tests_hook.sh",
                     "select_affected_tests.py"):
            shutil.copy(str(CIKTI / name), str(cikti))
        for name in SANDBOX_MANIFEST:
            (cikti / name).write_text(
                STUB_TEST if name != "test_coverage_report.py" else SANDBOX_COV,
                encoding="utf-8")
        (cikti / "check_unit_tests.list").write_text(
            "".join(n + "\n" for n in SANDBOX_MANIFEST), encoding="utf-8")
        return td.name

    def _hook(self, root, *args):
        return subprocess.run(
            ["bash", "_calisma/CIKTI/check_unit_tests_hook.sh", *args],
            capture_output=True, text=True, cwd=root)

    def test_matching_change_runs_only_that_test(self):
        root = self._sandbox()
        r = self._hook(root, "src/beta.py")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("artımlı", r.stdout)
        self.assertIn("1/3 test", r.stdout,
                      "tek eşleşen test varken tam batarya koşuldu")
        self.assertNotIn("tam batarya", r.stdout)

    def test_each_declared_glob_selects_its_own_test(self):
        root = self._sandbox()
        r = self._hook(root, "src/alpha.py")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("1/3 test", r.stdout)

    def test_unmatched_change_falls_back_to_full_battery(self):
        """Eşleşme yoksa seçim boştur; sarmalayıcı GÜVENLİ tarafa düşmeli."""
        root = self._sandbox()
        r = self._hook(root, "docs/notes.md")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("tam batarya", r.stdout)
        self.assertIn("3 test", r.stdout)

    def test_no_arguments_is_full_battery(self):
        root = self._sandbox()
        r = self._hook(root)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("tam batarya", r.stdout)

    def test_full_flag_is_full_battery(self):
        root = self._sandbox()
        r = self._hook(root, "--full")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("tam batarya", r.stdout)

    def test_hook_avoids_bash4_builtins(self):
        """macOS /bin/bash 3.2'dir: bash 4 builtin'leri sessizce düşer ve
        fail-safe tam bataryaya kaçar. Statik kapı, koşmadan önce yakalar.
        Yalnız KOD satırları taranır — yorumlarda builtin adı geçebilir
        (dosyada bunu açıklayan bir not var)."""
        code = "\n".join(
            ln for ln in HOOK_SH.read_text(encoding="utf-8").splitlines()
            if not ln.lstrip().startswith("#"))
        for builtin in ("mapfile", "readarray", "declare -A", "globstar",
                        "wait -n", "|&"):
            self.assertNotIn(builtin, code,
                             f"bash 4 bağımlılığı ({builtin}) macOS'ta yok: "
                             "sessizce tam bataryaya düşer")


if __name__ == "__main__":
    unittest.main()
