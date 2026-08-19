#!/usr/bin/env python3
"""test_check_commit_messages.py — check_commit_messages.py regresyon kapısı.

check_message() commit_msg_hook.sh'ı gerçekten çağırır (tek kaynak — kurallar
hook'ta yaşar). Test, geçerli başlık / format ihlali / uzunluk / noise /
merge-revert izni yollarını kapsar. stdlib unittest — ek bağımlılık yok.
"""
import pathlib
import sys
import unittest

CIKTI = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(CIKTI))

import check_commit_messages as ccm  # noqa: E402

HOOK = str(CIKTI / "commit_msg_hook.sh")


class TestCheckMessage(unittest.TestCase):
    def check(self, msg):
        rc, detail = ccm.check_message(msg, HOOK)
        return rc, detail

    def test_valid_subject(self):
        rc, _ = self.check("verify.yml: bütçe + pre-commit yorumunu birleştir\n\nGövde burada.\n")
        self.assertEqual(rc, 0)

    def test_missing_colon_space(self):
        rc, detail = self.check("sabitlenmedi-başlık")
        self.assertEqual(rc, 1)
        self.assertIn("formatında olmalı", detail)

    def test_too_long_subject(self):
        rc, detail = self.check("docs: " + "x" * 80)
        self.assertEqual(rc, 1)
        self.assertIn("sınır: 72", detail)

    def test_noise_marker(self):
        rc, detail = self.check("wip: yarım iş")
        self.assertEqual(rc, 1)
        self.assertIn("noise/marker", detail)

    def test_smoke_marker(self):
        rc, _ = self.check("smoke test: dene")
        self.assertEqual(rc, 1)

    def test_merge_and_revert_allowed(self):
        self.assertEqual(self.check("Merge branch 'x' into main")[0], 0)
        self.assertEqual(self.check('Revert "docs: önceki"')[0], 0)

    def test_template_placeholder(self):
        rc, detail = self.check("docs: <konu başlığı>")
        self.assertEqual(rc, 1)
        self.assertIn("placeholder", detail)


if __name__ == "__main__":
    unittest.main()
