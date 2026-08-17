/-!
# L₀-reduct invariance (Lemma: reduct-invariance) — Lean 4 formalization

`core_section.tex` Lemma `lem:reduct-invariance`:

  Let M₁⁺, M₂⁺ ∈ 𝒦 have identical L₀-reducts. Then, for every L₀-sentence φ,
  M₁⁺ ⊨ φ ⟺ M₂⁺ ⊨ φ.

The proof is a structural induction over L₀-formulas. Z3 cannot produce this
(second-order / syntax-level statement); here it is formalized and
machine-checked in Lean 4 (no Mathlib — self-contained).

We model the L₀-reduct abstractly: three sorts (`Imp`, `Cont`, `Ep`) and the
nine non-logical predicates. The L⁺ enrichment is deliberately absent: by
definition `Realize` for an L₀-formula never refers to L⁺ symbols, so the
enrichment cannot affect L₀-truth — the lemma reduces to the statement below,
which is *stronger* (covers open formulas via environments).

This file compiles standalone:  `lean ReductInvariance.lean`
-/

-- L₀ sıraları yapı parametreleri olarak soyut tipler:
--   Imp  = impressions (I),  Cont = contents,  Ep = cognitive episodes (B)
structure L0Structure (Imp Cont Ep : Type) where
  Kat : Imp → Prop
  Rep : Imp → Cont → Prop
  Grasp : Ep → Imp → Prop
  Assent : Ep → Cont → Prop
  Bel : Ep → Cont → Prop
  Causal : Ep → Cont → Prop
  Custom : Ep → Prop
  Just : Ep → Cont → Prop
  StoicEp : Ep → Prop

-- L₀ formül sözdizimi: 9 atom + Boole bağlaçları + 3 sıralı niceleyici.
-- Değişkenler her sıra için ayrı bir `Nat` ad-uzayı kullanır.
inductive Formula where
  | kat : Nat → Formula
  | rep : Nat → Nat → Formula
  | grasp : Nat → Nat → Formula
  | assent : Nat → Nat → Formula
  | bel : Nat → Nat → Formula
  | causal : Nat → Nat → Formula
  | custom : Nat → Formula
  | just : Nat → Nat → Formula
  | stoicEp : Nat → Formula
  | not : Formula → Formula
  | and : Formula → Formula → Formula
  | or : Formula → Formula → Formula
  | imp : Formula → Formula → Formula
  | iff : Formula → Formula → Formula
  | allImp : Nat → Formula → Formula
  | exImp : Nat → Formula → Formula
  | allCont : Nat → Formula → Formula
  | exCont : Nat → Formula → Formula
  | allEp : Nat → Formula → Formula
  | exEp : Nat → Formula → Formula

-- Değişken ataması (environment): üç sıra için `Nat → sort`.
structure Env (Imp Cont Ep : Type) where
  imp : Nat → Imp
  cont : Nat → Cont
  ep : Nat → Ep

def update {A : Type} (f : Nat → A) (k : Nat) (a : A) : Nat → A :=
  fun n => if n = k then a else f n

-- Tarski doyumu (satisfaction). Yalnızca L₀ sembollerine başvurur.
def Realize {Imp Cont Ep : Type} (M : L0Structure Imp Cont Ep) :
    Formula → Env Imp Cont Ep → Prop
  | .kat i, e => M.Kat (e.imp i)
  | .rep i c, e => M.Rep (e.imp i) (e.cont c)
  | .grasp b i, e => M.Grasp (e.ep b) (e.imp i)
  | .assent b c, e => M.Assent (e.ep b) (e.cont c)
  | .bel b c, e => M.Bel (e.ep b) (e.cont c)
  | .causal b c, e => M.Causal (e.ep b) (e.cont c)
  | .custom b, e => M.Custom (e.ep b)
  | .just b c, e => M.Just (e.ep b) (e.cont c)
  | .stoicEp b, e => M.StoicEp (e.ep b)
  | .not φ, e => ¬ Realize M φ e
  | .and φ ψ, e => Realize M φ e ∧ Realize M ψ e
  | .or φ ψ, e => Realize M φ e ∨ Realize M ψ e
  | .imp φ ψ, e => Realize M φ e → Realize M ψ e
  | .iff φ ψ, e => Realize M φ e ↔ Realize M ψ e
  | .allImp k φ, e => ∀ x : Imp, Realize M φ {e with imp := update e.imp k x}
  | .exImp k φ, e => ∃ x : Imp, Realize M φ {e with imp := update e.imp k x}
  | .allCont k φ, e => ∀ x : Cont, Realize M φ {e with cont := update e.cont k x}
  | .exCont k φ, e => ∃ x : Cont, Realize M φ {e with cont := update e.cont k x}
  | .allEp k φ, e => ∀ x : Ep, Realize M φ {e with ep := update e.ep k x}
  | .exEp k φ, e => ∃ x : Ep, Realize M φ {e with ep := update e.ep k x}

-- "Özdeş L₀-reduct": iki yapı dokuz yüklemi noktasal (extensionally) paylaşır.
structure L0Agree {Imp Cont Ep : Type} (M1 M2 : L0Structure Imp Cont Ep) : Prop where
  kat : ∀ i, M1.Kat i ↔ M2.Kat i
  rep : ∀ i c, M1.Rep i c ↔ M2.Rep i c
  grasp : ∀ b i, M1.Grasp b i ↔ M2.Grasp b i
  assent : ∀ b c, M1.Assent b c ↔ M2.Assent b c
  bel : ∀ b c, M1.Bel b c ↔ M2.Bel b c
  causal : ∀ b c, M1.Causal b c ↔ M2.Causal b c
  custom : ∀ b, M1.Custom b ↔ M2.Custom b
  just : ∀ b c, M1.Just b c ↔ M2.Just b c
  stoicEp : ∀ b, M1.StoicEp b ↔ M2.StoicEp b

/-- Lemma `lem:reduct-invariance` (yapısal tümevarım ile). -/
theorem reduct_invariance {Imp Cont Ep : Type} (M1 M2 : L0Structure Imp Cont Ep)
    (h : L0Agree M1 M2) :
    ∀ (φ : Formula) (e : Env Imp Cont Ep), Realize M1 φ e ↔ Realize M2 φ e := by
  intro φ
  induction φ with
  | kat i =>
      intro e; exact h.kat (e.imp i)
  | rep i c =>
      intro e; exact h.rep (e.imp i) (e.cont c)
  | grasp b i =>
      intro e; exact h.grasp (e.ep b) (e.imp i)
  | assent b c =>
      intro e; exact h.assent (e.ep b) (e.cont c)
  | bel b c =>
      intro e; exact h.bel (e.ep b) (e.cont c)
  | causal b c =>
      intro e; exact h.causal (e.ep b) (e.cont c)
  | custom b =>
      intro e; exact h.custom (e.ep b)
  | just b c =>
      intro e; exact h.just (e.ep b) (e.cont c)
  | stoicEp b =>
      intro e; exact h.stoicEp (e.ep b)
  | not φ ih =>
      intro e
      constructor
      · intro hn h2; exact hn ((ih e).2 h2)
      · intro hn h1; exact hn ((ih e).1 h1)
  | and φ ψ ihφ ihψ =>
      intro e
      constructor
      · intro h; exact ⟨(ihφ e).1 h.1, (ihψ e).1 h.2⟩
      · intro h; exact ⟨(ihφ e).2 h.1, (ihψ e).2 h.2⟩
  | or φ ψ ihφ ihψ =>
      intro e
      constructor
      · intro h; cases h with
        | inl a => exact Or.inl ((ihφ e).1 a)
        | inr b => exact Or.inr ((ihψ e).1 b)
      · intro h; cases h with
        | inl a => exact Or.inl ((ihφ e).2 a)
        | inr b => exact Or.inr ((ihψ e).2 b)
  | imp φ ψ ihφ ihψ =>
      intro e
      constructor
      · intro h h2; exact (ihψ e).1 (h ((ihφ e).2 h2))
      · intro h h1; exact (ihψ e).2 (h ((ihφ e).1 h1))
  | iff φ ψ ihφ ihψ =>
      intro e
      constructor
      · intro h
        constructor
        · intro a; exact (ihψ e).1 (h.1 ((ihφ e).2 a))
        · intro b; exact (ihφ e).1 (h.2 ((ihψ e).2 b))
      · intro h
        constructor
        · intro a; exact (ihψ e).2 (h.1 ((ihφ e).1 a))
        · intro b; exact (ihφ e).2 (h.2 ((ihψ e).1 b))
  | allImp k φ ih =>
      intro e
      constructor
      · intro h x; exact (ih {e with imp := update e.imp k x}).1 (h x)
      · intro h x; exact (ih {e with imp := update e.imp k x}).2 (h x)
  | exImp k φ ih =>
      intro e
      constructor
      · intro h; rcases h with ⟨x, hx⟩
        exact ⟨x, (ih {e with imp := update e.imp k x}).1 hx⟩
      · intro h; rcases h with ⟨x, hx⟩
        exact ⟨x, (ih {e with imp := update e.imp k x}).2 hx⟩
  | allCont k φ ih =>
      intro e
      constructor
      · intro h x; exact (ih {e with cont := update e.cont k x}).1 (h x)
      · intro h x; exact (ih {e with cont := update e.cont k x}).2 (h x)
  | exCont k φ ih =>
      intro e
      constructor
      · intro h; rcases h with ⟨x, hx⟩
        exact ⟨x, (ih {e with cont := update e.cont k x}).1 hx⟩
      · intro h; rcases h with ⟨x, hx⟩
        exact ⟨x, (ih {e with cont := update e.cont k x}).2 hx⟩
  | allEp k φ ih =>
      intro e
      constructor
      · intro h x; exact (ih {e with ep := update e.ep k x}).1 (h x)
      · intro h x; exact (ih {e with ep := update e.ep k x}).2 (h x)
  | exEp k φ ih =>
      intro e
      constructor
      · intro h; rcases h with ⟨x, hx⟩
        exact ⟨x, (ih {e with ep := update e.ep k x}).1 hx⟩
      · intro h; rcases h with ⟨x, hx⟩
        exact ⟨x, (ih {e with ep := update e.ep k x}).2 hx⟩

/-- Cümle (closed formula) özel durumu: her ortamda aynı doğruluk değeri. -/
theorem reduct_invariance_sentences {Imp Cont Ep : Type} (M1 M2 : L0Structure Imp Cont Ep)
    (h : L0Agree M1 M2) (φ : Formula) :
    (∀ e : Env Imp Cont Ep, Realize M1 φ e) ↔
      (∀ e : Env Imp Cont Ep, Realize M2 φ e) := by
  constructor
  · intro H e; exact (reduct_invariance M1 M2 h φ e).1 (H e)
  · intro H e; exact (reduct_invariance M1 M2 h φ e).2 (H e)

#check reduct_invariance
#check reduct_invariance_sentences
