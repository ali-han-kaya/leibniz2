#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_label_gate_contracts.py — label gate canlı etiket okuma sözleşmesi.

label_gate.js / label_gate_p1.js ile verify.yml label-gate job'ları
arasındaki tutarlılığı denetler:

  1) JS dosyaları var mı, okunabiliyor mu?
  2) Her JS'te doğru etiket adı (precommit-p0 / precommit-p1) aranıyor mu?
  3) Her JS'te setFailed çağrısı var mı (fail-closed)?
  4) Her JS'te listLabelsOnIssue çağrısı var mı (canlı okuma)?
  5) verify.yml'deki label-gate job'ı doğru JS dosyasını okuyor mu?
  6) label-gate-p1 job'ı doğru JS dosyasını okuyor mu?
  7) Her iki job if: pull_request koşuluyla mı çalışıyor?
  8) Her iki job pull-requests: read izni mi istiyor?

CI advisory: FAIL = sözleşme ihlali (drift); build'i bloke etmez
(if: always() + continue-on-error workflow adımında).
"""
import os
import re
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))

JS_P0 = os.path.join(HERE, "github_scripts", "label_gate.js")
JS_P1 = os.path.join(HERE, "github_scripts", "label_gate_p1.js")
WORKFLOW = os.path.join(REPO, ".github", "workflows", "verify.yml")


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


class TestLabelGateJSFiles(unittest.TestCase):
    """JS dosyaları mevcut ve okunabilir."""

    def test_p0_exists(self):
        self.assertTrue(os.path.isfile(JS_P0), f"yok: {JS_P0}")

    def test_p1_exists(self):
        self.assertTrue(os.path.isfile(JS_P1), f"yok: {JS_P1}")

    def test_p0_readable(self):
        content = _read(JS_P0)
        self.assertGreater(len(content), 10)

    def test_p1_readable(self):
        content = _read(JS_P1)
        self.assertGreater(len(content), 10)


class TestLabelGateContracts(unittest.TestCase):
    """Her JS'te sözleşme koşulları sağlanmalı."""

    @classmethod
    def setUpClass(cls):
        cls.p0 = _read(JS_P0)
        cls.p1 = _read(JS_P1)
        cls.wf = _read(WORKFLOW)

    # ── Eşiket adı sözleşmesi ──────────────────────────────────────────────

    def test_p0_references_precommit_p0(self):
        """label_gate.js 'precommit-p0' etiketini aramalı."""
        self.assertIn("precommit-p0", self.p0)

    def test_p1_references_precommit_p1(self):
        """label_gate_p1.js 'precommit-p1' etiketini aramalı."""
        self.assertIn("precommit-p1", self.p1)

    def test_p0_does_not_reference_p1(self):
        """label_gate.js p1 etiketine karışmamalı (sınır netliği)."""
        self.assertNotIn("precommit-p1", self.p0)

    def test_p1_does_not_reference_p0(self):
        """label_gate_p1.js p0 etiketine karışmamalı (sınır netliği)."""
        self.assertNotIn("precommit-p0", self.p1)

    # ── API çağrısı sözleşmesi ─────────────────────────────────────────────

    def test_p0_calls_listLabelsOnIssue(self):
        """label_gate.js listLabelsOnIssue ile canlı etiket okumalı."""
        self.assertIn("listLabelsOnIssue", self.p0)

    def test_p1_calls_listLabelsOnIssue(self):
        """label_gate_p1.js listLabelsOnIssue ile canlı etiket okumalı."""
        self.assertIn("listLabelsOnIssue", self.p1)

    # ── Fail-closed sözleşmesi ─────────────────────────────────────────────

    def test_p0_has_setFailed(self):
        """label_gate.js etiket varsa core.setFailed çağırmalı."""
        self.assertIn("setFailed", self.p0)

    def test_p1_has_setFailed(self):
        """label_gate_p1.js etiket varsa core.setFailed çağırmalı."""
        self.assertIn("setFailed", self.p1)

    # ── Guardrails ─────────────────────────────────────────────────────────

    def test_p0_no_unexpected_labels(self):
        """label_gate.js yalnızca precommit-p0 etiketini kontrol etmeli."""
        # label_gate.js 'some(l => l.name ===' kalıbını kullanmalı
        match = re.search(r"l\.name\s*===\s*'([^']+)'", self.p0)
        self.assertIsNotNone(match, "JS label name match pattern bulunamadı")
        self.assertEqual(match.group(1), "precommit-p0")

    def test_p1_no_unexpected_labels(self):
        """label_gate_p1.js yalnızca precommit-p1 etiketini kontrol etmeli."""
        match = re.search(r"l\.name\s*===\s*'([^']+)'", self.p1)
        self.assertIsNotNone(match, "JS label name match pattern bulunamadı")
        self.assertEqual(match.group(1), "precommit-p1")


class TestWorkflowLabelGateJobs(unittest.TestCase):
    """verify.yml label-gate job'ları doğru JS dosyalarını okuyor."""

    @classmethod
    def setUpClass(cls):
        cls.wf = _read(WORKFLOW)

    def _extract_job_scripts(self, job_id):
        """Bir job'un github_script adımında okunan JS dosya yolunu çıkar."""
        # Job başlangıç satırını bul
        lines = self.wf.splitlines()
        start = None
        for i, line in enumerate(lines):
            if line.strip() == f"{job_id}:" and line.startswith("  "):
                start = i
                break
        self.assertIsNotNone(start, f"job '{job_id}' bulunamadı")
        # Job bloğu: start'dan itibaren readFileSync('...label_gate...js') ara
        for i in range(start, min(start + 80, len(lines))):
            # Tam dosya adı eşleşmesi: label_gate.js VEYA label_gate_p1.js
            m = re.search(r"readFileSync\('([^']+/label_gate(?:_p1)?\.js)'", lines[i])
            if m:
                return m.group(1)
        self.fail(f"job '{job_id}' JS dosyası okunamadı")

    def test_label_gate_reads_p0_js(self):
        """label-gate job'u label_gate.js okumalı."""
        js = self._extract_job_scripts("label-gate")
        self.assertEqual(js, "_calisma/CIKTI/github_scripts/label_gate.js")

    def test_label_gate_p1_reads_p1_js(self):
        """label-gate-p1 job'u label_gate_p1.js okumalı."""
        js = self._extract_job_scripts("label-gate-p1")
        self.assertEqual(js, "_calisma/CIKTI/github_scripts/label_gate_p1.js")

    def test_both_gates_are_pr_only(self):
        """Her iki gate da pull_request'te koşmalı."""
        for job_id in ("label-gate", "label-gate-p1"):
            pattern = rf"{re.escape(job_id)}:\s*\n(.*?)(?=\n  \w|\Z)"
            m = re.search(pattern, self.wf, re.S)
            self.assertIsNotNone(m, f"job '{job_id}' bulunamadı")
            block = m.group(1)
            self.assertIn("pull_request", block,
                          f"job '{job_id}' pull_request koşulu içermiyor")

    def test_both_gates_have_pr_read_permission(self):
        """Her iki gate da pull-requests: read izni istemeli."""
        for job_id in ("label-gate", "label-gate-p1"):
            pattern = rf"{re.escape(job_id)}:\s*\n(.*?)(?=\n  \w|\Z)"
            m = re.search(pattern, self.wf, re.S)
            self.assertIsNotNone(m, f"job '{job_id}' bulunamadı")
            block = m.group(1)
            self.assertIn("pull-requests: read", block,
                          f"job '{job_id}' pull-requests: read izni içermiyor")

    def test_both_gates_need_budget(self):
        """Her iki gate da budget'a bağımlı olmalı (needs: [budget])."""
        for job_id in ("label-gate", "label-gate-p1"):
            pattern = rf"{re.escape(job_id)}:\s*\n(.*?)(?=\n  \w|\Z)"
            m = re.search(pattern, self.wf, re.S)
            self.assertIsNotNone(m, f"job '{job_id}' bulunamadı")
            block = m.group(1)
            self.assertIn("needs: [budget]", block,
                          f"job '{job_id}' needs: [budget] içermiyor")


if __name__ == "__main__":
    unittest.main()
