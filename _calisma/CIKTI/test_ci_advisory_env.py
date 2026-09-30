#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_ci_advisory_env.py — advisory adımların ORTAM sözleşmesi (fail-closed).

ÖLÇÜLEN OLAY (PR #54, 2026-09-30): PR'ı kırmızıya düşüren dört dalın
toplanması sırasında üç advisory adımının ortam sözleşmesi çözüldü. Üçü de
"advisory" oldukları için HİÇBİR ZAMAN kırmızı görünmüyordu — sessizce
ölçmeden geçiyorlardı. Üçünün ortak gerekçesi aynı: **eksik ortam, kapı
kırık gibi görünmemeli; ama ölçülemediğini de gizlememeli.**

  K1 gh çözümlemesi PATH'e bağlı değil
     `audit_live_ci_sync.run_gh()` çıplak `"gh"` çağırıyordu. Runner'da
     çalışır; minimal PATH'li (launchd/TCC) her ortamda `gh` PATH'te
     değilse denetimin TAMAMI düşüyor. Artık K16'nın `find_launchd_tool`
     sözleşmesi kullanılıyor (PATH önce, bilinen konumlar ikincil) ve
     hiçbiri yoksa **sessiz boş liste değil** RuntimeError (exit 2).

  K2 actions kapsamı token'la birlikte verilmeli
     `audit-live-ci` job'ı canlı run'ın job + ARTIFAKT listesini okuyor
     (`gh api repos/…/actions/runs/<id>/artifacts`) ama üst düzey izinler
     yalnız contents/pull-requests idi → 403, "hiçbir şey okunamadı".
     Aynı uçları kullanan refs-trend / audit-refs-trend / override-trend
     `actions: read` bildiriyor; bu iş eksik kalmıştı.

  K3 advisory adım kendi durumunu yazmalı
     GitHub'ın `shell: bash` komutu `bash -eo pipefail` ile koşar. Test
     düştüğünde `errexit` bir sonraki satırı çalıştırmaz — yani
     `echo "…: $?"` yazan eski hâl HATA HALİNDE ÇALIŞMAZDI ve karar
     loga hiç düşmezdi; `continue-on-error` job'u yeşil bırakıyordu.
     Yani kontrol tam olarak işe yaramadığı anda sessizdi.
     Doğru kalıp: `set +e` → çalıştır → `rc=$?` → `set -e`.
     Bu üç adım (label-gate, gen_config --dry-run, gen_changelog --check)
     aynı deseni paylaşır; kapı YALNIZCA eksik olanı yakalar.

Meta-not: bu dosya kurulum ortamını test etmez, SÖZLEŞMEYİ test eder —
yani düzeltmeler geri alınırsa kırmızıya döner.
"""

import os
import pathlib
import re
import subprocess
import sys
import inspect
import unittest
from unittest import mock

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent.parent
WORKFLOWS = ROOT / ".github" / "workflows"
VERIFY_YML = WORKFLOWS / "verify.yml"

sys.path.insert(0, str(HERE))
import audit_live_ci_sync as alcs  # noqa: E402

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None


def _load_verify():
    with open(VERIFY_YML, encoding="utf-8") as f:
        return yaml.safe_load(f)


class TestGhResolutionIsNotPathDependent(unittest.TestCase):
    """K1 — gh PATH'e bağlı değil, yoksa fail-closed."""

    def test_known_paths_cover_homebrew_layouts(self):
        self.assertTrue(alcs.GH_KNOWN_PATHS, "bilinen konum listesi boş")
        joined = " ".join(alcs.GH_KNOWN_PATHS)
        self.assertIn("/opt/homebrew/bin/gh", joined)
        self.assertIn("/usr/local/bin/gh", joined)
        self.assertIn("linuxbrew", joined,
                      "Linuxbrew konumu yok — Linux runner fallback'i eksik")

    def test_resolve_gh_falls_back_to_known_paths(self):
        """PATH boşken bilinen konumlardan biri bulunmalı (macOS ölçümü)."""
        real = os.path.exists
        with mock.patch.dict(os.environ, {"PATH": "/nonexistent"}):
            try:
                found = alcs.resolve_gh()
            except RuntimeError:
                self.skipTest("bu makinede bilinen konumda gh yok — "
                              "fallback doğrulanamıyor")
        self.assertTrue(os.path.isfile(found))
        self.assertTrue(real(found))

    def test_resolve_gh_fails_closed_when_absent(self):
        """Hiçbir yerde yoksa SESSİZ geçmemeli — RuntimeError (exit 2).

        Sessiz geçme, denetimi "eksik/fazla yok" diye yeşile çevirirdi:
        en kötü çıktı, çünkü denetimin işi tam olarak o listedir.
        """
        alcs.GH_KNOWN_PATHS = ()
        try:
            with mock.patch.dict(os.environ, {"PATH": "/nonexistent"}):
                with mock.patch("os.path.isfile", lambda p: False), \
                        mock.patch("os.access", lambda *a: False):
                    with self.assertRaises(RuntimeError) as ctx:
                        alcs.resolve_gh()
        finally:
            alcs.GH_KNOWN_PATHS = ("/opt/homebrew/bin/gh", "/usr/local/bin/gh",
                                   "/home/linuxbrew/.linuxbrew/bin/gh")
        self.assertIn("gh bulunamadı", str(ctx.exception))

    def test_run_gh_goes_through_resolver(self):
        """run_gh çıplak 'gh' çağırmamalı — çözümleyiciden geçmeli."""
        import inspect
        src = inspect.getsource(alcs.run_gh)
        self.assertIn("resolve_gh()", src)
        self.assertNotIn('subprocess.run(args,', src)

    def test_run_gh_executes_the_resolved_binary_end_to_end(self):
        """GERÇEKTEN çalıştır: sahte `gh` + PATH → argv DOĞRU mu?

        Ölçülen hata (ilk denemede CI'da yakalandı): çağıranlar
        `run_gh(["gh", "api", …])` diyordu, çözümleyici de program adını öne
        ekliyordu → `gh gh api …` → "unknown command \\"gh\\" for \\"gh\\"".
        Önceki testler argv'yi hiç ÇALIŞTIRMADIĞI için bunu göremedi;
        sahte executable ile uçtan uca ölçmek şart.
        """
        import stat
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            fake = os.path.join(td, "gh")
            with open(fake, "w", encoding="utf-8") as f:
                f.write("#!/bin/sh\nprintf '%s\\n' \"$@\"\n")
            os.chmod(fake, os.stat(fake).st_mode | stat.S_IEXEC)
            with mock.patch.dict(os.environ, {"PATH": td + os.pathsep +
                                              os.environ.get("PATH", "")}):
                # (a) sözleşme: program adı YOK
                out = alcs.run_gh(["api", "repos/x"])
                self.assertEqual(out.split(), ["api", "repos/x"])
                # (b) savunmacı katman: eski biçim de aynı yere gider
                out2 = alcs.run_gh(["gh", "api", "repos/x"])
                self.assertEqual(out2, out, "eski çağrı biçimi farklı "
                              "gidiyor — savunmacı katman çalışmıyor")

    def test_no_call_site_passes_the_program_name(self):
        """Hiçbir çağıran `run_gh(["gh", …])` biçimini kullanmamalı.

        Savunmacı katman var ama asıl sözleşme budur: program adı tek
        kaynaktan (resolve_gh) gelir, çağıranlardan gelmez.

        AST ile ölçülüyor, metin taramasıyla DEĞİL: `run_gh` docstring'i
        bu hatayı belgelediği için ham metin araması yanlış-pozitif verir
        (ilk yazımda öyle oldu).
        """
        import ast
        tree = ast.parse(inspect.getsource(alcs))
        offenders = []
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call)
                    and getattr(node.func, "id", None) == "run_gh"):
                continue
            if not node.args or not isinstance(node.args[0], (ast.List,
                                                              ast.Tuple)):
                continue
            first = node.args[0].elts[0] if node.args[0].elts else None
            if isinstance(first, ast.Constant) and first.value == "gh":
                offenders.append(node.lineno)
        self.assertEqual(offenders, [],
                         "run_gh çağrıları program adı taşımamalı "
                         "(satırlar: %s) — çözümleyici zaten veriyor, "
                         "çift verilince `gh gh …` olur" % offenders)

    def test_script_compiles_and_keeps_gh_contract(self):
        r = subprocess.run([sys.executable, "-m", "py_compile",
                            str(HERE / "audit_live_ci_sync.py")],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)


@unittest.skipIf(yaml is None, "PyYAML yok — workflow denetimi ölçülemiyor")
class TestActionsScopeMatchesWhatTheJobReads(unittest.TestCase):
    """K2 — token'ın KAPSAMI da verilmeli."""

    # Bu işler `actions/runs/<id>` ve `/artifacts` uçlarını okuyor.
    API_READERS = ("refs-trend", "audit-refs-trend", "override-trend",
                   "audit-live-ci")

    def _jobs(self):
        return _load_verify()["jobs"]

    def test_every_action_api_reader_declares_actions_read(self):
        for name in self.API_READERS:
            with self.subTest(job=name):
                perms = self._jobs()[name].get("permissions") or {}
                self.assertEqual(
                    perms.get("actions"), "read",
                    "%s job'ı actions API'sini okuyor ama `actions: read` "
                    "bildirmiyor → 403, denetim boş listeyi 'uyumlu' sanar"
                    % name)

    def test_top_level_permissions_cannot_grant_actions(self):
        """Üst düzey izin `actions` vermiyorsa job SEÇİCİ olmak zorunda.

        Kısıt bilinçli: daraltma bu PR'ın konusu değil, ama sessizce
        üst düzeyden kaldırılırsa aynı sınıf hatayı geri gelir.
        """
        top = _load_verify().get("permissions") or {}
        self.assertNotEqual(
            top.get("actions"), "read",
            "üst düzey `actions: read` yaygınlaştırıldıysa job seçicileri "
            " gereksizleşir; bu test bilinçli olarak kırmızıya döner")

    def test_audit_live_ci_keeps_pull_requests_write(self):
        """İzin daraltma, manifest/budget PR yorum işlerini kırmamalı."""
        perms = self._jobs()["audit-live-ci"].get("permissions") or {}
        self.assertEqual(perms.get("pull-requests"), "write")
        self.assertEqual(perms.get("contents"), "read")


# ── errexit güvenliği taraması ────────────────────────────────────────────
# `cmd; status=$?` deseni `bash -e` altında ÖLÜDÜR: cmd düşünce shell bir
# sonraki satıra geçmez. Üç koruma vardır ve hepsi kabul edilir:
#   1) `set +e` görüldü (o satırdan sonrası koşar)
#   2) `cmd || rc=$?` — `||` sağ operand'ı errexit'ten muaftır
#   3) `if cmd; then … else status=$?; fi` — else dalı muaftır
# Kapsam bilinçli olarak dar: yalnız kabuk satırı seviyesi. Buraya gömülü
# heredoc (K12/K13'ün PYEOF blokları) çözümlenmez; onların `$?` yakalaması
# heredoc'tan ÖNCE geldiği için ölçümü bozmaz.
_SET_PLUS_E = re.compile(r"^\s*set\s+\+e\s*$")
_OR_GUARDED = re.compile(r"(\|\||&&)\s*[\w-]*\s*=\s*\$\?")
_HAS_STATUS = re.compile(r"\$\?")
_IF_OPEN = re.compile(r"^if\b")
_ELIF = re.compile(r"^elif\b")
_ELSE = re.compile(r"^else\b")
_FI = re.compile(r"^fi\b")


def _unguarded_status_captures(run):
    """`(satır_no, kod)` — errexit'ten korunmamis `$?` yakalamaları."""
    offenders = []
    if_stack = []          # her if için "else görüldü mü"
    seen_set_plus_e = False
    for lineno, raw in enumerate(run.splitlines(), 1):
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        code = stripped.split(" #", 1)[0]
        if _SET_PLUS_E.match(code):
            seen_set_plus_e = True
            continue
        if _IF_OPEN.match(code):
            if_stack.append(False)
            continue
        if _ELIF.match(code):
            if if_stack:
                if_stack[-1] = False
            continue
        if _ELSE.match(code):
            if if_stack:
                if_stack[-1] = True
            continue
        if _FI.match(code):
            if if_stack:
                if_stack.pop()
            continue
        if not _HAS_STATUS.search(code):
            continue
        if seen_set_plus_e or _OR_GUARDED.search(code):
            continue
        if if_stack and if_stack[-1]:       # else dalı
            continue
        offenders.append((lineno, code))
    return offenders


@unittest.skipIf(yaml is None, "PyYAML yok — workflow denetimi ölçülemiyor")
class TestAdvisoryStepsCaptureTheirOwnStatus(unittest.TestCase):
    """K3 — advisory adım `errexit` yüzünden sessiz kalmamalı."""
    def _advisory_runs(self):
        for jname, job in _load_verify()["jobs"].items():
            for step in job.get("steps") or []:
                if not step.get("continue-on-error"):
                    continue
                run = step.get("run")
                if run and "$?" in run:
                    yield jname, step.get("name", ""), run

    def test_status_capture_survives_errexit(self):
        """`$?` YAKALAN her advisory adım `set +e` veya `if/else` ile korunmalı.

        GitHub `shell: bash` = `bash -eo pipefail`. Koruma yoksa komut
        düştüğünde yakalama satırı hiç çalışmaz.

        ÖNCEKİ KURAL ÇOK DARDI: yalnız `^\\s*echo\\b.*\\$\\?` arıyordu, yani
        `status=$?` gibi ATAMA kalıbını GÖRMÜYORDU — bu yüzden tam olarak
        kırık olan iki adım (pre-commit, check-unit-tests) yeşil geçiyordu.
        Artık `\\w+=\\$\\?` de kapsamda.

        `if/then/else` kalıbı güvenlidir (`else` dalındaki `$?` errexit'ten
        muaftır) — bu yüzden if/else yığını izlenir. K12/K13'ün o kalıbı
        kullandığı artifact'ta KANITLANDI: onların `.exit` dosyaları yazılmış,
        düz kalıbınkiler yazılmamıştı.
        """
        offenders = []
        for jname, name, run in self._advisory_runs():
            for lineno, code in _unguarded_status_captures(run):
                offenders.append("%s / %s:%d → %s"
                                 % (jname, name, lineno, code))
        self.assertEqual(offenders, [],
                         "advisory adımlarda errexit'e açık $? yakalama: %s"
                         % offenders)

    def test_label_gate_step_uses_the_canonical_pattern(self):
        """Somut kural: label-gate adımı set +e / rc / set -e kullanır."""
        jobs = _load_verify()["jobs"]
        step = next(s for s in jobs["verify"]["steps"]
                    if s.get("name") == "Label gate contract check (advisory)")
        run = step["run"]
        self.assertIn("set +e", run)
        self.assertIn("set -e", run)
        self.assertRegex(run, r"rc=\$\?")
        # Durum değişkeni gerçekten kullanılmalı (yoksa yine sessiz).
        self.assertRegex(run, r'echo "label gate contract check: \$rc"')

    def test_workflow_is_lintable_yaml(self):
        d = _load_verify()
        self.assertIn("jobs", d)
        self.assertGreater(len(d["jobs"]), 20)


class TestGatesMustRunInACleanCheckout(unittest.TestCase):
    """K4 — kapı, temiz klon'da da koşabilmeli.

    ÖLÇÜLEN OLAY: bu PR'yi `git worktree` ile TEMİZ bir klon üzerinde
    denediğimde `check-unit-tests` hook'u `test_dev_bootstrap` ile düştü.
    `test_check_passes_on_provisioned_checkout` yalnız VENV'in varlığını
    soruyordu, ama `dev_bootstrap.sh --check` DOKUZ unit'in tamamını
    ölçüyor. Kısmi kurulumda (venv var, node_modules yok — yani her temiz
    klon ve her CI) `--check` doğru biçimde "pptx eksik" dedi ve test
    ÇÖKTÜ. Yani test, ölçtüğü şey olan kapı değil, geliştirici kurulumuydu.

    Ders: bir testin skip koşulu, testin ÇALIŞTIĞI ortamın ön koşullarıyla
    aynı genişlikte olmalı. Aynı dosyanın kardeş testi
    (`test_check_fail_closed_on_broken_unit`) zaten doğru kalıbı
    kullanıyor (unit başına `skipTest`) — sapma oradaydı.
    """

    def _load(self):
        import importlib.util
        path = HERE / "test_dev_bootstrap.py"
        spec = importlib.util.spec_from_file_location("hyg_devboot", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_required_sentinels_cover_more_than_the_venv(self):
        """Skip koşulu tek birimi değil, --check'in ölçtüğü unit'leri kapsar."""
        mod = self._load()
        required = getattr(mod.TestCheckContract, "REQUIRED", ())
        self.assertGreaterEqual(
            len(required), 3,
            "REQUIRED yalnız venv'e bakıyor gibi — kısmi kurulumda test "
            "koşup çöker (ölçülen olay)")
        names = {name for name, _p, _probe in required}
        self.assertIn("venv_z3", names)
        self.assertIn("pptx", names,
                      "pptx npm bağımlılığı — en sık eksik olan unit")

    def test_skip_message_names_the_missing_units(self):
        """Skip mesajı EKSİK olanı söylemeli: 'kurulum değil' demek yetmez.

        Sessiz skip, bu sınıftaki ilk hatayı doğuran şeyin ta kendisi.
        """
        mod = self._load()
        src = inspect.getsource(
            mod.TestCheckContract.test_check_passes_on_provisioned_checkout)
        self.assertIn("skipTest", src)
        self.assertIn("missing", src)   # eksik unit listesi yazılıyor mu
        self.assertNotIn("assertEqual(r.returncode, 0, r.stdout + r.stderr)\n"
                         "        ", src.split("skipTest")[0])

    def test_sibling_test_already_used_the_canonical_pattern(self):
        """Kısmi kurulumda kardeş test zaten skip ediyor — sapma tekti."""
        mod = self._load()
        sibling = inspect.getsource(
            mod.TestCheckContract.test_check_fail_closed_on_broken_unit)
        self.assertIn("skipTest", sibling)

    def test_partially_provisioned_checkout_skips_instead_of_failing(self):
        """Somut kanıt: unit'leri gizleyince SKIP, FAIL değil."""
        mod = self._load()
        method = mod.TestCheckContract(
            "test_check_passes_on_provisioned_checkout")
        with mock.patch.object(mod.os.path, "isdir", lambda p: False), \
                mock.patch.object(mod.os.path, "isfile", lambda p: False):
            with self.assertRaises(unittest.SkipTest) as ctx:
                method.test_check_passes_on_provisioned_checkout()
        self.assertIn("tam kurulum değil", str(ctx.exception))


class TestPreCommitHooksSurviveACleanCheckout(unittest.TestCase):
    """K1 — hook `entry`'si venv YOLUNA bağlı olmamalı.

    CI kanıtı: `Executable \`_calisma/.venv_z3/bin/python\` not found`,
    duration 0 s — denetim hiç çalışmadan kırmızı. `language: system`
    hook'larda pre-commit, `entry`'deki executable'ı YOL olarak doğrulayıp
    "not found" ile reddediyor; sistem python3'üne düşen YOK.
    """

    VENV = "_calisma/.venv_z3/bin/python"

    def _hook(self, hook_id):
        for repo in (".pre-commit-config.yaml",):
            text = pathlib.Path(ROOT / repo).read_text(encoding="utf-8")
        blocks = re.split(r"\n      - id: ", text)
        for block in blocks[1:]:
            if block.split("\n", 1)[0].strip() == hook_id:
                return block
        self.fail("hook bulunamadı: %s" % hook_id)

    def _entry(self, hook_id):
        """Hook'un `entry` değeri — YAML katlanmış skaler olduğu için
        `entry:` satırından daha DERİN girintili devam satırları da alınır
        (aksi halde venv-guard'ın ikinci yarısı görünmez)."""
        block = self._hook(hook_id)
        lines = block.split("\n")
        for i, line in enumerate(lines):
            m = re.match(r"^(\s*)entry:\s*(.+)$", line)
            if not m:
                continue
            key_indent = len(m.group(1))
            parts = [m.group(2).strip()]
            for cont in lines[i + 1:]:
                if not cont.strip():
                    break
                cur_indent = len(cont) - len(cont.lstrip())
                if cur_indent <= key_indent:
                    break
                parts.append(cont.strip())
            return " ".join(parts)
        self.fail("entry yok: %s" % hook_id)

    def test_no_hook_entry_hardcodes_the_repo_venv(self):
        """Hiçbir hook `entry`'si düz venv yolu içermemeli.

        Tarama repo'nun TAMAMINI kapsar: aynı kusurun yeni bir hook'ta
        yeniden doğmasını engeller. `bash -c` ile sarılmış guard'lı
        entry'ler istisnadır (guard zaten `python3`'e düşebiliyor).
        """
        text = pathlib.Path(ROOT / ".pre-commit-config.yaml").read_text(
            encoding="utf-8")
        offenders = []
        for m in re.finditer(r"^(\s*)entry:\s*(.+)$", text, re.M):
            value = m.group(2)
            if "bash -c" in value or self.VENV not in value:
                continue          # ikinci satırda guard varsa `bash -c` zaten var
            offenders.append(value.strip())
        self.assertEqual(offenders, [],
                         "entry düz venv yoluna bağlı (temiz klon/CI'da "
                         "yok): %s" % offenders)

    def test_octokit_audit_uses_the_venv_guard_pattern(self):
        entry = self._entry("audit-octokit-names")
        self.assertIn("[ -x _calisma/.venv_z3/bin/python ]", entry,
                      "venv-guard deseni yok: %s" % entry)
        self.assertIn("audit_octokit_names.py", entry)

    def test_octokit_audit_needs_no_third_party_import(self):
        """Guard `python3`'e düşüyorsa betik stdlib-only olmalı."""
        src = (HERE / "audit_octokit_names.py").read_text(encoding="utf-8")
        third_party = {"yaml", "requests", "PIL", "numpy", "dotenv"}
        imported = set(re.findall(r"^\s*(?:import|from)\s+([A-Za-z_][\w.]*)",
                                  src, re.M))
        self.assertEqual(imported & third_party, set(),
                         "sistem python3'ünde eksik bağımlılık: %s"
                         % (imported & third_party))


@unittest.skipIf(yaml is None, "PyYAML yok — workflow denetimi ölçülemiyor")
class TestGhConsumingStepsReceiveAToken(unittest.TestCase):
    """K2 — `gh` çağıran CI adımı GH_TOKEN almak ZORUNDA.

    GitHub Actions `GH_TOKEN`'ı otomatik dışa aktarmaz. Kanıt (CI logu):
      "repo belirlenemedi: gh: To use GitHub CLI in a GitHub Actions
       workflow, set the GH_TOKEN environment variable" (exit 2, ERROR)
    Yani denetim "hiçbir şey ölçemedi" diye kırmızı; ölçtüğü şey yanlış.
    """

    PRECOMMIT_STEP = "Run pre-commit (advisory, all files, show diff on failure)"

    def _precommit_step(self):
        for job in _load_verify()["jobs"].values():
            for step in job.get("steps") or []:
                if step.get("name") == self.PRECOMMIT_STEP:
                    return step
        self.fail("pre-commit adımı bulunamadı: %s" % self.PRECOMMIT_STEP)

    def test_precommit_step_injects_gh_token(self):
        env = self._precommit_step().get("env") or {}
        self.assertIn("GH_TOKEN", env,
                      "pre-commit adımı GH_TOKEN vermiyor → gh kimliksiz "
                      "kalıyor ve branch-protection okuması hiç denenmiyor")
        self.assertIn("github.token", str(env["GH_TOKEN"]),
                      "GH_TOKEN değeri actions token'ı olmalı")

    def test_token_is_not_hardcoded(self):
        env = self._precommit_step().get("env") or {}
        self.assertNotRegex(str(env.get("GH_TOKEN", "")),
                            r"gh[pousr]_[A-Za-z0-9]{10,}",
                            "sabit token gömülü")

    def test_status_check_gate_is_gh_dependent(self):
        """Kuralın boşuna-geçmemesi: kapı gerçekten `gh` çağırıyor."""
        src = (HERE / "status_checks.py").read_text(encoding="utf-8")
        self.assertIn("run_gh(", src,
                      "status_checks.py gh kullanmıyorsa token kuralı "
                      "gereksizleşir")


if __name__ == "__main__":
    unittest.main(verbosity=2)
