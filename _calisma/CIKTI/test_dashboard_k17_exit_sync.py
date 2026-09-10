#!/usr/bin/env python3
import os
import pathlib
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1].parent
CIKTI = ROOT / "_calisma" / "CIKTI"
SMOKE = CIKTI / "dashboard_smoke.sh"
MIRROR = CIKTI / "sync_verify_mirror.sh"


class DashboardK17ExitSyncTests(unittest.TestCase):
    def _run_pair(self, mirror_dir, preview_dir, lean_dir):
        env = dict(os.environ, ROOT=str(ROOT), MIRROR_DIR=str(mirror_dir),
                   PREVIEW_MIRROR=str(preview_dir),
                   LEAN_MIRROR_DIR=str(lean_dir))
        k17 = subprocess.run(["bash", str(MIRROR), "--check"], env=env,
                             capture_output=True, text=True)
        smoke = subprocess.run(["bash", str(SMOKE), "--check"], env=dict(
            env, PY=str(pathlib.Path(os.sys.executable)),
            SIM_DIR=str(mirror_dir / "smoke"), SMOKE_SYNC="0"),
            capture_output=True, text=True)
        return k17, smoke

    def test_fresh_mirror_same_failure_code(self):
        with tempfile.TemporaryDirectory(prefix="k17-sync-") as td:
            root = pathlib.Path(td)
            k17, smoke = self._run_pair(root / "verify", root / "preview", root / "lean")
            self.assertEqual(k17.returncode, 1)
            self.assertEqual(smoke.returncode, k17.returncode)

    def test_missing_source_is_environment_error_for_both(self):
        with tempfile.TemporaryDirectory(prefix="k17-sync-") as td:
            env = dict(os.environ, ROOT=str(pathlib.Path(td)),
                       MIRROR_DIR=str(pathlib.Path(td) / "verify"),
                       PREVIEW_MIRROR=str(pathlib.Path(td) / "preview"),
                       LEAN_MIRROR_DIR=str(pathlib.Path(td) / "lean"),
                       PY=os.sys.executable,
                       SIM_DIR=str(pathlib.Path(td) / "sim"))
            k17 = subprocess.run(["bash", str(MIRROR), "--check"], env=env,
                                 capture_output=True, text=True)
            smoke = subprocess.run(["bash", str(SMOKE), "--check"], env=env,
                                   capture_output=True, text=True)
            # K17 has a distinct source-validation code (2); the dashboard
            # wrapper fails closed before attempting a verify (1).
            self.assertEqual(k17.returncode, 2)
            self.assertEqual(smoke.returncode, 1)
            self.assertNotEqual(smoke.returncode, 0)


if __name__ == "__main__":
    unittest.main()
