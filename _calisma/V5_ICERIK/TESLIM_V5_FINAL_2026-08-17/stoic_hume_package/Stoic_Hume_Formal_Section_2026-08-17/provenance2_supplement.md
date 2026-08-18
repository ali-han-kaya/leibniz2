# Provenance 2.0 — Supplementary Evidence Register

**Manuscript:** `ingiliz_empirizmi_v3` (V5, 33 pp.)
**Date:** 2026-08-17
**Status:** supplement — the main text keeps the 3-column Provenance Table; this
register is the 7-column expansion, one row per substantive claim.

This register implements the Provenance 2.0 specification of the V5
revision architecture (Master Plan §5.1): every substantive claim of
the manuscript is tagged with its claim identifier, section, literal
content, primary witness, secondary support, evidence type, and
confidence. It doubles as an editorial audit: any claim without a
row here is either formal/self-evident or should not be in the text.

---

## Evidence types

| Code | Meaning |
|------|---------|
| A1 | Primary text in a critical edition (or a translation of a primary text) |
| A2 | Bibliographic / database record (ISTC / USTC / library catalogue / edition record) |
| B1 | Secondary monograph or article |
| C1 | Formal proof, lemma, or machine-checked computation |

## Confidence

| Level | Meaning |
|-------|---------|
| High | Directly supported by a primary witness, a critical edition, or a formal/machine check |
| Medium | Primary witness present but the interpretation is contested, or secondary-only support |
| Low | Secondary-only or speculative (used only with an explicit caveat in the text) |

---

## Register

| ClaimID | § | Literal Claim | Primary Witness | Secondary Support | Evidence Type | Confidence |
|---|---|---|---|---|---|---|
| P-01 | Abstract | katalepsis is “cognition” (Long & Sedley translation convention) | Long & Sedley 1987, §40 | SEP “Stoicism” §3.7 | B1 | High |
| P-01b | Abstract | Fist analogy at Lucullus 145 = Long & Sedley 41B | Long & Sedley 1987, §41B (= Cicero, Lucullus 145) | — | A1 | High |
| P-03 | §2.9 | Kataleptic impression is “of such a kind as could not arise from what is not” (literal modal clause) | DL 7.46 [Dorandi 2013]; M 7.248, 7.402 [Bury 1935] | — | A1 | High |
| P-03b | §9 | katalepsis = sunkatathesis kataleptikei phantasiai; episteme = katalepsis asphales | M 7.151–152 [Bury 1935]; DL 7.47 [Dorandi 2013] | — | A1 | High |
| P-04 | §2.3 | T₂∧M₀⊨T₁ and T₁∧M₀⊭T₂, with unique countermodel (0,1,1,1) | Formal argument; Table A (16 Boolean rows) | — | C1 | High |
| P-04b | §2.3.1 | Bridge collapse: T₁∧M₀∧B₀⊨T₂ (0 falsifiers) | Formal argument; `core_formal_model_check.py` | — | C1 | High |
| P-05 | §2.4 | Grounding is hyperintensional; regimented on reified fact-objects | Fine 2012; Correia & Schnieder 2012; Schnieder 2011 | — | B1 | Medium |
| P-05b | §2.6 | Grounding atom G(custFact(b), nonjustFact(b,c)) not implicitly definable in L₀ over 𝒦 | Formal argument; Lemma (L₀-reduct invariance); `gate15_check.py` | Beth 1953 | C1 | High |
| P-05c | §2.6.1 | Explicit vs. implicit definability; Beth anchor | Beth 1953 | — | C1 | High |
| P-05d | §2.7 | Process reliabilism invoked only as a contemporary regimentation | Goldman 1979, 1–23; 1986 | — | B1 | Medium |
| P-06 | §2.7.2 | Justification logic: t:φ is a judgement of the metalanguage | Artemov 2008; Artemov & Fitting 2019 | — | B1 | High |
| P-16 | §2.12 | Encoding sensitivity: L₀^A undetermined 16/16; L₀^B 6/10 — encoding-sensitive in degree, robust in existence | `encoding_sensitivity_check.py` (frozen output) | — | C1 | High |
| P-17 | §2.14 | Gate 1.5 check 10/10 (T1–T10) discharged | `gate15_check.py`; Prop. 2.6; Def. 2.7–2.8; §2.10 | — | C1 | High |
| P-18 | §2.15 | Hyperintensionality four-layer claim HI1–HI4 (Literature → Formalization → Theorem → Interpretation) | SEP “Metaphysical Grounding”; Fine 2012; Schnieder 2011; Prop. 2.4 | — | B1/C1 | Medium |
| P-07 | §3 | Causal maxim is “neither intuitively nor demonstrably certain” | Hume, T 1.3.3 (Norton & Norton 2000); SBN 78–82 | — | A1 | High |
| P-07b | §3 | Necessity is “an internal impression of the mind, or a determination to carry our thoughts…” | Hume, T 1.3.14.20; SBN 164–65 | — | A1 | High |
| P-07c | §3 | “there is no absolute nor metaphysical necessity…” | Hume, T 1.3.14.35; SBN 172 | — | A1 | High |
| P-07d | §3 | “we are never able… to discover any power or necessary connexion” | Hume, E 7.6 (Beauchamp 1999); SBN 63 | — | A1 | High |
| P-07e | §3 | “reason is nothing but a wonderful and unintelligible instinct…” | Hume, T 1.3.16.9; SBN 178–9 | — | A1 | High |
| P-07f | §3.1 | Hume relocates the causal maxim from demonstration to custom (demotion); evaporation is a live alternative | Della Rocca 2010; Pruss 2006 | Garrett 1997; Beebee 2006; Millican 2002 | B1 | Medium |
| P-19 | §4.6 | Ev0–Ev4 evidence ladder; availability ≠ influence, citation ≠ dependence | Methodology of this note, applied to §4 | — | C1 | High |
| P-08 | §4.1 | Sextus printed transmission: Hypotyposes tr. Estienne 1562; Adv. Math. tr. Hervet 1569; Greek Opera 1621 | The 1562 / 1569 / 1621 printed editions | Floridi 2002; Popkin 1979, 18 | A2 | High |
| P-08b | §4.1 | Criterion texts: M 7.24–29; marks “enarges, ektypos, plektike” at M 7.257–58 | Sextus, M (Bury, Loeb) | — | A1 | High |
| P-09 | §4.2 | Diogenes Laertius transmission: Traversari 1433; Rome 1472; Venice 1475; Basel 1533 | Dorandi 2013, 15; ISTC id00219000 / id00220000 | — | A2 | High |
| P-10 | §4.3 | Fist analogy at Lucullus 145 (open hand → bent fingers → fist → fist grasped) | Cicero, Acad. (Brittain 2006); SVF 1.66 | — | A1 | High |
| P-10b | §4.3 | Neostoic reception: Lipsius 1584, 1604 | Lipsius, De Constantia (1584); Manuductio / Physiologia (1604) | SEP “Justus Lipsius”; Lagrée 1994 | A1 | High |
| P-11 | §4.4 | Hume’s library catalogue lists Cicero, not Sextus | Norton & Norton 1996 | Fosl 1998 | A1/B1 | High |
| P-11b | §4.4 | Hume’s access to Sextus via Bayle / Montaigne (mediated, not direct) | Popkin 1952, 65–81; 1951 | — | B1 | Medium |
| P-12 | §4.5 | Medieval discontinuity: no continuous direct transmission of the katalepsis doctrine | Floridi 2002; Schmitt 1972; SEP “Medieval Skepticism” | Nawar 2022 | B1 | Medium |
| P-12b | §4.5 | Locke’s critique of innate principles targets Herbert of Cherbury (I.3.15–27), not Descartes | Locke, Essay (Nidditch 1975), 77–84 | — | A1 | High |
| P-12c | §4.5 | “British Empiricism” is a 19th-century historiographical construction | Norton 1981 | — | B1 | High |
| P-13 | §5 | Catuṣkoṭi as four-cornered negation, formalizable in paraconsistent logic | Priest 2010; 2018 | Garfield 2014; Tillemans 1999 (contested) | B1 | Medium |
| P-13b | §5 | Xunzi 22: names are fixed by shared sensory experience and convention | Xunzi 22.5, 22.9 (ctext; Knoblock tr.) | Hansen 1992, ch. 9 | A1 | High |
| P-13c | §5 | Kaozheng: philological verification as method | Elman 1984, Introduction & ch. 5 (2nd ed. 2001) | — | B1 | High |
| P-13d | §5 | Mohist Xiaoqu and Gongsun Long White Horse — noted for completeness only | Graham 1978; 1989; Hansen 1983, 140–51 | — | B1 | Medium |
| P-15 | §8 | Limits of the note stated explicitly | This note | — | C1 | High |

---

## Notes

1. **Relation to the main text.** The 3-column Provenance Table in the
   manuscript is the compact form of this register; the ClaimIDs (P-codes)
   match row for row. The SC-ID mapping (CHK-02) in the manuscript maps
   SC-001–030 to the same sections; the P-codes here are the granular
   claim-level identifiers.
2. **V5 additions.** P-16 (encoding sensitivity), P-17 (Gate 1.5), P-18
   (HI1–HI4), P-19 (Ev0–Ev4) and P-03b (M 7.151–152) are new rows for the
   V5 content; all are machine-checked (C1) or primary-text anchored.
3. **Confidence discipline.** Rows marked *Medium* are exactly the claims
   the manuscript flags as interpretive (grounding as a contemporary
   regimentation; the demotion vs. evaporation reading of Hume; the
   Bayle-mediated access; the medieval discontinuity as negative evidence;
   Priest’s catuṣkoṭi reading). No row is marked *Low*; any claim that
   could only be supported at *Low* was either removed or explicitly
   caveated in the text.
4. **Negative-evidence rule.** P-11 and P-12 record claims built on
   absence; per §8 (Limits) these are recorded as negative-evidence
   claims, never as proofs of non-existence.
5. **Citation audit (2026-08-17).** Tillemans 1999 (P-13, Secondary
   Support, cited in §5) now has a full entry in the manuscript's
   References (Tillemans 1999, *Scripture, Logic, Language*,
   Wisdom Publications). Beauchamp 1999 and Nidditch 1975 now have
   standalone editor entries; Bury citations are annotated by volume
   year (1935 = Loeb vol. II). Garfield 2014 remains supplement-only
   secondary support (not cited in the manuscript).

---

*This supplement is part of the reproducibility package; it is not part of
the page count of the manuscript.*
