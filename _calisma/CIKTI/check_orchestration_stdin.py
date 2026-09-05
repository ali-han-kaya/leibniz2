#!/usr/bin/env python3
"""Fail-closed audit for opencode orchestration subprocess calls."""
import argparse
import ast
import pathlib
import sys

DEFAULT_FILES = ("coordinator_loop.py", "orchestrate_k_dag.py")


def _is_subprocess_run(call):
    return (isinstance(call.func, ast.Attribute)
            and call.func.attr == "run"
            and isinstance(call.func.value, ast.Name)
            and call.func.value.id == "subprocess")


def audit(path):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    findings = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not _is_subprocess_run(node):
            continue
        stdin = next((kw.value for kw in node.keywords if kw.arg == "stdin"), None)
        valid = (isinstance(stdin, ast.Attribute)
                 and isinstance(stdin.value, ast.Name)
                 and stdin.value.id == "subprocess"
                 and stdin.attr == "DEVNULL")
        if not valid:
            findings.append({"file": str(path), "line": node.lineno,
                             "message": "subprocess.run stdin=subprocess.DEVNULL değil"})
    return findings


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("paths", nargs="*", help="orchestration Python dosyaları")
    args = ap.parse_args(argv)
    base = pathlib.Path(__file__).resolve().parent
    paths = [base / p for p in (args.paths or DEFAULT_FILES)]
    findings = []
    for path in paths:
        if not path.is_file():
            findings.append({"file": str(path), "line": 0,
                             "message": "orchestration dosyası yok"})
            continue
        try:
            findings.extend(audit(path))
        except SyntaxError as exc:
            findings.append({"file": str(path), "line": exc.lineno or 0,
                             "message": f"syntax hatası: {exc}"})
    if findings:
        for finding in findings:
            print("FAIL: {file}:{line}: {message}".format(**finding), file=sys.stderr)
        return 1
    print(f"PASS: {len(paths)} orchestration dosyasında tüm subprocess.run çağrıları stdin=DEVNULL")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
