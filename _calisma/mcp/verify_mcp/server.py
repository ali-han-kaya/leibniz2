#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""verify_mcp — read-only MCP server for the local Stoic-Hume verification chain.

Exposes the state produced by the verification pipeline (verify_delivery.py /
preview_server.py) as MCP tools over stdio. Everything is read from the same
JSON artifacts the live dashboard serves:

  <preview-dir>/history.jsonl      — latest run summaries (JSONL, newest last)
  <preview-dir>/runs/run-<ts>.json — full run records (stdout+stderr included)

The default preview dir matches preview_server.py's DEFAULT_PREVIEW_DIR; pass
--preview-dir or set VERIFY_MCP_PREVIEW_DIR to point elsewhere.

All tools are read-only (readOnlyHint=true) and local (openWorldHint=false);
none of them triggers a verification run or mutates any state.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import re
import sys
from enum import Enum
from typing import Annotated, Any, Dict, List, Optional

from mcp.server.fastmcp import FastMCP
from pydantic import Field

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DEFAULT_PREVIEW_DIR = os.path.expanduser("~/Library/Caches/com.freebuff/preview")
HISTORY_MAX = 100          # mirror of preview_server.py HISTORY_MAX
RUN_LOG_MAX = 20           # mirror of preview_server.py RUN_LOG_MAX

REPO_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", ".."))
CIKTI_DIR = os.path.join(REPO_ROOT, "_calisma", "CIKTI")

# Reuse the repo's own mirror coverage checker in-process (no subprocess).
sys.path.insert(0, CIKTI_DIR)
import check_mirror_coverage as cmc  # noqa: E402

mcp = FastMCP("verify_mcp")

# Resolved at startup by main(); overridable by tests.
PREVIEW_DIR: Optional[str] = None

# Field selection for the compact summary shared by get_latest / history rows.
_SUMMARY_KEYS = (
    "ts", "verdict", "exit_code", "p0", "p1", "duration_s",
    "budget_usd", "budget_limit", "budget_method",
    "pdf_pages", "ref_count", "refs_verified", "refs_total", "refs_mismatch",
    "refs_by_source", "z3_passed", "z3_failed", "z3_total",
    "lean_ok", "lean_detail", "lineage_summary",
    "mirror_sync", "mirror_stale", "pattern_drift",
    "config_diff", "cli_overrides", "cli_override_count", "hook_env",
    "flaky_count", "deterministic_count", "cached",
    "findings", "failure_pattern",
)

# Common tool parameters (flat, agent-friendly input schema).
ResponseFormat = Annotated[
    str,
    Field(description="Output format: 'markdown' for human-readable, 'json' for machine-readable"),
]
Ts = Annotated[str, Field(description=(
    "Run timestamp as shown in history (e.g. '2026-08-25T21:06:07'). "
    "A prefix (e.g. '2026-08-25') also matches the newest run that day."),
    min_length=1, max_length=64)]
MaxStdout = Annotated[int, Field(
    description="Maximum stdout characters to include in the detail",
    ge=500, le=200000)]
Limit = Annotated[int, Field(
    description="Maximum number of rows to return", ge=1, le=50)]
Offset = Annotated[int, Field(
    description="Number of rows to skip", ge=0)]


# ---------------------------------------------------------------------------
# Data layer — same files the dashboard serves
# ---------------------------------------------------------------------------

def _preview_dir() -> str:
    if PREVIEW_DIR:
        return PREVIEW_DIR
    raise RuntimeError(
        "PREVIEW_DIR not resolved — start the server with --preview-dir "
        "or set VERIFY_MCP_PREVIEW_DIR"
    )


def _load_history() -> List[Dict[str, Any]]:
    """JSONL summary records, oldest → newest (mirrors preview_server.load_history)."""
    path = os.path.join(_preview_dir(), "history.jsonl")
    if not os.path.isfile(path):
        return []
    out: List[Dict[str, Any]] = []
    try:
        with open(path, encoding="utf-8") as f:
            for ln in f:
                ln = ln.strip()
                if not ln:
                    continue
                try:
                    out.append(json.loads(ln))
                except json.JSONDecodeError:
                    continue
    except OSError:
        return []
    return out[-HISTORY_MAX:]


def _load_run_logs(limit: Optional[int] = None) -> List[Dict[str, Any]]:
    """Full run records (stdout/stderr included), oldest → newest.

    Filenames are sortable ISO timestamps (run-<safe-ts>.json) so
    lexicographic order == chronological order, exactly like preview_server.
    """
    runs_dir = os.path.join(_preview_dir(), "runs")
    if not os.path.isdir(runs_dir):
        return []
    try:
        files = sorted(f for f in os.listdir(runs_dir) if f.endswith(".json"))
    except OSError:
        return []
    if limit is not None:
        files = files[-limit:]
    out: List[Dict[str, Any]] = []
    for name in files:
        try:
            with open(os.path.join(runs_dir, name), encoding="utf-8") as f:
                rec = json.load(f)
            if isinstance(rec, dict) and rec.get("ts"):
                out.append(rec)
        except (OSError, json.JSONDecodeError):
            continue
    return out


def _latest_record() -> Dict[str, Any]:
    """Newest run record: prefer full runs/ log, else history summary."""
    logs = _load_run_logs(limit=1)
    if logs:
        return logs[-1]
    hist = _load_history()
    if hist:
        return hist[-1]
    raise FileNotFoundError(
        f"no run records found in {_preview_dir()} "
        "(history.jsonl or runs/run-*.json missing). Start the dashboard once "
        "(start_preview.sh) or point the server at a populated preview dir "
        "with --preview-dir / VERIFY_MCP_PREVIEW_DIR."
    )


def _klayers_from_disk() -> Optional[Dict[str, Any]]:
    """Per-layer status from the klayers.json sidecar (CI --klayers-out).

    Checked in the preview dir, then the repo root (gen_repro_manifest
    flattens CI sidecars to the root). Returns the layers dict or None.
    """
    for base in (_preview_dir(), REPO_ROOT):
        path = os.path.join(base, "klayers.json")
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            continue
        layers = data.get("layers") if isinstance(data, dict) else None
        if isinstance(layers, dict) and layers:
            return layers
    return None


def _layer_counts(layers: Any) -> Dict[str, int]:
    """{'PASS': n, 'FAIL': n, 'SKIP': n} from the layers dict of a run record."""
    counts = {"PASS": 0, "FAIL": 0, "SKIP": 0}
    if not isinstance(layers, dict):
        return counts
    for meta in layers.values():
        status = meta.get("status") if isinstance(meta, dict) else None
        if status in counts:
            counts[status] += 1
    return counts


def _summarize(rec: Dict[str, Any]) -> Dict[str, Any]:
    """Curated summary of a run record (omits the bulky stdout/stderr)."""
    summary = {k: rec.get(k) for k in _SUMMARY_KEYS}
    summary["layers"] = rec.get("layers")
    summary["layer_counts"] = _layer_counts(rec.get("layers"))
    return {k: v for k, v in summary.items() if v is not None}


# ---------------------------------------------------------------------------
# Formatting — markdown for humans, JSON for programmatic use
# ---------------------------------------------------------------------------

def _emit(data: Any, fmt: str, markdown: str) -> str:
    if fmt == "json":
        return json.dumps(data, ensure_ascii=False, indent=2)
    return markdown


def _iso(ts: Optional[str]) -> str:
    return ts or "unknown"


def _verdict_md(rec: Dict[str, Any]) -> str:
    verdict = rec.get("verdict", "UNKNOWN")
    exit_code = rec.get("exit_code")
    if exit_code is not None:
        return f"**{verdict}** (exit {exit_code})"
    return f"**{verdict}**"


def _latest_md(rec: Dict[str, Any]) -> str:
    counts = _layer_counts(rec.get("layers"))
    lines = [
        f"# Latest run — {_iso(rec.get('ts'))}",
        "",
        f"- **Verdict**: {_verdict_md(rec)}",
        f"- **P0 / P1**: {rec.get('p0', 0)} / {rec.get('p1', 0)}",
    ]
    if rec.get("duration_s") is not None:
        lines.append(f"- **Duration**: {rec.get('duration_s')}s")
    if rec.get("budget_usd") is not None:
        budget = f"${rec.get('budget_usd')}"
        if rec.get("budget_limit") is not None:
            budget += f" / limit ${rec.get('budget_limit')}"
        if rec.get("budget_method"):
            budget += f" ({rec.get('budget_method')})"
        lines.append(f"- **Budget**: {budget}")
    if rec.get("layers") is not None:
        lines.append(
            f"- **Layers**: {counts.get('PASS', 0)} PASS · "
            f"{counts.get('FAIL', 0)} FAIL · {counts.get('SKIP', 0)} SKIP"
        )
    refs = []
    if rec.get("refs_verified") is not None:
        refs.append(f"{rec.get('refs_verified')}/{rec.get('refs_total', '?')} verified")
    if rec.get("refs_mismatch"):
        refs.append(f"{rec.get('refs_mismatch')} mismatch")
    if refs:
        lines.append(f"- **Refs**: {' · '.join(refs)}")
    z3 = []
    if rec.get("z3_total") is not None:
        z3.append(f"Z3 {rec.get('z3_passed', 0)}/{rec.get('z3_total')}")
    if rec.get("lean_ok") is not None:
        z3.append(f"Lean {'PASS' if rec.get('lean_ok') else 'FAIL'}")
    if z3:
        lines.append(f"- **Proofs**: {' · '.join(z3)}")
    mirror = rec.get("mirror_sync")
    if isinstance(mirror, dict):
        lines.append(f"- **Mirror**: {'OK' if mirror.get('ok') else 'MISSING/STALE'}")
    if rec.get("pattern_drift") is not None:
        lines.append(f"- **Pattern drift**: {rec.get('pattern_drift')}")
    lineage = rec.get("lineage_summary")
    if isinstance(lineage, dict):
        lines.append(
            f"- **Lineage**: {'OK' if lineage.get('ok') else 'CHECK'} "
            f"({lineage.get('count', '?')} records)")
    if rec.get("cached"):
        lines.append(f"- **Cached**: {rec.get('cached')}")
    if rec.get("findings"):
        lines.append(f"- **Findings**: {len(rec.get('findings'))}")
    return "\n".join(lines) + "\n"


def _sort_layers(layers: Dict[str, Any]) -> List[str]:
    def key(name: str) -> tuple:
        m = re.match(r"^K(\d+)$", name)
        return (0, int(m.group(1))) if m else (1, name)
    return sorted(layers.keys(), key=key)


def _layers_md(rec: Dict[str, Any]) -> str:
    layers = rec.get("layers")
    counts = _layer_counts(layers)
    lines = [
        f"# K-layer status — {_iso(rec.get('ts'))}",
        "",
        f"**{counts['PASS']} PASS · {counts['FAIL']} FAIL · {counts['SKIP']} SKIP**",
        "",
        "| Layer | Label | Status |",
        "|-------|-------|--------|",
    ]
    if not isinstance(layers, dict) or not layers:
        lines.append("_(no layer data in this record)_")
        return "\n".join(lines) + "\n"
    for name in _sort_layers(layers):
        meta = layers[name]
        label = meta.get("label", "") if isinstance(meta, dict) else ""
        status = meta.get("status", "?") if isinstance(meta, dict) else "?"
        lines.append(f"| {name} | {label} | {status} |")
    return "\n".join(lines) + "\n"


def _history_md(rows: List[Dict[str, Any]], total: int, offset: int, count: int) -> str:
    lines = [
        f"# Run history ({count} of {total})",
        "",
        "| # | ts | verdict | exit | P0/P1 | dur (s) |",
        "|---|----|---------|------|-------|---------|",
    ]
    for i, rec in enumerate(rows, start=offset + 1):
        lines.append(
            f"| {i} | {_iso(rec.get('ts'))} | {rec.get('verdict', '?')} "
            f"| {rec.get('exit_code', '')} | {rec.get('p0', 0)}/{rec.get('p1', 0)} "
            f"| {rec.get('duration_s', '')} |"
        )
    if not rows:
        lines.append("_(no run history yet)_")
    return "\n".join(lines) + "\n"


def _detail_md(rec: Dict[str, Any], max_stdout_chars: int) -> str:
    out = [f"# Run detail — {_iso(rec.get('ts'))}", ""]
    out.append(f"- **Verdict**: {_verdict_md(rec)}")
    out.append(f"- **P0 / P1**: {rec.get('p0', 0)} / {rec.get('p1', 0)}")
    for key, label in (
        ("duration_s", "Duration (s)"),
        ("pdf_pages", "PDF pages"),
        ("ref_count", "Reference count"),
        ("refs_verified", "Refs verified"),
        ("refs_total", "Refs total"),
        ("flaky_count", "Flaky count"),
        ("deterministic_count", "Deterministic count"),
    ):
        if rec.get(key) is not None:
            out.append(f"- **{label}**: {rec.get(key)}")
    stdout = rec.get("stdout") or ""
    if len(stdout) > max_stdout_chars:
        stdout = stdout[:max_stdout_chars] + f"\n…[truncated at {max_stdout_chars} chars]"
    out.append("")
    out.append(f"### stdout ({len(stdout)} chars)")
    out.append("")
    out.append("```")
    out.append(stdout)
    out.append("```")
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@mcp.tool(
    name="verify_get_latest",
    annotations={
        "title": "Get Latest Verification Run",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def verify_get_latest(response_format: ResponseFormat = "markdown") -> str:
    """Get the summary of the most recent verification run.

    Reads the newest full run record (runs/run-*.json) or, failing that, the
    newest history.jsonl summary. Returns verdict, exit code, P0/P1 counts,
    budget, per-layer PASS/FAIL/SKIP counts, reference verification totals,
    proof (Z3/Lean) status, mirror sync state, and any findings.

    Args:
        response_format (str): 'markdown' (default) or 'json'.

    Returns:
        str: Latest run summary. JSON includes the `layers` dict and
        `layer_counts` in addition to the summary fields.

    Examples:
        - "What's the latest verification verdict?" -> verify_get_latest
        - "Are there any P1 findings right now?" -> verify_get_latest (check `p1` and `findings`)
    """
    try:
        rec = _latest_record()
    except (FileNotFoundError, RuntimeError) as e:
        return f"Error: {e}"
    return _emit(_summarize(rec), response_format, _latest_md(rec))


@mcp.tool(
    name="verify_get_layer_status",
    annotations={
        "title": "Get K-Layer Status",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def verify_get_layer_status(response_format: ResponseFormat = "markdown") -> str:
    """Get the per-layer (K0..K22) PASS/FAIL/SKIP breakdown of the latest run.

    Layers are the verification gates (package integrity, determinism,
    lineage, proofs, mirror sync, …). FAIL layers identify what blocked the
    run. Sources, in order: the latest run record's `layers`, then the
    `klayers.json` sidecar (CI --klayers-out) in the preview dir, then the
    repo root. Local run records do not persist per-layer status — when no
    source is present the tool says so instead of guessing.

    Args:
        response_format (str): 'markdown' (default) or 'json'.

    Returns:
        str: Layer table (markdown) or the raw `layers` dict (JSON).

    Error Handling:
        - No layer data on disk: error names the sources that were checked.
    """
    try:
        rec = _latest_record()
        layers = rec.get("layers") or _klayers_from_disk()
    except (FileNotFoundError, RuntimeError) as e:
        return f"Error: {e}"
    if not isinstance(layers, dict) or not layers:
        return (
            f"Error: no per-layer status persisted in {_preview_dir()} "
            "(run records carry scalars like z3/lean, not the layers dict). "
            "Layer status is available from the live dashboard's /api/latest "
            "or the klayers.json sidecar (verify_delivery.py --klayers-out); "
            "point --preview-dir at a dir containing klayers.json."
        )
    return _emit(layers, response_format, _layers_md(rec))


@mcp.tool(
    name="verify_get_run_detail",
    annotations={
        "title": "Get Full Run Record",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def verify_get_run_detail(
    ts: Ts,
    max_stdout_chars: MaxStdout = 4000,
    response_format: ResponseFormat = "markdown",
) -> str:
    """Get the full record of a specific run, including captured stdout.

    Use the `ts` shown in run history. A prefix (e.g. the date '2026-08-25')
    matches the newest run that day. Full records exist only for runs kept in
    runs/; older runs fall back to the history.jsonl summary (no stdout).

    Args:
        ts (str): Run timestamp or prefix (e.g. '2026-08-25T21:06:07' or '2026-08-25').
        max_stdout_chars (int): Truncation cap for stdout (default 4000).
        response_format (str): 'markdown' (default) or 'json'.

    Returns:
        str: Full run record. JSON includes stdout/stderr and all LATEST fields.

    Error Handling:
        - Unknown ts: error lists the available timestamps so the caller can retry.
    """
    try:
        target = ts.strip()
        logs = _load_run_logs()
        hist = _load_history()
        rec = None
        for candidate in reversed(logs):
            if candidate.get("ts") == target or str(candidate.get("ts", "")).startswith(target):
                rec = candidate
                break
        if rec is None:
            for candidate in reversed(hist):
                if candidate.get("ts") == target or str(candidate.get("ts", "")).startswith(target):
                    rec = candidate
                    break
        if rec is None:
            available = [r.get("ts") for r in reversed(logs + hist)]
            sample = ", ".join(str(t) for t in available[:10])
            return (
                f"Error: no run matches ts '{target}'. "
                f"Available timestamps (newest first): {sample or 'none yet'}. "
                "Use verify_list_run_history to see the full list."
            )
        if response_format == "json":
            return json.dumps(rec, ensure_ascii=False, indent=2)
        return _detail_md(rec, max_stdout_chars)
    except (FileNotFoundError, RuntimeError) as e:
        return f"Error: {e}"


@mcp.tool(
    name="verify_list_run_history",
    annotations={
        "title": "List Run History",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def verify_list_run_history(
    limit: Limit = 20,
    offset: Offset = 0,
    response_format: ResponseFormat = "markdown",
) -> str:
    """List verification run history, newest first, with pagination.

    Rows are history.jsonl summaries (ts, verdict, exit_code, P0/P1,
    duration). Pagination metadata is returned in both formats.

    Args:
        limit (int): Rows per page, 1-50 (default 20).
        offset (int): Rows to skip (default 0).
        response_format (str): 'markdown' (default) or 'json'.

    Returns:
        str: Rows plus `total`, `count`, `offset`, `has_more`, `next_offset`.

    Examples:
        - "What were the last 5 run verdicts?" -> limit=5
        - "Page through more history" -> offset=20, limit=20
    """
    try:
        hist = _load_history()
    except (FileNotFoundError, RuntimeError) as e:
        return f"Error: {e}"
    rows = list(reversed(hist))
    total = len(rows)
    page = rows[offset: offset + limit]
    has_more = offset + len(page) < total
    data = {
        "total": total,
        "count": len(page),
        "offset": offset,
        "has_more": has_more,
        "next_offset": offset + len(page) if has_more else None,
        "items": [_summarize(r) for r in page],
    }
    return _emit(data, response_format, _history_md(page, total, offset, len(page)))


@mcp.tool(
    name="verify_check_mirror",
    annotations={
        "title": "Check Mirror Coverage",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def verify_check_mirror(response_format: ResponseFormat = "markdown") -> str:
    """Check that the mirror script list covers the repo's runtime file set.

    Reuses the repo's own check_mirror_coverage.py (K17 contract) in-process:
    expected runtime/zip/Lean/guide files vs. the sync script's --list output.
    Reports missing (EKSİK), dead/stale (BAYAT) and unexpected entries.
    Read-only: lists files only, never runs a sync.

    Args:
        response_format (str): 'markdown' (default) or 'json'.

    Returns:
        str: Coverage report with `ok`, `missing`, `dead`, `unexpected` lists
        and the checker's exit code.

    Error Handling:
        - sync_verify_mirror.sh missing or --list failing: actionable error with the exit code.
    """
    sync_script = os.path.join(CIKTI_DIR, "sync_verify_mirror.sh")
    if not os.path.isfile(sync_script):
        return (
            f"Error: sync_verify_mirror.sh not found at {sync_script}. "
            "The mirror check cannot run without the repo's sync script."
        )
    buf = io.StringIO()
    err = io.StringIO()
    rc = 2
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(err):
        rc = cmc.main(["--sync-script", sync_script, "--root", REPO_ROOT, "--json"])
    raw = buf.getvalue().strip()
    try:
        report = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        report = {}
    report["exit_code"] = rc
    if not report or not raw:
        detail = err.getvalue().strip() or "no output"
        return (
            f"Error: mirror check failed (exit {rc}): {detail}. "
            "If the repo moved, restart the server from the repo checkout."
        )
    if response_format == "json":
        return json.dumps(report, ensure_ascii=False, indent=2)
    status = "OK — mirror list covers the repo runtime set" if report.get("ok") else "MISSING/STALE — coverage gap"
    lines = [
        f"# Mirror coverage — {status} (exit {rc})",
        "",
    ]
    for label, key in (("EKSİK / missing", "missing"), ("BAYAT / dead", "dead"),
                       ("BEKLENMEYEN / unexpected", "unexpected")):
        paths = report.get(key) or []
        if paths:
            lines.append(f"**{label} ({len(paths)}):**")
            for p in paths:
                lines.append(f"- `{p}`")
    if not any(report.get(k) for k in ("missing", "dead", "unexpected")):
        lines.append("All expected runtime files are covered; no stale or unexpected entries.")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main(argv: Optional[List[str]] = None) -> int:
    global PREVIEW_DIR
    parser = argparse.ArgumentParser(
        description="verify_mcp — read-only MCP server for the local verification chain (stdio)",
    )
    parser.add_argument(
        "--preview-dir",
        default=None,
        help=f"preview state dir with history.jsonl + runs/ (default: {DEFAULT_PREVIEW_DIR})",
    )
    parser.add_argument(
        "--list-tools",
        action="store_true",
        help="print the registered tool names and exit (no MCP handshake)",
    )
    args = parser.parse_args(argv)

    PREVIEW_DIR = (
        args.preview_dir
        or os.environ.get("VERIFY_MCP_PREVIEW_DIR")
        or DEFAULT_PREVIEW_DIR
    )

    if args.list_tools:
        for name in sorted(mcp._tool_manager._tools):
            print(name)
        return 0

    mcp.run()  # stdio transport (default)
    return 0


if __name__ == "__main__":
    sys.exit(main())
