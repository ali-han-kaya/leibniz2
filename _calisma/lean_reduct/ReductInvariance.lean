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

The second half of this file ("Gerçek reduct senaryosu") then adds a genuine
L⁺ signature — two fresh symbols outside L₀ — together with the forgetful
`reduct` projection and two L⁺-expansions that *disagree* on L⁺ while sharing
their L₀-reduct: the paper's M₁⁺, M₂⁺ ∈ 𝒦 situation, machine-checked.

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

-- Concrete mini-model: two syntactically different mock interpretations of
-- the same L₀ reduct.  The second model uses `0 = 0` rather than `True`; the
-- proof below is deliberately about extensional agreement, not definitional
-- equality of the two mock definitions.
inductive MockImp where
  | i0 : MockImp

inductive MockCont where
  | c0 : MockCont

inductive MockEp where
  | e0 : MockEp

def mockModel (p : Prop) : L0Structure MockImp MockCont MockEp :=
  { Kat := fun _ => p
    Rep := fun _ _ => p
    Grasp := fun _ _ => p
    Assent := fun _ _ => p
    Bel := fun _ _ => p
    Causal := fun _ _ => p
    Custom := fun _ => p
    Just := fun _ _ => p
    StoicEp := fun _ => p }

def mockModelOne : L0Structure MockImp MockCont MockEp :=
  mockModel True

def mockModelTwo : L0Structure MockImp MockCont MockEp :=
  mockModel (0 = 0)

theorem mockL0Agree : L0Agree mockModelOne mockModelTwo := by
  constructor <;>
    simp [mockModelOne, mockModelTwo, mockModel]

def mockEnv : Env MockImp MockCont MockEp :=
  { imp := fun _ => .i0
    cont := fun _ => .c0
    ep := fun _ => .e0 }

def mockFormula : Formula :=
  .iff (.and (.kat 0) (.rep 0 0))
    (.or (.custom 0) (.stoicEp 0))

/-- The main reduct-invariance theorem instantiated in the concrete mock
model: the same L₀ formula and environment have equivalent truth values. -/
theorem mock_reduct_invariance :
    Realize mockModelOne mockFormula mockEnv ↔
      Realize mockModelTwo mockFormula mockEnv :=
  reduct_invariance mockModelOne mockModelTwo mockL0Agree mockFormula mockEnv

/-- The mock model is not merely formally interchangeable: the displayed
formula is true in both interpretations. -/
theorem mock_reduct_invariance_truth :
    Realize mockModelOne mockFormula mockEnv ∧
      Realize mockModelTwo mockFormula mockEnv := by
  constructor <;>
    simp [mockFormula, mockEnv, mockModelOne, mockModelTwo, mockModel,
      Realize]

/-!
# Gerçek reduct senaryosu: L⁺ zenginleşmesi + unutkan izdüşüm

Kağıdın lemması M₁⁺, M₂⁺ ∈ 𝒦 hakkında konuşur: L⁺-genişlemeleri, özdeş
L₀-reduct'li. Yukarıdaki mock'ta L⁺ yoktu; burada ikinci bir zenginleşme
(`Vivid`, `Familiar` — ikisi de L₀-dışı) gerçekten eklenir ve unutkan
`reduct` izdüşümü tanımlanır. `mockPlusOne` / `mockPlusTwo`, L₀'da birebir
aynı (`mockModel True`), L⁺'da taban tabana zıt yorumlara sahiptir —
`mockPlus_disagree` bunu tanıklar, `mock_plus_reduct_invariance` ise her
L₀-formülünde hemfikir olduklarını kanıtlar. Senaryo boş (vacuous) değildir:
modeller gerçekten farklıdır, ama fark L₀-cümlelerine yansımaz.
-/

-- L⁺ imza: L₀ + iki yeni sembol (ikinci zenginleşme).
--   Vivid    : Imp → Prop            (L⁺-unary, izlenim canlılığı)
--   Familiar : Ep → Cont → Prop      (L⁺-binary, aşinalık)
structure LPlusStructure (Imp Cont Ep : Type) extends L0Structure Imp Cont Ep where
  Vivid : Imp → Prop
  Familiar : Ep → Cont → Prop

-- Reduct izdüşümü (unutkan funktor): L⁺ sembollerini düşürür, L₀'yu korur.
def LPlusStructure.reduct {Imp Cont Ep : Type} (M : LPlusStructure Imp Cont Ep) :
    L0Structure Imp Cont Ep := M.toL0Structure

-- Parametrik mock L⁺-modeli: `l0` dokuz L₀ yüklemini, `v`/`f` L⁺ alanlarını besler.
def mockPlus (l0 v f : Prop) : LPlusStructure MockImp MockCont MockEp :=
  { mockModel l0 with
    Vivid := fun _ => v
    Familiar := fun _ _ => f }

-- Aynı L₀-reduct (`mockModel True`), zıt L⁺ yorumları.
def mockPlusOne : LPlusStructure MockImp MockCont MockEp :=
  mockPlus True True True

def mockPlusTwo : LPlusStructure MockImp MockCont MockEp :=
  mockPlus True False False

-- Reduct'ler özdeş: L0Agree, L⁺ alanlarına hiç bakmaz.
theorem mockPlusL0Agree : L0Agree mockPlusOne.reduct mockPlusTwo.reduct := by
  constructor <;>
    simp [mockPlusOne, mockPlusTwo, mockPlus, LPlusStructure.reduct, mockModel]

-- L⁺ ayrışma tanıkları: senaryonun boş olmadığını gösterir.
theorem mockPlus_disagree : mockPlusOne.Vivid .i0 ∧ ¬ mockPlusTwo.Vivid .i0 := by
  constructor
  · simp [mockPlusOne, mockPlus]
  · simp [mockPlusTwo, mockPlus]

theorem mockPlus_disagree_familiar :
    mockPlusOne.Familiar .e0 .c0 ∧ ¬ mockPlusTwo.Familiar .e0 .c0 := by
  constructor
  · simp [mockPlusOne, mockPlus]
  · simp [mockPlusTwo, mockPlus]

/-- Gerçek reduct senaryosu (açık formüller): L⁺'da ayrışan iki genişleme,
her L₀-formülünde her ortamda hemfikirdir. -/
theorem mock_plus_reduct_invariance (φ : Formula) (e : Env MockImp MockCont MockEp) :
    Realize mockPlusOne.reduct φ e ↔ Realize mockPlusTwo.reduct φ e :=
  reduct_invariance _ _ mockPlusL0Agree φ e

/-- Gerçek reduct senaryosu (cümleler): kağıdın lemmasının tam ifadesi,
L⁺-genişlemeleri üzerinde. -/
theorem mock_plus_reduct_invariance_sentences (φ : Formula) :
    (∀ e : Env MockImp MockCont MockEp, Realize mockPlusOne.reduct φ e) ↔
      (∀ e : Env MockImp MockCont MockEp, Realize mockPlusTwo.reduct φ e) :=
  reduct_invariance_sentences _ _ mockPlusL0Agree φ

/-- Reduct'lerde doğruluk: mock cümlesi iki reduct'te de doğrudur — L⁺
zıtlığına rağmen. -/
theorem mock_plus_reduct_truth :
    Realize mockPlusOne.reduct mockFormula mockEnv ∧
      Realize mockPlusTwo.reduct mockFormula mockEnv := by
  constructor <;>
    simp [mockFormula, mockEnv, mockPlusOne, mockPlusTwo, mockPlus,
      LPlusStructure.reduct, mockModel, Realize]

/-!
# Regresyon senaryoları: dosya içi pozitif örnekler + başarısız (fail-closed) örnekler

`mock_plus_reduct_invariance*` lemmaları için derleme-zamanı regresyon ağı:
pozitif `example`'lar lemmanın farklı formül şekillerinde (atomik, nicelikli,
yanlışlanan, cümle) çalıştığını; `¬`-teoremleri ise L⁺ farkının reduct'e
taşınamadığını — yani senaryonun boş olmadığını — sabitler. Bu bölümdeki
herhangi bir ispatın kırılması, L⁺/reduct kurgusundaki regresyon demektir:
dosya derlenmez (fail-closed).
-/

-- Reduct sabitleme (pin): iki genişlemenin reduct'ü de paylaşılan L₀-modelidir.
-- Biri L₀ parçasını asimetrik değiştirirse bu `rfl`'ler kırılır.
theorem mockPlus_reduct_shared_L0 :
    mockPlusOne.reduct = mockModelOne ∧ mockPlusTwo.reduct = mockModelOne := by
  constructor <;> rfl

-- Modeller gerçekten farklıdır (L⁺ yüzünden): eşitlik iddiası çürür.
theorem mockPlus_models_differ : ¬ mockPlusOne = mockPlusTwo := by
  intro h
  have hv := congrArg (fun M => M.Vivid .i0) h
  simp [mockPlusOne, mockPlusTwo, mockPlus] at hv

-- L⁺ korunmaz (başarısız örnekler): reduct-özdeşliği L⁺-doğruluğunu taşımaz.
-- Bu `¬`-teoremler derleniyorsa L⁺ ayrışması hâlâ gerçektir.
theorem mockPlus_vivid_not_preserved :
    ¬ (mockPlusOne.Vivid .i0 ↔ mockPlusTwo.Vivid .i0) := fun h =>
  mockPlus_disagree.2 (h.1 mockPlus_disagree.1)

theorem mockPlus_familiar_not_preserved :
    ¬ (mockPlusOne.Familiar .e0 .c0 ↔ mockPlusTwo.Familiar .e0 .c0) := fun h =>
  mockPlus_disagree_familiar.2 (h.1 mockPlus_disagree_familiar.1)

-- Atomik formülde anlaşma.
example : Realize mockPlusOne.reduct (.kat 0) mockEnv ↔
    Realize mockPlusTwo.reduct (.kat 0) mockEnv :=
  mock_plus_reduct_invariance _ _

-- Nicelikli formülde anlaşma (niceleyici durumları da regresyon ağında).
example : Realize mockPlusOne.reduct (.allEp 0 (.bel 0 1)) mockEnv ↔
    Realize mockPlusTwo.reduct (.allEp 0 (.bel 0 1)) mockEnv :=
  mock_plus_reduct_invariance _ _

-- Yanlışlanan formülde anlaşma: iki reduct'te de yanlış (`¬True` yönü).
example : ¬ Realize mockPlusOne.reduct (.not (.kat 0)) mockEnv ∧
    ¬ Realize mockPlusTwo.reduct (.not (.kat 0)) mockEnv := by
  constructor
  · intro hn
    exact hn (by simp [mockEnv, mockPlusOne, mockPlus,
      LPlusStructure.reduct, mockModel, Realize])
  · intro hn
    exact hn (by simp [mockEnv, mockPlusTwo, mockPlus,
      LPlusStructure.reduct, mockModel, Realize])

-- Cümle düzeyinde farklı bir örnek: niceleyicili cümlede anlaşma.
example : (∀ e : Env MockImp MockCont MockEp,
      Realize mockPlusOne.reduct (.allCont 0 (.rep 1 0)) e) ↔
    (∀ e : Env MockImp MockCont MockEp,
      Realize mockPlusTwo.reduct (.allCont 0 (.rep 1 0)) e) :=
  mock_plus_reduct_invariance_sentences _

/-!
# Karşılaştırma: iki farklı alan yorumu + nicelikli formül

Yukarıdaki senaryolar L₀-reduct'ü paylaşan modellerin hemfikir olduğunu
gösterdi. Bu bölüm ters yönü — hipotezin keskinliğini (sharpness) — sabitler:
L₀-alan yorumları farklıysa (`L0Agree` yoksa) aynı nicelikli L₀-formülü
modelleri ayırt eder. `mockModelThree` (`mockModel False`: dokuz yüklem de
boş) ile `mockModelOne` (`mockModel True`: dokuz yüklem de dolu)
karşılaştırılır; ayraç formüller niceliklidir (`exImp`/`allImp`), çünkü
açık-atomik ayrışma zaten tanım gereğidir — nicelikli durum, doyumun
ortam-güncelleme zinciri boyunca da farklılaştığını gösterir.
-/

-- Üçüncü mock: tüm L₀-alanları boş yorum (`mockModelOne`'un zıddı).
def mockModelThree : L0Structure MockImp MockCont MockEp :=
  mockModel False

-- `∃`-formülü ayraçtır: One'da tanık var (`.i0`), Three'da yok.
theorem mockModelOne_vs_Three_ex :
    Realize mockModelOne (.exImp 0 (.kat 0)) mockEnv ∧
      ¬ Realize mockModelThree (.exImp 0 (.kat 0)) mockEnv := by
  constructor
  · exact ⟨.i0, by simp [mockEnv, mockModelOne, mockModel, Realize, update]⟩
  · intro hn
    rcases hn with ⟨x, hx⟩
    simp [mockEnv, mockModelThree, mockModel, Realize, update] at hx

-- `∀`-formülün ikizi: One'da her atama tutar, Three'da `.i0` çürütür.
theorem mockModelOne_vs_Three_all :
    Realize mockModelOne (.allImp 0 (.kat 0)) mockEnv ∧
      ¬ Realize mockModelThree (.allImp 0 (.kat 0)) mockEnv := by
  constructor
  · intro x
    simp [mockEnv, mockModelOne, mockModel, Realize, update]
  · intro hn
    have h0 := hn .i0
    simp [mockEnv, mockModelThree, mockModel, Realize, update] at h0

-- Üçlü karşılaştırma: aynı nicelikli formül L⁺-çiftinde hemfikir
-- (`mock_plus_reduct_invariance`'ın somut yüzü), L₀-farklı modelde ayrışır.
example : Realize mockPlusOne.reduct (.exImp 0 (.kat 0)) mockEnv ∧
    Realize mockPlusTwo.reduct (.exImp 0 (.kat 0)) mockEnv ∧
      ¬ Realize mockModelThree (.exImp 0 (.kat 0)) mockEnv := by
  refine ⟨⟨.i0, by simp [mockEnv, mockPlusOne, mockPlus,
      LPlusStructure.reduct, mockModel, Realize, update]⟩,
    ⟨.i0, by simp [mockEnv, mockPlusTwo, mockPlus,
      LPlusStructure.reduct, mockModel, Realize, update]⟩, ?_⟩
  intro hn
  rcases hn with ⟨x, hx⟩
  simp [mockEnv, mockModelThree, mockModel, Realize, update] at hx

#check reduct_invariance
#check reduct_invariance_sentences
#check mockL0Agree
#check mock_reduct_invariance
#check mock_reduct_invariance_truth
#check LPlusStructure.reduct
#check mockPlusL0Agree
#check mockPlus_disagree
#check mockPlus_disagree_familiar
#check mock_plus_reduct_invariance
#check mock_plus_reduct_invariance_sentences
#check mock_plus_reduct_truth
#check mockPlus_reduct_shared_L0
#check mockPlus_models_differ
#check mockPlus_vivid_not_preserved
#check mockPlus_familiar_not_preserved
#check mockModelOne_vs_Three_ex
#check mockModelOne_vs_Three_all
