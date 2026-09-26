#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_latex_surface.py — fail-closed LaTeX surface gate.

The gate rejects active ``$$`` display delimiters and references without a
matching label.  It scans the tracked ``.tex`` surface by default, strips
comments without moving byte offsets, and resolves ``\\input``/``\\include``
graphs per document root.  Labels from an unrelated manuscript copy therefore
cannot mask a missing reference in the canonical article graph.

Exit codes: 0 = clean, 1 = findings, 2 = invocation/source error.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parents[2]
_REF_COMMAND = re.compile(r"\\(ref|eqref|autoref|cref|Cref|pageref)\*?\s*\{")
_LABEL_COMMAND = re.compile(r"\\label\s*\{")
_INPUT_COMMAND = re.compile(r"\\(input|include)\s*\{")
_DOCUMENTCLASS = re.compile(r"\\documentclass\b")


@dataclass(frozen=True)
class SurfaceFile:
    path: Path
    text: str
    labels: tuple[tuple[str, int], ...]
    refs: tuple[tuple[str, str, int], ...]
    inputs: tuple[str, ...]
    is_root: bool


def _is_escaped(text: str, index: int) -> bool:
    backslashes = 0
    index -= 1
    while index >= 0 and text[index] == "\\":
        backslashes += 1
        index -= 1
    return backslashes % 2 == 1


def strip_comments(text: str) -> str:
    """Blank unescaped LaTeX comments while preserving offsets/newlines."""
    chars = list(text)
    index = 0
    while index < len(chars):
        if chars[index] == "%" and not _is_escaped(text, index):
            while index < len(chars) and chars[index] != "\n":
                chars[index] = " "
                index += 1
        else:
            index += 1
    return "".join(chars)


def _line_column(text: str, offset: int) -> tuple[int, int]:
    line = text.count("\n", 0, offset) + 1
    last_newline = text.rfind("\n", 0, offset)
    return line, offset - last_newline


def _read_braced_argument(text: str, opening: int) -> tuple[str, int] | None:
    """Read a balanced ``{...}`` argument beginning at ``opening``."""
    if opening >= len(text) or text[opening] != "{":
        return None
    depth = 0
    index = opening
    while index < len(text):
        char = text[index]
        if char == "{" and not _is_escaped(text, index):
            depth += 1
        elif char == "}" and not _is_escaped(text, index):
            depth -= 1
            if depth == 0:
                return text[opening + 1:index], index + 1
        index += 1
    return None


def _scan_commands(text: str, pattern: re.Pattern[str], first_group: bool = True):
    """Yield (command/value, start offset) for balanced simple arguments."""
    for match in pattern.finditer(text):
        opening = text.find("{", match.start(), match.end() + 1)
        parsed = _read_braced_argument(text, opening)
        if parsed is None:
            continue
        value, end = parsed
        command = match.group(1) if first_group else ""
        yield command, value.strip(), match.start(), end


def parse_surface_file(path: Path, root: Path) -> SurfaceFile:
    raw = path.read_text(encoding="utf-8")
    text = strip_comments(raw)
    labels = tuple((value, start) for _command, value, start, _end
                   in _scan_commands(text, _LABEL_COMMAND, first_group=False)
                   if value)
    refs: list[tuple[str, str, int]] = []
    for command, value, start, _end in _scan_commands(text, _REF_COMMAND):
        targets = value.split(",") if command in {"cref", "Cref"} else [value]
        refs.extend((command, target.strip(), start) for target in targets if target.strip())
    inputs = tuple(value for _command, value, _start, _end
                   in _scan_commands(text, _INPUT_COMMAND, first_group=False)
                   if value)
    return SurfaceFile(
        path=path,
        text=text,
        labels=labels,
        refs=refs,
        inputs=inputs,
        is_root=bool(_DOCUMENTCLASS.search(text)),
    )


def _display_path(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _resolve_input(source: Path, target: str) -> Path:
    candidate = (source.parent / target).resolve()
    if candidate.suffix != ".tex":
        candidate = candidate.with_suffix(".tex")
    return candidate


def _reachable_graph(root_file: Path, by_path: dict[Path, SurfaceFile]) -> set[Path]:
    reachable: set[Path] = set()
    pending = [root_file.resolve()]
    while pending:
        path = pending.pop()
        if path in reachable or path not in by_path:
            continue
        reachable.add(path)
        surface = by_path[path]
        for target in surface.inputs:
            pending.append(_resolve_input(path, target))
    return reachable


def _surface_files(paths: Iterable[Path], root: Path) -> tuple[dict[Path, SurfaceFile], list[dict]]:
    findings: list[dict] = []
    by_path: dict[Path, SurfaceFile] = {}
    for raw_path in sorted({path.resolve() for path in paths}):
        try:
            raw_path.relative_to(root.resolve())
        except ValueError as exc:
            findings.append({
                "kind": "source_error",
                "file": str(raw_path),
                "detail": f"root dışındaki TeX yolu: {exc}",
            })
            continue
        if not raw_path.is_file():
            findings.append({
                "kind": "source_error",
                "file": _display_path(raw_path, root),
                "detail": "TeX dosyası okunamadı",
            })
            continue
        try:
            by_path[raw_path] = parse_surface_file(raw_path, root)
        except (OSError, UnicodeError) as exc:
            findings.append({
                "kind": "source_error",
                "file": _display_path(raw_path, root),
                "detail": f"TeX okunamadı: {exc}",
            })
    return by_path, findings


def _finding(kind: str, path: Path, root: Path, text: str, offset: int, detail: str) -> dict:
    line, column = _line_column(text, offset)
    return {
        "kind": kind,
        "file": _display_path(path, root),
        "line": line,
        "column": column,
        "detail": detail,
    }


def scan_surface(paths: Iterable[Path], root: Path) -> list[dict]:
    """Scan paths and return all fail-closed findings."""
    root = root.resolve()
    by_path, findings = _surface_files(paths, root)
    if not by_path:
        findings.append({"kind": "source_error", "file": ".", "detail": "hiç .tex kaynağı bulunamadı"})
        return findings

    # Active $$ is rejected once per source file, independently of input graphs.
    for path, surface in by_path.items():
        start = 0
        while True:
            offset = surface.text.find("$$", start)
            if offset < 0:
                break
            findings.append(_finding(
                "double_dollar", path, root, surface.text, offset,
                "aktif $$ display delimiter yasak; \\[...\\] veya uygun ortam kullanın",
            ))
            start = offset + 2

    roots = [path for path, surface in by_path.items() if surface.is_root]
    reachable_from_root: set[Path] = set()
    for root_path in roots:
        reachable_from_root.update(_reachable_graph(root_path, by_path))
    # A fragment not included by a document is still its own auditable surface.
    surface_roots = roots + [path for path in by_path if path not in reachable_from_root]

    seen_missing: set[tuple[str, int, str]] = set()
    for root_path in surface_roots:
        graph = _reachable_graph(root_path, by_path)
        labels = {name for path in graph for name, _offset in by_path[path].labels}
        for path in graph:
            surface = by_path[path]
            for command, target, offset in surface.refs:
                if target in labels:
                    continue
                key = (str(path), offset, target)
                if key in seen_missing:
                    continue
                seen_missing.add(key)
                findings.append(_finding(
                    "label_missing", path, root, surface.text, offset,
                    f"\\{command}{{{target}}} için aynı LaTeX input yüzeyinde label yok",
                ))

    findings.sort(key=lambda item: (item.get("file", ""), item.get("line", 0), item.get("column", 0), item["kind"]))
    return findings


def discover_tracked_tex(root: Path) -> list[Path]:
    """Return tracked .tex paths, with a filesystem fallback for tiny fixtures."""
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "ls-files", "-z", "--", "*.tex"],
            capture_output=True, check=True, text=False,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise RuntimeError(f"git ls-files başarısız: {exc}") from exc
    paths = [root / item.decode("utf-8") for item in result.stdout.split(b"\0") if item]
    if paths:
        return paths
    return sorted(
        path for path in root.rglob("*.tex")
        if ".git" not in path.parts and ".worktrees" not in path.parts
        and ".vercel" not in path.parts
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=REPO_ROOT,
                        help="repository root (default: inferred from script)")
    parser.add_argument("--file", type=Path, action="append", dest="files",
                        help="explicit .tex file; repeatable, primarily for fixtures")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--out", type=Path,
                        help="also write the JSON report to this path")
    args = parser.parse_args(argv)
    root = args.root.expanduser().resolve()
    try:
        paths = [path.expanduser() if path.is_absolute() else root / path
                 for path in args.files] if args.files else discover_tracked_tex(root)
    except (OSError, RuntimeError) as exc:
        print(f"HATA: {exc}", file=sys.stderr)
        return 2
    findings = scan_surface(paths, root)
    report = {
        "ok": not findings,
        "findings": findings,
        "root": str(root),
        "files": len(paths),
    }
    encoded = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(encoded, encoding="utf-8")
    if args.json:
        print(encoded, end="")
    else:
        print(f"check-latex-surface: {len(paths)} TeX dosyası")
        for item in findings:
            location = item.get("file", "?")
            if "line" in item:
                location += f":{item['line']}:{item.get('column', 1)}"
            print(f"  {item['kind'].upper()} {location} — {item['detail']}")
        print("SONUÇ: temiz" if not findings else f"SONUÇ: {len(findings)} bulgu — fail-closed")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
