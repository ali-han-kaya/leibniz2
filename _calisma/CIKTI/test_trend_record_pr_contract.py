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


class TrendRecordLossProof(unittest.TestCase):
    """Kayıp koruması + fail-closed merge yolu (koşum 37297101317 kanıtı).

    5 Ekim koşumu YEŞİL bitti ama ölçüm main'e girmedi: `gh pr create`
    repo ayarı yüzünden yetkisiz, adım bunu `|| echo` ile yutup 0 döndü.
    Ölçüm bot dalında sıkıştı (main 6 / dal 7 satır) ve sonraki `--force`
    push onu kalıcı olarak silecekti. İki sözleşme burada kilitleniyor.
    """

    @classmethod
    def setUpClass(cls):
        cls._body = record_step_text()

    def test_branch_record_is_merged_not_overwritten(self):
        """Dal kaydı üstüne yazılmaz; birleştirici çalıştırılır."""
        self.assertIn("trend_record_merge.py", self._body,
                      "kayıp koruması yok: dalda main'de olmayan ölçüm "
                      "force-push ile kalıcı olarak silinir")
        self.assertIn("--branch-file", self._body)

    def test_merge_result_is_committed_with_the_measurement(self):
        self.assertIn("git commit --amend --no-edit", self._body,
                      "birleştirilen kayıt aynı commit'te taşınmazsa PR "
                      "ölçümü içermez")

    def test_missing_merge_path_is_fail_closed(self):
        """PR kurulamazsa adım kırmızı: 'ölçüm merge yolunda değil' ≠ başarı."""
        self.assertIn("FAIL: trend kaydı için PR yolu kurulamadı", self._body)
        # PR yolu iki kez denenir (list → create → list); ikisi de boşsa çıkış 1
        self.assertGreaterEqual(self._body.count("gh pr list"), 2)
        no_pr = self._body.index("PR yolu kurulamadı")
        tail = self._body[no_pr:no_pr + 700]
        self.assertIn("exit 1", tail,
                      "PR yoksa adım 0 dönmeli — bu, sessiz kayıp tam olarak "
                      "5 Ekim'de yaşanan durumdu")

    def test_auto_merge_failure_is_fail_closed(self):
        m = re.search(r"gh pr merge.*?exit 1", self._body, re.S)
        self.assertIsNotNone(
            m, "auto-merge başarısızlığı sessizce yutuluyor — kayıt merge "
               "beklerken koşum yeşil görünür")

    def test_tolerant_success_claim_is_removed(self):
        """Eski yorum 'ölçüm yine bot dalında güvende' diyordu — ölçüldü ki
        YANLIŞ: kayıt main'e girmiyor ve sonraki push onu siliyor."""
        self.assertNotIn("ölçüm yine bot dalında güvende", self._body)
        self.assertNotIn("kayıp yok — koşum 35590265995", self._body,
                         "bu gerekçe ölçümle çürütüldü (koşum 37297101317: "
                         "kayıt bot dalında sıkıştı)")


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
