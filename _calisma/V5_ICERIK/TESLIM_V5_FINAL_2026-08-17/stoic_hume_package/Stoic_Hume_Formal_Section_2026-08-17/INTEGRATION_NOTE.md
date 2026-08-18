# Integration note: replacing the manuscript's §2 with the new core section
**Date:** 2026-08-17
**Status:** COMPLETED — the substitution described below has been
performed and extended with the V5 additions. The manuscript is now
`ingiliz_empirizmi_v3.tex` / `.pdf` (V5, 33 pp.), which already
contains the core section and the V5 additions. This note is retained
as the record of the integration.

This note documents how the new `core_section.tex` (in this
package) integrates with the manuscript
`ingiliz_empirizmi_v2.pdf` and what changes are required in
the surrounding sections. The mapping below is written
against the *pre-integration* manuscript (v2); every item
marked "Replace" or "New" has since been applied.

---

## Status: completed — current manuscript structure (V5)

The substitution described below has been applied and the
manuscript has been recompiled. The current manuscript
(`ingiliz_empirizmi_v3.tex` / `.pdf`, 33 pp. when compiled
with tectonic) now has this structure:

```
§1  Introduction: Scope and Limits
§2  Formalization: What Can and Cannot Be Encoded
      canonical core section (\input{core_section.tex}): §2.1–§2.11
    §2.12  Stoic Application: Encoding Sensitivity            (V5)
    §2.13  Expressive Enrichments: E0/E1/E2 Benchmark         (V5)
    §2.14  Gate 1.5: Non-Triviality / Recoverability Check    (V5)
    §2.15  Hyperintensionality: The Four-Layer Claim (HI1–HI4) (V5)
§3  Hume and the Principle of Sufficient Reason
§4  The Transmission of Stoic Epistemology
    §4.6  Historical-Evidential Method: The Ev0–Ev4 Ladder     (V5)
§5  A Comparative Note
§6  Objections and Replies (7 objections)                     (V5)
    §6.1  Negative-Result Matrix                              (V5)
§7  Conclusion
§8  Limits of This Note
§9  Appendix: Definitions
      Citations and Editions · Provenance Table
      Open Science Statement (V5) · References
```

The mapping tables in §1–§3 below are the record of the
v2→v3 substitution; the sentence-level items in §4 were
applied; the provenance table and the appendix were updated
with the new terms and citations (§4 items 17–18); the
disposition of §5 was decided as *keep as a comparative note*
(§6 item 4).

### V5 additions (2026-08-17) — applied to `ingiliz_empirizmi_v3`

1. **§2.12 Encoding sensitivity** — two Stoic formalizations
   (`L_0^A` minimal `Kat(i)`; `L_0^B` provenance decomposition
   `Veridical ∧ SourceMatch ∧ □_src ¬FalseSource`) and the
   executed computational test (script
   `encoding_sensitivity_check.py`): under `L_0^A` the modal
   content is undetermined for all 16 base assignments; under
   `L_0^B` for 6 of 10 admissible assignments. Verdict:
   encoding-sensitive in degree, robust in existence.
2. **§2.13 E0/E1/E2 benchmark** — the minimal-enlargement
   table (representability vs. adequacy).
3. **§2.14 Gate 1.5** — the ten-point non-triviality check
   (T1–T10); item T9 discharged by the encoding-sensitivity
   test.
4. **§2.15 Hyperintensionality: The Four-Layer Claim** — the
   HI1–HI4 chain (Literature → Formalization → Theorem →
   Interpretation), labelled to avoid collision with the
   Humean H1–H3.
5. **§4.6 Historical-Evidential Method: The Ev0–Ev4 Ladder** —
   evidence levels with Ev_n ⇏ Ev_{n+1} (availability ≠
   influence; citation ≠ dependence), labelled to avoid
   collision with the E0/E1/E2 enrichments.
6. **Appendix + Provenance** — katalepsis/episteme hierarchy
   (M 7.151–152) added as an appendix row and a provenance
   row [P-03b].
7. **§6 Objections and Replies** — seven objections in the
   objection–concession–distinction–response format, plus
   §6.1 the Negative-Result Matrix.
8. **Open Science Statement** — added before the References.
9. **Factual fix** — the Sextus 1562 translator in
   "Citations and Editions" corrected from Hervet to Henri
   Estienne (the body text was already correct).

No further editor action is required for the integration;
the package is in its final delivery state (see
`MANIFEST.txt`).

---

## 0. Summary of the change

The manuscript's existing §2 ("Formalization: What Can and
Cannot Be Encoded") uses a single-sorted, small-vocabulary
language
`L = { HCB(·), CC(·), J(·), Kat(·), Gr(·,·), Stoic(·) }`.
This is **superseded** by the new core section, which uses a
many-sorted, content-bearing, controlled-reification language
`L_0` and its extension `L^+`. The two languages are **not**
compatible; integrating the new core section is therefore a
**substitution**, not an extension. The rest of the
manuscript (§1, §3–§5, §6, §7) is unaffected in its
substantive content, but the references in those sections to
`L`, to "the language", to the names of the predicates, and
to the formal labels (`(Sto)`, `(Hum)`, `(Exc1)`, `(Exc2)`)
need to be aligned with the new core section.

Below is a mapping of every element that changes.

---

## 1. Signature mapping

| Manuscript §2.1 (old) | New core section (revised) | Action |
|-----------------------|----------------------------|--------|
| Single sort | `I`, `Cont`, `B` in `L_0`; `Fact ⊆ Cont`, `E` in enrichments | Replace |
| `HCB(x)` | `Causal(b, c)` (binary) | Replace; document the binary form |
| `CC(x)` | `Custom(b)` | Replace (same arity, same intent) |
| `J(x)` (unary, with `J(x) → ¬HCB(x)` axiom) | `Just(b, c)` (binary; no such axiom) | Replace; the absence of the `J → ¬HCB` axiom is a deliberate scope-narrowing (it is now H-I, a candidate, not a default) |
| `Kat(p)` | `Kat(i)` on sort `I` | Replace; the sort is now `I`, not `P` |
| `Gr(p, x)` | `Grasp(b, i)` and `Rep(i, c)` as two separate relations | Replace; the old conflation of "grasping" and "representation" is now undone |
| `Stoic(x)` | `StoicEp(b)` | Replace (name change; substance unchanged) |
| — | `Bel(b, c)`, `Assent(b, c)`, `Obtains(f)` (on `Fact`) | New; introduce |
| — | `custFact: B → Fact`, `nonjustFact: B × Cont → Fact` | New; controlled reification |
| — | `G ⊆ Fact × Fact` | New; grounding connective (reified) |
| — | `□_s` modal operator, with explicit index `s` | New; modal enrichment |
| — | `t:φ` for terms of sort `E` | New; justification-logic enrichment |

The binary nature of `Just(b, c)` is not a typographical
choice: it is the formal expression of the methodological
point that "justified" is content-relative, not
agent-relative. This should be called out in the introduction
of `Just`.

---

## 2. Axiom mapping

| Manuscript | New core section | Notes |
|------------|------------------|-------|
| `(Sto)` ∀z(Stoic(z) → ∃p(Kat(p) ∧ Gr(p, z))) | `(S)` ∀b(StoicEp(b) → ∃i ∈ I ∃c ∈ Cont. Kat(i) ∧ Rep(i,c) ∧ Grasp(b,i) ∧ Assent(b,c)) | Relabelled *minimal dependency skeleton*; the separation of `Rep` and `Assent` is the substantive change |
| `(Hum)` ∀z(HCB(z) → CC(z)) | `(M_0a)` ∀b∀c. Causal(b,c) → Custom(b) | Same intent; arity change |
| — | `(M_0b)` ∀b∀c. Causal(b,c) → Bel(b,c) | New; needed to keep `Bel` consistent with `Causal` |
| `(Exc1)` ∀z(HCB(z) → ¬J(z)) | `(T_1)` ∀b∀c. Causal(b,c) → ¬Just(b,c) | Same intent; arity change |
| `(Exc2)` ∀z(CC(z) → ¬J(z)) | `(H-I / T_2)` ∀b∀c. Custom(b) ∧ Bel(b,c) → ¬Just(b,c) | New antecedent `Bel(b,c)`; with `B_0` collapses to `(Exc2)` |
| — | `(B_0)` ∀b∀c. Custom(b) ∧ Bel(b,c) → Causal(b,c) | New; bridge axiom; **not** a default; introduced as an interpretive candidate |
| — | `(O_1)`, `(O_2)`, `(O_3)` | New; reification bridge axioms |

The manuscript's claim that `(Exc2)` and `(Hum)` together give
`(Exc1)` by transitivity of the conditional is **wrong** in the
new core section. The correct derivation requires `M_0b` as
well. The manuscript's wording should be replaced with the
revised proof of Proposition 1 (which uses `M_0a ∧ M_0b`, not
just `(Hum)`).

---

## 3. Theorem / proposition mapping

| Manuscript | New core section | Notes |
|------------|------------------|-------|
| §2.2 "T₁ ⊨ T₂, T₂ ⊭ T₁" | **Proposition 1** (renamed); conditional language added | The result is the same, but the *framing* is changed to be explicitly comparative and conditional |
| §2.2 model `{a, b}; HCB={a}; CC={a,b}; J={b}` | Boolean countermodel `(0, 1, 1, 1)` (Table A) | The Boolean model is the single `(b, c)` pair; the manuscript's two-element domain is collapsed |
| — | **Bridge collapse** (Proposition 1 / bridge) | New; addresses the "trivially distinguishes" objection |
| — | **Characterization $(\star)$** | New; gives the exact condition of separation over `M_0` |
| §2.3 model-pair argument (E1, E2) | **Proposition 2** (rebuilt as implicit-definability failure over `𝒦`) | The two arguments are **the same argument**, but the new framing fixes the language, the class, and the technical notion (implicit definability) used |
| — | **Definitional irreducibility** (Proposition 2b) | New; explicit version |
| — | **Stability under `L_0`-theories** (Proposition 2c) | New |
| — | **Definability qualification** (Beth anchor) | New; `§2.3` of the manuscript has no equivalent |

The manuscript's §2.3 "model-pair argument" is the intuition
for Proposition 2 but not its proof. The new proof uses the
class `𝒦`, the reduct-invariance lemma, and the
explicit/implicit definability framework. The manuscript's
text in §2.3 should be replaced or rewritten.

---

## 4. Sentences that need rewriting

The following claims in the manuscript require revision, in
the order they appear:

1. **Abstract** — the sentence "grounding is hyperintensional
   — it is not a truth-condition and therefore not part of FOL
   model theory" should be qualified: the new result is that
   the grounding atom is not **implicitly definable** in `L_0`
   over `𝒦`, not that grounding is **not a truth-condition**.
   The distinction is the heart of the revision.
2. **§2.1, language declaration** — replace the single-sorted
   `L` with the many-sorted `L_0` of the new core section.
3. **§2.1, `J(x) → ¬HCB(x)` axiom** — this axiom encodes
   the **strong exclusion reconstruction** (H-I) as a default.
   The new core section makes H-I a *candidate*, not a default.
   The manuscript's §2.1 wording should be aligned: either
   state the axiom explicitly as a candidate (H-I), or remove
   it. Removing it is the cleaner option.
4. **§2.1, definition of `Gr(p, x)`** — separate into `Rep(i, c)`
   and `Grasp(b, i)`. The conflation is the principal
   typographical cause of the "argument order" inconsistency
   the internal report flagged (P1-1).
5. **§2.2, derivation of `(Exc1)` from `(Exc2)` and `(Hum)`** —
   the new derivation uses `M_0a` and `M_0b`, not just `(Hum)`.
   The wording should be updated.
6. **§2.3, "The limit we state is semantic, not syntactic"** —
   keep this sentence; it is correct and is reinforced by the
   new core section.
7. **§2.3, "(E1) and (E2)"** — these become the canonical
   witnesses of the model pair. The new core section formalises
   them as `ℳ_1^+` and `ℳ_2^+` over `𝒦`. The manuscript's
   wording should be aligned.
8. **§2.3(a), `CC(z) < ¬J(z)` notation** — the manuscript
   uses this notation as a shorthand. The new core section
   adopts the convention that the relata of `<` (or `G`) are
   reified fact-objects, not formulas. A mutual consistency
   paragraph in both the manuscript and the core section
   should make this explicit (P1-2 of the internal report).
9. **§2.3(b), modal clause** — the new core section
   distinguishes the *minimal dependency skeleton* `(S)` from
   the modal clause; the modal clause is identified as a
   separate residue. The manuscript's §2.3(b) should be
   aligned with this separation.
10. **§2.4, justification logic** — the new core section
    makes the point that `t:φ` is a judgement of the
    metalanguage, not an `L_0` formula. The manuscript's §2.4(i)
    should be aligned.
11. **§2.4, grounding** — the new core section restates the
    grounding axioms on the reified fact-objects. The
    manuscript's §2.4(ii) should be aligned.
12. **§2.4, modal operator** — the new core section uses `□_s`
    with an explicit index `s`. The manuscript's §2.4(iii) should
    use the same notation.
13. **§3, Hume and the PSR** — the new core section adds a
    four-level Humean analysis. The manuscript's §3 already
    does the textual work; the four-level table should be
    inserted into the manuscript as a sub-paragraph or table.
14. **§4** — unaffected.
15. **§5** — the comparative section. The new core section
    defers it to an appendix or methodological note; the
    manuscript's §5 is acceptable as a comparative-analogue
    section provided it is reframed as analogy-only (which it
    already is).
16. **§6, §7, §8, References** — unaffected in content;
    possibly a sentence added to §6 referencing the new core
    section's narrower claim.
17. **Provenance table** — the new core section introduces
    citations (Beth 1953, Fine 2012, Schnieder 2011) that are
    not in the manuscript's table. Add the missing rows.
18. **Appendix: Definitions** — the manuscript's appendix
    should be updated to include the new terms (`L_0`, `L^+`,
    `𝒦`, `Obtains`, `custFact`, `nonjustFact`, `G`, the four
    Humean levels, the minimal dependency skeleton).

---

## 5. What is **not** changed

- The historical and historiographical work in §3, §4 (Hume
  on PSR; Sextus, Diogenes Laertius, Cicero, Lipsius;
  medieval discontinuity; Hume's own access; the Cartesian
  and Locke-Herbert comparisons). This is independent of
  the formal encoding and the peer review did not ask for
  changes there.
- The comparative section §5. The internal report and the
  external report agree that the analogy status is correctly
  stated in the manuscript; the only recommendation is to
  reduce or externalize it, which is a structural choice for
  the editor.
- The provenance table. The content of the table is
  unchanged; the revision only *adds* rows.

---

## 6. Recommended next step for the editor — RECORD (all completed)

The four steps below were performed on 2026-08-17; they are
kept here as the record of the integration.

1. **Substitute §2** of the manuscript with the new core
   section, preserving the surrounding §1 (introduction) and
   §3 (Hume and PSR) where possible.
2. **Apply** the sentence-level revisions listed in §4 above
   to the remaining sections of the manuscript.
3. **Update** the provenance table and the Appendix:
   Definitions to include the new terms and citations.
4. **Decide** the disposition of §5: keep as a comparative
   note (recommended) or externalize to an appendix
   (acceptable alternative).

After these steps, the manuscript's central claim is:

> "The grounding atom is not implicitly definable in `L_0`
> over the admissible class `𝒦`; representing it requires
> additional hyperintensional, modal, or explicit-evidence
> resources. This is a singular encoding limit, not a
> universal claim about the expressive limits of first-order
> logic."

This is the narrower, more defensible claim that both
internal and external peer reviews identified as the
publishable thesis of the paper.
