# L₀ / L⁺ Formal Specification — Core Paper
**Revision:** 2026-08-17 (post peer-review)

This document is the canonical machine-readable specification
corresponding to `core_section.tex`. It records sorts, predicates,
axioms, the admissible-enrichment class 𝒦, and the statement of
each proposition. Where a choice is interpretive, the choice is
flagged.

---

## 1. Sorts

| Sort | Element | Intended reading |
|------|---------|------------------|
| `I` | impression | Stoic *phantasia*; receives `Kat`, `Rep` |
| `Cont` | ordinary content | Representational content; ordinary propositions, contents of assent |
| `Fact` ⊆ `Cont` | reified fact-like object | Subsort; receives `Obtains`, hosts the grounding relata |
| `B` | cognitive episode | Humean belief-forming episode, Stoic cognitive uptake |
| `E` | explicit justification term | Sort of justification-logic terms; appears only in the JL enrichment (Lᴶᴸ) |

> **Sort discipline.** `Fact` is a subsort of `Cont`; both
> subsorts share the `Cont` semantics, but `Fact` is the range of
> the reification function symbols `custFact`, `nonjustFact`. This
> separation prevents the reification device from silently turning
> ordinary contents into fact-like objects, and it provides a
> natural home for the `Obtains` monad.

`L_0` consists of `I`, `Cont`, `B` and the predicates of §2 below.
`L⁺` adds `Fact`, `Obtains`, the reification functions, and `G`. The
sort `E` appears only in the justification-logic enrichment `Lᴶᴸ`.

The formal reconstruction brackets the full ontology of Stoic
*lekta* and Hume's full apparatus of passions, sympathy and moral
psychology, and retains only the minimum content-bearing structure
required for the formal result.

---

## 2. Base predicates / relations of `L_0`

| Predicate | Sort | Reading |
|-----------|------|---------|
| `Kat(i)` | `I` | `i` is kataleptic |
| `Rep(i,c)` | `I × Cont` | impression `i` represents content `c` |
| `Grasp(b,i)` | `B × I` | cognitive episode `b` grasps impression `i` |
| `Assent(b,c)` | `B × Cont` | `b` assents to content `c` |
| `Bel(b,c)` | `B × Cont` | `b` is a belief state with content `c` (whether or not causally formed) |
| `Causal(b,c)` | `B × Cont` | `b` is a causal belief with content `c` |
| `Custom(b)` | `B` | `b` is produced by custom |
| `Just(b,c)` | `B × Cont` | the relation of `b` to `c` is rationally justified |
| `StoicEp(b)` | `B` | `b` is a cognitive state to which the reconstructed Stoic condition applies |

> **`Bel` versus `Causal`.** `Bel` is content-bearing belief state
> in general; `Causal(b,c)` is the specific subcase of a belief
> that is causally produced. The original `CORE_L0_FORMAL_SPEC.md`
> draft used "causal/ordinary" in the gloss for `Bel`; this
> conflation has been removed. `M_0b` (causal → belief) makes
> the relationship precise.

> **`Just(b,c)` is binary.** The choice of `b` as ``episode''
> (rather than ``assent-token'' or ``agent-relative state'') is
> itself a hermeneutic decision, recorded so that no later
> inference silently presupposes a particular reading of Hume's
> ``belief''.

---

## 3. The Stoic minimal dependency skeleton (S)

```
∀b[ StoicEp(b)
   → ∃i ∈ I ∃c ∈ Cont.
        Kat(i) ∧ Rep(i,c) ∧ Grasp(b,i) ∧ Assent(b,c) ]
```

This is a *minimal dependency skeleton*, not a complete encoding
of Stoic epistemology. In particular it does **not** assert:

- that `b` is a belief state about `c` (no `Bel` axiom);
- that the `c` in `Rep(i,c)` is the same `c` as in `Assent(b,c)`
  (a content-equality axiom would be a separate interpretive
  decision);
- that `Kat(i)` entails truth or a ``could not arise from what is
  not'' clause (the modal clause is identified in §9 of the core
  section as a separate residue).

---

## 4. Humean mechanism axioms (M₀)

**M₀a** — every causal belief is custom-produced:
```
∀b ∀c. Causal(b,c) → Custom(b)
```

**M₀b** — every causal belief is a belief:
```
∀b ∀c. Causal(b,c) → Bel(b,c)
```

**Bridge axiom B₀** (introduced in §4 of the core section; not
adopted as default):
```
∀b ∀c. (Custom(b) ∧ Bel(b,c)) → Causal(b,c)
```

> **Note.** `B_0` is a candidate, not a default. The
> Proposition~1 / bridge-collapse result of the core section
> shows that `B_0` is the operative interpretive choice
> (annotation gap); the paper does not assert `B_0`.

---

## 5. Competing exclusion readings

### H-I — strong exclusion reconstruction (T₂)

```
∀b ∀c. (Custom(b) ∧ Bel(b,c)) → ¬Just(b,c)
```

H-I is a contemporary regimentation of one strong reading of
Hume's appeal to custom. It is **not** the default; the
naturalistic-compatible reading (H-II) is the default for the
rest of the formal apparatus.

### H-II — naturalistic-compatible reading (default)

No axiom connects `Custom` to `¬Just`. `Custom(b)` records a
belief-forming mechanism; the justificatory status of the
relation between `b` and `c` is separately determined. This is
the default in line with the methodological note's commitment
not to over-read Hume.

### T₁ — direct-attachment reading

```
∀b ∀c. Causal(b,c) → ¬Just(b,c)
```

`T_1` attaches the exclusion directly to causal beliefs. It is
logically stronger than `T_2` only when `B_0` is present.

---

## 6. Proposition 1: strength relation (T₂ / T₁ over M₀)

```
T_2 ∧ M_0  ⊨  T_1
T_1 ∧ M_0  ⊭  T_2
```

The countermodel to the second is **unique** in the Boolean
fragment (single `B`, single `Cont`):

| `Causal` | `Custom` | `Bel` | `Just` |
|---|---|---|---|
| false | true | true | true |

Plus the bridge-collapse corollary:

```
T_1 ∧ M_0 ∧ B_0  ⊨  T_2
```

and the **characterization of separation** over `M_0` — stated in two
parts, because the naive `⟺` holds only at the pair level:

```
(T₁ at (b,c)) ∧ ¬(T₂ at (b,c))
   ⟺  Custom(b) ∧ Bel(b,c) ∧ Just(b,c) ∧ ¬Causal(b,c)
```

Globally only one direction is a plain implication:

```
M ⊨ T₁ ∧ M₀ ∧ ¬T₂   →   M ⊨ ∃b∃c [ Custom(b) ∧ Bel(b,c) ∧ Just(b,c) ∧ ¬Causal(b,c) ]
```

and the correct global equivalence keeps `T₁ ∧ M₀` on the right:

```
M ⊨ T₁ ∧ M₀ ∧ ¬T₂
   ⟺  M ⊨ T₁ ∧ M₀ ∧ ∃b∃c [ Custom(b) ∧ Bel(b,c) ∧ Just(b,c) ∧ ¬Causal(b,c) ]
```

> **Scope note (Z3-verified).** `⋆` alone does **not** entail `T₁`:
> a model can satisfy `⋆` at one pair while violating `T₁`
> (`Causal ∧ Just`) at another. The earlier "if and only if" was
> therefore only valid at the single-pair level; the global
> equivalence requires the `T₁ ∧ M₀` conjunct on both sides.

---

## 7. Controlled reification and the enriched language L⁺

Because grounding relates fact-like propositions rather than
formulas, the enrichment does **not** use `G(formula, formula)`.
Instead:

| Symbol | Sort | Reading |
|--------|------|---------|
| `custFact` | `B → Fact` | `custFact(b)` = the fact that `b` is custom-produced |
| `nonjustFact` | `B × Cont → Fact` | `nonjustFact(b,c)` = the fact that the relation of `b` to `c` lacks justification |
| `Obtains` | `Fact → Bool` (monadic) | `Obtains(f)` = `f` obtains |
| `G` | `Fact × Fact` (binary relation) | `G(x,y)` = `x` grounds `y` |

The target atom is therefore well-typed:

```
G( custFact(b), nonjustFact(b,c) )
```

Bridge axioms for the reification (in `L⁺`):

```
Obtains( custFact(b) )           ↔  Custom(b)               (O_1)
Obtains( nonjustFact(b,c) )      ↔  ¬Just(b,c)              (O_2)
G(x,y)                           →  Obtains(x) ∧ Obtains(y)  (O_3)
```

> **Why `O_1` and `O_2`?** Without them, `custFact` and
> `nonjustFact` are ``floating'' objects that exist independently
> of whether the base condition holds. This is ontologically
> profligate and undermines the reification discipline.

---

## 8. Admissible-enrichment class 𝒦

A structure `ℳ⁺` for `L⁺` is in `𝒦` iff:

1. `ℳ⁺` satisfies `M_0a` and `M_0b` on its `L_0`-reduct.
2. Typing is respected: `custFact`, `nonjustFact` land in
   `Fact`; `G` is a binary relation on `Fact × Fact`.
3. The structural axioms `O_1`—`O_3` are satisfied.
4. **No further bridge axiom** connects `Custom`, `Just`, or
   `Bel` to the extension of `G` beyond `O_1` and `O_2`. In
   particular, no axiom of the form
   `φ(b,c) → G( custFact(b), nonjustFact(b,c) )`,
   with `φ` an `L_0` formula, is imposed.

Condition (4) is the operative one. It is what makes the
underdetermination result interesting rather than trivial.

---

## 9. Proposition 2: implicit definability failure over 𝒦

There exist `ℳ₁⁺, ℳ₂⁺ ∈ 𝒦` with identical `L_0`-reducts such that:

```
ℳ₁⁺  ⊨  G( custFact(b), nonjustFact(b,c) )
ℳ₂⁺  ⊭  G( custFact(b), nonjustFact(b,c) )
```

Hence the grounding atom is **not implicitly definable** in
`L_0` over `𝒦`.

> **Base model for the witness pair.** The script's pair uses a
> base model with `Custom(b1)` and `¬Just(b1,c1)`, so that by
> (O_1)–(O_2) both relata of the target atom obtain and (O_3)
> holds; the pair therefore lies in `𝒦`. (A base model with
> `Just=true` would violate (O_3) and is deliberately not used.)

Three auxiliary results are packaged together with the
proposition:

- **Definitional irreducibility** (Proposition 2b): no `L_0`
  formula `θ(b,c)` is equivalent to the grounding atom in both
  structures.
- **Stability under `L_0`-theories** (Proposition 2c): for any
  `L_0`-theory `T` true of the common `L_0`-reduct, both
  `ℳ₁⁺` and `ℳ₂⁺` satisfy `T`. Hence no `L_0`-theory can
  separate the two grounding readings while preserving the
  reduct.
- **Reactivity to definability theory.** The result is
  "implicit definability failure" in the standard sense. The
  classical Beth definability theorem (Beth 1953) does not
  apply directly: the class `𝒦` is closed under `L_0`-elementary
  equivalence but not under the constructions Beth's proof
  requires. The present argument is a direct construction, not
  a derivation from Beth.

---

## 10. The reduct-invariance lemma

For every `L_0`-sentence `φ` and every `ℳ₁⁺, ℳ₂⁺ ∈ 𝒦` with
identical `L_0`-reducts:

```
ℳ₁⁺ ⊨ φ   ⟺   ℳ₂⁺ ⊨ φ
```

Reason: semantic evaluation of `L_0` formulas depends only on
the `L_0` interpretation, and the two enriched structures share
the same `L_0`-reduct. (Standard structural induction.)

---

## 11. Richer-language enrichments (sketch)

| Enrichment | Symbol | Indexed reading | Notes |
|------------|--------|-----------------|-------|
| Modal `□_s` | `□_s φ` | `s` is an explicit index: source-reliability, epistemic, or metaphysical | Standard translation into FOL changes the signature |
| Justification logic `t:φ` | term of sort `E` | `t` is a justification for `φ` | `t:φ` is a *judgement* of the metalanguage, not an `L_0` formula |
| Grounding `<` | `x < y` on `Fact × Fact` | partial-grounding connective | hyperintensional; not definable in terms of strict implication |

> **Disjunctive conclusion.** No claim is made that one of these
> three is "the" right vehicle. The result is that *some*
> hyperintensional, modal, or explicit-evidence resource is
> required, and the `L_0`-reduct is not such a resource at
> this granularity.

---

## 12. Core methodological conclusion

The target claim is **not**:

> "FOL cannot represent grounding."

It **is**:

> "The grounding atom is not implicitly definable in
> `L_0` over the class of admissible enrichments `𝒦`."

Equivalently: for the explicitly specified extensional signature
`L_0` and class of admissible reconstructions `𝒦`, the intended
explanatory relation between custom-production and the absence
of rational warrant is not fixed by the `L_0`-reduct;
representing it requires additional structure whose philosophical
interpretation remains independently contestable.

---

## 13. Verification artefacts

- `core_formal_model_check.py` — Python script that
  exhaustively enumerates the 16-interpretation Boolean fragment
  (§4 of the core section, Table A) and constructs the model
  pair for Proposition 2.
- `model_check_report.md` — narrative record of the script's
  output and the manual reconciliation of the table.
- Both are shipped with the paper; results are stable across
  Python 3.10 / 3.11 / 3.12 and require no third-party
  library.

The finite Boolean enumeration is a *verification artefact* and
does not replace the general proof of Propositions 1 and 2; the
general proof is supplied by structural induction
(Lemma~\ref{lem:reduct-invariance} in the core section).
