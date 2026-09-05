#!/usr/bin/env python3
"""verify.yml trigger-split sözleşmesi: push-only vs pull_request kapıları.

Kural (fail-closed): PR'da koşan comment/yorum bölümleri `== 'pull_request'`
ile gated iken, push-koşullu job'lar (`refs-trend`, `audit-live-ci`) PR'a
kilitlenmemeli (`!= 'pull_request'` — yani job-level if'lerinde
`== 'pull_request'` OLMAMALI). Bir comment adımı PR kapısını kaybederse veya
bir push-only job yanlışlıkla PR'a kilitlenirse → commit bloke.

Not: `config-drift`, push'ta da koşan bloklayıcı drift kapısıdır (required
check); yalnızca 'Post config drift findings' ADIMI PR-gated'tır — kural bu
ayrımı adım düzeyinde doğrular. `manifest-comment` job'ı ise tamamen
PR-only'dır.
"""
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "verify.yml"

# PR-only'da koşması gereken comment/yorum bölümleri: (job_id, adım_marker).
# marker None ise job'ın tamamı PR-only'dır; değilse o job içindeki adımdır.
PR_ONLY_SECTIONS = (
    ("manifest-comment", None),              # Manifest PR comment job — tamamen PR
    ("budget-comment", None),                # Budget + pre-commit PR comment job — tamamen PR
    ("config-drift", "Post config drift findings as PR comment"),
    ("verify", "Parse + comment unit test failures"),
)

# Push-koşullu job'lar PR'a kilitlenmemeli (`!= 'pull_request'`).
PUSH_ONLY_JOBS = ("refs-trend", "audit-live-ci")

PR_GATE = "== 'pull_request'"
PUSH_GATE = "== 'push'"


def job_block(text, job_id):
    m = re.search(rf"^  {re.escape(job_id)}:\n(.*?)(?=^  [a-z0-9_-]+:|\Z)",
                  text, re.M | re.S)
    return m.group(1) if m else None


def step_block(text, name_marker):
    # Adım adı aynı satırda geçmeli (satır-içi `[^\n]*`) — DOTALL `.*`
    # yanlışlıkla ilk `- name:` satırına çapadan en son adıma kaymıştı.
    pattern = rf"^      - name: [^\n]*{re.escape(name_marker)}[^\n]*\n" \
              rf"(?P<body>[\s\S]*?)(?=^      - |^  [a-z0-9_-]+:|\Z)"
    m = re.search(pattern, text, re.M)
    return f"- name: {name_marker}\n{m.group('body')}" if m else None


class WorkflowTriggerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = WORKFLOW.read_text(encoding="utf-8")

    def test_pr_comment_sections_carry_pull_request_gate(self):
        # Her PR comment bölümü `== 'pull_request'` gated olmalı.
        for job_id, marker in PR_ONLY_SECTIONS:
            blk = job_block(self.text, job_id)
            self.assertIsNotNone(blk, f"{job_id} job bulunamadı")
            if marker is not None:
                blk = step_block(blk, marker)
                self.assertIsNotNone(
                    blk, f"{job_id}: '{marker}' adımı bulunamadı")
            self.assertIn(PR_GATE, blk,
                          f"'{marker or job_id}' PR comment bölümü "
                          f"{PR_GATE} kapısını taşımalı")

    def test_push_only_jobs_are_not_pull_request_restricted(self):
        # Push-koşullu job'lar `!= 'pull_request'`: job-level if'lerinde
        # `== 'pull_request'` OLMAMALI (PR'a kilitlenmemeli).
        for job_id in PUSH_ONLY_JOBS:
            blk = job_block(self.text, job_id)
            self.assertIsNotNone(blk, f"{job_id} job bulunamadı")
            self.assertNotIn(PR_GATE, blk,
                             f"'{job_id}' PR'a kilitlenmemeli "
                             f"({PR_GATE} içermemeli)")

    def test_push_gated_step_not_pull_request(self):
        # `== 'push'` ile gated bir adım (label sync) PR'a kilitlenmemiş.
        # Kural testinin aslında iki yönü ayırabildiğini doğrular.
        blk = step_block(self.text, "Sync label definitions")
        self.assertIsNotNone(blk, "label sync adımı yok")
        self.assertIn(PUSH_GATE, blk)
        self.assertNotIn(PR_GATE, blk)

    def test_both_push_and_pull_gates_exist(self):
        # Workflow'da hem PR-only hem push-koşullu kapı mevcut (kural anlamlı).
        self.assertGreaterEqual(len(re.findall(PR_GATE, self.text)), 1)
        self.assertGreaterEqual(len(re.findall(PUSH_GATE, self.text)), 1)


if __name__ == "__main__":
    unittest.main()