import pathlib
import sys
import unittest
from unittest import mock

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import coq_evidence_smoke as smoke


class TestCoqEvidenceSmoke(unittest.TestCase):
    def test_missing_inputs_fail_closed(self):
        with mock.patch.object(smoke, "COQ_DIR", pathlib.Path("/missing")):
            self.assertEqual(smoke.main(), 1)

    def test_missing_coqtop_is_explicit_skip(self):
        class Files:
            def is_file(self):
                return True
            def read_text(self, encoding=None):
                return "8.18\n"
        with mock.patch.object(smoke, "shutil") as sh, \
             mock.patch.object(smoke, "version_file", Files(), create=True), \
             mock.patch.object(smoke, "source", Files(), create=True):
            sh.which.return_value = None
            self.assertEqual(smoke.main(), 0)

    def test_version_and_compile_pass(self):
        version = mock.Mock(stdout="The Coq Proof Assistant, version 8.18.0", stderr="", returncode=0)
        compiled = mock.Mock(stdout="", stderr="", returncode=0)
        with mock.patch.object(smoke.shutil, "which", return_value="coqtop"), \
             mock.patch.object(smoke.subprocess, "run", side_effect=[version, compiled]):
            self.assertEqual(smoke.main(), 0)

    def test_version_mismatch_blocks(self):
        version = mock.Mock(stdout="The Coq Proof Assistant, version 8.19.0", stderr="", returncode=0)
        with mock.patch.object(smoke.shutil, "which", return_value="coqtop"), \
             mock.patch.object(smoke.subprocess, "run", return_value=version):
            self.assertEqual(smoke.main(), 1)


if __name__ == "__main__":
    unittest.main()
