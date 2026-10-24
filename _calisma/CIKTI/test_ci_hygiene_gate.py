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
import re
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

# Kapı (ci_hygiene_gate.py) PyYAML yoksa rc=2 verir (dürüst ortam hatası,
# sessiz-PASS yok). Bu dosya bu yüzden İKİ katmanlıdır: yaml VARSA kapıyı
# gerçekten koşturan davranış testleri, yaml YOKSA (ör. CI) metin-tabanlı
# statik katman koşar — dosya PyYAML'sız ortamda da KIRMIZI olabilir.
try:
    import yaml
    HAVE_YAML = True
except ImportError:  # pragma: no cover — ortama bağlı
    yaml = None
    HAVE_YAML = False


def run_gate(workflows_dir):
    return subprocess.run(
        [sys.executable, str(GATE), "--workflow", str(workflows_dir)],
        capture_output=True, text=True, timeout=30,
    )


def load(p):
    return yaml.safe_load(p.read_text(encoding="utf-8"))


@unittest.skipUnless(HAVE_YAML, "PyYAML gerekli — kapı rc=2 verir")
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


@unittest.skipUnless(HAVE_YAML, "PyYAML gerekli — kapı rc=2 verir")
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


class TestStaticTextLayer(unittest.TestCase):
    """PyYAML'sız ortamda da koşan metin katmanı (fail-closed).

    Kapı yaml'sız rc=2 verir; bu sınıf üç kuralın VARLIĞINI dosya metninden
    doğrular. Davranış testlerinden daha zayıftır (int aralığı/bool ayrımı
    yapmaz) ama her ortamda koşar: workflow'lardan biri permissions/concurrency/
    job-timeout kaybederse bu katman KIRMIZI olur — tüm-skip değildir.
    """

    JOB = re.compile(r"^  [A-Za-z0-9_-]+:\s*$")

    def test_every_workflow_has_top_level_permissions(self):
        for p in sorted(WORKFLOWS.glob("*.yml")):
            lines = p.read_text(encoding="utf-8").splitlines()
            self.assertTrue(
                any(ln.startswith("permissions:") for ln in lines),
                f"{p.name}: top-level permissions yok")

    def test_every_workflow_has_concurrency_group(self):
        for p in sorted(WORKFLOWS.glob("*.yml")):
            lines = p.read_text(encoding="utf-8").splitlines()
            i = next((n for n, ln in enumerate(lines)
                      if ln.startswith("concurrency:")), None)
            self.assertIsNotNone(i, f"{p.name}: top-level concurrency yok")
            group = ""
            for ln in lines[i + 1:]:
                if not ln.startswith((" ", "\t")):
                    break
                if ln.strip().startswith("group:"):
                    group = ln.split(":", 1)[1].strip()
                    break
            self.assertTrue(group, f"{p.name}: concurrency.group yok/boş")

    def test_every_job_declares_timeout_minutes(self):
        for p in sorted(WORKFLOWS.glob("*.yml")):
            lines = p.read_text(encoding="utf-8").splitlines()
            j = next((n for n, ln in enumerate(lines)
                      if ln.startswith("jobs:")), None)
            self.assertIsNotNone(j, f"{p.name}: jobs yok")
            starts = [n for n in range(j + 1, len(lines))
                      if self.JOB.match(lines[n])]
            self.assertTrue(starts, f"{p.name}: job yok")
            for start in starts:
                body = []
                for ln in lines[start + 1:]:
                    if self.JOB.match(ln) or (ln and not ln.startswith((" ", "\t"))):
                        break
                    body.append(ln)
                jid = lines[start].strip()
                self.assertTrue(
                    any(ln.strip().startswith("timeout-minutes:") for ln in body),
                    f"{p.name}:{jid}: timeout-minutes yok")


if __name__ == "__main__":
    unittest.main()
