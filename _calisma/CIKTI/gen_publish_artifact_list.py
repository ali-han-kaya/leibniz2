#!/usr/bin/env python3
"""Synchronize the canonical artifact-list block in PUBLISH_SCENARIO.md."""
import argparse
import os
import pathlib
import re
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
DOC = ROOT / "docs" / "PUBLISH_SCENARIO.md"
START = "**Artifact listesi ("
END = "\n\n**Not:**"


def render(names):
    lines = [f"**Artifact listesi ({len(names)}):**"]
    lines.extend(f"- `{name}`" for name in sorted(names))
    return "\n".join(lines)


def update(text, names):
    start = text.find(START)
    if start < 0:
        raise ValueError("Artifact listesi başlığı bulunamadı")
    end = text.find(END, start)
    if end < 0:
        raise ValueError("Artifact listesi sonu bulunamadı")
    return text[:start] + render(names) + text[end:]


def check_text(text, names):
    return update(text, names) == text


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--update", action="store_true")
    args = parser.parse_args(argv)
    if args.check and args.update:
        parser.error("--check ve --update birlikte kullanılamaz")
    if not args.check and not args.update:
        args.check = True
    from gen_repro_manifest import ARTIFACT_JOBS
    text = DOC.read_text(encoding="utf-8")
    expected = update(text, ARTIFACT_JOBS)
    if args.check:
        if not check_text(text, ARTIFACT_JOBS):
            print("FAIL: PUBLISH_SCENARIO artifact listesi ARTIFACT_JOBS ile drift ediyor")
            return 1
        print(f"PASS: {len(ARTIFACT_JOBS)} artifact ARTIFACT_JOBS ile senkron")
        return 0
    _dir = os.path.dirname(os.path.abspath(str(DOC))) or "."
    _fd, _tmp = tempfile.mkstemp(dir=_dir, prefix=DOC.name + ".tmp.")
    try:
        with os.fdopen(_fd, "w", encoding="utf-8") as _f:
            _f.write(expected)
        os.replace(_tmp, str(DOC))
    except BaseException:
        try:
            os.unlink(_tmp)
        except OSError:
            pass
        raise
    print(f"Güncellendi: {len(ARTIFACT_JOBS)} artifact")
    return 0


if __name__ == "__main__":
    sys.exit(main())
