#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_fail_closed_gates.py — required kapıların kırmızı-yol kırılma testleri.

Kapsam (2026-10-20 denetimi): `verify.yml`'deki required job'ların
fail-closed davranışı METİNDE var ama hiçbir test o davranışı KIRMIZIYA
DÜŞÜREREK kanıtlamıyordu — bekçi silinirse/gevşerse süit yeşil kalırdı.
Bu dosya her kapının kırmızı yolunu ya gerçek giriş noktasından koşturur
(davranışsal) ya da bekçi metnini sabitler (statik pin).

2026-10-23 — KALICI MUTASYON KANITI (`mutation_guard.py`):
Statik pin tek başına iddiayı KORUMAZ: pin gevşetilirse ya da kapı sessizce
`exit 0`'a dönerse süit yeşil kalır. Bu yüzden her kapının bekçisi
`*_violations(wf)` saf fonksiyonuna çıkarıldı; her bekçi için GERÇEK
workflow metninin geçici bir kopyasına MUTASYON uygulanıyor
(`mutation_guard.apply_mutations`) ve bekçinin kırmızıya dönmesi bekleniyor.
Mutasyon kaçarsa test fail eder — "fail-closed" kanıtı prose'ta değil, her
koşumda ölçülen bir davranıştır. Mutasyon metni kaynaktan kayarsa
`MutationNotApplicable` ile kanıt bayat sayılır (sessiz no-op yok).

Kapı → hüküm eşlemesi:
  * ci-simulate rc tüketimi       — statik keeper + mutasyon (rc/exit/coe)
  * config-drift gate             — davranışsal (boş dizinde rc!=0) + keeper
                                    + mutasyon (yokluk-varsayılanı/final rc)
  * refs-trend gate               — davranışsal (md yoksa 1, varsa 0) + keeper
                                    + mutasyon (exit 1 / build coe)
  * commit_msg_gate.js            — davranışsal (node: yok/bozuk/ihlalli→FAIL,
                                    temiz→PASS) + keeper + mutasyon (sidecar)
  * reports bundle zorunlu kopya  — keeper + mutasyon (|| true / coe)
  * a11y gate                     — keeper + mutasyon (coe / || true)

Tarihsel not: `TestCLSGateRc` 2026-10-23'e kadar var OLMAYAN bir adımı
pinliyordu ("Run CLS budget gate — dashboard" — workflow'da yalnız
"Run a11y gate" var; hiçbir workflow'da CLS adımı/dizesi geçmiyor), bu
yüzden dosya setUpClass'ta kırmızıydı. CLS pinleri kaldırıldı; bekçi gerçek
a11y adımına taşındı. CLS kapısı geri gelirse kendi keeper'ı + mutasyonu
eklenmeli (kanıtsız pin geri dönmemeli).

Kapsam-dışı (başka testte pimli, burada tekrar yok):
  * prettier OK(N>0) ölçümü      → test_prettier_ci_gate.py (davranışsal)
  * tarayıcı SKIP-red bekçileri  → test_browser_skip_audit.py (kayıt defteri)
  * coe upload always()           → test_advisory_coe_surfacing.py
  * rehearse dışı advisory'ler    → GATE_EXCLUDE gerekçeli (workflow_contract)

stdlib unittest — ağ yok, PyYAML yok (düz metin).
"""
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE))

import mutation_guard  # noqa: E402  (HERE sys.path'e eklendikten sonra)

WORKFLOW = ROOT / ".github" / "workflows" / "verify.yml"
COMMIT_MSG_GATE = HERE / "github_scripts" / "commit_msg_gate.js"


def _workflow_text():
    return WORKFLOW.read_text(encoding="utf-8")


def _step_block(wf, job_id, step_name):
    """(job, adım) → adım gövde metni; bulunamazsa AssertionError."""
    m = re.search(rf"^  {re.escape(job_id)}:\n(.*?)(?=^  [a-z0-9-]+:|\Z)",
                  wf, re.M | re.S)
    assert m, "job yok: %s" % job_id
    for sm in re.finditer(
            r"^      - name: ([^\n]*)\n([\s\S]*?)(?=^      - |\Z)",
            m.group(1), re.M):
        if sm.group(1).strip() == step_name:
            return sm.group(2)
    raise AssertionError("adım yok: %s / %s" % (job_id, step_name))


def _run_bash(snippet, cwd):
    return subprocess.run(["bash", "-c", snippet], cwd=str(cwd),
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          text=True, timeout=60)


def _mutated_workflow(mutations):
    """Gerçek workflow metninin mutasyonlu kopyası (dosya yazılmaz)."""
    return mutation_guard.apply_mutations(_workflow_text(), mutations)


# ---------------------------------------------------------------------------
# Bekçiler (keeper): metin → ihlal listesi ([] = kapı yerinde ve bağlı)
# ---------------------------------------------------------------------------
def ci_simulate_violations(wf):
    block = _step_block(
        wf, "ci-simulate",
        "Run CI-SIMULATE (status_checks + simulate_verify_job)")
    out = []
    if '[ "$sc_rc" -ne 0 ] || [ "$sim_rc" -ne 0 ]' not in block:
        out.append("rc karşılaştırması sökülmüş — simülasyon FAIL'ü yutulur")
    if "exit 1" not in block:
        out.append("exit 1 yok — set +e altında FAIL job'u düşürmez")
    if "continue-on-error: true" in block:
        # Gerçek YAML anahtarı aranır (`continue-on-error: true`); yorumdaki
        # "(continue-on-error kaldırıldı)" notu eşleşmemeli.
        out.append("coe + exit 1 bir arada: FAIL turuncuda ölür")
    return out


def config_drift_violations(wf):
    block = _step_block(wf, "config-drift", "Config drift fail-closed gate")
    out = []
    if "cat drift_rc.txt 2>/dev/null || echo 1" not in block:
        out.append("yokluk-varsayılanı sökülmüş — rc dosyası yazılamazsa kapı PASS")
    if 'exit "$final"' not in block:
        out.append("final rc taşınmıyor — hesaplanan karar uygulanmaz")
    return out


def refs_trend_violations(wf):
    gate = _step_block(wf, "refs-trend", "Refs trend fail-closed gate")
    build = _step_block(wf, "refs-trend", "Build refs trend table")
    out = []
    if "if [ ! -f refs-trend/refs-trend.md ]" not in gate:
        out.append("yokluk denetimi sökülmüş — tablo üretilmeden kapı PASS")
    if "exit 1" not in gate:
        out.append("yoklukta exit 1 yok")
    if "continue-on-error: true" not in build:
        out.append("üretim adımı coe'suz: geçici API hatası merge'i kilitler "
                   "(kapı required, üretim advisory — ayrım korunmalı)")
    return out


def commit_msg_violations(wf):
    dl_name = "Download commit-msg findings sidecar"
    gate_name = "Fail if commit-msg violations exist"
    dl = _step_block(wf, "commit-msg-gate", dl_name)
    gate = _step_block(wf, "commit-msg-gate", gate_name)
    out = []
    if "precommit-logs" not in dl:
        out.append("gate öncesi sidecar indirilmiyor (precommit-logs yok)")
    if "commit_msg_gate.js" not in gate:
        out.append("gate betiği bağlı değil")
    if wf.find(dl_name) > wf.find(gate_name):
        out.append("sidecar indirme gate'ten SONRA — kapı boş girdiyle koşar")
    return out


REPORTS_MANDATORY = [
    "cp _calisma/CIKTI/M0_TOOLKIT_DENETIM_RAPORU.md      reports/",
    "cp _calisma/CIKTI/REFERANS_KANIT_DENETIMI.md        reports/",
    "cp _calisma/CIKTI/SEMBOLIK_ISPAT_RAPORU.md          reports/",
]


def reports_bundle_violations(wf):
    block = _step_block(wf, "reports", "Bundle markdown reports")
    out = []
    for line in REPORTS_MANDATORY:
        if line not in block:
            out.append("zorunlu kopya kaymış: %s" % line)
    for line in block.splitlines():
        s = line.strip()
        for mandatory in REPORTS_MANDATORY:
            if s.startswith(mandatory.split("      reports/")[0].strip()):
                if "|| true" in s:
                    out.append("zorunlu kopya yutulabilir: %s" % s)
    if "continue-on-error" in block:
        out.append("bundle coe taşırsa eksik rapor turuncuda ölür")
    return out


# 2026-10-24 (PR #93) itibarıyla a11y kapısı TEK adım değil: yüzey başına
# (dashboard / guide / landing) bir adım, her adım dark+light temasını
# döngüde koşar ve rc'yi `exit $rc` ile taşır. Bekçi üç adımı da denetler;
# tek adıma indirilmiş ya da rc taşıması sökülmüş bir gate kırmızıya düşer.
A11Y_STEPS = (
    "Run a11y gate — dashboard",
    "Run a11y gate — guide",
    "Run a11y gate — landing",
)


def a11y_gate_violations(wf):
    out = []
    for step in A11Y_STEPS:
        block = _step_block(wf, "a11y-gate", step)
        if "a11y_gate.py" not in block:
            out.append("%s: a11y gate betiği bağlı değil" % step)
        if "continue-on-error: true" in block:
            out.append("%s: a11y kapısı turuncuya düşürülmüş (advisory) — "
                       "FAIL merge'i bloke etmez" % step)
        if "|| true" in block:
            out.append("%s: a11y rc'si yutuluyor (|| true)" % step)
        if "for theme in dark light" not in block:
            out.append("%s: tema döngüsü yok — tek tema kanıtı ikiye katlanmaz"
                       % step)
        if "exit $rc" not in block:
            out.append("%s: rc taşınmıyor — tema arızası adımı düşürmez" % step)
    return out


def _run_commit_msg_gate(workdir):
    """commit_msg_gate.js'i workflow'daki gibi eval-harness ile koşturur.

    Dönüş: (failed: bool, log: str). node yoksa SkipTest.
    """
    node = shutil.which("node")
    if node is None:
        raise unittest.SkipTest("node kurulu değil — JS kapı koşamaz")
    body = COMMIT_MSG_GATE.read_text(encoding="utf-8")
    harness = ("const core = { _failed: null, "
               "setFailed(m) { this._failed = String(m); } };\n"
               "(async () => {\n" + body + "\n})().then(() => {\n"
               "if (core._failed !== null) { "
               "console.log('GATE-FAILED: ' + core._failed); "
               "process.exitCode = 1; }\n"
               "}).catch((e) => { console.log('GATE-ERROR: ' + e.message); "
               "process.exitCode = 2; });\n")
    proc = subprocess.run(
        [node, "-e", harness],
        cwd=str(workdir), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, timeout=60)
    return proc.returncode != 0, proc.stdout + proc.stderr


class TestCISimulateGate(unittest.TestCase):
    def test_real_workflow_is_green(self):
        self.assertEqual(ci_simulate_violations(_workflow_text()), [])

    def test_mutation_missing_rc_compare_is_caught(self):
        wf = _mutated_workflow([(
            'if [ "$sc_rc" -ne 0 ] || [ "$sim_rc" -ne 0 ]; then',
            "if false; then")])
        self.assertIn("rc karşılaştırması",
                      " ".join(ci_simulate_violations(wf)))

    def test_mutation_exit_zero_is_caught(self):
        wf = _mutated_workflow([(
            '            echo "CI-SIMULATE FAIL: status_checks=$sc_rc '
            'simulate_verify_job=$sim_rc" >&2\n            exit 1',
            '            echo "CI-SIMULATE FAIL" >&2\n            exit 0')])
        self.assertIn("exit 1 yok",
                      " ".join(ci_simulate_violations(wf)))


class TestConfigDriftGate(unittest.TestCase):
    def test_real_workflow_is_green(self):
        self.assertEqual(config_drift_violations(_workflow_text()), [])

    def test_missing_rc_file_defaults_to_fail(self):
        # `|| echo 1` yoksa `$(cat ...)` boş döner, `$rc != 0` tutmaz → PASS.
        self.assertIn("cat drift_rc.txt 2>/dev/null || echo 1",
                      _step_block(_workflow_text(), "config-drift",
                                  "Config drift fail-closed gate"))

    def test_missing_inputs_fail_closed_live(self):
        """Davranışsal: boş dizinde kapı rc!=0 vermeli (fail-closed)."""
        with tempfile.TemporaryDirectory(prefix="driftgate_") as td:
            proc = _run_bash(
                "rc=$(cat drift_rc.txt 2>/dev/null || echo 1)\n"
                "diffrc=$(cat diffdrift_rc.txt 2>/dev/null || echo 0)\n"
                "final=0\n"
                "[ \"$rc\" != \"0\" ] && final=$rc\n"
                "[ \"$diffrc\" != \"0\" ] && final=$diffrc\n"
                "exit \"$final\"", td)
            self.assertNotEqual(
                proc.returncode, 0,
                "kapı girdisiz PASS döndü — yokluk yeşil sayılıyor: %r" % proc)

    def test_clean_inputs_pass_live(self):
        """Negatif kontrol: rc=0 girdilerinde kapı 0 verir (körü körüne kırmızı değil)."""
        with tempfile.TemporaryDirectory(prefix="driftgate_") as td:
            pathlib.Path(td, "drift_rc.txt").write_text("0\n", encoding="utf-8")
            pathlib.Path(td, "diffdrift_rc.txt").write_text("0\n", encoding="utf-8")
            proc = _run_bash(
                "rc=$(cat drift_rc.txt 2>/dev/null || echo 1)\n"
                "diffrc=$(cat diffdrift_rc.txt 2>/dev/null || echo 0)\n"
                "final=0\n"
                "[ \"$rc\" != \"0\" ] && final=$rc\n"
                "[ \"$diffrc\" != \"0\" ] && final=$diffrc\n"
                "exit \"$final\"", td)
            self.assertEqual(proc.returncode, 0,
                             "temiz girdide kapı kırmızı — bekçi fazla sıkı: %r" % proc)

    def test_mutation_absence_default_is_caught(self):
        wf = _mutated_workflow([(
            "        run: |\n"
            "          rc=$(cat drift_rc.txt 2>/dev/null || echo 1)",
            "        run: |\n"
            "          rc=$(cat drift_rc.txt 2>/dev/null || echo 0)")])
        self.assertIn("yokluk-varsayılanı",
                      " ".join(config_drift_violations(wf)))

    def test_mutation_dropped_final_exit_is_caught(self):
        wf = _mutated_workflow([(
            '          exit "$final"', "          exit 0")])
        self.assertIn("final rc",
                      " ".join(config_drift_violations(wf)))


class TestRefsTrendGate(unittest.TestCase):
    SNIPPET = ('if [ ! -f refs-trend/refs-trend.md ]; then\n'
               '  echo "REFS-TREND P0" >&2\n'
               '  exit 1\n'
               'fi\n')

    def test_real_workflow_is_green(self):
        self.assertEqual(refs_trend_violations(_workflow_text()), [])

    def test_missing_table_fails_live(self):
        with tempfile.TemporaryDirectory(prefix="refsgate_") as td:
            proc = _run_bash(self.SNIPPET, td)
            self.assertEqual(proc.returncode, 1,
                             "tablo yokken kapı 0 döndü: %r" % proc)

    def test_present_table_passes_live(self):
        with tempfile.TemporaryDirectory(prefix="refsgate_") as td:
            d = pathlib.Path(td, "refs-trend")
            d.mkdir()
            (d / "refs-trend.md").write_text("# trend\n", encoding="utf-8")
            proc = _run_bash(self.SNIPPET, td)
            self.assertEqual(proc.returncode, 0,
                             "tablo varken kapı kırmızı: %r" % proc)

    def test_mutation_gate_exit_zero_is_caught(self):
        wf = _mutated_workflow([(
            '                 "required kapı PASS edemez (fail-closed)" >&2\n'
            "            exit 1",
            '                 "required kapı PASS edemez (fail-closed)" >&2\n'
            "            exit 0")])
        self.assertIn("exit 1 yok", " ".join(refs_trend_violations(wf)))

    def test_mutation_build_step_promoted_to_blocking_is_caught(self):
        wf = _mutated_workflow([(
            "      - name: Build refs trend table\n"
            "        continue-on-error: true",
            "      - name: Build refs trend table")])
        self.assertIn("üretim adımı coe'suz",
                      " ".join(refs_trend_violations(wf)))


class TestCommitMsgGate(unittest.TestCase):
    def test_real_workflow_is_green(self):
        self.assertEqual(commit_msg_violations(_workflow_text()), [])

    def test_missing_sidecar_fails_live(self):
        """Sidecar indirilemezse kapı PASS edemez (fail-closed)."""
        with tempfile.TemporaryDirectory(prefix="cmsg_") as td:
            (pathlib.Path(td) / "logs").mkdir()
            failed, log = _run_commit_msg_gate(td)
            self.assertTrue(failed, "sidecar yokken kapı PASS: %s" % log)
            self.assertIn("commit_msg_findings.json yok", log)

    def test_corrupt_sidecar_fails_live(self):
        with tempfile.TemporaryDirectory(prefix="cmsg_") as td:
            logs = pathlib.Path(td) / "logs"
            logs.mkdir()
            (logs / "commit_msg_findings.json").write_text("{bozuk", encoding="utf-8")
            failed, log = _run_commit_msg_gate(td)
            self.assertTrue(failed, "bozuk sidecar PASS: %s" % log)

    def test_violations_fail_live(self):
        with tempfile.TemporaryDirectory(prefix="cmsg_") as td:
            logs = pathlib.Path(td) / "logs"
            logs.mkdir()
            (logs / "commit_msg_findings.json").write_text(
                '{"checked": 2, "violations": [{"commit": "abc", '
                '"subject": "wip", "detail": "kısa"}]}', encoding="utf-8")
            failed, log = _run_commit_msg_gate(td)
            self.assertTrue(failed, "ihlal varken kapı PASS: %s" % log)

    def test_clean_passes_live(self):
        """Negatif kontrol: temiz sidecar PASS (kapı körü körüne kırmızı değil)."""
        with tempfile.TemporaryDirectory(prefix="cmsg_") as td:
            logs = pathlib.Path(td) / "logs"
            logs.mkdir()
            (logs / "commit_msg_findings.json").write_text(
                '{"checked": 3, "violations": []}', encoding="utf-8")
            failed, log = _run_commit_msg_gate(td)
            self.assertFalse(failed, "temiz sidecar FAIL: %s" % log)

    def test_mutation_sidecar_name_is_caught(self):
        wf = _mutated_workflow([(
            "      - name: Download commit-msg findings sidecar\n"
            "        continue-on-error: true\n"
            "        uses: actions/download-artifact@v7\n"
            "        with:\n"
            "          name: precommit-logs",
            "      - name: Download commit-msg findings sidecar\n"
            "        continue-on-error: true\n"
            "        uses: actions/download-artifact@v7\n"
            "        with:\n"
            "          name: other-logs")])
        self.assertIn("precommit-logs",
                      " ".join(commit_msg_violations(wf)))

    def test_mutation_gate_script_detached_is_caught(self):
        wf = _mutated_workflow([("commit_msg_gate.js",
                                 "commit_msg_gate_disabled.js")])
        self.assertIn("gate betiği",
                      " ".join(commit_msg_violations(wf)))


class TestReportsBundle(unittest.TestCase):
    def test_real_workflow_is_green(self):
        self.assertEqual(reports_bundle_violations(_workflow_text()), [])

    def test_mutation_swallowed_copy_is_caught(self):
        wf = _mutated_workflow([(
            "          cp _calisma/CIKTI/REFERANS_KANIT_DENETIMI.md        reports/",
            "          cp _calisma/CIKTI/REFERANS_KANIT_DENETIMI.md        "
            "reports/ || true")])
        self.assertIn("zorunlu kopya yutulabilir",
                      " ".join(reports_bundle_violations(wf)))

    def test_mutation_non_blocking_bundle_is_caught(self):
        wf = _mutated_workflow([(
            "      - name: Bundle markdown reports\n        run: |",
            "      - name: Bundle markdown reports\n"
            "        continue-on-error: true\n        run: |")])
        self.assertIn("bundle coe",
                      " ".join(reports_bundle_violations(wf)))


class TestA11yGate(unittest.TestCase):
    """Gerçek a11y kapısı (CLS pinlerinin yerine — bkz. modül docstring'i)."""

    def test_real_workflow_is_green(self):
        self.assertEqual(a11y_gate_violations(_workflow_text()), [])

    def test_mutation_advisory_downgrade_is_caught(self):
        wf = _mutated_workflow([(
            "      - name: Run a11y gate — dashboard\n        shell: bash",
            "      - name: Run a11y gate — dashboard\n"
            "        continue-on-error: true\n        shell: bash")])
        self.assertIn("turuncuya",
                      " ".join(a11y_gate_violations(wf)))

    def test_mutation_swallowed_rc_is_caught(self):
        wf = _mutated_workflow([(
            '              --output "a11y_dashboard_${theme}.json" || rc=1',
            '              --output "a11y_dashboard_${theme}.json" || true')])
        self.assertIn("|| true", " ".join(a11y_gate_violations(wf)))

    def test_mutation_missing_theme_loop_is_caught(self):
        wf = _mutated_workflow([(
            "          rc=0\n          for theme in dark light; do\n"
            "            python3 _calisma/CIKTI/a11y_gate.py \\\n"
            "              --base-url \"http://127.0.0.1:$A11Y_PORT\" \\\n"
            "              --page /guide.html",
            "          rc=0\n          for theme in dark; do\n"
            "            python3 _calisma/CIKTI/a11y_gate.py \\\n"
            "              --base-url \"http://127.0.0.1:$A11Y_PORT\" \\\n"
            "              --page /guide.html")])
        self.assertIn("tema döngüsü yok",
                      " ".join(a11y_gate_violations(wf)))

    def test_mutation_missing_rc_exit_is_caught(self):
        wf = _mutated_workflow([(
            "              --output \"a11y_landing_${theme}.json\" || rc=1\n"
            "          done\n          exit $rc",
            "              --output \"a11y_landing_${theme}.json\" || rc=1\n"
            "          done\n          true")])
        self.assertIn("rc taşınmıyor",
                      " ".join(a11y_gate_violations(wf)))


if __name__ == "__main__":
    unittest.main()
