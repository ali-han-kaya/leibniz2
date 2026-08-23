#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_verify_checks.py — verify_checks() birim kapısı (mock gh + python3).

docs/publish_wrapper.sh (--verify-checks / AŞAMA 1) ve docs/publish_precheck.sh
(--verify-checks) tarafından ORTAK source edilen _calisma/CIKTI/verify_checks.sh
fonksiyonunu deterministik doğrular: gh + python3 tamamen mock'lanır (canlı ağ
yok). Fonksiyon, iki gerçek çağıran bağlamının her ikisinde de çalıştırılır:

  precheck bağlamı  — log/warn/fail = [INFO]/[UYARI]/[FAIL] printf; fail exit
                      ETMEZ (FAILED işaretler) → dönüş koduyla kapı kapanır.
  wrapper bağlamı   — log zaman damgalı; fail exit 1 → set -e altında aynı
                      kararlar.

Kapsanan çıkış dalları (status_checks.py --gh sözleşmesi):
  PASS         → exit 0 + "birebir eşleşiyor ✓"
  koruma yok   → exit 0 + UYARI (gh api 404 — publish öncesi normal)
  erişilemedi  → exit 0 + UYARI (403 yetki/ağ — fail değil)
  gerçek drift → exit 1 + "eksik/fazla check" (fail-closed)
  taban FAIL   → status_checks.py --gh'siz bile çalışmazsa exit 1

Sidecar (VERIFY_CHECKS_OUT setse): verdict PASS|WARN|FAIL + rc + note + ham
--gh --json detayı tek JSON dosyasına yazılır — PASS/WARN/FAIL üçü de kapsanır.

stdlib unittest — ek bağımlılık yok.
"""
import json
import os
import pathlib
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest

CIKTI = pathlib.Path(__file__).resolve().parent
LIB = CIKTI / "verify_checks.sh"

# Çağıran bağlamları (gerçek scriptlerdeki helper tanımları).
PRECHECK_HELPERS = (
    "log()  { printf '  [INFO] %s\\n' \"$*\"; }\n"
    "warn() { printf '  [UYARI] %s\\n' \"$*\"; }\n"
    "fail() { printf '  [FAIL] %s\\n' \"$*\"; }\n"
)
WRAPPER_HELPERS = (
    "log()  { echo \"[$(date +%H:%M:%S)] $*\"; }\n"
    "warn() { log \"UYARI: $*\"; }\n"
    "fail() { log \"HATA: $*\"; log \"SONUÇ: FAIL\"; exit 1; }\n"
)

# (ad, mock --gh çıktısı, mock exit, beklenen rc, beklenen çıktı parçaları)
SCENARIOS = {
    "pass": {
        "out": "  [PASS] Delivery verification — K1-K14 (single entry point)\n"
               "\n── PR-merge engeli smoke (koruma ayarları) ──\n"
               "  [PASS] required_status_checks.strict\n"
               "  [PASS] enforce_admins.enabled (admin bypass kapalı)\n"
               "\nSONUÇ: PASS — 12 check birebir eşleşiyor (workflow ↔ GitHub) "
               "ve merge engeli etkin",
        "exit": 0,
        "rc": 0,
        "contains": ["birebir eşleşiyor ✓"],
        "not_contains": ["[FAIL]", "[UYARI]"],
        "sidecar_verdict": "PASS",
        "sidecar_rc": 0,
        "detail_verdict": "PASS",
    },
    "not_set_up": {
        "out": "HATA: branch protection kurulu değil — HTTP 404: Not Found "
               "(gh api repos/owner/name/branches/main/protection)\n"
               "  --gh modu fail-closed: doğrulanamıyorsa exit 1.\n"
               "\nUYARI: branch protection kurulu değil — HTTP 404: Not Found\n"
               "  Kurulum: gh api -X PUT repos/.../branches/main/protection",
        "exit": 1,
        "rc": 0,
        "contains": ["UYARI", "kurulu değil"],
        "not_contains": ["[FAIL]"],
        "sidecar_verdict": "WARN",
        "sidecar_rc": 0,
        "detail_verdict": "NOT_SET_UP",
    },
    "unreadable": {
        "out": "HATA: branch protection erişilemedi (yetki/ağ) — HTTP 403: "
               "Resource not accessible by integration\n"
               "\nUYARI: branch protection erişilemedi (yetki/ağ) — HTTP 403",
        "exit": 1,
        "rc": 0,
        "contains": ["UYARI", "erişilemedi"],
        "not_contains": ["[FAIL]"],
        "sidecar_verdict": "WARN",
        "sidecar_rc": 0,
        "detail_verdict": "UNREADABLE",
    },
    "drift": {
        "out": "  [FAIL] workflow'da var ama GitHub'da yok: Commit-msg gate\n"
               "  [FAIL] workflow'da var ama GitHub'da yok: CI-SIMULATE (advisory)\n"
               "\nSONUÇ: FAIL — eksik: ['Commit-msg gate', "
               "'CI-SIMULATE (advisory)'], fazla: []\n"
               "  Düzeltme: AŞAMA 1 (b) web UI'da required check listesini "
               "yukarıdaki adlarla eşitle",
        "exit": 1,
        "rc": 1,
        "contains": ["eksik/fazla check"],
        "sidecar_verdict": "FAIL",
        "sidecar_rc": 1,
        "detail_verdict": "FAIL",
    },
}

# status_checks.py --gh --json ham detayı (sidecar'ın protection bloğu).
DETAILS = {
    "PASS": {
        "verdict": "PASS", "names_ok": True, "enforcement_ok": True,
        "missing": [], "extra": [], "repo": "owner/name", "branch": "main",
        "smoke": [{"label": "strict", "ok": True}, {"label": "enforce", "ok": True}],
    },
    "NOT_SET_UP": {
        "verdict": "NOT_SET_UP", "warning": "HTTP 404: Not Found",
        "missing": [], "extra": [], "repo": "owner/name", "branch": "main",
    },
    "UNREADABLE": {
        "verdict": "UNREADABLE", "warning": "HTTP 403: Resource not accessible",
        "missing": [], "extra": [], "repo": "owner/name", "branch": "main",
    },
    "FAIL": {
        "verdict": "FAIL", "names_ok": False, "enforcement_ok": True,
        "missing": ["Commit-msg gate"], "extra": [], "repo": "owner/name",
        "branch": "main",
        "smoke": [{"label": "strict", "ok": True}],
    },
}


class VerifyChecksBase(unittest.TestCase):
    """Mock gh/python3 kurar ve verify_checks()'i verilen bağlamda koşar."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = pathlib.Path(tempfile.mkdtemp(prefix="verify_checks_test_"))
        cls.bin = cls.tmp / "bin"
        cls.bin.mkdir()
        cls._write_mocks()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    @classmethod
    def _write_mocks(cls):
        gh = cls.bin / "gh"
        gh.write_text(
            "#!/usr/bin/env bash\n"
            'if [ "${1:-}" = "api" ] && [ "${2:-}" = "user" ]; then\n'
            '  echo "mock-user"\n'
            "  exit 0\n"
            "fi\n"
            'echo "gh: bilinmeyen çağrı: $*" >&2\n'
            "exit 1\n")
        gh.chmod(0o755)

        py = cls.bin / "python3"
        py.write_text(
            "#!/usr/bin/env bash\n"
            "# status_checks.py mock'u.\n"
            "#  - tek argüman '-' (stdin modu): verify_checks'in sidecar yazma\n"
            "#    python'unu GERÇEK python3 ile çalıştır (heredoc stdin'de).\n"
            "#  - '--json' içerir: MOCK_SC_GH_JSON_OUT (sidecar detayı).\n"
            "#  - '--gh' (--json'suz): MOCK_SC_GH_OUT (insan-okur çıktı).\n"
            "#  - başka: ad listesi (exit MOCK_SC_BASE_EXIT).\n"
            f'REAL_PY={shlex.quote(sys.executable)}\n'
            'has_json=0; has_gh=0\n'
            'for a in "$@"; do\n'
            '  if [ "$a" = "-" ]; then exec "$REAL_PY"; fi\n'
            '  [ "$a" = "--json" ] && has_json=1\n'
            '  [ "$a" = "--gh" ] && has_gh=1\n'
            "done\n"
            'if [ "$has_json" = "1" ]; then\n'
            '  [ -n "${MOCK_SC_GH_JSON_OUT:-}" ] && printf "%s\\n" "$MOCK_SC_GH_JSON_OUT"\n'
            '  exit "${MOCK_SC_GH_JSON_EXIT:-0}"\n'
            "fi\n"
            'if [ "$has_gh" = "1" ]; then\n'
            '  [ -n "${MOCK_SC_GH_OUT:-}" ] && printf "%s\\n" "$MOCK_SC_GH_OUT"\n'
            '  exit "${MOCK_SC_GH_EXIT:-0}"\n'
            "fi\n"
            '[ -n "${MOCK_SC_BASE_ERR:-}" ] && printf "%s\\n" "$MOCK_SC_BASE_ERR" >&2\n'
            'echo "Beklenen status check adları (12) — kaynak: .github/workflows/verify.yml"\n'
            'echo "  1. Delivery verification — K1-K14 (single entry point)"\n'
            'echo "GitHub ile doğrulamak için: --gh (branch protection kuruluysa)"\n'
            'exit "${MOCK_SC_BASE_EXIT:-0}"\n')
        py.chmod(0o755)

    def _run(self, helpers, scenario_key, bash_opts=(), sidecar_out=None):
        sc = SCENARIOS[scenario_key]
        env = dict(os.environ)
        env["PATH"] = str(self.bin) + os.pathsep + env.get("PATH", "")
        env["MOCK_SC_GH_OUT"] = sc["out"]
        env["MOCK_SC_GH_EXIT"] = str(sc["exit"])
        env["MOCK_SC_GH_JSON_OUT"] = json.dumps(DETAILS[sc["detail_verdict"]])
        if sidecar_out is not None:
            env["VERIFY_CHECKS_OUT"] = str(sidecar_out)
        script = (helpers
                  + f"source {shlex.quote(str(LIB))}; verify_checks")
        cmd = ["bash", *bash_opts, "-c", script]
        return subprocess.run(cmd, cwd=str(self.tmp), env=env,
                              capture_output=True, text=True)

    def _assert_scenario(self, r, key):
        sc = SCENARIOS[key]
        combined = r.stdout + r.stderr
        self.assertEqual(
            r.returncode, sc["rc"],
            f"rc beklenen {sc['rc']} — stdout={r.stdout!r} stderr={r.stderr!r}")
        for frag in sc["contains"]:
            self.assertIn(frag, combined)
        for frag in sc.get("not_contains", []):
            self.assertNotIn(frag, combined)
        # status_checks.py'nin taban koşusu gerçekten çalıştı (ad listesi).
        self.assertIn("Beklenen status check adları", r.stdout)

    def _assert_sidecar(self, path, key):
        sc = SCENARIOS[key]
        self.assertTrue(path.is_file(), f"sidecar yazılmadı: {path}")
        d = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(d["verdict"], sc["sidecar_verdict"])
        self.assertEqual(d["rc"], sc["sidecar_rc"])
        self.assertEqual(d["tool"], "verify_checks.sh")
        self.assertEqual(d["protection"]["verdict"], sc["detail_verdict"])
        self.assertIn("generated_at", d)
        self.assertIn("note", d)


class TestPrecheckContext(VerifyChecksBase):
    """publish_precheck.sh bağlamı: set -e YOK, fail exit etmez, rc ile kapı."""

    OPTS = ("-u", "-o", "pipefail")

    def test_pass(self):
        self._assert_scenario(self._run(PRECHECK_HELPERS, "pass", self.OPTS), "pass")

    def test_not_set_up_warns(self):
        self._assert_scenario(
            self._run(PRECHECK_HELPERS, "not_set_up", self.OPTS), "not_set_up")

    def test_unreadable_warns(self):
        self._assert_scenario(
            self._run(PRECHECK_HELPERS, "unreadable", self.OPTS), "unreadable")

    def test_drift_fails_closed(self):
        self._assert_scenario(
            self._run(PRECHECK_HELPERS, "drift", self.OPTS), "drift")


class TestWrapperContext(VerifyChecksBase):
    """publish_wrapper.sh bağlamı: set -euo pipefail, fail exit 1."""

    OPTS = ("-e", "-u", "-o", "pipefail")

    def test_pass(self):
        self._assert_scenario(self._run(WRAPPER_HELPERS, "pass", self.OPTS), "pass")

    def test_not_set_up_warns(self):
        self._assert_scenario(
            self._run(WRAPPER_HELPERS, "not_set_up", self.OPTS), "not_set_up")

    def test_unreadable_warns(self):
        self._assert_scenario(
            self._run(WRAPPER_HELPERS, "unreadable", self.OPTS), "unreadable")

    def test_drift_fails_closed(self):
        self._assert_scenario(
            self._run(WRAPPER_HELPERS, "drift", self.OPTS), "drift")


class TestStatusChecksBaseFailure(VerifyChecksBase):
    """status_checks.py taban koşusu (--gh'siz) bile FAIL ederse fail-closed."""

    def test_base_run_failure_exits_1(self):
        env = dict(os.environ)
        env["PATH"] = str(self.bin) + os.pathsep + env.get("PATH", "")
        env["MOCK_SC_BASE_EXIT"] = "1"
        env["MOCK_SC_BASE_ERR"] = "PyYAML bulunamadı: yaml.load"
        script = (PRECHECK_HELPERS
                  + f"source {shlex.quote(str(LIB))}; verify_checks")
        r = subprocess.run(["bash", "-u", "-o", "pipefail", "-c", script],
                           cwd=str(self.tmp), env=env,
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 1)
        self.assertIn("çalışmadı", r.stdout)


class TestSidecar(VerifyChecksBase):
    """VERIFY_CHECKS_OUT setse JSON sidecar'ı doğru yazılır (PASS/WARN/FAIL)."""

    OPTS = ("-u", "-o", "pipefail")

    def _run_with_sidecar(self, key):
        out = self.tmp / f"sidecar_{key}.json"
        r = self._run(PRECHECK_HELPERS, key, self.OPTS, sidecar_out=out)
        self._assert_scenario(r, key)
        self._assert_sidecar(out, key)

    def test_pass_writes_sidecar(self):
        self._run_with_sidecar("pass")

    def test_not_set_up_writes_sidecar(self):
        self._run_with_sidecar("not_set_up")

    def test_unreadable_writes_sidecar(self):
        self._run_with_sidecar("unreadable")

    def test_drift_writes_sidecar(self):
        self._run_with_sidecar("drift")

    def test_no_out_no_sidecar(self):
        # VERIFY_CHECKS_OUT verilmezse hiçbir dosya yazılmaz (varsayılan davranış).
        out = self.tmp / "should_not_exist.json"
        r = self._run(PRECHECK_HELPERS, "pass", self.OPTS)
        self.assertEqual(r.returncode, 0)
        self.assertFalse(out.exists())


if __name__ == "__main__":
    unittest.main()
