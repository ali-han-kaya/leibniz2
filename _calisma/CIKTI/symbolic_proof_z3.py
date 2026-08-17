#!/usr/bin/env python3
"""
symbolic_proof_z3.py — Stoic-Hume V5 formal çekirdeğinin SEMBOLİK ispatı.

Finite-check'in (16 satırlık Boolean fragment) ötesine geçer: L_0 fragmanındaki
tüm gerektirme iddialarını Z3 ile, TÜM yapılar (her domain, her yorum) üzerinden
ispatlar. UNSAT = geçerlilik kanıtı (ispat); SAT = açık karşı-model (tanık).

Kapsam (core_section.tex §2 formal çekirdeği):
  Prop 1       T2 ∧ M0 ⊨ T1  ve  T1 ∧ M0 ⊭ T2 (karşı-model ile)
  Bridge       T1 ∧ B0 ⊨ T2 (M0 üzerinde)
  Karakteriz.  (T1 ∧ M0 ∧ ¬T2) ⇄ ⋆  -- İKİ YÖN AYRI AYRI test edilir
  Prop 2       L0-reduct'i özdeş, G'si farklı iki admissibl model tanığı

L_0 fragmanı (fonksiyon sembolü içermeyen ∃*∀* / Bernays–Schönfinkel sınıfı)
Z3'ün MBQI'si için karar verilebilir: bu sınıfta UNSAT sonucu buluşsal değil,
gerçek bir geçerlilik ispatıdır. L^+ (Prop 2) fonksiyon sembolü içerir; orada
sadece SAT (tanık model) isteniyor ve SAT sonucu her zaman seslidir (sound).

Kullanım:
    ./.venv_z3/bin/python symbolic_proof_z3.py
Exit kodu: 0 = tüm beklenen sonuçlar doğrulandı, 1 = beklenmedik sonuç.
"""
import sys
from z3 import (And, BoolSort, Const, Consts, DeclareSort, Exists, ForAll,
                Function, Implies, Not, Or, Solver, sat, unsat, unknown)

# --------------------------------------------------------------------------
# Sıralar ve L_0 söz dağarcığı
# --------------------------------------------------------------------------
B = DeclareSort('B')          # cognitive episodes
Cont = DeclareSort('Cont')    # ordinary representational contents

b = Const('b', B)
c = Const('c', Cont)

Causal = Function('Causal', B, Cont, BoolSort())   # Causal(b,c)
Custom = Function('Custom', B, BoolSort())         # Custom(b)
Bel    = Function('Bel', B, Cont, BoolSort())      # Bel(b,c)
Just   = Function('Just', B, Cont, BoolSort())     # Just(b,c)

# --------------------------------------------------------------------------
# Aksiyomlar (core_section.tex / L0_Lplus_spec.md §4-5)
# --------------------------------------------------------------------------
M0a = ForAll([b, c], Implies(Causal(b, c), Custom(b)))
M0b = ForAll([b, c], Implies(Causal(b, c), Bel(b, c)))
T1  = ForAll([b, c], Implies(Causal(b, c), Not(Just(b, c))))           # T_1
T2  = ForAll([b, c], Implies(And(Custom(b), Bel(b, c)),
                             Not(Just(b, c))))                         # H-I
B0  = ForAll([b, c], Implies(And(Custom(b), Bel(b, c)), Causal(b, c))) # B_0
M0  = And(M0a, M0b)

STAR = Exists([b, c], And(Custom(b), Bel(b, c), Just(b, c),
                          Not(Causal(b, c))))                          # ⋆
NOT_T2 = Exists([b, c], And(Custom(b), Bel(b, c), Just(b, c)))         # ¬T_2

# Çift (pair) düzeyinde değerlendirme (sabit b0, c0)
b0 = Const('b0', B)
c0 = Const('c0', Cont)
T1_pair = Implies(Causal(b0, c0), Not(Just(b0, c0)))
T2_pair = Implies(And(Custom(b0), Bel(b0, c0)), Not(Just(b0, c0)))
STAR_pair = And(Custom(b0), Bel(b0, c0), Just(b0, c0), Not(Causal(b0, c0)))

RESULTS = []   # (id, isim, beklenen, alınan, not)


def record(cid, name, expected, got, note=""):
    ok = (expected == got)
    RESULTS.append((cid, name, expected, got, note, ok))
    return ok


def check_validity(name, formula, timeout_ms=30000):
    """formula'nın GEÇERLİ olup olmadığını test et: Not(formula) UNSAT mı?"""
    s = Solver()
    s.set(timeout=timeout_ms)
    s.add(Not(formula))
    r = s.check()
    return s, r


def sat_countermodel(name, formula, timeout_ms=30000):
    """formula'nın doyurulabilir olduğunu kanıtla (karşı-model/tanık üret)."""
    s = Solver()
    s.set(timeout=timeout_ms)
    s.add(formula)
    r = s.check()
    return s, r


def verdict_str(r):
    if r == sat:
        return "SAT"
    if r == unsat:
        return "UNSAT"
    return "UNKNOWN"


print("=" * 70)
print("SEMBOLİK İSPAT — core_section.tex (Z3, tüm yapılar üzerinden)")
print("=" * 70)

# --------------------------------------------------------------------------
# 1) Prop 1: T2 ∧ M0 ⊨ T1   (geçerlilik = UNSAT)
# --------------------------------------------------------------------------
s, r = check_validity("P1-a: (T2 ∧ M0) → T1", Implies(And(T2, M0), T1))
record("P1-a", "(T2 ∧ M0) ⊨ T1", "UNSAT", verdict_str(r))
print(f"[P1-a] (T2 ∧ M0) → T1  : {verdict_str(r)}  (beklenen UNSAT)")

# --------------------------------------------------------------------------
# 2) Prop 1: T1 ∧ M0 ⊭ T2   (karşı-model = SAT)
# --------------------------------------------------------------------------
s, r = sat_countermodel("P1-b: T1 ∧ M0 ∧ ¬T2", And(T1, M0, NOT_T2))
ok = record("P1-b", "T1 ∧ M0 ⊭ T2", "SAT", verdict_str(r))
print(f"[P1-b] T1 ∧ M0 ∧ ¬T2   : {verdict_str(r)}  (beklenen SAT = karşı-model)")
if r == sat:
    m = s.model()
    # tanığın kendisi: ¬T2'yi doğrulayan (b,c) çifti Z3 modelinde bulunur.
    print("        Karşı-model (Z3 tanığı) — ¬T2 tanığı aranıyor...")
    # Modeldeki yorumu okunabilir göster: 4 yüklemi b0/c0 yerine bize verilen
    # sabitlerde değil; Z3'ün seçtiği tanık elemanları Const'larla eşleşmez.
    # Bu yüzden yüklemleri tanık değerleriyle değil, "model tamlığı" açarak
    # basitçe tüm atomları rapor ederiz (b0,c0 sabitleri modelde serbest).
    print(f"        Custom(b0)={m.eval(Custom(b0), True)} "
          f"Bel(b0,c0)={m.eval(Bel(b0, c0), True)} "
          f"Just(b0,c0)={m.eval(Just(b0, c0), True)} "
          f"Causal(b0,c0)={m.eval(Causal(b0, c0), True)}")

# --------------------------------------------------------------------------
# 3) Bridge collapse: T1 ∧ B0 ⊨ T2 (M0 üzerinde)   (geçerlilik = UNSAT)
# --------------------------------------------------------------------------
s, r = check_validity("P2: (T1 ∧ B0 ∧ M0) → T2",
                      Implies(And(T1, B0, M0), T2))
record("P2", "T1 ∧ B0 ⊨ T2 (M0)", "UNSAT", verdict_str(r))
print(f"[P2]  (T1 ∧ B0 ∧ M0) → T2 : {verdict_str(r)}  (beklenen UNSAT)")

# --------------------------------------------------------------------------
# 4) Çift düzeyinde karakterizasyon (DOĞRU iff — kağıttaki 16 satırın nedeni)
#    (T1_pair ∧ ¬T2_pair) ⇄ STAR_pair
# --------------------------------------------------------------------------
s, r = check_validity("P3-a: (T1_pair ∧ ¬T2_pair) → ⋆_pair",
                      Implies(And(T1_pair, Not(T2_pair)), STAR_pair))
record("P3-a", "(T1∧¬T2) → ⋆ (pair)", "UNSAT", verdict_str(r))
print(f"[P3-a] (T1_pair ∧ ¬T2_pair) → ⋆_pair : {verdict_str(r)}  (beklenen UNSAT)")

s, r = check_validity("P3-b: ⋆_pair → (T1_pair ∧ ¬T2_pair)",
                      Implies(STAR_pair, And(T1_pair, Not(T2_pair))))
record("P3-b", "⋆ → (T1∧¬T2) (pair)", "UNSAT", verdict_str(r))
print(f"[P3-b] ⋆_pair → (T1_pair ∧ ¬T2_pair) : {verdict_str(r)}  (beklenen UNSAT)")

# --------------------------------------------------------------------------
# 5) GLOBAL karakterizasyon — İKİ YÖN AYRI. (kağıttaki 'iff' iddiasının denetimi)
#    (→): (T1 ∧ M0 ∧ ¬T2) → ⋆
#    (←): ⋆ → (T1 ∧ M0 ∧ ¬T2)
# --------------------------------------------------------------------------
s, r = check_validity("P4-a: (T1 ∧ M0 ∧ ¬T2) → ⋆",
                      Implies(And(T1, M0, NOT_T2), STAR))
record("P4-a", "(T1∧M0∧¬T2) → ⋆", "UNSAT", verdict_str(r))
print(f"[P4-a] (T1 ∧ M0 ∧ ¬T2) → ⋆ : {verdict_str(r)}  (beklenen UNSAT)")

s, r = check_validity("P4-b: ⋆ → (T1 ∧ M0 ∧ ¬T2)",
                      Implies(STAR, And(T1, M0, NOT_T2)))
# Beklenen: SAT (iff'in ters yönü GEÇERLİ DEĞİL)
record("P4-b", "⋆ → (T1∧M0∧¬T2)", "SAT", verdict_str(r))
print(f"[P4-b] ⋆ → (T1 ∧ M0 ∧ ¬T2) : {verdict_str(r)}  (beklenen SAT = karşı-model)")
if r == sat:
    m = s.model()
    print("        ⋆ doğru ama sonuç yanlış bir model var (karşı-model):")
    print(f"        M0a={m.eval(M0a, True)} M0b={m.eval(M0b, True)} "
          f"T1={m.eval(T1, True)} ¬T2={m.eval(NOT_T2, True)} "
          f"⋆={m.eval(STAR, True)}")

# Keskin karşı-model: ⋆ ∧ ¬T1 doyurulabilir mi? (⋆, T1'i bile ima etmez)
s, r = sat_countermodel("P4-c: ⋆ ∧ ¬T1", And(STAR, Not(T1)))
record("P4-c", "⋆ ∧ ¬T1 doyurulabilir", "SAT", verdict_str(r))
print(f"[P4-c] ⋆ ∧ ¬T1           : {verdict_str(r)}  (beklenen SAT)")
if r == sat:
    m = s.model()
    print("        Tanık: ⋆ doğruyken T1 yanlış (iki ayrı (b,c) çifti yeterli).")

# DÜZELTİLMİŞ global karakterizasyon — kağıda yazılacak doğru önerme.
# (T1 ∧ M0 ∧ ⋆) ⟺ (T1 ∧ M0 ∧ ¬T2)
s, r = check_validity("P4-d: (T1 ∧ M0 ∧ ⋆) ⟺ (T1 ∧ M0 ∧ ¬T2)",
                      And(Implies(And(T1, M0, STAR), And(T1, M0, NOT_T2)),
                          Implies(And(T1, M0, NOT_T2), And(T1, M0, STAR))))
record("P4-d", "(T1∧M0∧⋆) ⟺ (T1∧M0∧¬T2)", "UNSAT", verdict_str(r))
print(f"[P4-d] (T1 ∧ M0 ∧ ⋆) ⟺ (T1 ∧ M0 ∧ ¬T2) : {verdict_str(r)}  (beklenen UNSAT)")

# ⋆ tek başına ¬T2'yi ima eder (ama T1'i etmez — P4-c)
s, r = check_validity("P4-e: ⋆ → ¬T2", Implies(STAR, NOT_T2))
record("P4-e", "⋆ → ¬T2", "UNSAT", verdict_str(r))
print(f"[P4-e] ⋆ → ¬T2            : {verdict_str(r)}  (beklenen UNSAT)")

# --------------------------------------------------------------------------
# 6) Prop 2 — özdeş L_0-reduct'li, G'si farklı İKİ admissibl model (tanık)
# --------------------------------------------------------------------------
print("-" * 70)
print("Prop 2: özdeş L_0-reduct + farklı G — iki model tanığı")
Fact = DeclareSort('Fact')
x, y = Consts('x y', Fact)

# Tek ortak L_0 (yukarıdaki Causal/Custom/Bel/Just), iki kopya L^+ eki:
def lplus(k):
    G      = Function(f'G{k}', Fact, Fact, BoolSort())
    Obt    = Function(f'Obt{k}', Fact, BoolSort())
    cust   = Function(f'cust{k}', B, Fact)
    nonj   = Function(f'nonj{k}', B, Cont, Fact)
    O1 = ForAll([b], Obt(cust(b)) == Custom(b))
    O2 = ForAll([b, c], Obt(nonj(b, c)) == Not(Just(b, c)))
    O3 = ForAll([x, y], Implies(G(x, y), And(Obt(x), Obt(y))))
    return G, Obt, cust, nonj, And(O1, O2, O3)

G1, Obt1, cust1, nonj1, AX1 = lplus(1)
G2, Obt2, cust2, nonj2, AX2 = lplus(2)

atom1 = G1(cust1(b0), nonj1(b0, c0))
atom2 = G2(cust2(b0), nonj2(b0, c0))

witness = And(M0a, M0b, AX1, AX2,
              Custom(b0) == True, Just(b0, c0) == False,   # relata obtain (O3)
              atom1 == True, atom2 == False)               # farklı G

s, r = sat_countermodel("P5: Prop 2 tanık çifti", witness)
record("P5", "Prop 2 model çifti", "SAT", verdict_str(r))
print(f"[P5]  İki admissibl model (özdeş L_0, farklı G) : {verdict_str(r)} "
      f"(beklenen SAT)")
if r == sat:
    m = s.model()
    print(f"        atom1 = G1(cust1(b0),nonj1(b0,c0)) = "
          f"{m.eval(atom1, True)}")
    print(f"        atom2 = G2(cust2(b0),nonj2(b0,c0)) = "
          f"{m.eval(atom2, True)}")
    print(f"        Ortak L_0: Custom(b0)={m.eval(Custom(b0), True)}, "
          f"Just(b0,c0)={m.eval(Just(b0, c0), True)}, "
          f"Causal(b0,c0)={m.eval(Causal(b0, c0), True)}, "
          f"Bel(b0,c0)={m.eval(Bel(b0, c0), True)}")
    print(f"        Aksiyomlar (her iki modelde doğru): "
          f"M0a={m.eval(M0a, True)} M0b={m.eval(M0b, True)} "
          f"O1..O3(1)={m.eval(AX1, True)} O1..O3(2)={m.eval(AX2, True)}")

# Bonus: Just=true taban modeli O_3 yüzünden admissibl DEĞİL (spec §9 notu)
s, r = sat_countermodel("P5-note: Just=true + G1 atomu",
                        And(M0a, M0b, AX1,
                            Custom(b0) == True, Just(b0, c0) == True,
                            atom1 == True))
record("P5-note", "Just=true taban modeli admissibl değil", "UNSAT", verdict_str(r))
print(f"[P5-note] Just(b0,c0)=true iken G1 atomu (O_3 ile) : "
      f"{verdict_str(r)}  (beklenen UNSAT)")

# --------------------------------------------------------------------------
# Özet + exit kodu
# --------------------------------------------------------------------------
print("=" * 70)
allok = all(ok for (_, _, _, _, _, ok) in RESULTS)
for cid, name, exp, got, note, ok in RESULTS:
    mark = "PASS" if ok else "FAIL"
    print(f"  [{mark}] {cid:<8} {name:<28} beklenen={exp:<6} alınan={got}")
print("=" * 70)
print("SONUÇ:", "TÜMÜ PASS" if allok else "BEKLENMEDİK SONUÇ VAR")
sys.exit(0 if allok else 1)
