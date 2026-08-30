# verify_mcp

Read-only MCP server for the local Stoic-Hume verification chain. Exposes the
state produced by `verify_delivery.py` / `preview_server.py` as MCP tools over
stdio — run summaries, full run logs, K-layer status, run history, and mirror
coverage — so agents can answer questions like *"what was the latest verdict?"*
without starting the dashboard.

Everything is read from the same JSON artifacts the dashboard serves; **no tool
triggers a verification run and nothing is ever written** (all tools are
`readOnlyHint=true`, `openWorldHint=false`).

## Setup

Requires Python ≥ 3.11 (the repo's default `python3` is 3.9, too old for the
MCP SDK).

```bash
cd _calisma/mcp/verify_mcp
python3.11 -m venv .venv
.venv/bin/pip install -r requirements.txt

# sanity check
.venv/bin/python server.py --list-tools
```

The venv is already created in this checkout; `pip install -r requirements.txt`
recreates it after a clean clone.

## Running

```bash
# Default preview dir (~/Library/Caches/com.freebuff/preview)
.venv/bin/python server.py

# Explicit state dir (tests, CI artifacts, another machine)
.venv/bin/python server.py --preview-dir /path/to/preview
```

Also honored: `VERIFY_MCP_PREVIEW_DIR` (environment) → `--preview-dir` (flag)
→ default. The server speaks newline-delimited JSON-RPC over stdio and never
logs to stdout (all diagnostics go to stderr), so any MCP client can spawn it
directly.

### Client configuration

Claude Code / Claude Desktop:

```json
{
  "mcpServers": {
    "verify": {
      "command": "/Users/<you>/Desktop/leibniz2/_calisma/mcp/verify_mcp/.venv/bin/python",
      "args": ["/Users/<you>/Desktop/leibniz2/_calisma/mcp/verify_mcp/server.py"]
    }
  }
}
```

## Tools

All tools accept `response_format` (`"markdown"` default for humans,
`"json"` for programmatic use) and are annotated read-only / idempotent.

### `verify_get_latest`
Newest run summary: verdict, exit code, P0/P1, budget, layer counts, refs
verified, Z3/Lean status, mirror state, findings.

```text
> verify_get_latest
# Latest run — 2026-08-29T23:45:43.824627+00:00
- **Verdict**: **PASS** (exit 0)
- **P0 / P1**: 0 / 0
- **Duration**: 30.87s
- **Refs**: 61/61 verified
- **Proofs**: Z3 12/12 · Lean PASS
```

```text
> verify_get_latest response_format="json"
{"ts": "…", "verdict": "PASS", "exit_code": 0, "layer_counts": {"PASS": 1, …}, …}
```

Use cases: current chain health, "any P1 findings right now?", budget usage.

### `verify_list_run_history`
Paginated run history (newest first) from `history.jsonl`. Returns `total`,
`count`, `offset`, `has_more`, `next_offset`.

```text
> verify_list_run_history limit=3
# Run history (3 of 100)
| # | ts | verdict | exit | P0/P1 | dur (s) |
|---|----|---------|------|-------|---------|
| 1 | 2026-08-29T23:45:43.824627+00:00 | PASS | 0 | 0/0 | 30.87 |
| 2 | 2026-08-29T23:44:42.932799+00:00 | PASS | 0 | 0/0 | 31.18 |
```

Use cases: trend over the last N runs, finding a run to inspect next.

### `verify_get_run_detail`
Full record of one run by timestamp, including captured stdout. Accepts a
prefix (a date matches the newest run that day). Unknown timestamps return the
available list to retry from.

```text
> verify_get_run_detail ts="2026-08-29T23:45:43" max_stdout_chars=2000
```

Use cases: reading a failing run's output, checking what a layer actually did.

### `verify_get_layer_status`
Per-layer (K0..K22) PASS/FAIL/SKIP table. Sources, in order: the latest run
record's `layers`, then the `klayers.json` sidecar (`verify_delivery.py
--klayers-out`) in the preview dir, then the repo root.

> **Note:** local run records do *not* persist the `layers` dict (it lives in
> the dashboard's in-memory `/api/latest`), so on a machine without a
> `klayers.json` sidecar this tool reports that clearly instead of guessing
> from scalars. The CI `klayers` artifact or a `--klayers-out` run provides it.

```text
> verify_get_layer_status
# K-layer status — 2026-08-29T23:45:43.824627+00:00
**12 PASS · 0 FAIL · 2 SKIP**
| Layer | Label | Status |
|-------|-------|--------|
| K1 | Dış zip sidecar | PASS |
```

### `verify_check_mirror`
Mirror coverage (K17 contract) via the repo's own `check_mirror_coverage.py`,
run in-process. Reports `ok`, `missing` (EKSİK), `dead` (BAYAT), `unexpected`
and the checker's exit code. Lists files only — never syncs.

```text
> verify_check_mirror response_format="json"
{"ok": true, "exit_code": 0, "missing": [], "dead": [], "unexpected": []}
```

## Data sources

| Tool | Source |
|------|--------|
| get_latest / layer_status | newest `runs/run-*.json`, else newest `history.jsonl` line |
| list_run_history | `history.jsonl` (last 100 lines, oldest→newest on disk) |
| get_run_detail | `runs/run-<ts>.json` (full stdout/stderr) or history fallback |
| check_mirror | repo `sync_verify_mirror.sh --list` + `check_mirror_coverage.py` |

Field names and file layout mirror `preview_server.py` exactly
(`HISTORY_MAX=100`, `RUN_LOG_MAX=20`, sortable `run-<ts>.json` filenames).

## Security

- Read-only by construction: no tool writes, runs, or triggers anything.
- stdio transport, no network surface; no secrets, tokens, or credentials.
- `--preview-dir` is the only configuration; it can point anywhere the user
  running the server can read.
- Path inputs are matched against record timestamps only — no filesystem paths
  are accepted from callers.

## Tests

```bash
.venv/bin/python -m unittest discover -s tests -v
```

Covers the data layer, every tool (json + markdown), the mirror wrapper, and a
real newline-delimited JSON-RPC session over stdio (initialize → tools/list →
tools/call). An interactive alternative is the MCP Inspector:
`npx @modelcontextprotocol/inspector` pointed at
`.venv/bin/python server.py`.

## Evaluation

`evaluation.xml` holds 10 read-only QA pairs for measuring whether an agent can
answer realistic questions about the chain through this server.
