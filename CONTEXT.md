# CONTEXT.md — domain glossary

Terms that name the repo's seams and modules. Architecture reviews and
refactors use these names; add a term here whenever a deepened module is
named after a concept that did not have one yet.

## Pre-commit log

**Pre-commit log** — the verbose output of a `pre-commit run --all-files`
session: the hook status lines (`Name....Passed`), the `hook id:` attribute
blocks, the update-config block, and the P0/P1 findings block.

It arrives through two routes (both are the same log):

- live, as subprocess `stdout`/`stderr` of a pre-commit run started by the
  dashboard (`preview_server.py`);
- on disk, as `logs/precommit.log` (read by the report generator).

Its parsed form is the **hook record** (`{name, id, status, source}`): the
single record shape shared by the dashboard panel, the SSE payload, and the
`PRECOMMIT_RAPORU.json` sidecar. `source` says which route the records were
read from (`stderr` | `stdout` | `sidecar` | `log`).

The module that owns this concept is `_calisma/CIKTI/precommit_log.py`
(pure parsers + one collector owning the source-priority chain).
