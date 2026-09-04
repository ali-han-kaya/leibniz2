#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Verify that sidecar-consuming workflow jobs receive their inputs."""

import os
import re
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
WORKFLOW = os.path.join(HERE, "..", "..", ".github", "workflows", "verify.yml")

# (job, artifact, hedef) — hedef None: workspace kökü (path'siz / merge)
DELIVERIES = [
    ("commit-msg-gate", "precommit-logs", "logs"),
    ("budget-comment", "budget", "budget/"),
    ("budget-comment", "precommit-logs", "precommit_findings/"),
    ("budget-comment", "k0-findings", None),
    ("budget-comment", "lineage-findings", None),
    ("budget-comment", "klayers", None),
    ("budget-comment", "reproducibility", "reproducibility/"),
]

EVAL_SCRIPTS = {
    "commit-msg-gate": "commit_msg_gate.js",
    "budget-comment": "pr_status_comment.js",
}


def _job_section(text, job):
    """Job'un metin bölümü (üst bilgiden sonraki job üst bilgisine)."""
    lines = text.splitlines()
    start = next((i for i, ln in enumerate(lines)
                  if re.match(r"^  %s:\s*$" % re.escape(job), ln)), None)
    if start is None:
        return ""
    end = next((i for i in range(start + 1, len(lines))
                if re.match(r"^  [a-zA-Z0-9_.-]+:\s*$", lines[i])), len(lines))
    return "\n".join(lines[start:end])


def _steps(section):
    """Adım blokları: [(ad, gövde satırları), ...]."""
    blocks = []
    cur = None
    for line in section.splitlines():
        m = re.match(r"^\s{6}- name:\s*(.+?)\s*$", line)
        if m:
            if cur:
                blocks.append(cur)
            cur = [m.group(1).strip("'\""), []]
        elif cur is not None:
            cur[1].append(line)
    if cur:
        blocks.append(cur)
    return blocks


def _deliveries(body):
    """Download adımının teslim ettiği {artifact: hedef|None} kümesi.

    name-tabanlı: tek artifact; `path` yoksa kök. pattern+merge-multiple:
    her eşleşen artifact hedefe düzleşir (path yoksa kök). Merge'siz
    pattern köke DÜŞMEZ (alt dizinlere iner) — teslim sayılmaz.
    """
    kv = {}
    for ln in body:
        m = re.match(r"^\s{10}(name|path|pattern|merge-multiple):\s*(.+?)\s*$",
                     ln)
        if m:
            kv[m.group(1)] = m.group(2).strip("'\"")
    if "name" in kv:
        return {kv["name"]: kv.get("path")}
    if "pattern" in kv and kv.get("merge-multiple") == "true":
        return {a: kv.get("path")
                for a in re.findall(r"\b[a-z0-9-]+\b", kv["pattern"])}
    return {}


class TestCiSidecarWiring(unittest.TestCase):
    """Check sidecar delivery and evaluation order."""

    @classmethod
    def setUpClass(cls):
        with open(WORKFLOW, encoding="utf-8") as workflow:
            cls.text = workflow.read()
        cls.delivered = {}
        cls.pre_eval_steps = {}
        cls.total_input_steps = {}
        for job in set(j for j, _, _ in DELIVERIES) | set(EVAL_SCRIPTS):
            section = _job_section(cls.text, job)
            d = {}
            input_steps = 0
            for name, body in _steps(section):
                joined = "\n".join(body)
                if "actions/download-artifact@v7" in joined:
                    d.update(_deliveries(body))
                    input_steps += 1
                elif "k10_verdict.txt" in joined:
                    input_steps += 1
                elif ("uses: actions/github-script@v8" in joined
                      and EVAL_SCRIPTS[job] in joined):
                    cls.pre_eval_steps[job] = input_steps
            cls.delivered[job] = d
            cls.total_input_steps[job] = input_steps

    def test_contract_deliveries(self):
        """Tablodaki her (job, artifact, hedef) teslim edilmeli."""
        missing = []
        for job, art, dest in DELIVERIES:
            got = self.delivered.get(job, {}).get(art, "YOK")
            if got != dest:
                missing.append(f"{job}/{art}: beklenen {dest!r}, teslim "
                               f"{got!r}")
        self.assertFalse(missing, "; ".join(missing))

    def test_deliveries_precede_evaluation(self):
        """Tüm girdi teslimleri (download + k10 üretici) script'i koşan
        github-script adımından ÖNCE gelmeli — aksi halde girdi yokken
        koşulur (fail-open / boş bölüm)."""
        for job in EVAL_SCRIPTS:
            self.assertIn(job, self.pre_eval_steps,
                          f"{job}: github-script adımı bulunamadı")
            self.assertEqual(
                self.pre_eval_steps[job], self.total_input_steps[job],
                f"{job}: girdi teslimleri github-script adımından önce "
                f"değil ({self.pre_eval_steps[job]}/"
                f"{self.total_input_steps[job]})")

    def test_budget_comment_needs_reproducibility(self):
        """reproducibility yüklenmeden job koşmamalı
        (needs sıralaması)."""
        section = _job_section(self.text, "budget-comment")
        self.assertRegex(
            section, r"needs:\s*\[[^\]]*\breproducibility\b[^\]]*\]",
            "budget-comment needs'inde reproducibility yok")


class TestBudgetGateFailClosed(unittest.TestCase):
    """budget (required) kapısı fail-closed: taraf yüklemesi düşse/pattern
    eşleşmese/hepsi bozuk olsa bile job PASS etmemeli (commit-msg gate
    sidecar bağlamasıyla aynı desen)."""

    @classmethod
    def setUpClass(cls):
        with open(WORKFLOW, encoding="utf-8") as workflow:
            cls.text = workflow.read()
        cls.job = _job_section(cls.text, "budget")

    def test_consolidate_step_fails_on_empty_sidecars(self):
        """Consolidate adımı consolidate_budget.py'nin exit 1'ini job'a
        iletir (|| { … exit 1 } guard'ı)."""
        self.assertRegex(
            self.job, r"python3 _calisma/CIKTI/consolidate_budget\.py\s*\|\|\s*\{",
            "consolidate_budget.py fail-closed guard'ı yok")
        self.assertIn("fail-closed", self.job)

    def test_summary_step_rechecks_empty_runs(self):
        """Run-summary adımı index.json'daki boş runs'u yeniden denetler
        (sidecarsız özet PASS'e dönüşemez)."""
        m = re.search(
            r"- name: Budget gate — run summary.*?(?=\n      - name: )",
            self.job, re.S)
        self.assertIsNotNone(m, "Budget gate — run summary adımı yok")
        body = m.group(0)
        self.assertIn("run_summary_budget.py", body)
        self.assertIn("runs", body)
        self.assertIn("sys.exit(1)", body)

    def test_sidecar_pattern_has_merge_multiple(self):
        """pattern-indirme merge-multiple ile köke düzleşmeli — aksi halde
        cp budget_sidecars/*.json boş glob olur (sessiz teslimatsızlık)."""
        m = re.search(
            r"- name: Download budget sidecars.*?(?=\n      - name: )",
            self.job, re.S)
        self.assertIsNotNone(m, "Download budget sidecars adımı yok")
        self.assertIn("pattern: budget-*", m.group(0))
        self.assertIn("merge-multiple: true", m.group(0))


class TestRequiredGateVerdictBinding(unittest.TestCase):
    """REQUIRED job'ların kendi sonucunu job exit'ine bağlaması (rubber-
    stamp kapı yasağı): continue-on-error verdict adımı olan job'lar
    sonradan bir fail-closed gate adımıyla bağlamalı — aksi halde kapı
    ASLA FAIL olamaz (commit-msg/budget sidecar bağlamasıyla aynı desen).
    """

    @classmethod
    def setUpClass(cls):
        with open(WORKFLOW, encoding="utf-8") as workflow:
            cls.text = workflow.read()

    def _gate_body(self, job, gate_name):
        section = _job_section(self.text, job)
        for name, body in _steps(section):
            if name == gate_name:
                return "\n".join(body)
        self.fail(f"{job}: '{gate_name}' fail-closed gate adımı yok")

    def test_refs_trend_gate_binds_artifact(self):
        """refs-trend (required): build adımı coe=True'dur; gate adımı
        refs-trend.md olmadan exit 1 verir (tablosuz PASS yasağı)."""
        body = self._gate_body("refs-trend", "Refs trend fail-closed gate")
        self.assertIn("refs-trend/refs-trend.md", body)
        self.assertIn("exit 1", body)

    def test_preview_reload_gate_binds_smoke_rc(self):
        """preview-reload-smoke (required): smoke adımı coe=True'dur ve
        smoke_rc hiçbir yerde bağlanmıyordu — gate adımı çıktıyı okuyup
        exit 1'e çevirir; boş/eksik çıktı da FAIL (fail-closed)."""
        body = self._gate_body("preview-reload-smoke",
                               "Preview reload fail-closed gate")
        self.assertIn("steps.smoke.outputs.smoke_rc", body)
        self.assertIn("exit 1", body)


if __name__ == "__main__":
    unittest.main()
