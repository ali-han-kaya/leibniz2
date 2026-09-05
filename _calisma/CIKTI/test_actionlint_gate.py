import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from actionlint_gate import classify


class TestActionlintGate(unittest.TestCase):
    def test_clean_pass(self):
        self.assertEqual(classify([]), ([], []))

    def test_shellcheck_is_advisory(self):
        structural, advisory = classify([
            '.github/workflows/verify.yml:10:2: shellcheck reported SC2086 (info)',
        ])
        self.assertEqual(structural, [])
        self.assertEqual(len(advisory), 1)

    def test_yaml_syntax_fails(self):
        structural, advisory = classify([
            '.github/workflows/verify.yml:10:2: syntax error: unexpected }',
        ])
        self.assertEqual(len(structural), 1)
        self.assertEqual(advisory, [])

    def test_rc1_shellcheck_only_is_success(self):
        """RC=1 is PASS when every diagnostic is shellcheck info/hint."""
        lines = [
            'verify.yml:10:2: shellcheck reported SC2086 (info)',
            'verify.yml:11:4: shellcheck hint: quote this variable',
        ]
        structural, advisory = classify(lines)
        self.assertEqual(structural, [])
        self.assertEqual(len(advisory), 2)

        with tempfile.TemporaryDirectory() as td:
            source = pathlib.Path(td, 'actionlint.log')
            sidecar = pathlib.Path(td, 'actionlint_findings.json')
            source.write_text('\n'.join(lines) + '\n', encoding='utf-8')
            result = subprocess.run([
                sys.executable, str(ROOT / 'actionlint_gate.py'),
                '--input', str(source), '--out', str(sidecar),
            ], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0)
            data = json.loads(sidecar.read_text(encoding='utf-8'))
            self.assertTrue(data['ok'])
            self.assertEqual(data['verdict'], 'WARN')
            self.assertEqual(data['structural_count'], 0)
            self.assertEqual(data['advisory_count'], 2)

    def test_cli_writes_machine_readable_sidecar(self):
        with tempfile.TemporaryDirectory() as td:
            inp, out = pathlib.Path(td) / 'lint.txt', pathlib.Path(td) / 'findings.json'
            inp.write_text('workflow.yml:1:1: shellcheck SC2086 (info)\n', encoding='utf-8')
            r = subprocess.run([sys.executable, str(ROOT / 'actionlint_gate.py'),
                                '--input', str(inp), '--out', str(out)], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0)
            data = json.loads(out.read_text(encoding='utf-8'))
            self.assertEqual(data['verdict'], 'WARN')
            self.assertEqual(data['structural_count'], 0)


if __name__ == '__main__':
    unittest.main()
