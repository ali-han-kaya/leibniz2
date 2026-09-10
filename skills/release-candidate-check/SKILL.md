---
name: release-candidate-check
description: Use this skill when building, extending, testing, or evaluating the verify_mcp MCP server for the local verification chain. Apply it when adding read-only MCP tools, changing tool schemas or annotations, updating JSONL/run-log data access, maintaining evaluation QA pairs, or preparing an MCP release candidate. Follow the stdio contract, preserve read-only behavior, and run focused tests plus the live tool-list/handshake checks before reporting readiness.
---

# verify_mcp release-candidate workflow

Use this workflow for changes to `_calisma/mcp/verify_mcp`. The server is a
read-only MCP adapter over local verification artifacts. It must not trigger a
verification run, mutate files, sync a mirror, or require a network service.

## 1. Inspect the contract first

Read:

- `_calisma/mcp/verify_mcp/server.py`
- `_calisma/mcp/verify_mcp/tests/test_verify_mcp.py`
- `_calisma/mcp/verify_mcp/README.md`
- `_calisma/mcp/verify_mcp/evaluation.xml`

Confirm the requested change has a public MCP seam: tool name, input schema,
output format, source artifacts, and error behavior. Keep the existing
`response_format` convention (`markdown` or `json`) unless the request
explicitly changes it.

## 2. Preserve the safety boundary

Every tool must be annotated as:

```python
annotations={
    "readOnlyHint": True,
    "destructiveHint": False,
    "idempotentHint": True,
    "openWorldHint": False,
}
```

Read from the configured preview directory and committed repository artifacts.
Do not accept filesystem paths, arbitrary SQL, shell commands, URLs, or tool
names from callers. Never use a tool implementation to start verification,
write JSONL, update sidecars, sync files, or alter the mirror.

Prefer the existing data-layer helpers (`_load_history`, `_load_run_logs`,
`_latest_record`, `_summarize`, `_emit`, `_klayers_from_disk`) over new parsing
paths. Preserve the source precedence and bounded history behavior documented
in the README.

## 3. Implement test-first

For every behavior change:

1. Add one focused test at the public tool seam.
2. Run it and confirm it fails for the expected missing behavior.
3. Add the smallest implementation that passes.
4. Run the focused test again.
5. Update README and `evaluation.xml` only when the public contract changed.

Tests should exercise real formatting and data flow with temporary preview
state, not private implementation details or mock call counts. Cover boundary
cases such as missing history, corrupt JSONL, absent layer sidecars, invalid
pagination, and empty findings where relevant.

## 4. Validate the server

From `_calisma/mcp/verify_mcp` with the Python 3.11 environment:

```bash
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python server.py --list-tools
```

The tool list must be deterministic and alphabetically ordered. The process
must emit no diagnostics to stdout in normal stdio mode; stdout is reserved for
JSON-RPC responses. Diagnostics belong on stderr.

For protocol changes, exercise a real newline-delimited JSON-RPC session:

```bash
printf '%s\n' \
  '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"rc-check","version":"1"}}}' \
  '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}' \
  | .venv/bin/python server.py --preview-dir /path/to/preview
```

Use a temporary populated preview directory for tool calls. Confirm the JSON
responses are valid, tool annotations remain read-only, and no write or run
side effects occur.

## 5. Evaluation contract

`evaluation.xml` contains the compact QA contract for the server. When tool
names, counts, parameter defaults, annotations, or mirror behavior change,
update the affected QA answer and add a focused unit test. Keep questions
answerable from the live server or its tool schema; avoid timestamps and other
unstable data unless the fixture controls them.

A release candidate is ready only when:

- focused and full MCP tests pass;
- `--list-tools` reports the expected sorted tools;
- the live stdio handshake returns valid protocol responses;
- all tools retain read-only/local annotations;
- malformed or missing local artifacts produce explicit, non-authoritative
  errors;
- the README and evaluation QA contract match the implementation; and
- `git diff --check` is clean.

## Reporting

Report the exact commands run, test counts, tool list, and any remaining
limitations. Do not claim the live evaluation passes unless the evaluation
harness actually ran against the live agent. A local unit suite is useful but
is not a substitute for an agent-backed evaluation.
