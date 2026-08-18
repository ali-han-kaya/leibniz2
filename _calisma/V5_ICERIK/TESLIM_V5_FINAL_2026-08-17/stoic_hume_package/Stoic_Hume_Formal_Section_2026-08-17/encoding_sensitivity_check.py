"""
encoding_sensitivity_check.py
==============================

Finite-validation artefact for the encoding-sensitivity test of
the Stoic modal clause ("of such a kind as could not arise from
what is not") under two encodings:

  L0^A  minimal encoding: base atoms Kat, Veridical, SourceMatch,
        FalseSource; no modal vocabulary, no decomposition axiom.

  L0^B  provenance/modal decomposition: base atoms plus the
        decomposition axiom

            Kat(i) <-> Veridical(i) ∧ SourceMatch(i) ∧ M,

        where M = Box_src ¬FalseSource(i) is evaluated by the
        standard translation of modal logic over a two-world
        frame {i, j}:

            M = (R(i,i) -> ¬F(i)) ∧ (R(i,j) -> ¬F(j)).

The extensional base assignment is E = (Kat, Veridical,
SourceMatch, FalseSource(i)).  The modal resource is the frame:
the accessibility relation R and the value of FalseSource at the
non-base world j.

For each encoding the script asks: for how many base assignments
E is the modal content M left undetermined (i.e. both M = 0 and
M = 1 are realized by suitable modal resources, subject to the
theory of the encoding)?

Verdict criterion (V5, Gate 1.5, item T9): if the two encodings
yield the same underdetermination result the negative result is
robust; if they differ it is encoding-sensitive.

Run:    python3 encoding_sensitivity_check.py
Output: VERDICT line on stdout. Deterministic, stdlib only
        (itertools.product), verified on Python 3.10/3.11/3.12.
"""
from itertools import product


def modal_clause(r_ii, r_ij, f_i, f_j):
    """M = Box_src ¬FalseSource(i), standard translation over {i, j}."""
    return (not r_ii or not f_i) and (not r_ij or not f_j)


def base_assignments():
    """All E = (Kat, Veridical, SourceMatch, FalseSource(i)), 16 in total."""
    return list(product((0, 1), repeat=4))


def modal_resources():
    """All (R(i,i), R(i,j), FalseSource(j)), 8 in total."""
    return list(product((0, 1), repeat=3))


# ---------------------------------------------------------------------------
# L0^A: minimal encoding — no theory constraints on M
# ---------------------------------------------------------------------------

def l0A_realized_modal_values(E):
    """Set of M values realizable under some modal resource, given E."""
    vals = set()
    for r_ii, r_ij, f_j in modal_resources():
        vals.add(modal_clause(r_ii, r_ij, E[3], f_j))
    return vals


# ---------------------------------------------------------------------------
# L0^B: provenance/modal decomposition — decomposition axiom
#       Kat(i) <-> Veridical(i) ∧ SourceMatch(i) ∧ M
# ---------------------------------------------------------------------------

def l0B_models(E):
    """All M values realized by models of the theory with base E."""
    models = []
    for r_ii, r_ij, f_j in modal_resources():
        m = modal_clause(r_ii, r_ij, E[3], f_j)
        if E[0] == (E[1] and E[2] and m):
            models.append(m)
    return models


def main():
    names = ("Kat", "Veridical", "SourceMatch", "FalseSource(i)")

    under_A = 0
    for E in base_assignments():
        if len(l0A_realized_modal_values(E)) == 2:
            under_A += 1

    admissible_B = 0
    under_B = 0
    det_B = []
    for E in base_assignments():
        models = l0B_models(E)
        if not models:
            continue  # inadmissible: no model with this base assignment
        admissible_B += 1
        if len(set(models)) == 2:
            under_B += 1
        else:
            det_B.append(E)

    print("Encoding sensitivity check: Stoic modal clause M")
    print("M = Box_src not FalseSource(i), standard translation over {i, j}")
    print("Base E = (Kat, Veridical, SourceMatch, FalseSource(i));")
    print("modal resource = (R(i,i), R(i,j), FalseSource(j)).")
    print()

    print(f"L0^A (minimal):        {under_A}/{len(base_assignments())} "
          f"base assignments leave M undetermined")
    print(f"L0^B (decomposition):  {under_B}/{admissible_B} admissible "
          f"base assignments leave M undetermined, "
          f"{len(det_B)}/{admissible_B} determine it")
    print()
    print("Determined under L0^B (base assignment, forced M):")
    for E in det_B:
        m_val = 1 if E[0] else 0
        print("   " + ", ".join(f"{n}={v}" for n, v in zip(names, E))
              + f"  -> M = {m_val} (forced by decomposition axiom)")
    print()

    same_result = (under_A == len(base_assignments())) == (under_B == admissible_B) \
        and (under_A == 0) == (under_B == 0)
    if same_result:
        verdict = ("ROBUST: the two encodings yield the same "
                   "underdetermination result")
    else:
        verdict = ("ENCODING-SENSITIVE: the two encodings yield different "
                   "underdetermination results")
    print("VERDICT: " + verdict)
    print("Subsidiary: under BOTH encodings there exist admissible base")
    print("assignments on which the extensional base does not fix M;")
    print("where L0^B determines M, the determination comes from the")
    print("modal resource written into the theory itself. General thesis")
    print("(extensional base alone does not fix the modal content) holds")
    print("under both encodings.")


if __name__ == "__main__":
    main()
