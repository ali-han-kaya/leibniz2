#!/usr/bin/env python3
"""verify.yml artifact üretimleri ile doc/manifest kapsamını karşılaştır."""
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent.parent
WORKFLOW = ROOT / ".github/workflows/verify.yml"
DOC = ROOT / "docs/PUBLISH_SCENARIO.md"
sys.path.insert(0, str(HERE))
import audit_live_ci_sync as als  # noqa: E402
import gen_repro_manifest as grm  # noqa: E402


def workflow_artifacts(text):
    names = []
    in_upload = False
    for line in text.splitlines():
        if re.match(r"^\s*- name: Upload ", line):
            in_upload = True
            continue
        if in_upload and re.match(r"^\s*- name:", line):
            in_upload = False
        if in_upload:
            m = re.match(r"^\s{10}name:\s*([^#\s]+)", line)
            if m and m.group(1) not in names:
                names.append(m.group(1).strip("'\""))
    return names


def check():
    errors = []
    wf = workflow_artifacts(WORKFLOW.read_text(encoding="utf-8"))
    doc = als.parse_doc_artifacts(DOC.read_text(encoding="utf-8"))
    jobs = set(grm.ARTIFACT_JOBS)
    for name in sorted(set(wf) - set(doc) - {"badge-check"}):
        errors.append(f"workflow upload-artifact '{name}' PUBLISH_SCENARIO listesinde yok")
    for name in sorted(set(wf) - jobs - {
            "badge-check", "action-pins", "audit-live-ci",
            "pattern-drift", "preview-reload-smoke"}):
        errors.append(f"workflow upload-artifact '{name}' ARTIFACT_JOBS'ta yok")
    for name in sorted(jobs - set(wf) - {"reproducibility"}):
        errors.append(f"ARTIFACT_JOBS '{name}' için verify.yml upload-artifact yok")
    return wf, doc, errors


def main():
    wf, doc, errors = check()
    print(f"workflow upload-artifact: {len(wf)}")
    print(f"PUBLISH_SCENARIO artifact: {len(doc)}")
    print(f"ARTIFACT_JOBS: {len(grm.ARTIFACT_JOBS)}")
    if errors:
        for error in errors:
            print(f"FAIL: {error}", file=sys.stderr)
        return 1
    print("PASS: workflow ↔ PUBLISH_SCENARIO ↔ ARTIFACT_JOBS senkron")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
