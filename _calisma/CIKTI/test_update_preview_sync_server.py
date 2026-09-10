#!/usr/bin/env python3
import os
import pathlib
import subprocess
import tempfile
import unittest


HERE = pathlib.Path(__file__).resolve().parent
SCRIPT = HERE / "update_preview.sh"
SERVER = HERE / "preview_server.py"


class SyncServerTests(unittest.TestCase):
    def test_sync_server_copies_server_atomically_to_preview_dir(self):
        with tempfile.TemporaryDirectory() as td:
            preview = pathlib.Path(td) / "preview"
            env = dict(os.environ, HOME=td, DST=str(preview / "preview.html"))
            result = subprocess.run(
                ["bash", str(SCRIPT), "--sync-server"],
                cwd=str(HERE), env=env, text=True,
                capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((preview / "preview_server.py").read_bytes(),
                             SERVER.read_bytes())
            self.assertFalse(list(preview.glob("preview_server.py.tmp.*")))

    def test_sync_server_fails_closed_when_source_is_missing(self):
        with tempfile.TemporaryDirectory() as td:
            result = subprocess.run(
                ["bash", str(SCRIPT), "--sync-server"],
                cwd=td, env=dict(os.environ, HOME=td, SERVER_SRC=str(pathlib.Path(td) / "missing.py")), text=True,
                capture_output=True, timeout=10)
            self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
