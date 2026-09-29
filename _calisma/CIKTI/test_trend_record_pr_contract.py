"""test_trend_record_pr_contract.py — determinism-trend kayıt-adımı PR-sözleşmesi.

Branch protection main'e bot-push'u bloklar (GH006; schedule koşumu
35580855610 kanıtı: deney+kayıt success, commit-push failure). Kayıt
adımı bu yüzden bot-dalı + PR yoluyla main'e inmek ZORUNDA. Sözleşme:
  1) kayıt adımı bare `git push` (default-branch push) İÇERMEZ
  2) TREND_BRANCH bot-dalı env'de pinli; push o dala yapılır
  3) permissions pull-requests: write içerir (gh pr create/merge)
  4) PR oluşturma/merge yolu (gh pr ...) mevcut
  5) fail-closed boş-stage koruması korunur (eski invariant)
"""
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
WF = ROOT / ".github" / "workflows" / "determinism-trend.yml"


def record_step_text() -> str:
    text = WF.read_text(encoding="utf-8")
    m = re.search(
        r"- name: Commit trend record\n(.*?)(?=\n      - name: )", text, re.S
    )
    assert m, "Commit trend record adımı workflow'ta yok"
    return m.group(1)


class TrendRecordPRContract(unittest.TestCase):
    def test_step_does_not_push_default_branch(self):
        body = record_step_text()
        bare = [ln for ln in body.splitlines() if re.match(r"^\s*git push\s*$", ln)]
        self.assertEqual(
            bare, [], "bare `git push` = default-branch push — GH006'e düşer"
        )

    def test_step_pushes_bot_branch(self):
        body = record_step_text()
        self.assertIn("TREND_BRANCH", body, "bot-dalı env'de pinli olmalı")
        self.assertRegex(
            body, r"git push\s+--force\s+origin\s+\"HEAD:\$TREND_BRANCH\""
        )

    def test_permissions_include_pull_requests_write(self):
        text = WF.read_text(encoding="utf-8")
        m = re.search(r"^permissions:\n((?:\s+.*\n)+)", text, re.M)
        assert m, "permissions bloğu yok"
        self.assertIn("pull-requests: write", m.group(1))

    def test_step_ensures_pr_exists(self):
        body = record_step_text()
        self.assertIn("gh pr list", body)
        self.assertIn("gh pr create", body)

    def test_step_attempts_auto_merge_nonfatally(self):
        body = record_step_text()
        self.assertIn("gh pr merge", body)
        self.assertRegex(body, r"gh pr merge.*--auto")

    def test_empty_stage_fail_closed_guard_kept(self):
        body = record_step_text()
        self.assertIn("stage boş", body)
        self.assertIn("exit 1", body)


if __name__ == "__main__":
    unittest.main()
