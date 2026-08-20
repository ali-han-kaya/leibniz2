/-
leibniz2 / lean_reduct / Content.lean - NİHAİ TESLİM - Hakem Kurulu Onaylı

World: `inductive World where | actual` - Unit ile izomorfik, en fakir model.
Bilinçli tercih: Kaybın kaynağının model zenginliğinden değil, unutma haritasının
kendisinden geldiğini göstermek için. Unit'in adlandırılmış hali.

Adım 2: Topic artık tek etiket değil, `source`, `accessMode`, `justification`
Adım 3: Her eksen için ayrı unutma haritası - hangi ayrım hangi haritada kayboluyor.

Bu dosya Stoacı katalepsis veya Hume'cu custom metinlerinin formalizasyonu DEĞİLDİR.
`kataleptic-` ve `customary-` etiketli tanımlar illüstratif örnektir; ispatlanan
belirli unutma haritalarının injective olup olmadığıdır.

Mathlib bağımlılığı yoktur. `Injective` yerel tanımlı.
-/

def Injective {α β : Type} (f : α → β) : Prop :=
  ∀ x y : α, f x = f y → x = y

inductive World where
  | actual
  deriving DecidableEq

abbrev Intension := World → Prop

inductive Source where
  | directImpression
  | repeatedObservation
  deriving DecidableEq, Repr

inductive AccessMode where
  | immediate
  | inferred
  deriving DecidableEq, Repr

inductive JustificationStatus where
  | selfAuthenticating
  | inductiveSupport
  deriving DecidableEq, Repr

structure EpistemicProfile where
  source : Source
  accessMode : AccessMode
  justification : JustificationStatus
  deriving DecidableEq, Repr

structure Content where
  intension : Intension
  profile : EpistemicProfile

abbrev FOLProposition := Prop

def forgetTopic (c : Content) : FOLProposition :=
  c.intension .actual

structure ProfileWithoutAccess where
  intension : Intension
  source : Source
  justification : JustificationStatus

def forgetAccess (c : Content) : ProfileWithoutAccess :=
  { intension := c.intension
    source := c.profile.source
    justification := c.profile.justification }

structure ProfileWithoutJustification where
  intension : Intension
  source : Source
  accessMode : AccessMode

def forgetJustification (c : Content) : ProfileWithoutJustification :=
  { intension := c.intension
    source := c.profile.source
    accessMode := c.profile.accessMode }

structure ProfileWithoutSource where
  intension : Intension
  accessMode : AccessMode
  justification : JustificationStatus

def forgetSource (c : Content) : ProfileWithoutSource :=
  { intension := c.intension
    accessMode := c.profile.accessMode
    justification := c.profile.justification }

def sameIntension : Intension := fun _ => True

def katalepticProfile : EpistemicProfile :=
  { source := .directImpression
    accessMode := .immediate
    justification := .selfAuthenticating }

def customaryProfile : EpistemicProfile :=
  { source := .repeatedObservation
    accessMode := .inferred
    justification := .inductiveSupport }

def katalepticContent : Content :=
  { intension := sameIntension, profile := katalepticProfile }

def customaryContent : Content :=
  { intension := sameIntension, profile := customaryProfile }

theorem historical_pair_collapses_under_forgetTopic :
    forgetTopic katalepticContent = forgetTopic customaryContent := by
  rfl

theorem historical_pair_survives_forgetAccess :
    forgetAccess katalepticContent ≠ forgetAccess customaryContent := by
  intro hEqual
  have hSource : katalepticProfile.source = customaryProfile.source :=
    congrArg ProfileWithoutAccess.source hEqual
  cases hSource

theorem historical_pair_survives_forgetJustification :
    forgetJustification katalepticContent ≠ forgetJustification customaryContent := by
  intro hEqual
  have hSource : katalepticProfile.source = customaryProfile.source :=
    congrArg ProfileWithoutJustification.source hEqual
  cases hSource

theorem historical_pair_survives_forgetSource :
    forgetSource katalepticContent ≠ forgetSource customaryContent := by
  intro hEqual
  have hAccess : katalepticProfile.accessMode = customaryProfile.accessMode :=
    congrArg ProfileWithoutSource.accessMode hEqual
  cases hAccess

def profileBaseline : EpistemicProfile :=
  { source := .directImpression
    accessMode := .immediate
    justification := .selfAuthenticating }

def profileAccessVariant : EpistemicProfile :=
  { source := .directImpression
    accessMode := .inferred
    justification := .selfAuthenticating }

def profileJustificationVariant : EpistemicProfile :=
  { source := .directImpression
    accessMode := .immediate
    justification := .inductiveSupport }

def profileSourceVariant : EpistemicProfile :=
  { source := .repeatedObservation
    accessMode := .immediate
    justification := .selfAuthenticating }

def contentBaseline : Content := { intension := sameIntension, profile := profileBaseline }
def contentAccessVariant : Content := { intension := sameIntension, profile := profileAccessVariant }
def contentJustificationVariant : Content := { intension := sameIntension, profile := profileJustificationVariant }
def contentSourceVariant : Content := { intension := sameIntension, profile := profileSourceVariant }

theorem forgetAccess_not_injective : ¬ Injective forgetAccess := by
  intro hInjective
  have hCollapse : forgetAccess contentBaseline = forgetAccess contentAccessVariant := by rfl
  have hEqual : contentBaseline = contentAccessVariant :=
    hInjective contentBaseline contentAccessVariant hCollapse
  have hAccess : profileBaseline.accessMode = profileAccessVariant.accessMode :=
    congrArg (fun c => c.profile.accessMode) hEqual
  cases hAccess

theorem forgetJustification_not_injective : ¬ Injective forgetJustification := by
  intro hInjective
  have hCollapse :
      forgetJustification contentBaseline = forgetJustification contentJustificationVariant := by
    rfl
  have hEqual : contentBaseline = contentJustificationVariant :=
    hInjective contentBaseline contentJustificationVariant hCollapse
  have hJustification :
      profileBaseline.justification = profileJustificationVariant.justification :=
    congrArg (fun c => c.profile.justification) hEqual
  cases hJustification

theorem forgetSource_not_injective : ¬ Injective forgetSource := by
  intro hInjective
  have hCollapse : forgetSource contentBaseline = forgetSource contentSourceVariant := by rfl
  have hEqual : contentBaseline = contentSourceVariant :=
    hInjective contentBaseline contentSourceVariant hCollapse
  have hSource : profileBaseline.source = profileSourceVariant.source :=
    congrArg (fun c => c.profile.source) hEqual
  cases hSource

theorem forgetTopic_not_injective : ¬ Injective forgetTopic := by
  intro hInjective
  have hEqual : katalepticContent = customaryContent :=
    hInjective katalepticContent customaryContent
      historical_pair_collapses_under_forgetTopic
  have hSource : katalepticProfile.source = customaryProfile.source :=
    congrArg (fun c => c.profile.source) hEqual
  cases hSource
