#!/usr/bin/env python3
import os
import pathlib
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
HOOK = ROOT / "_calisma/CIKTI/check_fallback_evidence_hook.sh"


class TestFallbackEvidenceHook(unittest.TestCase):
    def _run_with_fake_evidence(self, output, exit_code=0):
        with tempfile.TemporaryDirectory() as td:
            fake = pathlib.Path(td) / "ia_ol_fallback_evidence.py"
            fake.write_text(
                "#!/usr/bin/env python3\n"
                "import sys\n"
                f"print({output!r})\n"
                f"sys.exit({exit_code})\n",
                encoding="utf-8",
            )
            fake.chmod(0o755)
            # Hook resolves the real script by path, so temporarily replace it
            # and restore it after the subprocess (no repository mutation left).
            target = ROOT / "_calisma/CIKTI/ia_ol_fallback_evidence.py"
            original = target.read_bytes()
            mode = target.stat().st_mode
            try:
                target.write_bytes(fake.read_bytes())
                target.chmod(0o755)
                result = subprocess.run(
                    ["sh", str(HOOK)], cwd=ROOT, text=True, capture_output=True,
                )
            finally:
                target.write_bytes(original)
                target.chmod(mode)
            return result

    def test_five_of_five_passes(self):
        result = self._run_with_fake_evidence(
            "SONUÇ: PASS — 5/5 kaynak çevrimiçi doğrulandı")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_non_five_of_five_is_blocked(self):
        result = self._run_with_fake_evidence(
            "SONUÇ: FAIL — 4/5 kaynak çevrimiçi doğrulandı")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("5/5", result.stderr)

    def test_tool_failure_is_blocked(self):
        result = self._run_with_fake_evidence("", exit_code=1)
        self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
