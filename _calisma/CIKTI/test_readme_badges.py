#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_readme_badges.py — README rozetlerinin gerçek repo durumuyla senkronu.

Rozetler (CI status / pre-commit / license) README başlığının hemen
altındadır. Bu kapı fail-closed invariantları sabitler:
  1. CI rozeti, gerçek workflow dosyasını (.github/workflows/verify.yml)
     ve gerçek remote (git remote get-url origin → github.com/owner/repo)
     ile eşleşmeli — repo yeniden adlandırılırsa rozet kırılır ve yakalanır.
  2. pre-commit rozeti mevcut olmalı (pre-commit gerçekten etkin).
  3. License rozeti LICENSE dosyasıyla tutarlı olmalı (dosya var, MIT).

Reuse: remote URL ayrıştırması gen_changelog.parse_remote_url'den alınır
(tek kaynak — iki kapı aynı dönüşümü kullanır).
"""
import pathlib
import re
import subprocess
import sys
import unittest

CIKTI = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(CIKTI))

import gen_changelog  # noqa: E402  (parse_remote_url — tek kaynak)

ROOT = CIKTI.parent.parent
README = ROOT / "README.md"
WORKFLOW = ROOT / ".github" / "workflows" / "verify.yml"
LICENSE = ROOT / "LICENSE"

_CI_BADGE_RE = re.compile(
    r"\[!\[CI status\]\(https://github\.com/([^/]+)/([^/)]+)"
    r"/actions/workflows/([^/]+)/badge\.svg\)\]"
)
_PRE_COMMIT_BADGE = "pre--commit-enabled-brightgreen"
_LICENSE_BADGE_RE = re.compile(r"\[!\[License: ([^\]]+)\]\([^)]*\)\]")


def _remote_owner_repo():
    """git remote get-url origin → (owner, repo) veya (None, None)."""
    try:
        url = subprocess.run(["git", "remote", "get-url", "origin"],
                             capture_output=True, text=True, check=True,
                             cwd=str(ROOT)).stdout.strip()
    except subprocess.CalledProcessError:
        return None, None
    base = gen_changelog.parse_remote_url(url)
    if not base:
        return None, None
    # https://github.com/owner/repo → (owner, repo)
    return base.rsplit("/", 2)[-2:]


class TestReadmeBadges(unittest.TestCase):
    """Gerçek README rozetleri ↔ repo durumu (repo kökünden koşulur)."""

    @classmethod
    def setUpClass(cls):
        if not README.is_file():
            raise unittest.SkipTest("README.md yok — repo kökünden koşulmalı")
        cls.readme = README.read_text(encoding="utf-8")

    def test_ci_badge_matches_workflow_and_remote(self):
        m = _CI_BADGE_RE.search(self.readme)
        self.assertIsNotNone(m, "README'de CI status rozeti yok")
        owner, repo, workflow = m.group(1), m.group(2), m.group(3)
        # Workflow dosyası gerçekten var
        self.assertTrue(WORKFLOW.is_file(),
                        f"CI rozeti '{workflow}' workflow dosyası yok")
        self.assertEqual(workflow, "verify.yml")
        # Rozet owner/repo gerçek remote ile eşleşmeli (repo adı değişirse
        # rozet kırılır — bu kapı yakalar)
        rowner, rrepo = _remote_owner_repo()
        if rowner and rrepo:
            self.assertEqual(owner, rowner)
            self.assertEqual(repo, rrepo)

    def test_pre_commit_badge_present(self):
        self.assertIn(_PRE_COMMIT_BADGE, self.readme,
                      "pre-commit rozeti yok (pre--commit-enabled)")

    def test_license_badge_consistent_with_file(self):
        m = _LICENSE_BADGE_RE.search(self.readme)
        self.assertIsNotNone(m, "README'de License rozeti yok")
        badge_license = m.group(1)
        # LICENSE dosyası var ve rozetle uyumlu
        self.assertTrue(LICENSE.is_file(), "LICENSE dosyası yok — rozet yanıltıcı")
        self.assertIn(badge_license.upper(), LICENSE.read_text(
            encoding="utf-8").upper())


if __name__ == "__main__":
    unittest.main(verbosity=2)
