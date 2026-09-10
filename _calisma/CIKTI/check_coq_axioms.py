#!/usr/bin/env python3
"""K19 Coq proof-gap pre-gate: scan .v sources before coqtop."""
import argparse
import json
import os
import re

_GAP_RE = re.compile(r"\b(?:admit|Admitted)\b")
_STRING_RE = re.compile(r'"(?:[^"\\]|\\.)*"')


def _clean(text):
    """Mask nested Coq comments and strings while preserving line numbers."""
    out = list(text)
    i = 0
    depth = 0
    in_string = False
    while i < len(text):
        if depth:
            if text.startswith("(*", i):
                depth += 1
                out[i:i + 2] = "  "
                i += 2
            elif text.startswith("*)", i):
                depth -= 1
                out[i:i + 2] = "  "
                i += 2
            else:
                if text[i] != "\n":
                    out[i] = " "
                i += 1
        elif text.startswith("(*", i):
            depth = 1
            out[i:i + 2] = "  "
            i += 2
        elif text[i] == '"':
            m = _STRING_RE.match(text, i)
            if m:
                out[i:m.end()] = [" " if c != "\n" else "\n" for c in m.group(0)]
                i = m.end()
            else:
                i += 1
        else:
            i += 1
    return "".join(out)


def scan_coq_dir(directory):
    """Return (clean, findings) for every .v file under directory."""
    if not os.path.isdir(directory):
        return False, [{"file": "", "line": 0, "kind": "error", "snippet": "directory missing"}]
    findings = []
    for root, dirs, files in os.walk(directory):
        dirs[:] = sorted(d for d in dirs if d not in {"_build", ".git"})
        for name in sorted(files):
            if not name.endswith(".v"):
                continue
            path = os.path.join(root, name)
            rel = os.path.relpath(path, directory)
            try:
                with open(path, encoding="utf-8") as fh:
                    source = fh.read()
            except OSError as exc:
                findings.append({"file": rel, "line": 0, "kind": "error", "snippet": str(exc)})
                continue
            for line_no, line in enumerate(_clean(source).splitlines(), 1):
                for match in _GAP_RE.finditer(line):
                    findings.append({"file": rel, "line": line_no, "kind": "admitted", "snippet": line.strip()[:120]})
                decl = re.match(r"^\s*(Axiom|Parameter)\b", line)
                if decl:
                    findings.append({"file": rel, "line": line_no, "kind": decl.group(1).lower(), "snippet": line.strip()[:120]})
    return not findings, findings


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--coq-dir", default=os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "coq_reduct")))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    ok, findings = scan_coq_dir(args.coq_dir)
    payload = {"ok": ok, "findings": findings, "coq_dir": args.coq_dir}
    if args.json:
        print(json.dumps(payload, ensure_ascii=False))
    else:
        for item in findings:
            print(f"{item['kind'].upper()} {item['file']}:{item['line']} — {item['snippet']}")
        print("SONUÇ: temiz" if ok else f"SONUÇ: {len(findings)} bulgu — fail-closed")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
