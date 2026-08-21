#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_check_python3_shell.py — check_python3_shell.py kapısı.

Workflow ayrıştırma + denetim mantığını ağsız ve deterministik doğrular:
geçerli Python `shell: python3 {0}` adımı PASS, kabuk komutu FAIL,
bash adımları kapsam dışı (PASS). stdlib unittest.
"""
import os
import pathlib
import sys
import unittest

CIKTI = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(CIKTI))

import check_python3_shell as cps  # noqa: E402


def wf(step_body):
    """Adım gövdesini gerçek workflow formatına sarar."""
    return ("name: verify\n"
            "on: [push]\n"
            "jobs:\n"
            "  verify:\n"
            "    runs-on: ubuntu-latest\n"
            "    steps:\n" + step_body)


class TestParse(unittest.TestCase):
    def test_parse_shell_and_run(self):
        text = wf("""      - name: Manifest
        shell: python3 {0}
        run: |
          import json
          print("ok")
""")
        steps = cps.parse_steps(text)
        self.assertEqual(len(steps), 1)
        self.assertEqual(steps[0]["shell"], "python3 {0}")
        self.assertEqual(steps[0]["run_kind"], "block")
        self.assertIn("import json", steps[0]["run_source"])

    def test_parse_inline_run(self):
        text = wf("""      - name: X
        shell: python3
        run: import json
""")
        steps = cps.parse_steps(text)
        self.assertEqual(steps[0]["run_kind"], "inline")
        self.assertEqual(steps[0]["run_source"], "import json")

    def test_parse_uses_step_no_run(self):
        text = wf("""      - uses: actions/checkout@v7
      - name: Y
        shell: bash
        run: echo hi
""")
        steps = cps.parse_steps(text)
        self.assertEqual(len(steps), 2)
        self.assertIsNone(steps[0]["run_source"])

    def test_parse_multiple_steps(self):
        text = wf("""      - name: A
        shell: python3 {0}
        run: |
          x = 1
      - name: B
        shell: bash
        run: |
          ls -la
""")
        steps = cps.parse_steps(text)
        self.assertEqual(len(steps), 2)
        self.assertEqual(steps[0]["name"], "A")
        self.assertEqual(steps[1]["name"], "B")
        # B bloğu A'nın run'una sızmamalı
        self.assertNotIn("ls -la", steps[0]["run_source"])
        self.assertIn("ls -la", steps[1]["run_source"])


class TestCheckStep(unittest.TestCase):
    def test_valid_python_pass(self):
        step = {"name": "M", "shell": "python3 {0}",
                "run_source": "import json\n"
                              "d = {'a': 1}\n"
                              "print(json.dumps(d))\n",
                "run_kind": "block"}
        v, d = cps.check_step(step)
        self.assertEqual(v, "PASS", d)

    def test_shell_commands_blocked(self):
        # kabuk komutu python3-shell altında → SyntaxError (compile kapısı)
        step = {"name": "M", "shell": "python3 {0}",
                "run_source": "cd _calisma/CIKTI\n"
                              "python3 verify_delivery.py\n",
                "run_kind": "block"}
        v, d = cps.check_step(step)
        self.assertEqual(v, "FAIL", d)
        self.assertIn("Python değil", d)

    def test_echo_pattern_caught(self):
        # `echo "hi"` Python olarak DERLENİR ama kabuk kalıbı → FAIL
        step = {"name": "M", "shell": "python3",
                "run_source": 'echo "merhaba"\n', "run_kind": "block"}
        v, d = cps.check_step(step)
        self.assertEqual(v, "FAIL", d)
        self.assertIn("echo", d)

    def test_and_and_dollar_patterns(self):
        step = {"name": "M", "shell": "python3 {0}",
                "run_source": "x = 1\n"
                              "cd /tmp && python3 y.py\n"
                              "echo $HOME\n",
                "run_kind": "block"}
        v, d = cps.check_step(step)
        self.assertEqual(v, "FAIL", d)
        self.assertIn("&&", d)
        self.assertIn("ortam değişkeni", d)  # $HOME kalıbı etiketi

    def test_bash_step_out_of_scope(self):
        step = {"name": "B", "shell": "bash",
                "run_source": "cd /tmp && ls -la\n", "run_kind": "block"}
        v, d = cps.check_step(step)
        self.assertEqual(v, "PASS", d)

    def test_no_shell_out_of_scope(self):
        step = {"name": "B", "shell": None,
                "run_source": "anything\n", "run_kind": "block"}
        v, d = cps.check_step(step)
        self.assertEqual(v, "PASS", d)

    def test_empty_run_fails(self):
        step = {"name": "M", "shell": "python3 {0}",
                "run_source": "", "run_kind": "inline"}
        v, d = cps.check_step(step)
        self.assertEqual(v, "FAIL", d)

    def test_python_variant_detected(self):
        step = {"name": "M", "shell": "python",
                "run_source": "print(1)\n", "run_kind": "block"}
        v, d = cps.check_step(step)
        self.assertEqual(v, "PASS", d)

    def test_shell_value_with_quotes(self):
        step = {"name": "M", "shell": "'python3 {0}'",
                "run_source": "print(1)\n", "run_kind": "block"}
        v, d = cps.check_step(step)
        self.assertEqual(v, "PASS", d)


class TestAudit(unittest.TestCase):
    def test_mixed_steps(self):
        text = wf("""      - name: Iyi
        shell: python3 {0}
        run: |
          import json
          print("ok")
      - name: Kotu
        shell: python3 {0}
        run: |
          cd /tmp && python3 run.py
""")
        findings = cps.audit(text)
        self.assertEqual(len(findings), 2)
        by_name = {f["step"]: f for f in findings}
        self.assertEqual(by_name["Iyi"]["verdict"], "PASS")
        self.assertEqual(by_name["Kotu"]["verdict"], "FAIL")

    def test_no_python3_shell(self):
        text = wf("""      - name: A
        shell: bash
        run: |
          python3 x.py
""")
        findings = cps.audit(text)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["verdict"], "PASS")

    def test_real_workflow_passes(self):
        # Gerçek verify.yml'de python3-shell adımı YOK — kapı PASS (kapsam 0).
        path = pathlib.Path(CIKTI).parent.parent / ".github" / "workflows" / "verify.yml"
        if not path.exists():
            self.skipTest("workflow yok")
        findings = cps.audit(path.read_text(encoding="utf-8"))
        fails = [f for f in findings if f["verdict"] == "FAIL"]
        self.assertEqual(fails, [])


class TestMultiWorkflow(unittest.TestCase):
    """`--workflow` çoklu yol + varsayılan glob (tüm .github/workflows/*.yml)."""

    GOOD = wf("""      - name: Iyi
        shell: python3 {0}
        run: |
          import json
          print("ok")
""")
    BAD = wf("""      - name: Kotu
        shell: python3 {0}
        run: |
          cd /tmp && python3 run.py
""")

    def setUp(self):
        import tempfile
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = pathlib.Path(self.tmp.name)
        self.a = self.dir / "a.yml"
        self.b = self.dir / "b.yml"
        self.a.write_text(self.GOOD, encoding="utf-8")
        self.b.write_text(self.BAD, encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_audit_file_report(self):
        r = cps.audit_file(str(self.a))
        self.assertEqual(r["verdict"], "PASS")
        self.assertEqual(r["python3_shell_steps"], 1)
        r2 = cps.audit_file(str(self.b))
        self.assertEqual(r2["verdict"], "FAIL")
        self.assertEqual(r2["fail"], 1)

    def test_main_multi_workflow_json(self):
        rc = cps.main(["--workflow", str(self.a), str(self.b), "--json"])
        self.assertEqual(rc, 1)  # b FAIL → genel FAIL

    def test_main_multi_workflow_json_content(self):
        import io
        import json
        out = io.StringIO()
        err = io.StringIO()
        old_out, old_err = sys.stdout, sys.stderr
        sys.stdout, sys.stderr = out, err
        try:
            rc = cps.main(["--workflow", str(self.a), str(self.b), "--json"])
        finally:
            sys.stdout, sys.stderr = old_out, old_err
        self.assertEqual(rc, 1)
        report = json.loads(out.getvalue())
        self.assertEqual(report["verdict"], "FAIL")
        self.assertEqual(len(report["workflows"]), 2)
        by_path = {os.path.basename(r["path"]): r for r in report["files"]}
        self.assertEqual(by_path["a.yml"]["verdict"], "PASS")
        self.assertEqual(by_path["b.yml"]["verdict"], "FAIL")

    def test_main_all_good_returns_zero(self):
        rc = cps.main(["--workflow", str(self.a)])
        self.assertEqual(rc, 0)

    def test_main_missing_file_exit_2(self):
        rc = cps.main(["--workflow", str(self.dir / "yok.yml")])
        self.assertEqual(rc, 2)

    def test_resolve_default_globs_all_workflows(self):
        # Varsayılan glob: .github/workflows/*.yml — yeni workflow dosyaları
        # kapıya otomatik girer (tek komutta tümü denetlenir).
        wf_dir = pathlib.Path(CIKTI).parent.parent / ".github" / "workflows"
        paths = cps.resolve_workflows([])
        self.assertIn(str(wf_dir / "verify.yml"), paths)

    def test_resolve_deduplicates(self):
        paths = cps.resolve_workflows([str(self.a), str(self.a), str(self.b)])
        self.assertEqual(paths, sorted({str(self.a), str(self.b)}))

    def test_default_glob_main_returns_zero_on_real_repo(self):
        # Tek komut (--workflow'suz) gerçek repo'da PASS vermeli.
        rc = cps.main([])
        self.assertEqual(rc, 0)


if __name__ == "__main__":
    unittest.main()
