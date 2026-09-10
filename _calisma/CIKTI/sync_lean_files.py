#!/usr/bin/env python3
"""Regenerate sync_verify_mirror.sh's LEAN_FILES block from lean_reduct."""
from pathlib import Path
import argparse
import os
import re


def source_files(root: Path):
    base = root / "_calisma" / "lean_reduct"
    if not base.is_dir():
        raise FileNotFoundError(base)
    out = []
    for path in base.rglob("*"):
        if not path.is_file() or ".lake" in path.parts or path.name == "lake-manifest.json":
            continue
        if path.suffix == ".lean" or path.name in {"lean-toolchain", "lakefile.toml"}:
            out.append(path.relative_to(base).as_posix())
    return sorted(out)


def update(script: Path, root: Path):
    text = script.read_text(encoding="utf-8")
    files = source_files(root)
    block = "LEAN_FILES=(\n" + "".join(f'  "{name}|{name}"\n' for name in files) + ")"
    pattern = re.compile(r"LEAN_FILES=\(\n.*?\n\)", re.S)
    updated, count = pattern.subn(block, text, count=1)
    if count != 1:
        raise ValueError("LEAN_FILES bloğu bulunamadı")
    if updated != text:
        script.write_text(updated, encoding="utf-8")
    return len(files), updated != text


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1].parent)
    ap.add_argument("--script", type=Path, default=Path(__file__).with_name("sync_verify_mirror.sh"))
    args = ap.parse_args(argv)
    count, changed = update(args.script, args.root.resolve())
    print(f"LEAN_FILES {'güncellendi' if changed else 'güncel'}: {count} kaynak")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
