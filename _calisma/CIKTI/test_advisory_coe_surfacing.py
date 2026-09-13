#!/usr/bin/env python3
"""Advisory continue-on-error surfacing contracts for verify.yml.

Audit (2026-09-11) classification of the 43 step-level continue-on-error
(coe) sites: a coe step can mask a real finding two ways —

  (A) its output file is never published (no upload covers it), so the
      finding dies in the runner workspace;
  (B) a LATER upload step in the same job lacks if: always(): with the
      default `if: success()`, a failed coe step marks the job red but a
      *non-coe* intermediate failure skips the upload — and any future
      edit that flips an intermediate step to outcome-gated silently
      drops the bundle.

Contracts pinned here (fail-closed, static regex — same style as
test_workflow_install_hardening.py):

  1. reports:        'Upload reports bundle' carries if: always()
  2. reproducibility:'Upload reproducibility bundle' carries if: always()
  3. verify:         the advisory commit-msg block-evidence step writes
                     into logs/ (covered by the always() logs/ upload) —
                     not the repo root, where nothing published reaches.
  4. Generalized guard: in ANY job containing a coe step, EVERY
     upload-artifact step must carry if: always().

stdlib unittest — no PyYAML requirement.
"""
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "verify.yml"


def job_block(text, job_id):
    m = re.search(rf"^  {re.escape(job_id)}:\n(.*?)(?=^  [a-z0-9_-]+:|\Z)",
                  text, re.M | re.S)
    return m.group(1) if m else None


def step_blocks(job_text):
    """Split a job body into (name, body) step chunks."""
    out = []
    for m in re.finditer(
            r"^      - name: ([^\n]*)\n(?P<body>[\s\S]*?)(?=^      - |\Z)",
            job_text, re.M):
        out.append((m.group(1).strip(), m.group("body")))
    return out


class TestUploadAlwaysInCoeJobs(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = WORKFLOW.read_text(encoding="utf-8")

    def _upload_steps(self, job_id):
        job = job_block(self.text, job_id)
        self.assertIsNotNone(job, f"job '{job_id}' yok")
        return [(n, b) for n, b in step_blocks(job)
                if "upload-artifact" in b]

    def test_reports_bundle_upload_is_always(self):
        ups = [b for n, b in self._upload_steps("reports")]
        self.assertTrue(ups, "reports job'unda upload yok")
        for body in ups:
            self.assertRegex(body, r"if:\s*always\(\)",
                             "reports bundle upload if: always() değil — "
                             "coe adım çöktüğünde bulgular yayınlanmaz")

    def test_reproducibility_bundle_upload_is_always(self):
        ups = [b for n, b in self._upload_steps("reproducibility")]
        self.assertTrue(ups, "reproducibility job'unda upload yok")
        for body in ups:
            self.assertRegex(body, r"if:\s*always\(\)",
                             "reproducibility bundle upload if: always() "
                             "değil — download coe zinciri kırılınca "
                             "manifest yayınlanmaz")

    def test_commit_msg_evidence_writes_into_logs(self):
        job = job_block(self.text, "verify")
        evid = [(n, b) for n, b in step_blocks(job)
                if "commit-msg block evidence" in n]
        self.assertTrue(evid, "commit-msg block evidence adımı yok")
        for _name, body in evid:
            self.assertIn("logs/COMMIT_MSG_BLOCK_EVIDENCE.md", body,
                          "block-evidence repo köküne yazılıyor — hiçbir "
                          "upload kapsamında değil (maskeli bulgu); "
                          "logs/ altına yazılmalı")

    def test_every_upload_in_coe_jobs_is_always(self):
        """Generalize: coe içeren her job'da her upload if: always()."""
        text = self.text
        current = None
        job_has_coe = {}
        job_uploads = {}
        for m in re.finditer(r"^  ([a-z0-9_-]+):\n([\s\S]*?)(?=^  [a-z0-9_-]+:|\Z)", text, re.M):
            jid, body = m.group(1), m.group(2)
            steps = step_blocks(body)
            job_has_coe[jid] = any(
                re.search(r"continue-on-error:\s*true", b) for _n, b in steps)
            job_uploads[jid] = [(n, b) for n, b in steps
                                if "upload-artifact" in b]
        offenders = []
        for jid, uploads in job_uploads.items():
            if not job_has_coe.get(jid):
                continue
            for n, b in uploads:
                if not re.search(r"if:\s*always\(\)", b):
                    offenders.append(f"{jid}:{n}")
        self.assertEqual(offenders, [],
                         "coe içeren job'larda if: always()'sız upload "
                         "adımları bulgu maskeler: " + ", ".join(offenders))


if __name__ == "__main__":
    unittest.main()
