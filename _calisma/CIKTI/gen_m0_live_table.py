#!/usr/bin/env python3
"""Generate the M0 live K14/K16/K17 table from the three gate commands.

The report is updated only between explicit markers, so surrounding historical
M0 evidence remains untouched. Commands are run in the requested checkout and
non-zero exits are preserved as FAIL rows rather than being mistaken for PASS.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

START = "<!-- M0-LIVE-TABLE:START -->"
END = "<!-- M0-LIVE-TABLE:END -->"
COMMANDS = (
    ("K14", "Cleanup kaydı", ("--check-cleanup",)),
    ("K16", "GitHub-scripts self-test", ("--check-github-scripts",)),
    ("K17", "Mirror sync", ("--check-mirror", "--mirror-auto-sync")),
)


def run_gate(verify: Path, args: tuple[str, ...], cwd: Path) -> tuple[int, str]:
    result = subprocess.run(
        [sys.executable, str(verify), "--dir", str(verify.parent), *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=600,
    )
    return result.returncode, (result.stdout + result.stderr).strip()


def concise_detail(output: str, key: str) -> str:
    """Select the machine-relevant summary line without fabricating success."""
    patterns = {
        "K14": r"^\[K14\].*$",
        "K16": r"^\[K16\].*$",
        "K17": r"^\[K17\].*$",
    }
    matches = [line.strip() for line in output.splitlines()
               if re.match(patterns[key], line.strip())]
    if matches:
        return matches[-1]
    return "çıktı özeti bulunamadı"


def render(rows: list[tuple[str, str, str]]) -> str:
    lines = [START, "", "| Katman | Kontrol | Sonuç |", "|---|---|---|"]
    lines.extend(f"| {key} | {label} | {result} |" for key, label, result in rows)
    lines.extend(["", END])
    return "\n".join(lines)


def update_report(report: Path, table: str) -> None:
    text = report.read_text(encoding="utf-8")
    pattern = re.compile(re.escape(START) + r".*?" + re.escape(END), re.S)
    if not pattern.search(text):
        raise ValueError(f"M0 canlı tablo marker'ları yok: {report}")
    report.write_text(pattern.sub(table, text, count=1), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify", default=None, help="verify_delivery.py yolu")
    parser.add_argument("--report", default=None, help="M0 raporu; verilirse tablo marker'ları güncellenir")
    parser.add_argument("--root", default=None, help="repo kökü (varsayılan verify dosyasından türetilir)")
    parser.add_argument("--output", default=None, help="JSON/text komut kanıtı için çıktı dosyası")
    args = parser.parse_args(argv)

    verify = Path(args.verify or Path(__file__).with_name("verify_delivery.py")).resolve()
    root = Path(args.root or verify.parents[2]).resolve()
    rows = []
    evidence = []
    for key, label, command in COMMANDS:
        rc, output = run_gate(verify, command, root)
        status = "PASS" if rc == 0 else f"FAIL (exit {rc})"
        detail = concise_detail(output, key)
        rows.append((key, label, f"{status} — {detail}"))
        evidence.append({"layer": key, "command": " ".join(command), "exit": rc,
                         "status": status, "detail": detail, "output": output})

    table = render(rows)
    if args.report:
        update_report(Path(args.report).resolve(), table)
    if args.output:
        Path(args.output).write_text("\n\n".join(
            f"[{item['layer']}] exit={item['exit']}\n{item['output']}"
            for item in evidence
        ) + "\n", encoding="utf-8")
    print(table)
    return 0 if all(item["exit"] == 0 for item in evidence) else 1


if __name__ == "__main__":
    raise SystemExit(main())
