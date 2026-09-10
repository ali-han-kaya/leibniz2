# Core formal section — Reproducibility package
**Manuscript:** "What an Extensional First-Order Formalization Leaves
Underdetermined: Stoic Katalepsis and Humean Custom"
**Revision:** 2026-08-17 (V5: full manuscript `ingiliz_empirizmi_v3.tex`/`.pdf`
included; encoding-sensitivity test added)

This package ships the formal section of the manuscript together
with the artefacts needed to reproduce the computational checks
cited in it.

## Files

| File | Role |
|------|------|
| `core_section.tex` | The LaTeX source of the formal section. |
| `L0_Lplus_spec.md` | Machine-readable specification of `L_0` / `L^+` / `𝒦`. |
| `model_check_report.md` | Narrative model-check report (with Table A). |
| `core_formal_model_check.py` | Python script: Proposition 1 (Boolean + bridge + characterization) and Proposition 2 (model pair). |
| `encoding_sensitivity_check.py` | Python script (V5): encoding-sensitivity test of the Stoic modal clause under `L_0^A` and `L_0^B`. |
| `gate15_check.py` | Python script (V5): Gate 1.5 model-pair items T2–T5, incl. the structural constraints `Γ` on both `G` extensions. |
| `REPRODUCIBILITY.md` | This file. |\n| `Makefile` | Reproducible tectonic + `SOURCE_DATE_EPOCH` PDF build. |
| `requirements.txt` | Empty: the scripts depend only on the Python 3 standard library. |
| `test_output.txt` | Captured output of `core_formal_model_check.py` on Python 3.11 (also verified on 3.10 and 3.12). |
| `encoding_sensitivity_output.txt` | Captured output of `encoding_sensitivity_check.py` on Python 3.11 (also verified on 3.10 and 3.12). |
| `gate15_output.txt` | Captured output of `gate15_check.py` on Python 3.11 (also verified on 3.10 and 3.12). |
| `provenance2_supplement.md` | Provenance 2.0 evidence register — 7-column expansion of the manuscript's Provenance Table (ClaimID, §, Literal Claim, Primary Witness, Secondary Support, Evidence Type, Confidence). Optional supplement; not part of the page count. |
| `ingiliz_empirizmi_v3.tex` | Full manuscript (LaTeX), V5 revision, 33 pp. when compiled. |
| `ingiliz_empirizmi_v3.pdf` | Full manuscript (PDF), compiled with tectonic (33 pp.). |

## Reproducible PDF build (tectonic + SOURCE_DATE_EPOCH)

The repository-level example `docs/Makefile.tectonic` follows the academic
Makefile pattern while keeping the build inputs explicit. It derives the
default epoch from the latest Git commit; set it explicitly when reproducing
a historical build:

```sh
make -f docs/Makefile.tectonic pdf
SOURCE_DATE_EPOCH=1755600000 make -f docs/Makefile.tectonic check
```

The Makefile writes intermediate files under `.build/tectonic`, copies the
resulting PDF into this package, and prints its SHA-256. `tectonic` must be
installed; missing tooling is an environment error for this explicit build
command, rather than a false reproducibility PASS.

## Reproducible PDF build (tectonic + SOURCE_DATE_EPOCH)

The package `Makefile` follows the academic `md-to-pdf-academic` pattern,
using tectonic as the PDF engine and making the epoch explicit. The default
epoch is the latest Git commit timestamp; override it to reproduce a
historical build:

```sh
make pdf
SOURCE_DATE_EPOCH=1755600000 make check
make clean
```

Intermediate files are isolated under `.build/tectonic`. The build prints the
PDF SHA-256; missing tectonic is an environment error (exit 2), not a false
reproducibility success. The repository-level copy is `docs/Makefile.tectonic`.

## Reproducing the model checks

```sh
# (1) verify Python version
python3 --version   # 3.10 / 3.11 / 3.12 tested (3.9.6 also verified byte-for-byte, 2026-08-17)

# (2) no third-party dependencies
cat requirements.txt   # (empty)

# (3) core model check
python3 core_formal_model_check.py
# Expected final line:
# PASS: Proposition 1 (Boolean + bridge + characterization) and Proposition 2 (model pair).

# (4) encoding-sensitivity check (V5)
python3 encoding_sensitivity_check.py
# Expected final line:
# VERDICT: ENCODING-SENSITIVE: the two encodings yield different
#          underdetermination results

# (5) Gate 1.5 model-pair check (V5)
python3 gate15_check.py
# Expected final line:
# PASS: Gate 1.5 model-pair items T2-T5.
```

The outputs are deterministic: they do not depend on the host
operating system, on locale, on time-of-day, or on any
non-standard library. The output hash for a given Python
version is stable; each output must match its frozen
counterpart (`test_output.txt`, `encoding_sensitivity_output.txt`,
`gate15_output.txt`) byte-for-byte.

## What the script checks

The script is a **finite-validation artefact**. It does not
replace the general mathematical proof of the two propositions
in the manuscript; that proof is given in the manuscript
itself, in the form of a structural induction over `L_0`
formulas (Lemma "L_0-reduct invariance"). The script's role
is to verify the finite Boolean fragment in which the strength
relation, the bridge collapse, and the characterization $(\star)$
become mechanical checks, and to construct the model pair that
the implicit-definability result requires.

Specifically:

1. **Proposition 1, strength relation.** Enumerates all 16
   interpretations of the four predicates `Causal`, `Custom`,
   `Bel`, `Just` on a single `(b, c)` pair; checks that
   `T_2 ∧ M_0 ⊨ T_1` (zero falsifying rows) and that
   `T_1 ∧ M_0 ⊭ T_2` (at least one falsifying row); records
   that the falsifying row is unique.
2. **Bridge collapse.** Adds the bridge axiom `B_0` to the
   enumeration; checks that with `B_0`, no row of
   `T_1 ∧ M_0 ∧ B_0` falsifies `T_2`.
3. **Characterization of separation.** Checks that
   `T_1 ∧ M_0 ∧ ¬T_2` is equivalent to the single row
   `(Causal=0, Custom=1, Bel=1, Just=1)`.
4. **Proposition 2, model pair.** Constructs two
   `L^+` structures with the same `L_0` interpretation and
   distinct `G` extensions, one containing the target
   grounding atom and one not. The base model is chosen with
   `Custom(b1)` and `¬Just(b1,c1)`, so that by (O_1)–(O_2)
   both relata of the target atom obtain and (O_3) holds:
   the pair lies in the admissible class `𝒦`. The script also
   asserts (O_1)–(O_3) directly, and the `L_0`-reduct equality
   is exercised.
5. **Encoding-sensitivity test (V5).** For the Stoic modal
   clause `M = □_src ¬FalseSource(i)` (standard translation
   over a two-world frame), the script enumerates all 16 base
   assignments `E = (Kat, Veridical, SourceMatch,
   FalseSource(i))` and all 8 modal resources `(R(i,i),
   R(i,j), FalseSource(j))`, and asks, for each encoding,
   whether `M` is fixed by `E` alone. Under `L_0^A` (minimal)
   `M` is undetermined for all 16 assignments; under `L_0^B`
   (decomposition `Kat ↔ Veridical ∧ SourceMatch ∧ M`) it is
   undetermined for 6 of the 10 admissible assignments and
   determined for 4 (the kataleptic case and its direct
   negation, forced by the decomposition axiom itself).
   Verdict: encoding-sensitive in degree, robust in existence.
6. **Gate 1.5 model-pair check (V5).** Reconstructs the
   Proposition 2.4 pair and verifies the computational Gate 1.5
   items: T2 (both structures in `𝒦`: (O_1)–(O_3) and M_0 hold),
   T3 (identical `L_0`-reduct), T4 (different `G` at the target),
   and T5 (both `G` extensions satisfy `Γ` = irreflexivity,
   asymmetry, transitivity). The remaining items are discharged
   by proof or definition in the manuscript (T1 §2.4–2.5; T6
   Prop. 2.6; T7 Def. 2.7–2.8; T8 §2.13; T10 §2.10) and item T9
   by the encoding-sensitivity script.

## Versions tested

| Python | Core check | Encoding-sensitivity check | Gate 1.5 check |
|--------|------------|----------------------------|----------------|
| 3.10   | PASS       | PASS                       | PASS           |
| 3.11   | PASS       | PASS                       | PASS           |
| 3.12   | PASS       | PASS                       | PASS           |
| 3.9.6  | PASS       | PASS                       | PASS           |

3.9.6 was verified byte-for-byte during the 2026-08-17 M0 toolkit
audit: on Python 3.9.6 all three scripts reproduced their frozen
outputs exactly (`diff` clean).

## Limits of the finite check (preserved in the manuscript)

- The Boolean fragment is **single-`B`, single-`Cont`**: it does
  not exercise the quantifier prefix of the propositions in the
  general case. The general argument is the structural
  induction of Lemma "L_0-reduct invariance" and is
  independent of the script.
- The model pair is a *finite* construction, sufficient to
  witness the failure of implicit definability. The model-class
  claim (Proposition 2) is the existence of *some* such pair
  in `𝒦`, which the construction supplies.
- The "unique countermodel" claim is a finite statement: there
  is exactly one Boolean row witnessing the separation. The
  manuscript does not claim uniqueness in the general
  first-order model class.
- The encoding-sensitivity check is a *finite* enumeration over
  one impression and a two-world frame. The modal clause in the
  general case is a first-order modal claim; the finite check
  fixes its Boolean skeleton. The manuscript's §2.12 states the
  philosophical reading of the result (hermeneutic dependence)
  independently of the enumeration.
- The Gate 1.5 check verifies the structural constraints `Γ` on
  the *constructed* finite pair only; that the admissible class
  `𝒦` does not impose `Γ` as axioms is a separate, definitional
  fact (condition 4 of `𝒦`, §2.5). The non-triviality of the
  result (T6) rests on Proposition 2.6 (stability under arbitrary
  `L_0`-theories), which is a proof, not an enumeration.
- The scripts do **not** perform symbolic reasoning; they
  enumerate. For deeper symbolic verification (e.g.\ Z3-based
  checks of the bridge collapse and the model pair in the
  general case), the manuscript's structural induction is the
  authoritative argument.

## Citation

If you reuse or extend this package, please cite the
manuscript and the relevant classical sources:

- For the manuscript, the bibliographic information in the
  main PDF (§References).
- For grounding, Fine (2012), Correia & Schnieder (2012).
- For justification logic, Artemov (2008), Artemov & Fitting
  (2019).
- For Beth definability, Beth (1953).

## Contact

Bugs, questions and extension proposals should be reported to
the corresponding author of the manuscript.
