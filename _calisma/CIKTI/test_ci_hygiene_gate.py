#!/usr/bin/env python3
"""test_ci_hygiene_gate.py — CI hijyen kapısı sözleşmesi (fail-closed).

Üç kural, tüm .github/workflows/*.yml'ye sabit:

  K1 permissions: her workflow'da top-level `permissions:` haritası VAR
     (yoksa GitHub default broad-GITHUB_TOKEN sessizce devreye girer —
     en-yetkili-olmayan-ihlal).
  K2 timeout-minutes: her job'da VAR; 1..120 aralığında int. `true` gibi
     bool değerler reddedilir (bool, int alt-tipidir — kapı ayrım yapar).
  K3 concurrency: her workflow'da top-level, non-empty `group` (aynı ref'te
     üst üste binen koşumlar eski-yeni çakışır; verify.yml referans-standart).

Kapı betiği ci_hygiene_gate.py aynı kuralları hook/CI yüzeyinde koşar:
rc 0=PASS, 1=FAIL(≥1 ihlal), 2=kullanım/ortam hatası — sessiz-PASS yok.
"""
import pathlib
import subprocess
import sys
import tempfile
import textwrap
import unittest

_TMP = pathlib.Path(tempfile.gettempdir())

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent.parent
WORKFLOWS = ROOT / ".github" / "workflows"
GATE = HERE / "ci_hygiene_gate.py"

try:
    import yaml  # noqa: F401 — ci_hygiene_gate'in import-yüzeyi; yoksa SKIP
    HAS_YAML = True
except ImportError:
    HAS_YAML = False


def run_gate(workflows_dir):
    return subprocess.run(
        [sys.executable, str(GATE), "--workflow", str(workflows_dir)],
        capture_output=True, text=True, timeout=30,
    )


def load(p):
    return yaml.safe_load(p.read_text(encoding="utf-8"))


@unittest.skipUnless(HAS_YAML, "PyYAML yok — kapı import-yüzeyi koşulamaz (dürüst-SKIP)")
class TestWorkflowHygieneInvariants(unittest.TestCase):
    """Repo yüzeyi: mevcut workflow'lar kapıyı geçmeli (regresyon-blokajı)."""

    def test_all_workflows_pass_the_gate(self):
        r = run_gate(WORKFLOWS)
        self.assertEqual(
            r.returncode, 0,
            f"CI hijyen ihlalleri:\n{r.stdout}{r.stderr}",
        )

    def test_all_jobs_have_timeout_minutes(self):
        for p in sorted(WORKFLOWS.glob("*.yml")):
            for jid, job in (load(p).get("jobs") or {}).items():
                to = (job or {}).get("timeout-minutes")
                self.assertIsInstance(
                    to, int, f"{p.name}:{jid}: timeout-minutes yok/geçersiz")
                self.assertTrue(
                    1 <= to <= 120, f"{p.name}:{jid}: aralık-dışı {to!r}")

    def test_all_workflows_have_permissions_and_concurrency(self):
        for p in sorted(WORKFLOWS.glob("*.yml")):
            doc = load(p)
            self.assertIn("permissions", doc, p.name)
            conc = doc.get("concurrency")
            self.assertIsInstance(conc, dict, f"{p.name}: concurrency yok")
            self.assertTrue(str(conc.get("group") or "").strip(),
                            f"{p.name}: concurrency.group boş")


@unittest.skipUnless(HAS_YAML, "PyYAML yok — kapı import-yüzeyi koşulamaz (dürüst-SKIP)")
class TestGateFailClosed(unittest.TestCase):
    """Kapı yüzeyi: her ihlal-tipi tek tek rc=1 üretmeli."""

    def gate_fails(self, yml, needle):
        with tempfile.TemporaryDirectory() as td:
            (pathlib.Path(td) / "wf.yml").write_text(
                textwrap.dedent(yml), encoding="utf-8")
            r = run_gate(td)
        self.assertEqual(r.returncode, 1, f"rc={r.returncode}\n{r.stdout}")
        self.assertIn(needle, r.stdout)

    def test_missing_permissions_fails(self):
        self.gate_fails("""\
            name: x
            on: push
            concurrency: {group: g}
            jobs:
              a:
                runs-on: ubuntu-latest
                timeout-minutes: 5
                steps: []
        """, "permissions")

    def test_missing_job_timeout_fails(self):
        self.gate_fails("""\
            name: x
            on: push
            permissions: {contents: read}
            concurrency: {group: g}
            jobs:
              a:
                runs-on: ubuntu-latest
                steps: []
        """, "timeout-minutes")

    def test_missing_concurrency_fails(self):
        self.gate_fails("""\
            name: x
            on: push
            permissions: {contents: read}
            jobs:
              a:
                runs-on: ubuntu-latest
                timeout-minutes: 5
                steps: []
        """, "concurrency")

    def test_bool_timeout_rejected(self):
        # bool, int alt-tipidir — `timeout-minutes: true` yasal görünmesin.
        self.gate_fails("""\
            name: x
            on: push
            permissions: {contents: read}
            concurrency: {group: g}
            jobs:
              a:
                runs-on: ubuntu-latest
                timeout-minutes: true
                steps: []
        """, "timeout-minutes")

    def test_empty_dir_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            r = run_gate(td)
        self.assertEqual(r.returncode, 1)
        self.assertIn("workflow", r.stdout)

    def test_missing_dir_is_usage_error(self):
        r = run_gate(_TMP / "yok-boyle-dizin-xyz")
        self.assertEqual(r.returncode, 2)


if __name__ == "__main__":
    unittest.main()
