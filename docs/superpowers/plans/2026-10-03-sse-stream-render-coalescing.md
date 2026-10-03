# SSE Stream Render Coalescing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop `/preview.html` from freezing its main thread for ~88 s on load by rendering the SSE run-stream once per frame instead of once per received line.

**Architecture:** `connectStream()` currently rebuilds a 600-line HTML block (`el.innerHTML = streamLines.join("\n")`) on **every** line it receives. With 15 run logs replayed on connect that is 14,591 rebuilds of up to 600 HTML lines — quadratic work that blocks the main thread. The fix introduces a single `scheduleStreamRender()` helper inside `connectStream()` that coalesces all render requests into at most one DOM rebuild per ~16 ms, and routes all four existing render sites through it. `streamLines` stays the single source of truth, so trimming (`STREAM_MAX`) and scroll-pinning are unchanged.

**Tech Stack:** Vanilla ES2020 browser JS (`_calisma/CIKTI/preview.js`), stdlib-only Python `unittest` for the contract test, Playwright/Chromium for the measurement step.

**Spec:** No spec doc exists — this plan is the direct descendant of a `brainstorming` spike whose evidence is reproduced below and which was approved for a plan on 2026-10-03. Because the spike is the spec, its measurements are copied verbatim into the Evidence section.

## Evidence (measured 2026-10-03, not estimated)

CDP CPU profile spanning the stall (`Profiler.setSamplingInterval` 200 µs), seeded 8-row history, real `preview_server`, 15 run logs on disk:

```
nav=178ms  marker=86388ms  maxGap=86036ms at=239ms
=== TOP SELF-TIME FRAMES (of 321552 samples) ===
    62369.8ms  311849  push @ preview.js:1329
      627.2ms    3136  (garbage collector)
       96.0ms     480  (anonymous) @ preview.js:1419
```

`push` = **62.4 s of an 86.0 s freeze**, 311,849 of 321,552 samples (~97%).

SSE replay volume, counted directly off `/api/run-stream`:

| preview dir | events | bytes | main-thread max gap | marker |
| --- | --- | --- | --- | --- |
| `runs/` populated | **14,591** | 1,635,953 | 89.8 s / 110.3 s | 90.2 s / 122.3 s |
| `runs/` emptied | **1** | 99 | 30.3 s / 30.6 s | 30.4 s / 30.8 s |

2×2 isolation (same page, same dir, only `runs/` and the background verify differ):

| case | marker | max gap |
| --- | --- | --- |
| runs=ON, verify=ON | 93,824 ms | 57,331 ms |
| runs=OFF, verify=ON | **139 ms** | **90 ms** |
| runs=OFF, verify=OFF | **78 ms** | **62 ms** |
| runs=ON, verify=OFF | 124,040 ms | 111,404 ms |

→ **`runs/` is the sole driver.** The background verify subprocess is irrelevant (B ≈ C), and with replay removed the page is instant. The spike's earlier "30 s residual" was an artefact of a single unpurged run log left in the "empty" dir by the seeding step; the matrix above re-measured it away.

Prototype fixes measured on the same seeded fixture:

| variant | main-thread max gap | marker | page errors |
| --- | --- | --- | --- |
| baseline (current) | **88,000 ms** | 301 ms | 0 |
| `requestAnimationFrame` coalescing | 135–148 ms | 226 ms | 0 |
| `setTimeout(…, 16)` coalescing | **103 ms** | — | 0 |
| incremental DOM append | 64 ms | 85 ms | 0 |

Correctness check after full replay drained (coalesced variant): exactly **600** lines (trim intact), scroll pinned to bottom, findings panel populated (`155` bytes), **0 page errors**.

**Approach chosen: `setTimeout(…, 16)` coalescing.** It is a 1-helper/4-call-site diff, measured to eliminate the freeze (88,000 ms → 103 ms), and unlike `requestAnimationFrame` it still fires when the tab is backgrounded — `rAF` is paused in hidden tabs, which would leave the stream blank while the dashboard is not focused. Incremental append measured marginally faster (64 ms) but needs per-node bookkeeping and an equivalence contract that this plan does not need to carry.

## Global Constraints

- `_calisma/` runtime surfaces (comments, user-facing strings): Turkish. Commit messages: ASCII-only Turkish, `type(scope): <subject>` ≤ 72 chars, footer `Generated with Codebuff` + `Co-Authored-By: Codebuff <noreply@codebuff.com>`.
- Prettier must pass: `singleQuote`, `printWidth: 80`, `semi`, `arrowParens: always` (`.prettierrc`). The gate `check-prettier-format` runs in pre-commit and CI.
- Battery stays green at every commit (currently 158 test files; 159 after Task 2).
- Battery-imported Python is stdlib-only (`check-unit-tests` runs under `_calisma/.venv_z3`).
- **Do not change** `STREAM_MAX` (600) or the server's `RUN_LOG_MAX` (20). Replay volume is a product decision; this plan fixes the renderer's complexity, not the amount of history.
- Fail-closed gates stay fail-closed: never use `--no-verify` to land a commit.
- No new runtime dependency: `setTimeout` is already used in `preview.js`.

---

### Task 1: Coalesce the stream render (freeze fix)

**Files:**
- Modify: `_calisma/CIKTI/preview.js` (`connectStream()`, ~1315–1455)
- Test: `_calisma/CIKTI/test_stream_render_coalescing.py` (create)

**Interfaces:**
- Consumes: nothing from earlier tasks (first task).
- Produces: `scheduleStreamRender()` — a `const` arrow function declared inside `connectStream()`, taking no arguments, returning `undefined`. It reads the module-level `streamLines` array and the closure-local `el`; it schedules at most one DOM rebuild per ~16 ms. Task 2 registers the test file in the battery.

- [x] **Step 1: Write the failing test**

Create `_calisma/CIKTI/test_stream_render_coalescing.py` with exactly this content:

```python
#!/usr/bin/env python3
"""test_stream_render_coalescing.py — SSE akis render'i kare-basina sozlesmesi.

KOK NEDEN (olcum 2026-10-03, CDP CPU profili; spec: plan dosyasinin
"Evidence" bolumu):
  `push` her satirda `el.innerHTML = streamLines.join("\\n")` ile 600 satirlik
  HTML blogunu yeniden kuruyordu. Replay 14.591 satir oldugunda bu ikinci
  dereceden is 88.0 sn ana-thread kilidi uretti; profilde `push` 62.4 sn
  self-time (311.849/321.552 ornek). Kapinin settle tavani bu yuzden 180 sn'ye
  cikarilmisti.

SOZLESME:
  1) Satir-basina yeniden kurma YOK: `el.innerHTML = streamLines.join` TAM
     OLARAK BIR kez gecer ve o da coalescing yardimcisinin icindedir.
  2) Dort render noktasi da yardimciyi cagirir.
  3) Yardimci bekleyen-bayrak ile korunur: N satir -> tek render.
  4) Kirpma (STREAM_MAX) ve scroll korunur.
  5) rAF DEGIL setTimeout: rAF gizli sekmede duraklatilir, akis bos kalirdi.
"""
import os
import re
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PREVIEW_JS = os.path.join(HERE, "preview.js")

RENDER_BODY = 'el.innerHTML = streamLines.join("\\n");'
HELPER_CALL = "scheduleStreamRender();"


class StreamRenderCoalescingTests(unittest.TestCase):
    """preview.js kaynagi: render kare-basina, satir-basina degil."""

    @classmethod
    def setUpClass(cls):
        with open(PREVIEW_JS, encoding="utf-8") as stream:
            cls.src = stream.read()

    def connect_stream_body(self):
        """connectStream() govdesi (ilk sutun-0 '}' ile biter)."""
        match = re.search(r"function connectStream\(\) \{(.*?)\n\}",
                          self.src, re.S)
        self.assertIsNotNone(match, "connectStream bulunamadi")
        return match.group(1)

    def helper_body(self):
        """scheduleStreamRender govdesi (const ... = () => { ... };)."""
        match = re.search(
            r"const scheduleStreamRender = \(\) => \{(.*?)\n  \};",
            self.src, re.S)
        self.assertIsNotNone(match, "scheduleStreamRender bulunamadi")
        return match.group(1)

    def test_helper_exists_inside_connect_stream(self):
        """Yardimci connectStream icinde olmali: `el` closure'dan gelir."""
        body = self.connect_stream_body()
        self.assertIn("const scheduleStreamRender = () => {", body)

    def test_no_per_line_rebuild_remains(self):
        """Satir-basina yeniden kurma kalkmali.

        Mutation kaniti: `push` icindeki cagriyi eski iki satirlik
        `el.innerHTML = ...` bloguna dondurmek bu testi kirmiziya dusurur.
        """
        body = self.connect_stream_body()
        # push'un kendi govdesinde yeniden kurma YOK
        push = re.search(r"const push = \(tag, line, replay\) => \{(.*?)\n  \};",
                         body, re.S)
        self.assertIsNotNone(push, "push bulunamadi")
        self.assertNotIn(RENDER_BODY, push.group(1),
                         "push satir-basina innerHTML kurmamali")

    def test_rebuild_happens_exactly_once_and_in_the_helper(self):
        """`innerHTML = streamLines.join` tam olarak bir kez, yardimci icinde."""
        self.assertEqual(self.src.count(RENDER_BODY), 1,
                         "yeniden kurma tek noktada olmali (yardimci)")
        self.assertIn(RENDER_BODY, self.helper_body(),
                      "yeniden kurma yardimcinin icinde olmali")

    def test_all_render_sites_use_the_helper(self):
        """Dort render nokasi da (push/replay-start/replay-end/end) yardimciyi cagirir."""
        self.assertEqual(self.connect_stream_body().count(HELPER_CALL), 4,
                         "4 render nokasi da scheduleStreamRender cagirmali")

    def test_helper_is_coalesced_with_a_pending_flag(self):
        """N satir -> tek render: bayrak olmadan coalescing olmaz."""
        body = self.helper_body()
        self.assertIn("_streamRenderPending", body)
        self.assertRegex(body, r"if \(_streamRenderPending\) return;",
                         "bekleyen render varsa erken donmeli")
        self.assertIn("_streamRenderPending = true;", body)
        self.assertIn("_streamRenderPending = false;", body)

    def test_helper_uses_timeout_not_raf(self):
        """rAF gizli sekmede duraklatilir; akis bos kalmasin diye setTimeout."""
        body = self.helper_body()
        self.assertIn("setTimeout(", body)
        self.assertNotIn("requestAnimationFrame", body)

    def test_trim_and_scroll_preserved(self):
        """Kirpma ve scroll davranisi degismemeli."""
        body = self.helper_body()
        self.assertIn("el.scrollTop = el.scrollHeight;", body)
        # STREAM_MAX kirpmasi connectStream icinde kalmaya devam ediyor
        self.assertIn("STREAM_MAX", self.connect_stream_body())

    def test_no_other_quadratic_renderer_added(self):
        """connectStream tek render noktasi tasimali.

        Dosya genelinde baska `innerHTML = ...join` noktalari var (grafik
        `svg`, tooltip `tip` vb.) ve bunlar akis yolu degil; olcum onlari
        isaret etmedi. Sozlesme yalnizca akis yolunu baglar: connectStream
        icinde TEK join'li innerHTML kalmali ve o da yardimcinin icinde.
        """
        joins = re.findall(
            r"innerHTML = [A-Za-z_]+\.join\(", self.connect_stream_body()
        )
        self.assertEqual(
            len(joins), 1, "akis yolunda tek render noktasi olmali (yardimci)"
        )


if __name__ == "__main__":
    unittest.main()
```

- [x] **Step 2: Run test to verify it fails**

Run: `cd /private/tmp/wtfaz4/_calisma/CIKTI && python3 -m unittest test_stream_render_coalescing -v`

Expected: **FAIL** — all 8 tests fail. `helper_body()` returns `None` for the 4 tests that reach the helper; `test_no_per_line_rebuild_remains` fails because `push` still contains `RENDER_BODY`; and `test_rebuild_happens_exactly_once_and_in_the_helper` reports `4 != 1` because the idiom still appears at all four sites. (Verified against the unfixed `preview.js`: `Ran 8 tests ... FAILED (failures=8)`.)

- [x] **Step 3: Write minimal implementation**

In `_calisma/CIKTI/preview.js`, inside `connectStream()`, insert the helper immediately **before** the line `  const push = (tag, line, replay) => {`:

```js
  // ─── Akış render'ı: satır-başına değil, kare-başına ─────────────────────
  // ÖLÇÜM 2026-10-03 (CDP CPU profili): replay 14.591 satır geldiğinde her
  // satırda 600 satırlık HTML bloğunu yeniden kurmak ana thread'i 88.0 sn
  // kilitliyordu (profilde `push` 62.4 sn self-time = 311.849/321.552 örnek;
  // maxGap 88.000 ms -> coalescing ile 103 ms). rAF DEĞİL setTimeout: rAF
  // gizli sekmede duraklatılır ve akış boş kalırdı; setTimeout ~16 ms'de
  // birleştirir. `streamLines` tek doğruluk kaynağı kalır — kırpma ve scroll
  // davranışı değişmez.
  let _streamRenderPending = false;
  const scheduleStreamRender = () => {
    if (_streamRenderPending) return;
    _streamRenderPending = true;
    setTimeout(() => {
      _streamRenderPending = false;
      el.innerHTML = streamLines.join("\n");
      el.scrollTop = el.scrollHeight;
    }, 16);
  };
```

Then replace **all four** occurrences of this exact two-line pair:

```js
    el.innerHTML = streamLines.join("\n");
    el.scrollTop = el.scrollHeight;
```

with this single call:

```js
    scheduleStreamRender();
```

The four sites are: the tail of `push`, the tail of the `replay-start` handler, the tail of the `replay-end` handler, and the tail of the `end` handler. Leave the surrounding `if (streamLines.length > STREAM_MAX) streamLines = streamLines.slice(-STREAM_MAX);` trimming exactly as it is.

- [x] **Step 4: Run test to verify it passes**

Run: `cd /private/tmp/wtfaz4/_calisma/CIKTI && python3 -m unittest test_stream_render_coalescing -v`

Expected: **PASS** (`Ran 8 tests ... OK`).

- [x] **Step 5: Verify syntax and formatting**

Run:
```bash
cd /private/tmp/wtfaz4 && export PATH="$HOME/.nvm/versions/node/v22.23.2/bin:$PATH"
node --check _calisma/CIKTI/preview.js && echo "JS SYNTAX OK"
python3 _calisma/CIKTI/check_prettier_format.py --diff --base origin/main
```

Expected: `JS SYNTAX OK`, and the prettier gate reports no files (SKIP).

Note (corrected during execution): do **not** run `npx prettier` on these two
files. `_calisma/CIKTI/preview.js` is listed in `.prettierignore` (a patcher
owns its formatting, see the ignore file's rationale) and the gate only scans
`js/jsx/ts/tsx/json`, so a `.py` argument fails with "No parser could be
inferred". The real gate is `check_prettier_format.py`.

- [x] **Step 6: Measure the fix end-to-end (the evidence this plan exists for)**

Run the coalescing measurement script (create it as a throwaway outside the repo, e.g. `/tmp/measure_coalescing.py`, reusing the fixture pattern: seed 8 rows via `seed_a11y_history.py`, start `preview_server.py --interval 3600`, load `/preview.html` in headless Chromium with the `setInterval` heartbeat init-script, and report `maxGap`).

Expected: main-thread `maxGap` drops from ~88,000 ms to **< 500 ms**, and `#runstream` still holds exactly 600 lines with scroll pinned to the bottom. Record the before/after numbers for the commit message.

**Measured (2026-10-03, this execution):**

| variant | marker | maxGap | lines | scroll | errors |
| --- | --- | --- | --- | --- | --- |
| baseline | 252 ms | **87,480 ms** | 600 | pinned | 0 |
| fixed | 337 ms | **125 ms** | 600 | pinned | 0 |

Both variants replayed exactly **14,591** events on connect. Repeats of the
fixed variant measured 142 ms and 152 ms; baseline repeats 83,873 ms and
90,262 ms — so the fix is stable, not a lucky sample.

**Additional equivalence check (beyond the plan):** with the live verify
disabled (`SPIKE_NO_VERIFY`, replay only, so page lifetime cannot confound),
baseline and fixed are byte-identical: 600 lines, 28,087 chars of stream text,
identical event sequence (`replay-start` 15 / `replay-end` 15), scroll pinned,
0 page errors. The live `end` handler (render site 4) was verified separately:
run-end boundary drawn, 600 lines, pinned, 0 errors.

**Why the findings panel looked different at first:** with verify ON, the
freeze keeps the baseline page alive ~90 s while the fixed page finishes in
~6 s, so the baseline simply receives more live verify lines before the
snapshot. The panel is rebuilt from `liveFindings`, which the fix does not
touch. With replay only (the change's actual scope) the panels are identical.

- [x] **Step 7: Commit**

```bash
cd /private/tmp/wtfaz4
git add _calisma/CIKTI/preview.js _calisma/CIKTI/test_stream_render_coalescing.py
git commit -F - <<'EOF'
perf(dashboard): akis render'i kare-basina, satir-basina degil

/preview.html ana thread'i acilista ~88 sn kilitleniyordu. Kok neden CDP CPU
profili ile olculdu: connectStream'in `push` fonksiyonu HER satirda 600
satirlik HTML blogunu `el.innerHTML = streamLines.join("\n")` ile yeniden
kuruyordu. Sunucu baglantida 15 run logunu replay ettigi icin bu 14.591
yeniden kurma demek -- satir sayisiyla ikinci dereceden is.

Profil (321.552 ornek): push 62.4 sn self-time = 311.849 ornek (~%97);
maxGap 88.0 sn, isaret 86.4 sn'de geliyordu.

IZOLASYON (ayni sayfa, ayni dizin; tek fark runs/ ve arka plan verify):
  runs=ON  verify=ON    isaret 93.824 ms  maxGap  57.331 ms
  runs=OFF verify=ON    isaret    139 ms  maxGap      90 ms
  runs=OFF verify=OFF   isaret     78 ms  maxGap      62 ms
  runs=ON  verify=OFF   isaret 124.040 ms  maxGap 111.404 ms
Yani tek surucu replay hacmi; arka plan verify'in etkisi yok (B ~ C).

DUZELTME: scheduleStreamRender yardimcisi tum render noktalarini ~16 ms'de
birlestirir (N satir -> tek render). Olculen sonuc:
  once:  maxGap 88.000 ms
  sonra: maxGap    103 ms
Dort render nokasi da (push/replay-start/replay-end/end) yardimcidan gecer.
rAF DEGIL setTimeout: rAF gizli sekmede duraklatilir ve akis bos kalirdi.

streamLines tek dogruluk kaynagi kalir: kirpma (STREAM_MAX=600) ve scroll
davranisi degismedi (dogrulama: 600 satir, scroll dipte, 0 sayfa hatasi).

Kontrat testi (test_stream_render_coalescing.py, 8 test) mutasyon kanitli:
eski iki satirlik blogu geri koymak testi kirmiziya dusurur.

Generated with Codebuff
Co-Authored-By: Codebuff <noreply@codebuff.com>
EOF
```

Note: the pre-commit hook runs the full battery (~90 s) and may block on `check-precommit-orphans` if stale `~/.cache/pre-commit/patch*` files exist. If it blocks, archive them as the hook's own recovery message instructs — do **not** use `--no-verify`.

Note (corrected during execution): this commit **cannot** land on its own. The
fail-closed `check-coverage-report` gate rejects a new test file that no hook
covers, and pre-commit stashes *unstaged* changes before running hooks — so the
`check_unit_tests.list` / `test_coverage_report.py` registration has to be in
the same commit as the test. Task 1 Step 7 and Task 2 were therefore landed as
one atomic commit (`perf(dashboard): akis render'i kare-basina, satir-basina
degil`, 970fc0f). Do not split them.

---

### Task 2: Register the contract test in the battery

**Files:**
- Modify: `_calisma/CIKTI/check_unit_tests.list` (generated — edit via the sync tool)
- Modify: `_calisma/CIKTI/test_coverage_report.py` (`HOOK_COVERAGE` — generated, same tool)

**Interfaces:**
- Consumes: `test_stream_render_coalescing.py` from Task 1 (must exist and pass before this task).
- Produces: the test runs in the `check-unit-tests` gate on every commit, so the regression cannot silently return.

- [x] **Step 1: Run the sync tool to register the test**

Run:
```bash
cd /private/tmp/wtfaz4
python3 _calisma/CIKTI/sync_check_unit_tests.py --update --no-stage
```

Expected: output names `test_stream_render_coalescing.py` as `EKLENDİ` (added) for both the manifest and `HOOK_COVERAGE`.

- [x] **Step 2: Verify the manifest is in sync**

Run:
```bash
cd /private/tmp/wtfaz4 && python3 _calisma/CIKTI/sync_check_unit_tests.py --check
```

Expected: exit code 0, no drift reported.

- [x] **Step 3: Run the battery**

Run (the file is a bash script — `python3` on it fails with a SyntaxError):
```bash
cd /private/tmp/wtfaz4 && bash _calisma/CIKTI/check_unit_tests_hook.sh
```

Expected: `check-unit-tests: 157 test dosyası PASS.`

Note (corrected during execution): the hook counts manifest **entries**, not
file lines — `check_unit_tests.list` is 159 lines because 2 are comments, so
158 lines before / 159 after corresponds to **156 / 157 entries**.

If any unrelated test fails, **stop** and report — do not fold an unrelated fix
into this plan.

- [x] **Step 4: Commit**

**Folded into Task 1's commit during execution.** A separate commit is not
possible (see the note in Task 1 Step 7): the coverage gate blocks the test
commit until the manifest is registered, and pre-commit stashes unstaged
changes. The registration was staged together with `preview.js` and the test,
and the single commit's body carries the registration rationale. Verified
after the commit: `sync_check_unit_tests.py --check` exits 0,
`bash _calisma/CIKTI/check_unit_tests_hook.sh` prints
`check-unit-tests: 157 test dosyası PASS.`, and the new test is discoverable at
its manifest line (`test_stream_render_coalescing.py`).

---

## Execution record (2026-10-03)

Landed as a single commit `970fc0f` on branch `fix/stream-render-coalescing`
(based on `origin/main` = `df94b8e`), 5 files: `preview.js`, the new
`test_stream_render_coalescing.py`, `check_unit_tests.list`,
`test_coverage_report.py`, and the changelog row `README.md` that the repo's
own `check-changelog-sync` hook stages.

Defects found in this plan while executing it (all corrected above):

1. **Test regex was file-wide.** `test_no_other_quadratic_renderer_added`
   counted `innerHTML = <id>.join(` across the whole 3,000-line file, which
   matches 8 unrelated pre-existing sites (chart `svg`, tooltip `tip`), so it
   could never pass. Scoped to `connectStream()`; the assertion is now
   `== 1` (single render point in the stream path).
2. **Step 5 asked Prettier to parse a `.py` file**, which has no parser, and
   `preview.js` is `.prettierignore`d anyway. Replaced with the real gate.
3. **Two commits were impossible**; the manifest registration had to be in the
   same atomic commit as the test (coverage gate + pre-commit stash).
4. **Battery count was mis-stated** (159 lines vs 157 entries) and the battery
   script was invoked with `python3` instead of `bash`.

Contract test: 8 tests, mutation-checked (reverting one call site to the old
two-line rebuild turns 4 of them red). Battery green: 157 entries.

## Out of scope (deliberately not in this plan)

- **Replay volume itself.** `RUN_LOG_MAX = 20` and `STREAM_MAX = 600` are unchanged. This plan fixes the renderer's complexity, not how much history is replayed.
- **`renderLiveFindings()`** rebuilds `#findings-panel` from all `liveFindings` on each P0/P1 line — the same class of quadratic pattern. Measured **not** to be a bottleneck on this fixture (findings panel rendered 155 bytes; `runs=OFF` case is instant with it unchanged). Fix it only if a future measurement shows it dominating; adding it now would be speculative.
- **`applyStdout()`** (`el.innerHTML = colorizeStdout(text)`) runs once per snapshot with a 50-line cap — not per line. Left alone.
- **The 180 s `settle.timeout_ms`.** It was raised to survive this freeze. Do not lower it in this plan: that is a separate decision that needs its own measurement, and lowering it while the freeze fix is fresh would conflate two changes.
- **`loadDeterminismTrend()`** is defined but never called, so `#det-trend` never renders. Unrelated; noted only so it is not mistaken for part of this work.

## Self-Review

**Spec coverage:** The spike's single finding (per-line `innerHTML` rebuild → 88 s freeze) is covered by Task 1 Steps 1–7. The "5 render sites" observation from the spike is covered: `test_all_render_sites_use_the_helper` asserts all four `streamLines` sites route through the helper (the fifth `innerHTML` site the spike listed is `renderLiveFindings`, explicitly out of scope above with a measurement justifying that).

**Placeholder scan:** No "TBD"/"handle edge cases"/"similar to Task N". Every code step carries the literal code; every command carries its expected output.

**Type consistency:** `scheduleStreamRender` is spelled identically in the helper declaration, all four call sites, the test's `HELPER_CALL` constant, and Task 2's description. `_streamRenderPending` is the single flag name used in both implementation and test. `STREAM_MAX` and `streamLines` match the existing module-level names.
