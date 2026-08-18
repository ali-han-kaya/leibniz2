#!/usr/bin/env python3
"""test_gen_repro_manifest.py — gen_repro_manifest.py regresyon kapısı.

PROVENANCE bölümünü (artifact → job kaynağı) denetler: precommit-logs ve
config artifact'ları verify job'undan gelir ve prefixed indirme sayesinde
bundle'da kendi adları altında işaretlenir. stdlib unittest + subprocess —
ek bağımlılık yok.
"""
import json
import os
import pathlib
import subprocess
import tempfile
import unittest

CIKTI = pathlib.Path(__file__).resolve().parent
GEN = CIKTI / "gen_repro_manifest.py"


def _run_gen(artifacts_dir, out_dir):
    r = subprocess.run(
        ["python3", str(GEN), "--artifacts-dir", artifacts_dir,
         "--out-dir", out_dir],
        capture_output=True, text=True,
    )
    return r


class TestProvenance(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name)
        self.artifacts = self.root / "all_artifacts"
        (self.artifacts / "config").mkdir(parents=True)
        (self.artifacts / "precommit-logs").mkdir(parents=True)
        (self.artifacts / "config" / "verify_delivery.config.json").write_text(
            "raw\n", encoding="utf-8")
        (self.artifacts / "precommit-logs" / "precommit.log").write_text(
            "log\n", encoding="utf-8")
        (self.artifacts / "verify_report.txt").write_text(
            "flat\n", encoding="utf-8")
        self.out = self.root / "reproducibility"

    def tearDown(self):
        self.tmp.cleanup()

    def _gen(self):
        r = _run_gen(str(self.artifacts), str(self.out))
        self.assertEqual(r.returncode, 0, r.stderr)
        return r

    def test_manifest_json_has_artifact_jobs(self):
        self._gen()
        m = json.loads((self.out / "manifest.json").read_text(encoding="utf-8"))
        jobs = m["provenance"]["artifact_jobs"]
        self.assertEqual(jobs["precommit-logs"], "verify")
        self.assertEqual(jobs["config"], "verify")
        self.assertEqual(jobs["budget"], "budget")
        self.assertEqual(jobs["repack-verify"], "repack-verify")

    def test_manifest_txt_provenance_section(self):
        self._gen()
        txt = (self.out / "manifest.txt").read_text(encoding="utf-8")
        self.assertIn("PROVENANCE (artifact → job kaynağı)", txt)
        self.assertIn("precommit-logs", txt)
        self.assertIn("prefixed (1 dosya)", txt)  # precommit-logs tek dosya

    def test_prefixed_files_present_in_bundle(self):
        self._gen()
        # gen_repro_manifest.py bundle'a kopyalar → rel yol korunmalı.
        self.assertTrue(
            (self.out / "precommit-logs" / "precommit.log").is_file())
        self.assertTrue(
            (self.out / "config" / "verify_delivery.config.json").is_file())

    def test_precommit_logs_section(self):
        # PRECOMMIT_CACHE.md dahil precommit-logs/ dosyaları CONFIG gibi ayrı
        # bölümde işaretlenir + tek-hash combined_sha256 özetlenir.
        (self.artifacts / "precommit-logs" / "PRECOMMIT_CACHE.md").write_text(
            "cache\n", encoding="utf-8")
        self._gen()
        txt = (self.out / "manifest.txt").read_text(encoding="utf-8")
        self.assertIn("PRECOMMIT LOGS ARTIFACT (ayrı bölüm)", txt)
        self.assertIn("precommit_combined_sha256", txt)
        m = json.loads((self.out / "manifest.json").read_text(encoding="utf-8"))
        pc = m["precommit_logs"]
        self.assertIn(
            "precommit-logs/PRECOMMIT_CACHE.md", pc["files"])
        self.assertTrue(len(pc["combined_sha256"]) == 64)

    def test_env_override_artifact_jobs(self):
        env = dict(os.environ)
        env["REPRO_ARTIFACT_JOBS"] = '{"precommit-logs": "custom-job"}'
        r = subprocess.run(
            ["python3", str(GEN), "--artifacts-dir", str(self.artifacts),
             "--out-dir", str(self.out)],
            capture_output=True, text=True, env=env,
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        m = json.loads((self.out / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(
            m["provenance"]["artifact_jobs"]["precommit-logs"], "custom-job")


if __name__ == "__main__":
    unittest.main()
