import pathlib
import sys
import unittest
from unittest import mock

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import gen_publish_artifact_list as gen


class TestArtifactList(unittest.TestCase):
    def test_render_is_sorted_and_counted(self):
        self.assertEqual(gen.render({"z-artifact": "job", "a-artifact": "job"}),
                         "**Artifact listesi (2):**\n- `a-artifact`\n- `z-artifact`")

    def test_update_replaces_only_artifact_block(self):
        text = "before\n**Artifact listesi (1):**\n- `old`\n\n**Not:** keep\nafter"
        self.assertEqual(gen.update(text, {"new": "job"}),
                         "before\n**Artifact listesi (1):**\n- `new`\n\n**Not:** keep\nafter")

    def test_update_rejects_missing_markers(self):
        with self.assertRaises(ValueError):
            gen.update("no list", {})

    def test_check_detects_real_doc_drift(self):
        text = "**Artifact listesi (1):**\n- `old`\n\n**Not:** x"
        self.assertFalse(gen.check_text(text, {"new": "job"}))

    def test_check_passes_for_generated_doc(self):
        from gen_repro_manifest import ARTIFACT_JOBS
        text = gen.update("**Artifact listesi (0):**\n\n**Not:** x", ARTIFACT_JOBS)
        self.assertTrue(gen.check_text(text, ARTIFACT_JOBS))


if __name__ == "__main__":
    unittest.main()
