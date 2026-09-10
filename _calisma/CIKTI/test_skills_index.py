#!/usr/bin/env python3
import unittest

import check_skills_index as audit


class TestSkillsIndex(unittest.TestCase):
    def test_real_readme_lists_every_skill_directory(self):
        self.assertEqual(audit.check(), 0)

    def test_missing_skill_is_reported(self):
        text = "## Skills\n\n| Skill |\n|---|\n| `skills/verify-chain/SKILL.md` |\n"
        self.assertEqual(audit.check(text, {"verify-chain", "reproducible-pdf-build"}), 1)

    def test_stale_skill_is_reported(self):
        text = "## Skills\n\n| Skill |\n|---|\n| `skills/verify-chain/SKILL.md` |\n| `skills/old-skill/SKILL.md` |\n"
        self.assertEqual(audit.check(text, {"verify-chain"}), 1)


if __name__ == "__main__":
    unittest.main()
