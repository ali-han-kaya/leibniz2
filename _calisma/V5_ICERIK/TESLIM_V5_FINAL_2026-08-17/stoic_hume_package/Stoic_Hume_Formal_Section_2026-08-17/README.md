# Stoic Katalepsis and Humean Custom — Formal Section Package
**Revision:** 2026-08-17 (post peer-review, complete)
**V5:** 2026-08-17 — manuscript updated to the locked V5 architecture
(see `ingiliz_empirizmi_v3.tex` / `.pdf` in this package)
**Manuscript:** *What an Extensional First-Order Formalization Leaves Underdetermined: Stoic Katalepsis and Humean Custom*

---

## What this package contains

This is the **final, peer-reviewed, reproducibility-ready** package
of the formal section of the manuscript, together with all
artefacts needed to verify the formal claims and integrate them
with the rest of the manuscript.

| File | Role | Status |
|------|------|--------|
| `core_section.tex` | **Formal-section deliverable** — LaTeX source of the formal section (885 lines, 11 subsections, 9 subsubsections); V5g bridge-collapse scope fix applied | REVISED |
| `L0_Lplus_spec.md` | Machine-readable specification of `L_0`, `L^+`, `𝒦` | REVISED |
| `model_check_report.md` | Narrative model-check report with Table A (16 Boolean rows) | REVISED |
| `core_formal_model_check.py` | Core model-check script, stdlib only — **PASS** | REVISED |
| `encoding_sensitivity_check.py` | **Encoding-sensitivity test** (`L_0^A` vs `L_0^B`) — stdlib only — **PASS** | NEW |
| `gate15_check.py` | **Gate 1.5 model-pair check** (T2–T5, incl. `Γ` on the pair) — stdlib only — **PASS** | NEW |
| `test_output.txt` | Captured output of `core_formal_model_check.py` on Python 3.11 | FROZEN |
| `encoding_sensitivity_output.txt` | Captured output of `encoding_sensitivity_check.py` on Python 3.11 | FROZEN |
| `gate15_output.txt` | Captured output of `gate15_check.py` on Python 3.11 | FROZEN |
| `provenance2_supplement.md` | **Provenance 2.0** — 7-column evidence register (ClaimID, §, Literal Claim, Primary Witness, Secondary Support, Evidence Type, Confidence) | NEW |
| `requirements.txt` | Dependency list (empty by design) | FROZEN |
| `REPRODUCIBILITY.md` | Run instructions, scope notes, version matrix | REVISED |
| `INTEGRATION_NOTE.md` | Sentence-by-sentence map for replacing the manuscript's §2 | REVISED |
| `internal_review_report.md` | The detailed internal peer review (input document) | REFERENCE |
| `ingiliz_empirizmi_v3.tex` | **Full manuscript (LaTeX)** — V5 revision (33 pp.) | REVISED |
| `ingiliz_empirizmi_v3.pdf` | **Full manuscript (PDF)** — compiled with tectonic | REVISED |
| `original_manuscript.pdf` | Pre-integration manuscript (PDF), for reference | REFERENCE |
| `MANIFEST.txt` | File-by-file MD5 hashes and sizes | FROZEN |

---

## What's in the formal section — at a glance

```
§1  Interpretive and Formal Preconditions
§2  The Minimal Extensional Language L_0
    §2.1  Stoic Minimal Dependency Skeleton
    §2.2  Humean Mechanism and the Exclusion Readings
§3  Proposition 1: Strength Relation Between Two Reconstructions
    §3.1  Bridge collapse and characterization (★)
§4  Controlled Reification and the Enriched Language
§5  The Class of Admissible Reconstructions 𝒦
§6  Proposition 2: Implicit Definability Failure over 𝒦
    §6.1  Definability qualification (Beth anchor)
§7  What Richer Languages Add
    Modal (□_s) · Justification logic (t:φ) · Grounding (G)
§8  Historical Anchoring: Four-Level Humean Analysis
§9  The Stoic Modal Clause: A Note
§10 Verification Status (Table A included)
§11 Scope of the Formal Result (final thesis statement)
```

**Six labelled results:** one Lemma (`lem:reduct-invariance`) and
five Propositions (`prop:strength`, `prop:bridge-collapse`,
`prop:underdet`, `prop:definability`, `prop:stability`).

### V5 additions to the manuscript (`ingiliz_empirizmi_v3.tex`)

The full manuscript now also contains, beyond the canonical core
section above:

- **§2.12 Stoic Application: Encoding Sensitivity** — two
  formalizations `L_0^A` (minimal `Kat(i)`) and `L_0^B`
  (provenance decomposition `Veridical ∧ SourceMatch ∧ □_src ¬FalseSource`)
  and the executed computational test (see below).
- **§2.13 Expressive Enrichments: The Minimal-Enlargement Benchmark**
  — the E0/E1/E2 table (representability vs. adequacy).
- **§2.14 Gate 1.5: Non-Triviality / Recoverability Check** — the
  ten-point T1–T10 test that the formal section must pass in full.
- **§2.15 Hyperintensionality: The Four-Layer Claim** — the HI1–HI4
  chain (Literature → Formalization → Theorem → Interpretation),
  labelled to avoid collision with the Humean H1–H3.
- **§4.6 Historical-Evidential Method: The Ev0–Ev4 Ladder** —
  bibliographic presence … influence, with Ev_n ⇏ Ev_{n+1}
  (availability ≠ influence; citation ≠ dependence), labelled to
  avoid collision with the E0/E1/E2 enrichments.
- **Appendix + Provenance** — the katalepsis/episteme hierarchy
  (M 7.151–152: katalepsis = sunkatathesis kataleptikei phantasiai;
  episteme = katalepsis asphales) added.
- **§6 Objections and Replies** — seven objections in the
  objection–concession–distinction–response format, plus
  §6.1 the Negative-Result Matrix.
- **Open Science Statement** — AI-assistance and verification
  disclosure before the References.

The manuscript is **33 pages** when compiled with tectonic. Gate 1.5
(§2.14) now carries the complete **10/10 verification table**
(Table 1): items T1/T6/T7/T8/T10 discharged by proof or definition;
items T2–T5 verified by `gate15_check.py`; item T9 by
`encoding_sensitivity_check.py`.

**Provenance 2.0** (`provenance2_supplement.md`) is the 7-column
expansion of the manuscript's 3-column Provenance Table — one row
per substantive claim, tagged with ClaimID, section, literal
claim, primary witness, secondary support, evidence type, and
confidence. It doubles as an editorial audit: any claim without a
row is either formal/self-evident or should not be in the text.
The ClaimIDs (P-codes) match the manuscript's Provenance Table row
for row; the V5 rows (P-16…P-19, P-03b) are included. This is an
optional supplement — it is not part of the page count.

---

## How to reproduce the verification

```sh
# (1) Python — no third-party dependencies
python3 --version          # 3.10 / 3.11 / 3.12 tested (3.9.6 also verified byte-for-byte, 2026-08-17)

# (2) Core model check
python3 core_formal_model_check.py
# Expected last line:
# PASS: Proposition 1 (Boolean + bridge + characterization)
#       and Proposition 2 (model pair).

# (3) Encoding-sensitivity test (V5)
python3 encoding_sensitivity_check.py
# Expected last line:
# VERDICT: ENCODING-SENSITIVE: the two encodings yield different
#          underdetermination results

# (4) Gate 1.5 model-pair check (V5)
python3 gate15_check.py
# Expected last line:
# PASS: Gate 1.5 model-pair items T2-T5.
```

All three scripts are deterministic: same output across runs on
the same Python version, no host-OS dependency, no locale
dependency, no time dependency. Their outputs must match
`test_output.txt`, `encoding_sensitivity_output.txt` and
`gate15_output.txt` byte-for-byte.

---

## What was changed vs. the previous version

The two peer reviews (the *external* one quoted in the original
request and the *internal* technical review included here) were
combined and every P0/P1/P2 item was applied. Highlights:

### V5 (2026-08-17)

- **Encoding-sensitivity test executed.** `encoding_sensitivity_check.py`
  enumerates all base assignments and modal resources for the Stoic
  modal clause. Result: under `L_0^A` the modal content is
  undetermined for all 16 base assignments; under `L_0^B` for 6 of
  10 admissible assignments (determined in the kataleptic case and
  its direct negation, by the decomposition axiom itself).
  Verdict: **encoding-sensitive in degree, robust in existence** —
  the general thesis survives both encodings. Written into §2.12
  and Gate 1.5 item T9.
- **Objections and Replies** added as §6 (seven objections) with the
  Negative-Result Matrix (§6.1).
- **Gate 1.5** ten-point non-triviality check added as §2.14, now
  with the complete 10/10 verification table (Table 1): items
  T2–T5 verified by `gate15_check.py` (admissibility, same reduct,
  different `G`, and `Γ` on the pair); T1/T6/T7/T8/T10 by proof;
  T9 by the encoding-sensitivity test.
- **E0/E1/E2** minimal-enlargement benchmark added as §2.13.
- **Open Science Statement** added before the References.
- **Factual fix:** the Sextus 1562 translator in “Citations and
  Editions” corrected from Hervet to Henri Estienne (the body text
  was already correct).
- **Citation audit (V5f):** Tillemans 1999 (cited in §5) added to
  References; standalone editor entries added for Beauchamp 1999 and
  Nidditch 1975; Bury entry annotated by volume year (1935 = Loeb
  vol. II); body Nidditch citation now year-bearing. Manuscript
  recompiled (still 33 pp.).

- **Thesis narrowed** to "the grounding atom is not implicitly
  definable in `L_0` over `𝒦`" (no longer "FOL cannot represent
  grounding").
- **Proposition 1** (formerly "Theorem 1") is now explicitly
  conditional and is followed by a new **bridge-collapse
  proposition** + **characterization $(\star)$**.
- **Proposition 2** (formerly "Theorem 2") is rebuilt as an
  *implicit definability failure* with three auxiliary
  propositions (definitional irreducibility, stability under
  `L_0`-theories, and definability qualification with the Beth
  anchor).
- **Stoic** formula is relabelled *minimal dependency skeleton*;
  the modal clause is identified as a separate residue.
- **Hume** analysis is organised into a four-level table
  (psychological-genetic / epistemic / normative exclusion /
  grounding), with H-I marked as the *strong exclusion
  reconstruction* (a candidate, not the default).
- **Sort discipline:** `I`, `Cont`, `B` in `L_0`; `Fact ⊆ Cont`
  in `L^+`; `E` only in the justification-logic enrichment.
- **Modal operator** is now `□_s` with an explicit index
  (source-reliability, epistemic, or metaphysical).
- **Justification logic** is correctly typed as a separate
  *judgement* of the metalanguage, not as an `L_0` formula.
- **Verification** now includes a 16-row Boolean table
  (Table A) and the "unique countermodel" claim is documented
  and machine-checked.

---

## Citation

The manuscript and this package should be cited together.
For internal use, the manuscript's bibliographic information
in the original PDF (§References) applies.

Classical sources used by the package:
- Stoic epistemology: DL 7.46 [Dorandi 2013]; M 7.248, 7.402
  [Bury 1935]; Frede 1983; Bobzien 2003.
- Hume: T (Norton & Norton 2000); E (Beauchamp 1999);
  Garrett 1997; Millican 2002; Beebee 2006; Della Rocca 2010;
  Pruss 2006.
- Grounding: Fine 2012; Correia & Schnieder 2012; Schnieder
  2011.
- Justification logic: Artemov 2008; Artemov & Fitting 2019.
- Definability: Beth 1953.

---

## Contact

Bugs, questions and extension proposals: the corresponding
author of the manuscript.
