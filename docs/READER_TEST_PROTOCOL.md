# Reader-Test Protocol (fresh-session spec comprehension)

**Status:** Protocol — ready to run
**Author:** Buffy (Codebuff) with ali-han-kaya
**Path:** Process — spec quality gate (pre-implementation / post-implementation)
**Instance under test:** `docs/superpowers/specs/2026-09-17-a11y-gate-design.md`
**Baseline run:** 2026-09-17 — verdict `reader-tested (2 gaps fixed inline)`,
fixed by commit `66721a4` (“add reporting surfaces”).

## 1. What this protocol is

A **reader test** answers one question: *can a competent reader who has never
seen this repo reconstruct the spec’s decisions from the spec text alone?*
It is not a review, not a code read-through, and not a discussion. It is a
one-way probe: the spec goes in, ten questions come out, and every answer is
scored against the decision the spec actually made.

The reader must be a **genuinely fresh session**: no conversation history, no
repo access, no tools, no browsing, no prior exposure to this project. If the
reader can guess the answer from anything other than the pasted spec, the test
is void.

Why re-run: the 2026-09-17 run was informal — its verdict is recorded
(`2 gaps fixed inline`) but the question set and per-question answers were not
committed, so the pass is not reproducible. This protocol makes the run
repeatable: fixed battery, fixed answer key, fixed rubric, recorded template.

## 2. Protocol mechanics (operator steps)

1. **Prepare the artifact.** Use the spec file verbatim — no trimming, no
   added summary. Copy its bytes; do not retype.
   ```
   shasum -a 256 docs/superpowers/specs/2026-09-17-a11y-gate-design.md
   ```
2. **Open a fresh session.** New conversation, no repo/system context, tools
   and browsing disabled. Record the model name, session id and start time.
3. **Paste the spec as the entire first message**, preceded only by the
   neutral frame below. Nothing else — no question list, no hint of what will
   be asked.
   ```
   You will be given a design document. Read it carefully. Afterwards I will
   ask you questions about it. Answer only from the document text. You may not
   browse, use tools, or ask me for clarification. If the document does not
   determine an answer, say exactly: "not specified in the document".
   ```
4. **Ask the ten questions one per turn, in the fixed order of §3.** One
   question per message prevents later questions from priming earlier answers.
5. **Do not lead.** Do not paraphrase the question, do not hint at the answer,
   do not confirm or correct mid-run. If the reader answers with a
   counter-question, record it verbatim — a clarifying counter-question is
   itself a gap signal — and reply only:
   `The document is the only source. Answer from it, or say it is not specified.`
6. **Record verbatim.** Capture each answer in full (not a summary), plus the
   reader’s stated confidence if offered (1–5), before the next question.
7. **Score after the run ends** (§4), never during it.
8. **Write the result** into the template in §6 and commit it next to this
   file as `docs/reader_test/<date>-a11y-gate.md`.

## 3. Canonical question battery (10)

The battery is fixed so runs are comparable. Each question probes exactly one
decision the spec is expected to have made, and each has one ground truth.

**Q1 — Placement.** *Which workflow file and which job run the accessibility
gate, and does this work create a new workflow file?*
Probes: CI placement decision. Key: `a11y-gate` job inside the existing
`.github/workflows/verify.yml`; **no new workflow file**. Gap class if failed:
missing decision.

**Q2 — Runtime and engine.** *What automation runtime and what browser/engine
does the gate use, and does it introduce a Node/npm dependency?*
Probes: technology constraint. Key: Python Playwright driving a real headless
Chromium; **no Node/npm** (repo has no `package.json`). Gap class: contradiction
/ unstated constraint.

**Q3 — Fail policy.** *Which axe impact levels block the run, which only warn,
and how are `incomplete` results treated?*
Probes: threshold contract. Key: `critical` + `serious` block; `moderate` +
`minor` warn (report-only level, never change the exit code); `incomplete` is
report-only. Gap class: ambiguity.

**Q4 — Unknown severity.** *What happens when axe returns an impact level the
configuration does not list?*
Probes: default-deny posture. Key: treated as **blocking** — unknown severity
blocks. Gap class: missing decision.

**Q5 — Supply-chain pin.** *How is the vendored axe bundle verified, and what
happens if the verification does not match?*
Probes: fail-closed file pin. Key: pinned by version **and** sha256 in the
sibling `axe.min.js.sha256` file; mismatch → **FAIL**. Gap class: missing
decision.

**Q6 — Server contract.** *How does the gate locate the dashboard server: what
argument does it take, which port, and how is readiness established?*
Probes: data-flow contract. Key: `--base-url http://127.0.0.1:PORT`; the job
assigns an **ephemeral port**; readiness is a **bounded poll — 30 × 1 s of
`GET /api/health`** (HTTP 200, body `ok`). Gap class: ambiguity / missing
decision.

**Q7 — Server late/absent.** *If the server is not up within the readiness
window, what is the outcome?*
Probes: fail-closed vs skip. Key: **FAIL** — never skip. Gap class: missing
decision.

**Q8 — Exit codes.** *List the exit codes and what each one means.*
Probes: machine contract. Key: `0` PASS, `1` FAIL (blocking violation or any
fail-closed condition), `2` usage/environment error. Gap class: missing
decision.

**Q9 — Reporting surfaces.** *Name the three reporting surfaces, and state
whether a `warn` finding can change the exit code.*
Probes: **the historical gap from the 2026-09-17 run** — this is the
regression check. Key: stdout (one-line verdict + violation table), the
`a11y_report.json` artifact (full axe payload + config echo + timestamps +
page URL), and the job-summary markdown table; a `warn` **never** changes the
exit code. Gap class: missing decision.

**Q10 — Allowlisting.** *What do allowlist entries match on, which field is
required, and is an allowlisted violation hidden from the report?*
Probes: debt-visibility invariant. Key: entries match an axe **rule id** plus
an **optional `target` selector substring**; every entry requires a
**`reason`**; allowlisted violations are **still printed**, marked
`allowlisted` — nothing is hidden. Gap class: unstated invariant.

**Deliberate invention trap (embedded in Q6, scored separately).** The spec
fixes the Playwright version only as “chosen at implementation time and
recorded in the workflow” — no number. A reader that states a concrete version
number, or that the port is fixed, is **inventing**; record an
`invented-specific` flag even if the surrounding answer is right.

## 4. Scoring rubric

Score each question on its own line; do not average away a failure.

| Mark | Meaning |
| --- | --- |
| `PASS` | Answer matches the key on every decision the question names. |
| `PARTIAL` | Directionally right, imprecise on a decision the spec fixes. |
| `FAIL` | Wrong, or contradicts the spec. |
| `UNSPECIFIED` | The reader says the document does not determine it **and the spec is in fact silent** — this is a *spec gap*, not a reader failure. |

Flags (orthogonal to the mark):

- `invented-specific` — the reader supplied a value the spec deliberately leaves open.
- `counter-question` — the reader asked for clarification instead of answering.
- `hedged` — the reader gave two mutually exclusive answers.

**Gap taxonomy** (classify each `FAIL` / `UNSPECIFIED`): *ambiguity*,
*missing decision*, *contradiction*, *unstated invariant*.

## 5. Pass criteria and regression check

- **Protocol pass:** all ten questions `PASS`, **or** every non-`PASS` line is
  classified as a spec gap and fixed inline in the spec before re-running.
- **Regression check (must hold):** **Q9 = `PASS`.** The 2026-09-17 run found
  two reporting-surface gaps, fixed by adding §“Reporting Surfaces” to the
  spec (`66721a4`). If Q9 fails now, the fix has regressed or the spec has
  drifted since.
- A single `PASS` run is not enough to claim “reader-tested” again: after any
  inline fix, **re-run the full battery on a fresh session**. Only the second
  clean run restores the claim, and the status line should cite this file plus
  the result document.
- Before promoting the claim, confirm the implementation matches the battery:
  unresolved answers are not spec gaps, they are implementation drift.

**Implementation cross-check (2026-09-24, post-implementation).** The key in §3
was checked against the shipped code so that a failed question is a spec gap
and not drift:

| Q | Verified against | Result |
| - | ---------------- | ------ |
| 1 | `.github/workflows/verify.yml` (`a11y-gate` job) | matches |
| 2 | `pip install playwright==1.63.0`; no `package.json` | matches (number deliberately absent from the spec) |
| 3 | `a11y_gate_config.json` (`blocking`/`warn`/`incomplete`) | matches |
| 5 | `axe.min.js.sha256` pin check in `a11y_gate.py` | matches |
| 6 | ephemeral port + 30 × 1 s `/api/health` poll; body `ok` asserted | matches (key widened to include the body check) |
| 10 | `VALID_ENTRY_KEYS = {rule, reason, target}`; empty `reason` rejected | matches |

## 6. Result template

```
# Reader-Test Result — A11y Gate Design
Date:            YYYY-MM-DDTHH:MMZ
Spec:            docs/superpowers/specs/2026-09-17-a11y-gate-design.md
Spec sha256:     <shasum -a 256 output>
Reader:          <model + version> / fresh session <id>
Operator:        <name>
Battery:         docs/READER_TEST_PROTOCOL.md §3 (10 questions, fixed order)
Protocol:        one question per turn; no tools; no clarification

| # | Mark | Flags | Gap class | Evidence (verbatim, trimmed) |
| - | ---- | ----- | --------- | ---------------------------- |
| 1 |      |       |           |                              |
| 2 |      |       |           |                              |
| 3 |      |       |           |                              |
| 4 |      |       |           |                              |
| 5 |      |       |           |                              |
| 6 |      |       |           |                              |
| 7 |      |       |           |                              |
| 8 |      |       |           |                              |
| 9 |      |       |           | (regression check)           |
|10 |      |       |           |                              |

verdict:            PASS | FAIL
regression Q9:      PASS | FAIL
spec gaps found:    <n>   (classes: …)
invented answers:   <n>
inline fixes:       <list, or "none">
re-run required:    yes | no
```

## 7. Reusing this protocol for another spec

1. Copy §3 into a new battery for the target spec: one question per fixed
   decision, each with a single ground truth, plus one *invention trap* for a
   value the spec deliberately defers.
2. Keep §2, §4 and §5 unchanged — the mechanics are what make runs comparable.
3. Freeze the battery before the run. Editing questions mid-run invalidates
   the run; extend the battery only in a new revision of this file.
