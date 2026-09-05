#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""İlk publish AŞAMA 0-4 akışının doc ↔ wrapper senkron kapısı."""
import pathlib
import sys
import unittest

CIKTI = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(CIKTI))
import check_doc_wrapper_sync as sync  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[2]
DOC = ROOT / "docs" / "PUBLISH_SCENARIO.md"
WRAPPER = ROOT / "docs" / "publish_wrapper.sh"

ANCHORS = [
    ("AŞAMA 0 precheck", ["bash docs/publish_precheck.sh"]),
    ("repo oluşturma", ["gh repo create", "--public"]),
    ("status checks", ["status_checks.py --gh"]),
    ("remote ekleme", ["git remote add origin"]),
    ("push", ["git push -u origin main"]),
    ("CI listeleme", ["gh run list", "--json databaseId"]),
    ("CI izleme", ["gh run watch", "--exit-status"]),
    ("CI artifact doğrulama", ["gh run view", "--json artifacts"]),
    ("AŞAMA 4 branch protection", ["test/protection-check", "gh pr create", "gh pr merge"]),
]


class TestFullPublishDocSync(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = DOC.read_text(encoding="utf-8")
        cls.wrapper = WRAPPER.read_text(encoding="utf-8")

    def test_stage_0_to_4_anchors_exist_in_both_sources(self):
        missing = sync.check(self.doc, self.wrapper, ANCHORS)
        self.assertEqual([], missing, f"AŞAMA 0-4 doc↔wrapper drift: {missing}")

    def test_wrapper_has_first_publish_and_stage4_paths(self):
        self.assertIn("AŞAMA 1 — GitHub repo oluştur", self.wrapper)
        self.assertIn("if [ \"$WITH_STAGE4\" = \"1\" ]", self.wrapper)
        self.assertIn("--with-stage4", self.wrapper)

    def test_doc_describes_full_flow(self):
        self.assertRegex(self.doc, r"AŞAMA 0")
        self.assertRegex(self.doc, r"AŞAMA 1")
        self.assertRegex(self.doc, r"AŞAMA 2")
        self.assertRegex(self.doc, r"AŞAMA 3")
        self.assertRegex(self.doc, r"AŞAMA 4")


if __name__ == "__main__":
    unittest.main()
