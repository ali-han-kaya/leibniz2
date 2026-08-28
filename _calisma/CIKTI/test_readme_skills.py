#!/usr/bin/env python3
import unittest

import check_skills_index as audit


class TestReadmeSkillsSection(unittest.TestCase):
    def test_readme_has_skills_heading_and_current_entries(self):
        text = audit.README.read_text(encoding="utf-8")
        self.assertRegex(text, r"(?im)^##\s+Skills\s*$")
        expected = audit.skill_names()
        listed = audit.readme_skill_names(text)
        self.assertEqual(listed, expected)
        for name in expected:
            self.assertIn(f"skills/{name}/SKILL.md", text)


if __name__ == "__main__":
    unittest.main()
