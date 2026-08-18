"""
gate15_check.py
===============

Finite-validation artefact for the Gate 1.5 non-triviality /
recoverability check of the core section (manuscript §2.14).

This script verifies the model-pair items of the ten-point
Gate 1.5 check that are computational:

    T2  at least two enriched structures M_1^G, M_2^G in the
        admissible class K exist (reification axioms O_1-O_3
        hold on the pair);
    T3  the two structures share the same L_0-reduct;
    T4  the two structures have different G extensions;
    T5  both G extensions satisfy the standard grounding-theoretic
        structural constraints Gamma = {irreflexivity, asymmetry,
        transitivity}.

Items T1 (T_G explicitly defined), T6 (non-triviality, Prop. 2.6),
T7 (definability application, Def. 2.7-2.8), T8 (E1/E2 comparison),
T10 (machine verification separated from proof) are discharged by
proof or by definition in the manuscript and are not enumerated
here. Item T9 (encoding sensitivity) is discharged by the separate
script encoding_sensitivity_check.py.

The model pair is the one constructed in Proposition 2.4: both
structures extend the same base interpretation M, with

    G_1 = { (custFact(b1), nonjustFact(b1, c1)) },   G_2 = {}.

Run:    python3 gate15_check.py
Output: PASS line on stdout, or AssertionError on failure.
Deterministic, stdlib only.
"""

# ---------------------------------------------------------------------------
# The model pair of Proposition 2.4 (same base interpretation as
# core_formal_model_check.py, so the results are consistent).
# ---------------------------------------------------------------------------

def model_pair():
    """Return (M1G, M2G, target) for the Proposition 2.4 pair.
    Each structure is (L0_reduct, G_extension)."""
    # L_0 interpretation: Causal=0, Custom=1, Bel=1, Just=0; the
    # single-episode / single-content Boolean core.
    L0 = {
        "Kat":     {("i1",)},
        "Rep":     {("i1", "c1")},
        "Grasp":   {("b1", "i1")},
        "Assent":  {("b1", "c1")},
        "Bel":     {("b1", "c1")},
        "Causal":  set(),
        "Custom":  {("b1",)},
        "Just":    set(),
        "StoicEp": {("b1",)},
    }
    target = (("custFact", "b1"), ("nonjustFact", "b1", "c1"))
    G1 = {target}
    G2 = set()
    return (L0, G1), (L0, G2), target


# ---------------------------------------------------------------------------
# T2: both structures lie in the admissible class K
# ---------------------------------------------------------------------------

def t2_in_K(M1G, M2G):
    """Check the reification axioms (O_1)-(O_3) on the pair."""
    L0, G1, G2 = M1G[0], M1G[1], M2G[1]
    # O_1: Obtains(custFact(b1)) <-> Custom(b1)
    obtains_cust = ("b1",) in L0["Custom"]
    assert obtains_cust, "(O_1) violated: custFact(b1) must obtain"

    # O_2: Obtains(nonjustFact(b1,c1)) <-> ~Just(b1,c1)
    obtains_nonjust = ("b1", "c1") not in L0["Just"]
    assert obtains_nonjust, "(O_2) violated: nonjustFact(b1,c1) must obtain"

    # O_3: every grounding pair has obtaining relata
    for (x, y) in G1:
        assert x == ("custFact", "b1") and obtains_cust
        assert y == ("nonjustFact", "b1", "c1") and obtains_nonjust
    assert G2 == set(), "(O_3) must hold vacuously on M_2"

    # Mechanism axioms M_0a / M_0b on the L_0-reduct
    assert not L0["Causal"] or ("b1",) in L0["Custom"], "(M_0a) violated"
    assert not L0["Causal"] or ("b1", "c1") in L0["Bel"], "(M_0b) violated"
    return True


# ---------------------------------------------------------------------------
# T3 / T4: same L_0-reduct, different G
# ---------------------------------------------------------------------------

def t3_same_reduct(M1G, M2G):
    """The two enrichments share the same L_0-reduct."""
    assert M1G[0] == M2G[0], "L_0-reducts must be identical"
    return True


def t4_different_G(G1, G2, target):
    assert target in G1, "G_1 must contain the target grounding atom"
    assert target not in G2, "G_2 must not contain the target"
    assert G1 != G2, "G extensions must differ"
    return True


# ---------------------------------------------------------------------------
# T5: Gamma = {irreflexivity, asymmetry, transitivity} on both G's
# ---------------------------------------------------------------------------

def irreflexive(R):
    return all(x != y for (x, y) in R)


def asymmetric(R):
    return all((y, x) not in R for (x, y) in R)


def transitive(R):
    for (x, y) in R:
        for (z, w) in R:
            if y == z and (x, w) not in R:
                return False
    return True


def t5_gamma(G1, G2):
    for name, G in (("G_1", G1), ("G_2", G2)):
        assert irreflexive(G), f"{name} is not irreflexive"
        assert asymmetric(G), f"{name} is not asymmetric"
        assert transitive(G), f"{name} is not transitive"
    return True


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

def main():
    M1G, M2G, target = model_pair()
    L0, G1, G2 = M1G[0], M1G[1], M2G[1]

    print("Gate 1.5 model-pair check (items T2-T5)")
    print(f"target grounding atom = {target}")
    print(f"G_1 = {sorted(G1) if G1 else '{}'}")
    print(f"G_2 = {{}}")
    print()

    t2_in_K(M1G, M2G)
    print("T2  PASS  (M_1^G, M_2^G in K: O_1-O_3 and M_0 hold)")

    t3_same_reduct(M1G, M2G)
    print("T3  PASS  (identical L_0-reduct)")

    t4_different_G(G1, G2, target)
    print("T4  PASS  (G_1 != G_2 at the target atom)")

    t5_gamma(G1, G2)
    print("T5  PASS  (Gamma = {irreflexivity, asymmetry, transitivity} "
          "on both G_1 and G_2)")
    print()

    print("T1/T6/T7/T8/T10: discharged by proof/definition in the manuscript")
    print("(T1 §2.4-2.5; T6 Prop. 2.6; T7 Def. 2.7-2.8; T8 §2.13; T10 §2.10).")
    print("T9: separate script encoding_sensitivity_check.py.")
    print()
    print("PASS: Gate 1.5 model-pair items T2-T5.")


if __name__ == "__main__":
    main()
