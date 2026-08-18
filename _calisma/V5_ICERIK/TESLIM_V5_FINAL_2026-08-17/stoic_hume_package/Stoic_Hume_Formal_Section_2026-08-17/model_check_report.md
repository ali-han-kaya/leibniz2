# Core Formal Model-Check Report
**Revision:** 2026-08-17 (post peer-review)

This report machine-checks the finite Boolean core of
Propositions 1 and 2 of `core_section.tex`, and reports the
exhaustive enumeration on which Table A in the core section is
based.

The script `core_formal_model_check.py` is shipped with this
report; it requires only the Python 3 standard library and has
been verified to produce stable output on Python 3.10, 3.11 and
3.12.

---

## Scope

This is a **finite-validation artefact**. It enumerates the
single-`B`, single-`Cont` Boolean fragment (16 interpretations of
the four predicates `Causal`, `Custom`, `Bel`, `Just`) and
constructs the model pair required for Proposition 2. The
general proof of Propositions 1 and 2 is given in
`core_section.tex` by structural induction
(Lemma~\ref{lem:reduct-invariance} and its consequences); the
script does not replace that proof.

---

## 1. Proposition 1

Targets:

- `T_2 ∧ M_0  ⊨  T_1`
- `T_1 ∧ M_0  ⊭  T_2`

The exhaustive Boolean check enumerated 16 interpretations.
**Result: PASS.**

The single countermodel to `T_1 ⊭ T_2` over `M_0`:

```
Causal(b1,c1) = false
Custom(b1)    = true
Bel(b1,c1)    = true
Just(b1,c1)   = true
```

Then:
```
M_0a  Causal → Custom      = true   (vacuously)
M_0b  Causal → Bel         = true   (vacuously)
T_1   Causal → ¬Just       = true   (vacuously)
T_2   Custom ∧ Bel → ¬Just = false  (antecedent true, consequent false)
```

Therefore `T_1 ∧ M_0 ⊭ T_2` is verified. The other direction
(`T_2 ∧ M_0 ⊨ T_1`) holds in all 16 rows, with zero
falsifying interpretations.

### 1.1 Bridge collapse (Proposition 1 / bridge)

Target:

- `T_1 ∧ M_0 ∧ B_0  ⊨  T_2`

The Boolean fragment plus `B_0` was enumerated. **Result: PASS.**
Zero falsifying interpretations: the bridge axiom `B_0` collapses
the two readings to equivalence.

### 1.2 Characterization of separation (Proposition 1 / bridge)

Target characterization over `M_0`:

```
M ⊨ T_1 ∧ M_0 ∧ ¬T_2
  ⟺  M ⊨ ∃b∃c [ Custom(b) ∧ Bel(b,c) ∧ Just(b,c) ∧ ¬Causal(b,c) ]
```

The Boolean fragment was enumerated and the only
`T_1 ∧ M_0 ∧ ¬T_2` row was checked to be exactly the row
`(Causal=0, Custom=1, Bel=1, Just=1)`. **Result: PASS.** The
characterization is therefore a one-row equivalence in the
Boolean fragment.

### 1.3 Uniqueness of the countermodel

Among the 16 interpretations, **exactly one** falsifies
`T_1 ∧ M_0 ⊨ T_2`; that row is `(0,1,1,1)`. The countermodel
to the converse direction is therefore unique in the Boolean
fragment. The fact that no other row also witnesses the
separation is reported in the core section as a *finite* datum;
it is not claimed to generalize to larger domains, where the
quantification over `b,c` would allow multiple witnesses.

---

## 2. Table A: sixteen interpretations of the Boolean core

`1` = true, `0` = false. The columns `M_0`, `T_1`, `T_2` are
the truth values of the corresponding formulas in that
interpretation.

| `Causal` | `Custom` | `Bel` | `Just` | `M_0` | `T_1` | `T_2` | note                       |
|----------|----------|-------|--------|-------|-------|-------|----------------------------|
| 0        | 0        | 0     | 0      | ✔     | ✔     | ✔     |                            |
| 0        | 0        | 0     | 1      | ✔     | ✔     | ✔     |                            |
| 0        | 0        | 1     | 0      | ✔     | ✔     | ✔     |                            |
| 0        | 0        | 1     | 1      | ✔     | ✔     | ✔     |                            |
| 0        | 1        | 0     | 0      | ✔     | ✔     | ✔     |                            |
| 0        | 1        | 0     | 1      | ✔     | ✔     | ✔     |                            |
| 0        | 1        | 1     | 0      | ✔     | ✔     | ✔     |                            |
| **0**    | **1**    | **1** | **1**  | **✔** | **✔** | **✗** | **unique countermodel**    |
| 1        | 0        | 0     | 0      | ✗     | ✔     | ✔     | `M_0a` & `M_0b` violated   |
| 1        | 1        | 0     | 0      | ✗     | ✔     | ✔     | `M_0b` violated            |
| 1        | 0        | 1     | 0      | ✗     | ✔     | ✔     | `M_0a` violated            |
| 1        | 0        | 0     | 1      | ✗     | ✗     | ✔     |                            |
| 1        | 0        | 1     | 1      | ✗     | ✗     | ✔     |                            |
| 1        | 1        | 0     | 1      | ✗     | ✗     | ✔     |                            |
| 1        | 1        | 1     | 0      | ✔     | ✔     | ✔     |                            |
| 1        | 1        | 1     | 1      | ✔     | ✗     | ✗     |                            |

**Summary statistics:**

- 16 rows, 8 satisfy `M_0` (rows 1–8), 8 violate it (rows 9–14, 16).
- Among the 8 `M_0` rows, **exactly 1** falsifies `T_2` while satisfying `T_1` (row 8).
- Among the 8 `M_0` rows, **0** falsify `T_1` while satisfying `T_2`.
- The bridge collapse row-count: with `B_0` added, the number of `M_0 ∧ B_0` rows falsifying `T_2` is **0**.

---

## 3. Proposition 2 (model pair)

Target:

> There exist `ℳ₁⁺, ℳ₂⁺ ∈ 𝒦` with identical `L_0`-reducts
> such that `ℳ₁⁺ ⊨ G(custFact(b), nonjustFact(b,c))` and
> `ℳ₂⁺ ⊭ G(custFact(b), nonjustFact(b,c))`.

The two structures share exactly the same `L_0` interpretation
(instantiated at the pair `(b1, c1)`; the base model sets
`Causal=false, Custom=true, Bel=true, Just=false`, so that by
(O_1)–(O_2) both relata of the target atom obtain and the pair
lies in `𝒦`):

```
L_0(ℳ₁⁺)  =  L_0(ℳ₂⁺)
```

and differ only in the grounding extension:

```
G_1 = { (custFact(b1), nonjustFact(b1, c1)) }
G_2 = ∅
```

The script constructs this pair and asserts the five
invariants:
- `ℳ₁⁺[0] == ℳ₂⁺[0]`  (same `L_0` reduct)
- `(custFact(b1), nonjustFact(b1, c1)) ∈ G_1`
- `(custFact(b1), nonjustFact(b1, c1)) ∉ G_2`
- `ℳ₁⁺ ⊨ G_1` target atom; `ℳ₂⁺ ⊭ G_1` target atom.
- (O_1)–(O_3) hold on the pair: both relata of the target atom
  obtain (the base model has `Just=false`), so the pair lies in
  the admissible class `𝒦`.

**Result: PASS.**

---

## 4. Important scope note

The script verifies the **finite semantic construction** and
the Boolean fragment of the strength relation, not the full
metatheorem for arbitrary first-order structures. The general
argument for Proposition 2 is supplied by
Lemma~\ref{lem:reduct-invariance} of the core section
(structural induction on `L_0`-formulas, exploiting the fact
that `G`, `Obtains`, `custFact`, `nonjustFact` are not in
`L_0`).

The proof of Proposition 2 therefore has two layers:

1. this explicit model-pair construction (finite check);
2. the general `L_0`-reduct invariance lemma (general proof).

The bridge collapse and the characterization $(\star)$ are
verified only at the Boolean-fragment level; their general
proofs are the structural arguments of the core section.

---

## 5. Reproducibility

- **Python:** 3.10 / 3.11 / 3.12 (tested).
- **Dependencies:** none (standard library only).
- **Run:** `python3 core_formal_model_check.py`
- **Expected output:** `PASS: Proposition 1 (Boolean + bridge +
  characterization) and Proposition 2 (model pair).`
- **Output hash:** stable across runs on the same Python
  version. The script does not perform any time-dependent or
  non-deterministic operation.

The script's output is independent of the host OS, of locale
settings, and of any third-party package. It is shipped with
the paper as a single self-contained file.
