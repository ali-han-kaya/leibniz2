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


def workflow_text() -> str:
    return WF.read_text(encoding="utf-8")


def step_body(name: str) -> str:
    """Adı verilen step'in gövdesi (sonraki step'e kadar)."""
    text = workflow_text()
    m = re.search(r"- name: %s\n(.*?)(?=\n      - name: |\Z)" % re.escape(name),
                  text, re.S)
    assert m, "workflow'ta '%s' adımlı step yok" % name
    return m.group(1)


class TrendArtifactContract(unittest.TestCase):
    """Haftalık koşum svg/json kanıtını artifact olarak yayımlar.

    Ölçülen boşluk: determinism_trend_badge.py svg + json ÜRETİYOR ama
    haftalık workflow onu hiç çalıştırmıyor ve artifact yüklemiyordu.
    Yani üretilen kanıt koşumdan sonra yalnız PR metninde kalan ham jsonl
    satırıydı; görsel/kanıt taşıyıcısı kayboluyordu. Sözleşme:
      1) üretim adımı determinism_trend_badge.py'yi çalıştırır
      2) kayıt adımından SONRA gelir (yeni satırı görsün)
      3) artifact yükleme adımı her iki dosyayı da kapsar
      4) if-no-files-found: error (fail-closed — sessizce boş artifact yok)
      5) retention-days tanımlı (kanıt bir haftada kaybolmasın)
      6) yükleme if: always() — PR yolu çökse bile kanıt kurtarılır
    """

    GEN = "Generate determinism-trend svg/json"
    UPLOAD = "Upload determinism-trend artifact"

    def test_generation_step_runs_badge_generator(self):
        body = step_body(self.GEN)
        self.assertIn("determinism_trend_badge.py", body)

    def test_generation_step_happens_after_recording(self):
        text = workflow_text()
        self.assertIn("- name: Record trend measurement", text)
        rec = text.index("- name: Record trend measurement")
        gen = text.index("- name: %s" % self.GEN)
        self.assertLess(rec, gen,
                        "üretim, kayıttan sonra olmalı (yeni satırı görmeli)")

    def test_generation_also_writes_json_and_svg_explicitly(self):
        # Varsayılan out-dir kök altına yazıyor; artifact yolu bunu
        # göreli tutmalı ki upload adımı aynı dosyaları bulsun.
        body = step_body(self.GEN)
        self.assertIn("--out-dir", body)
        self.assertRegex(body, r"determinism-trend\.svg")
        self.assertRegex(body, r"determinism-trend\.json")

    def test_artifact_upload_step_exists_and_carries_both_files(self):
        body = step_body(self.UPLOAD)
        self.assertIn("actions/upload-artifact", body)
        self.assertRegex(body, r"determinism-trend\.svg")
        self.assertRegex(body, r"determinism-trend\.json")

    def test_artifact_upload_is_fail_closed_and_retained(self):
        body = step_body(self.UPLOAD)
        self.assertRegex(body, r"if-no-files-found:\s*error",
                         "artifact yoksa sessiz geçmemeli (fail-closed)")
        self.assertRegex(body, r"retention-days:\s*\d+")

    def test_artifact_upload_survives_pr_path_failure(self):
        # Commit/PR adımı çökse bile ölçüm kanıtı kurtarılmalı: PR yolu
        # repo tarihinde Actions-PR-yasak senaryosunda başarısız oluyor.
        text = workflow_text()
        m = re.search(r"(- name: %s\n)((?:(?!- name: ).)*?)(?=\n      - name: |\Z)"
                      % re.escape(self.UPLOAD), text, re.S)
        assert m, "yükleme adımı yok"
        self.assertIn("if: always()", m.group(2),
                      "kanıt PR yolu çökse de yüklenmeli")


if __name__ == "__main__":
    unittest.main()
