#!/usr/bin/env python3
"""test_dashboard_smoke.py — dashboard_smoke.sh sözleşme testleri.

dashboard_smoke.sh (canlı dashboard PASS'ini tek komutta yeniden üreten
smoke) iki kilit davranışı garanti eder:

  1) Senkron + minimal PATH + --full + verdict PASS → exit 0 + rapor.
  2) Verdict FAIL (P0>0 veya P1>0) → exit 1 (fail-closed — yanlış yeşil yok).

Bu testler gerçek ağ/Lean/Z3 koşturmaz: SMOKE_SYNC=0 ile senkron atlanır ve
fake mirror'a yerleştirilen stub verify_delivery.py sabit bir JSON üretir.
Böylece sözleşme (env yayılımı, minimal PATH aktarımı, verdict ayrıştırma,
rapor yazımı) Linux CI'da da offline doğrulanır. Gerçek senkron adımı
test_mirror_check.py'de (K17) zaten kapsanır.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SMOKE = os.path.join(HERE, "dashboard_smoke.sh")

STUB = '''\
#!/usr/bin/env python3
"""Stub verify_delivery.py — dashboard_smoke testleri için sabit JSON."""
import json, os, sys

VERDICT = os.environ.get("STUB_VERDICT", "PASS")
P0 = int(os.environ.get("STUB_P0", "0"))
P1 = int(os.environ.get("STUB_P1", "0"))
out = {
    "tool": "stub verify_delivery.py",
    "verdict": VERDICT,
    "counts": {"P0": P0, "P1": P1},
    "findings": [],
    "pdf_pages": 33,
    "ref_count": 64,
    "layers": {
        "K6": {"label": "PDF + referanslar", "status": "PASS", "ran": True},
        "K16": {"label": "GScripts self-test", "status": "PASS", "ran": True},
        "K17": {"label": "Mirror sync", "status": "PASS", "ran": True},
    },
    "probe_path": os.environ.get("PATH", ""),
    "probe_cwd": os.getcwd(),
    "probe_dir_arg": (sys.argv[sys.argv.index("--dir") + 1]
                      if "--dir" in sys.argv else None),
    "probe_full": "--full" in sys.argv,
    "probe_json": "--json" in sys.argv,
}
json.dump(out, sys.stdout, indent=2, ensure_ascii=False)
'''


def make_stub_mirror(work):
    """Fake mirror dizini + stub verify_delivery.py kurar; path döner."""
    mirror = os.path.join(work, "verify-mirror")
    os.makedirs(mirror, exist_ok=True)
    stub_path = os.path.join(mirror, "verify_delivery.py")
    with open(stub_path, "w", encoding="utf-8") as f:
        f.write(STUB)
    os.chmod(stub_path, 0o755)
    return mirror


def run_smoke(work, verdict="PASS", p0=0, p1=0, minimal_path=None):
    """dashboard_smoke.sh'yi stub mirror + stub verdict ile koşar.

    SMOKE_SYNC=0 (senkron atlanır), MIRROR_DIR=fake, PY=sys.executable.
    CompletedProcess döner.
    """
    mirror = make_stub_mirror(work)
    env = dict(os.environ)
    env.update({
        "SMOKE_SYNC": "0",
        "MIRROR_DIR": mirror,
        "PREVIEW_MIRROR": os.path.join(work, "preview-mirror"),
        "LEAN_MIRROR_DIR": os.path.join(work, "lean-mirror"),
        "PY": sys.executable,
        "STUB_VERDICT": verdict,
        "STUB_P0": str(p0),
        "STUB_P1": str(p1),
        "SIM_DIR": os.path.join(work, "sim"),
    })
    if minimal_path is not None:
        env["MINIMAL_PATH"] = minimal_path
    return subprocess.run(["bash", SMOKE], env=env, capture_output=True,
                          text=True, timeout=300)


class TestDashboardSmokeVerdict(unittest.TestCase):
    """Verdict PASS → exit 0; FAIL → exit 1 (fail-closed)."""

    def test_pass_verdict_exit_0(self):
        with tempfile.TemporaryDirectory(prefix="dash-smoke-") as work:
            r = run_smoke(work, verdict="PASS")
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("SONUÇ: PASS", r.stdout)
            report = os.path.join(work, "sim", "dashboard_smoke_report.txt")
            self.assertTrue(os.path.isfile(report), report)
            with open(report, encoding="utf-8") as f:
                self.assertIn("SONUÇ: PASS", f.read())

    def test_fail_p0_exit_1(self):
        with tempfile.TemporaryDirectory(prefix="dash-smoke-") as work:
            r = run_smoke(work, verdict="FAIL", p0=1)
            self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
            self.assertIn("SONUÇ: FAIL", r.stdout)
            report = os.path.join(work, "sim", "dashboard_smoke_report.txt")
            with open(report, encoding="utf-8") as f:
                self.assertIn("SONUÇ: FAIL", f.read())

    def test_fail_p1_exit_1(self):
        with tempfile.TemporaryDirectory(prefix="dash-smoke-") as work:
            r = run_smoke(work, verdict="FAIL", p1=2)
            self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
            self.assertIn("SONUÇ: FAIL", r.stdout)

    def test_verify_json_persisted(self):
        with tempfile.TemporaryDirectory(prefix="dash-smoke-") as work:
            r = run_smoke(work, verdict="PASS")
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            vj = os.path.join(work, "sim", "verify.json")
            self.assertTrue(os.path.isfile(vj), vj)
            with open(vj, encoding="utf-8") as f:
                data = json.load(f)
            self.assertEqual(data["verdict"], "PASS")
            self.assertEqual(data["counts"], {"P0": 0, "P1": 0})


class TestDashboardSmokeEnv(unittest.TestCase):
    """Minimal PATH + --full + --dir stub'a doğru aktarılmalı."""

    def test_minimal_path_applied(self):
        with tempfile.TemporaryDirectory(prefix="dash-smoke-") as work:
            minimal = "/usr/bin:/bin:/usr/sbin:/sbin"
            r = run_smoke(work, minimal_path=minimal)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            vj = os.path.join(work, "sim", "verify.json")
            with open(vj, encoding="utf-8") as f:
                data = json.load(f)
            self.assertEqual(data["probe_path"], minimal)

    def test_full_and_json_flags_passed(self):
        with tempfile.TemporaryDirectory(prefix="dash-smoke-") as work:
            r = run_smoke(work)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            vj = os.path.join(work, "sim", "verify.json")
            with open(vj, encoding="utf-8") as f:
                data = json.load(f)
            self.assertTrue(data["probe_full"], "stub --full görmeli")
            self.assertTrue(data["probe_json"], "stub --json görmeli")
            self.assertIsNotNone(data["probe_dir_arg"], "stub --dir görmeli")

    def test_verify_dir_passed_to_stub(self):
        with tempfile.TemporaryDirectory(prefix="dash-smoke-") as work:
            r = run_smoke(work)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            vj = os.path.join(work, "sim", "verify.json")
            with open(vj, encoding="utf-8") as f:
                data = json.load(f)
            mirror = os.path.join(work, "verify-mirror")
            self.assertEqual(data["probe_dir_arg"], mirror)

    def test_verify_extra_appended(self):
        with tempfile.TemporaryDirectory(prefix="dash-smoke-") as work:
            mirror = make_stub_mirror(work)
            env = dict(os.environ)
            env.update({
                "SMOKE_SYNC": "0",
                "MIRROR_DIR": mirror,
                "PY": sys.executable,
                "STUB_VERDICT": "PASS",
                "SIM_DIR": os.path.join(work, "sim"),
                "VERIFY_EXTRA": "--budget 5.0 --budget-method weighted",
            })
            r = subprocess.run(["bash", SMOKE], env=env, capture_output=True,
                               text=True, timeout=300)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            vj = os.path.join(work, "sim", "verify.json")
            with open(vj, encoding="utf-8") as f:
                data = json.load(f)
            # Stub yalnızca bilinen bayrakları probe eder; extra bayraklar
            # argparse'i kırmadan geçmeli (stub argv'yi yoksayar).
            self.assertEqual(data["verdict"], "PASS")


if __name__ == "__main__":
    unittest.main()
