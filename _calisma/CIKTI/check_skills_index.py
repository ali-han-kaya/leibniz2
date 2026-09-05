#!/usr/bin/env python3
"""Fail-closed README ↔ skills/ index check."""
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
README = ROOT / "README.md"
SKILLS = ROOT / "skills"


def skill_names():
    return {p.parent.name for p in SKILLS.glob("*/SKILL.md") if p.is_file()}


def readme_skill_names(text):
    marker = re.search(r"(?im)^##\s+Skills\s*$", text)
    if not marker:
        return set()
    tail = text[marker.end():]
    next_heading = re.search(r"(?m)^##\s+", tail)
    section = tail[:next_heading.start()] if next_heading else tail
    return set(re.findall(r"`?skills/([a-z0-9][a-z0-9-]*)/SKILL\.md`?", section))


def check(readme_text=None, available=None):
    text = README.read_text(encoding="utf-8") if readme_text is None else readme_text
    expected = skill_names() if available is None else set(available)
    listed = readme_skill_names(text)
    missing = sorted(expected - listed)
    stale = sorted(listed - expected)
    if missing or stale:
        print("FAIL: README skills index drift")
        if missing:
            print("  missing:", ", ".join(missing))
        if stale:
            print("  stale:", ", ".join(stale))
        return 1
    print(f"PASS: README skills index synced ({len(expected)} skills)")
    return 0


if __name__ == "__main__":
    sys.exit(check())
