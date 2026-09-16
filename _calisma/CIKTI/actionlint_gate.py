#!/usr/bin/env python3
"""Output-sensitive actionlint gate.

Structural actionlint diagnostics fail the gate. Shellcheck *info/hint/style*
lines stay advisory. CRITICAL (2026-09-16 audit): actionlint emits shellcheck
*error*-level findings as "SC1073:error:..." — these are NOT advisory. The old
regex matched any line containing "SC\\d+" and silently classified fatal
here-doc/parse errors as advisory (fail-open). Now the severity token is
parsed: only info|hint|style pass as advisory; error|warning-class shellcheck
lines are structural.
"""
import argparse
import json
import re
import sys

_STRUCTURAL = re.compile(
    r"(?:syntax error|yaml|expression|invalid (?:context|value|key)|"
    r"unknown (?:property|context)|job .* not found|needs:|mapping values|"
    r"duplicate key|unexpected token)", re.I)
_SHELLCHECK_LINE = re.compile(r"\bshellcheck\b|\bSC\d{3,5}\b", re.I)
# severity: ayırıcı ':sev:' biçiminde (SC1073:error:6:13) ya da (severity)
# etiketi içinde. Yalnızca info/hint/style advisory'dir.
_SEV_ERROR = re.compile(r"SC\d{3,5}:(error|warning)|\(error\)|\(warning\)", re.I)
_SEV_INFO = re.compile(r"SC\d{3,5}:(info|hint|style)|\(info\)|\(hint\)|\(style\)|\bhint\b", re.I)


def classify(lines):
    structural, advisory = [], []
    for line in lines:
        if not line.strip():
            continue
        if _SHELLCHECK_LINE.search(line):
            # shellcheck kaynaklı: severiteye göre ayrıştır.
            if _SEV_ERROR.search(line):
                structural.append(line.rstrip())
            else:
                advisory.append(line.rstrip())
        elif _STRUCTURAL.search(line):
            structural.append(line.rstrip())
        else:
            # actionlint diagnostics with file:line:col are structural by
            # default; ordinary progress output is informational.
            (structural if re.match(r"^.*:\d+:\d+:\s*", line) else advisory).append(line.rstrip())
    return structural, advisory


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    text = open(args.input, encoding="utf-8").read()
    structural, advisory = classify(text.splitlines())
    result = {"tool": "actionlint", "ok": not structural,
              "verdict": "FAIL" if structural else ("WARN" if advisory else "PASS"),
              "structural_errors": structural, "shellcheck_advisory": advisory,
              "structural_count": len(structural), "advisory_count": len(advisory)}
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(json.dumps(result, ensure_ascii=False))
    return 1 if structural else 0


if __name__ == "__main__":
    sys.exit(main())
