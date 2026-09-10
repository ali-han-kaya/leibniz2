#!/usr/bin/env python3
"""E2E reproduce-job contracts for audit-refs-trend and daemon-http."""
import hashlib
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent
GEN = HERE / "gen_repro_manifest.py"
VERIFY = HERE / "verify_delivery.py"


def run(cmd, **kwargs):
    env = {**os.environ, "PYTHONPATH": str(HERE), "PYTHONWARNINGS": "ignore"}
    return subprocess.run(cmd, capture_output=True, text=True, env=env, **kwargs)


class TestReproduceArtifactSections(unittest.TestCase):
    def test_sections_are_hashed_and_k10_closes(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            artifacts = root / "all_artifacts"
            for name, payload in {
                "audit-refs-trend/audit_refs_trend.json": {"verdict": "PASS", "coverage": "61/61"},
                "daemon-http/daemon_http_report.json": {
                    "ok": True, "endpoints": {"/api/latest": 200, "/api/events": 200, "/api/run-now": 200}
                },
            }.items():
                path = artifacts / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
            out = root / "reproducibility"
            generated = run([sys.executable, str(GEN), "--artifacts-dir", str(artifacts), "--out-dir", str(out)])
            self.assertEqual(generated.returncode, 0, generated.stderr)
            manifest_path = out / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            for section_name, rel in (
                ("audit_refs_trend", "audit-refs-trend/audit_refs_trend.json"),
                ("daemon_http", "daemon-http/daemon_http_report.json"),
            ):
                section = manifest[section_name]
                self.assertEqual(section["files"][rel], hashlib.sha256((artifacts / rel).read_bytes()).hexdigest())
                expected = hashlib.sha256(
                    "".join(f"{key}\0{section['files'][key]}\n" for key in sorted(section["files"])).encode()
                ).hexdigest()
                self.assertEqual(section["combined_sha256"], expected)
                self.assertEqual(manifest["provenance"]["artifact_jobs"][section_name.replace("_", "-")], section_name.replace("_", "-"))
            verified = run([sys.executable, str(VERIFY), "--verify-manifest", str(manifest_path)])
            self.assertEqual(verified.returncode, 0, verified.stderr + verified.stdout)
            self.assertIn("audit_refs_trend", verified.stdout)
            self.assertIn("daemon_http", verified.stdout)

    def test_tampering_section_combined_hash_fails_k10(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            artifacts = root / "artifacts"
            path = artifacts / "audit-refs-trend" / "audit_refs_trend.json"
            path.parent.mkdir(parents=True)
            path.write_text('{"verdict":"PASS"}\n', encoding="utf-8")
            out = root / "manifest"
            generated = run([sys.executable, str(GEN), "--artifacts-dir", str(artifacts), "--out-dir", str(out)])
            self.assertEqual(generated.returncode, 0, generated.stderr)
            manifest_path = out / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["audit_refs_trend"]["combined_sha256"] = "0" * 64
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            verified = run([sys.executable, str(VERIFY), "--verify-manifest", str(manifest_path)])
            self.assertNotEqual(verified.returncode, 0)
            self.assertIn("audit_refs_trend", verified.stdout + verified.stderr)


if __name__ == "__main__":
    unittest.main()
