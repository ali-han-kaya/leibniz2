import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import check_coq_axioms as scanner


class CoqAxiomScannerTests(unittest.TestCase):
    def _scan(self, source):
        with tempfile.TemporaryDirectory() as directory:
            pathlib.Path(directory, "Content.v").write_text(source, encoding="utf-8")
            return scanner.scan_coq_dir(directory)

    def test_clean_source_passes(self):
        ok, findings = self._scan("Theorem t : True. Proof. exact I. Qed.\n")
        self.assertTrue(ok)
        self.assertEqual(findings, [])

    def test_admitted_and_top_level_axiom_fail(self):
        ok, findings = self._scan("Admitted.\nAxiom unsafe_fact : False.\n")
        self.assertFalse(ok)
        self.assertEqual([f["kind"] for f in findings], ["admitted", "axiom"])

    def test_comments_and_strings_are_ignored(self):
        ok, findings = self._scan('(* Admitted. *)\nDefinition s := "Axiom fake".\n')
        self.assertTrue(ok)
        self.assertEqual(findings, [])

    def test_parameter_is_a_gap(self):
        ok, findings = self._scan("Parameter hidden : False.\n")
        self.assertFalse(ok)
        self.assertEqual(findings[0]["kind"], "parameter")

    def test_missing_directory_fails_closed(self):
        ok, findings = scanner.scan_coq_dir("/definitely/missing/coq")
        self.assertFalse(ok)
        self.assertEqual(findings[0]["kind"], "error")


if __name__ == "__main__":
    unittest.main()
