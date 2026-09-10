#!/usr/bin/env python3
"""Focused E2E contract for REPRO_ARTIFACT_JOBS override provenance."""
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent
GEN = HERE / "gen_repro_manifest.py"


class TestReproArtifactJobsOverride(unittest.TestCase):
    def test_override_artifact_is_pinned_in_manifest(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            artifacts = root / "artifacts"
            artifacts.mkdir()
            (artifacts / "ci-simulate").mkdir()
            (artifacts / "ci-simulate" / "result.json").write_text(
                '{"ok": true, "source": "cli"}\n', encoding="utf-8"
            )
            out = root / "manifest"
            result = subprocess.run(
                [sys.executable, str(GEN), "--artifacts-dir", str(artifacts),
                 "--out-dir", str(out)],
                env={**__import__("os").environ,
                     "REPRO_ARTIFACT_JOBS": '{"ci-simulate": "override-verify"}',
                     "REPRO_MANIFEST_ALLOW_NO_YAML": "1"},
                capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
            jobs = manifest["provenance"]["artifact_jobs"]
            self.assertEqual(jobs["ci-simulate"], "override-verify")
            self.assertTrue(
                any("ci-simulate" in name for name in manifest.get("files", {}))
                or "ci_simulate" in manifest
            )


if __name__ == "__main__":
    unittest.main()
