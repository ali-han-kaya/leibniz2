"""
core_formal_model_check.py
==========================

Finite-validation artefact for the core section of
"What an Extensional First-Order Formalization Leaves
Underdetermined: Stoic Katalepsis and Humean Custom".

The script:

1.  Exhaustive Boolean check of Proposition 1
    (T_2 ∧ M_0 ⊨ T_1   and   T_1 ∧ M_0 ⊭ T_2),
    the bridge collapse (T_1 ∧ M_0 ∧ B_0 ⊨ T_2), and the
    characterization of separation (∗).

2.  Construction of the model pair required by
    Proposition 2 (implicit definability failure), together
    with a direct check of the reification axioms (O_1)-(O_3)
    on that pair (so the pair provably lies in the admissible
    class K).

Run:    python3 core_formal_model_check.py
Output: PASS line on stdout, or AssertionError on failure.

The script depends only on the Python 3 standard library
(itertools.product). It is deterministic and has been
verified on Python 3.10, 3.11, 3.12.

The general proof of the two propositions is the
structural-induction argument in the core section
(Lemma: L_0-reduct invariance). This script is a
verification layer, not a substitute.
"""

from itertools import product


# ---------------------------------------------------------------------------
# Proposition 1: strength relation (T_2 / T_1) over M_0
# ---------------------------------------------------------------------------

def check_proposition_1():
    """
    Exhaustively enumerate the single-B / single-C Boolean fragment
    (16 interpretations) and check:

        (a) T_2 ∧ M_0 ⊨ T_1  (zero falsifying rows)
        (b) T_1 ∧ M_0 ⊭ T_2  (at least one falsifying row)
        (c) T_1 ∧ M_0 ∧ B_0 ⊨ T_2  (bridge collapse; zero falsifying)
        (d) the unique countermodel of (b) is exactly the row
            (Causal=0, Custom=1, Bel=1, Just=1)
    """
    rows = []
    for causal, custom, bel, just in product([False, True], repeat=4):
        # Mechanism axioms M_0a and M_0b
        m0a = (not causal) or custom
        m0b = (not causal) or bel
        m0 = m0a and m0b

        # Bridge axiom B_0
        b0 = (not (custom and bel)) or causal

        # T_1 (direct-attachment reading)
        t1 = (not causal) or (not just)

        # T_2 (strong exclusion reconstruction, H-I)
        t2 = (not (custom and bel)) or (not just)

        rows.append({
            "Causal": causal, "Custom": custom, "Bel": bel, "Just": just,
            "M_0": m0, "B_0": b0, "T_1": t1, "T_2": t2,
        })

    # (a) T_2 ∧ M_0 ⊨ T_1
    falsify_a = [r for r in rows if r["M_0"] and r["T_2"] and not r["T_1"]]
    assert not falsify_a, f"T_2 ∧ M_0 ⊨ T_1 falsified by {falsify_a}"

    # (b) T_1 ∧ M_0 ⊭ T_2
    falsify_b = [r for r in rows if r["M_0"] and r["T_1"] and not r["T_2"]]
    assert falsify_b, "T_1 ∧ M_0 ⊨ T_2 unexpectedly holds everywhere"

    # (d) uniqueness: exactly one falsifying row, and it is the
    #     expected (0,1,1,1) signature.
    assert len(falsify_b) == 1, (
        f"Expected unique countermodel, got {len(falsify_b)} rows"
    )
    only = falsify_b[0]
    assert (only["Causal"], only["Custom"], only["Bel"], only["Just"]) \
        == (False, True, True, True), (
        f"Unexpected countermodel: {only}"
    )

    # (c) bridge collapse: with B_0, no row of T_1 ∧ M_0 ∧ B_0
    #     falsifies T_2.
    falsify_c = [r for r in rows
                 if r["M_0"] and r["B_0"] and r["T_1"] and not r["T_2"]]
    assert not falsify_c, f"Bridge collapse falsified by {falsify_c}"

    return rows


# ---------------------------------------------------------------------------
# Characterization of separation (∗)
# ---------------------------------------------------------------------------

def check_characterization(rows):
    """
    Verify the equivalence:

        M ⊨ T_1 ∧ M_0 ∧ ¬T_2
            ⟺ M ⊨ ∃b∃c [ Custom ∧ Bel ∧ Just ∧ ¬Causal ]

    In the Boolean fragment, this reduces to:
    the single row (0,1,1,1) is the only one with
    T_1 ∧ M_0 ∧ ¬T_2.
    """
    lhs = [r for r in rows if r["M_0"] and r["T_1"] and not r["T_2"]]
    rhs = [r for r in rows
           if r["Custom"] and r["Bel"] and r["Just"] and not r["Causal"]]

    # Both sides must be the same singleton, and equal to (0,1,1,1).
    assert len(lhs) == 1 and len(rhs) == 1, (
        f"Characterization (∗) failed: lhs={lhs}, rhs={rhs}"
    )
    only = lhs[0]
    assert (only["Causal"], only["Custom"], only["Bel"], only["Just"]) \
        == (False, True, True, True)
    return only


# ---------------------------------------------------------------------------
# Proposition 2: implicit definability failure (model pair)
# ---------------------------------------------------------------------------

def construct_proposition_2_pair():
    """
    Build two L^+ structures M_1^G and M_2^G with identical
    L_0-reducts but different G extensions, where

        target = (custFact(b1), nonjustFact(b1, c1))

    is in G_1 and not in G_2.
    """
    # The L_0 interpretation. The single-episode / single-content
    # Boolean core. Each predicate is the set of tuples for which
    # it is true. Causal=0, Custom=1, Bel=1, Just=0.
    #
    # Note on Just=0: the reification axioms (O_2) read
    #   Obtains(nonjustFact(b,c)) <-> ~Just(b,c).
    # If Just were true, the fact-object nonjustFact(b1,c1) would
    # NOT obtain, and the target grounding atom would violate the
    # relata axiom (O_3) — the pair would not lie in K. The base
    # model is therefore chosen with Just=0, so that both relata
    # of the target atom obtain and (O_1)-(O_3) hold.
    L0 = {
        "Kat":     {("i1",)},
        "Rep":     {("i1", "c1")},
        "Grasp":   {("b1", "i1")},
        "Assent":  {("b1", "c1")},
        "Bel":     {("b1", "c1")},
        "Causal":  set(),                      # false
        "Custom":  {("b1",)},                  # true
        "Just":    set(),                      # false (see note)
        "StoicEp": {("b1",)},
    }

    target = (("custFact", "b1"), ("nonjustFact", "b1", "c1"))

    # Both enrichments share the same L_0-reduct (the same
    # interpretation dictionary). The two structures differ only
    # in the G extension: G_1 contains the target, G_2 does not.
    M1G = (L0, {target})
    M2G = (L0, set())

    # Invariants: the L_0-reducts are equal as values, and the
    # G extensions differ at the target.
    assert M1G[0] == M2G[0], "L_0-reducts must be identical"
    assert target in M1G[1], "G_1 must contain the target grounding atom"
    assert target not in M2G[1], "G_2 must not contain the target"
    assert M1G[1] != M2G[1], "G extensions must differ"

    # Reification axioms (O_1)-(O_3) on the pair. Obtains is
    # derived from the L_0 facts via (O_1) and (O_2); (O_3)
    # requires every grounding pair to have obtaining relata.
    l0 = M1G[0]
    obtains_cust = ("b1",) in l0["Custom"]           # O_1
    obtains_nonjust = ("b1", "c1") not in l0["Just"]  # O_2
    assert obtains_cust, "(O_1) violated: custFact(b1) must obtain"
    assert obtains_nonjust, "(O_2) violated: nonjustFact(b1,c1) must obtain"
    for (x, y) in M1G[1]:
        assert x == ("custFact", "b1") and obtains_cust
        assert y == ("nonjustFact", "b1", "c1") and obtains_nonjust
    assert M2G[1] == set(), "(O_3) must hold vacuously on M_2"

    return M1G, M2G, target


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

def print_table(rows):
    """Pretty-print the 16-row Boolean table (Table A)."""
    header = ("Causal  Custom  Bel  Just   M_0  B_0  T_1  T_2")
    print(header)
    print("-" * len(header))
    for r in rows:
        line = "  ".join(
            "T" if r[k] else "F"
            for k in ("Causal", "Custom", "Bel", "Just",
                      "M_0", "B_0", "T_1", "T_2")
        )
        marker = "  <-- unique countermodel" \
            if (r["Causal"], r["Custom"], r["Bel"], r["Just"]) \
               == (False, True, True, True) \
            else ""
        print(line + marker)


if __name__ == "__main__":
    rows = check_proposition_1()
    only = check_characterization(rows)
    m1, m2, target = construct_proposition_2_pair()

    print_table(rows)
    print()
    print(f"Unique countermodel of T_1 ∧ M_0 ⊭ T_2: {only}")
    print(f"Proposition 2 model pair constructed; target = {target}")
    print()
    print(
        "PASS: Proposition 1 (Boolean + bridge + characterization) "
        "and Proposition 2 (model pair)."
    )
