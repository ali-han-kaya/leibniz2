# ADR: MCP Python SDK 1.x → 2.x migration (`_calisma/mcp`)

**Status:** Accepted and applied in the working tree. Not committed.
**Date:** 2026-10-17
**Scope:** the main checkout only. Two MCP servers: `_calisma/mcp/server.py` (leibniz2, 7 tools) and `_calisma/mcp/verify_mcp/server.py` (verify, 5 tools).

## Context

- Both servers were pinned below 2.x:
  - `_calisma/mcp/requirements.txt`: `mcp[cli]>=1.10,<2`, `pydantic>=2.7,<3`
  - `_calisma/mcp/verify_mcp/requirements.txt`: `mcp>=1.29,<2`
- MCP SDK 2.x (2.3.0 is the latest on PyPI, Python >=3.10) renames `FastMCP` to `MCPServer` (`mcp.server.mcpserver`). The old `mcp.server.fastmcp` module is removed. Migration guide: https://github.com/modelcontextprotocol/python-sdk/blob/main/docs/migration.md
- The guide raises the pydantic floor to `>=2.12`.

## Decision

1. Move both servers to `MCPServer` and pin `mcp>=2,<3`. Set the leibniz2 pydantic floor to `>=2.12,<3`.
2. Keep the change surface small:
   - Keep dict-valued `annotations=` on `@tool`. 2.x coerces the dict into `ToolAnnotations`.
   - Replace the private `mcp._tool_manager._tools` in verify's `--list-tools` with the public `await mcp.list_tools()`.
3. Scope: only the main checkout is migrated. The seven `.worktrees/*` checkouts on feature branches stay on FastMCP with `<2` pins. See "Merge consequence" below.

## Evidence (measured 2026-10-17)

| Check | v1 (mcp 1.30.0 leibniz / 1.29.1 verify) | v2 (mcp 2.3.0, pydantic 2.14.1) |
|---|---|---|
| `_calisma/mcp/smoke_mcp.py` exit | 0 (all scenarios green; run before the `read_only_hint` assertion was added) | 0 (all scenarios green, including the `read_only_hint` assertion) |
| `verify_mcp` unittest (`discover -s tests`) | 26 tests, OK | 26 tests, OK |
| verify `server.py --list-tools` | exit 0, 5 tools | exit 0, 5 tools |
| Tool surface (`list_tools` dump: names, descriptions, input schemas, annotations) | leibniz 7, verify 5 | identical (`diff` empty for both servers) |
| `ResourceWarning` count in verify tests | 8 | 8 (already present before the migration) |

The v1 side of the tool-surface comparison uses the current files with `MCPServer` reverted to `FastMCP` by text substitution. This isolates the SDK change from the other uncommitted edits in those files.

**Mutation check (annotation regression):** I renamed `"readOnlyHint"` to `"readonlyhint"` in `server.py`. The smoke exited 1 and flagged all 7 leibniz2 tools for `read_only_hint`. After restoring `server.py` from a backup, its SHA-256 prefix matched the pre-mutation value (`4e334e768caacb8c`), and the smoke went green again.

## Per-file change list

| # | File | Change |
|---|---|---|
| 1 | `_calisma/mcp/requirements.txt` | `mcp[cli]>=1.10,<2` → `mcp[cli]>=2,<3`; `pydantic>=2.7,<3` → `pydantic>=2.12,<3`; comment updated |
| 2 | `_calisma/mcp/verify_mcp/requirements.txt` | `mcp>=1.29,<2` → `mcp>=2,<3`; comment updated |
| 3 | `_calisma/mcp/server.py` | `from mcp.server.fastmcp import FastMCP` → `from mcp.server.mcpserver import MCPServer`; `FastMCP("leibniz2_mcp")` → `MCPServer("leibniz2_mcp")` |
| 4 | `_calisma/mcp/verify_mcp/server.py` | Same import swap; `FastMCP("verify_mcp")` → `MCPServer("verify_mcp")`; added `import asyncio`; `--list-tools` uses `sorted(t.name for t in asyncio.run(mcp.list_tools()))` instead of `mcp._tool_manager._tools` |
| 5 | `_calisma/mcp/README.md` | Pin note `<2` → `>=2,<3`; FastMCP wording updated |
| 6 | `_calisma/mcp/verify_mcp/tests/test_verify_mcp.py` | Docstring only: "FastMCP tool functions" → "MCPServer tool functions" (no code change) |
| 7 | `_calisma/mcp/smoke_mcp.py` | New assertion after the `list_tools` name check: every tool must have `annotations.read_only_hint is True` (`getattr` default `None` fails closed) |
| — | `_calisma/mcp/.venv`, `_calisma/mcp/verify_mcp/.venv` | Rebuilt on `python3.11` from the new requirements. Untracked and gitignored. |

Rows 3–7 sit on top of pre-existing uncommitted edits in `server.py`, `smoke_mcp.py`, and `evals.xml` (the `/api/health` plain-text fix and the `MCP_SMOKE_BASE_URL` live-base option). The migration did not change `evals.xml`.

**Rollback:** restore the `<2` pins and the `FastMCP` import and constructor lines by hand. Do not run `git checkout` on these files, because they carry uncommitted work that is not from this migration.

## Merge consequence

Seven `.worktrees/*` checkouts still contain the FastMCP v1 `server.py` and `mcp>=1.29,<2` (verified: 7 of 7). Their branches are `codex/ci-cache6-setup-python7-20260925`, `feat/github-site-sample`, `land/trivy-ci-hygiene-20261005`, `land/trivy-ci-hygiene-cve-20261005`, `ledger-cb6f607`, `split/ci-hygiene-trivy-20261006`, and `feat/vercel-git-deploy`. Merging any of them into main will conflict with rows 1–4 of the change list. The v2 versions should win at merge time. Those worktrees were not touched.

## Not verified / limitations

- **Evals:** `_calisma/mcp/evals.xml` and `verify_mcp/evaluation.xml` have no runner in the repo. Only that every tool they name still exists was checked.
- **CI:** no workflow in `.github/workflows/` references `mcp` or its requirements. Whether CI runs the smoke with these pins was not verified.
- **Dockerfiles:** none found that pin `mcp`.
- **Annotation assertion coverage:** the new `read_only_hint` assertion covers only the leibniz2 server. The verify server has no equivalent check.
- **Python:** the system `python3` is older than 3.10, which 2.x requires. All venvs were built with `python3.11`.
- **Merge conflicts:** not tested. See "Merge consequence".
