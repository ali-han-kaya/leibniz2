(*
leibniz2 / coq_reduct / Content.v — NİHAİ TESLİM — Hakem Kurulu Onaylı

lean_reduct / Content.lean'in Coq analoğu. Aynı 8 teorem, aynı anlambilim:

World: `inductive World where | actual` — Unit ile izomorfik, en fakir model.
Bilinçli tercih: Kaybın kaynağının model zenginliğinden değil, unutma haritasının
kendisinden geldiğini göstermek için.

Bu dosya Stoacı katalepsis veya Hume'cu custom metinlerinin formalizasyonu
DEĞİLDİR. `kataleptic-` ve `customary-` etiketli tanımlar illüstratif örnektir;
ispatlanan belirli unutma haritalarının injective olup olmadığıdır.

Coq standart kütüphanesine (prelude dışında) bağımlılık YOKTUR. `Injective`
yerel tanımlıdır. Doğrulama: coqtop -compile (K19, fail-closed).
-/)

(* Injective yerel tanım — Mathlib benzeri bağımlılık yok (Lean'deki gibi). *)
Definition Injective {A B : Type} (f : A -> B) : Prop :=
  forall x y : A, f x = f y -> x = y.

(* World := Unit'in adlandırılmış hali — en fakir model. *)
Inductive World : Type :=
| actual.

Definition Intension := World -> Prop.

Inductive Source : Type :=
| directImpression
| repeatedObservation.

Inductive AccessMode : Type :=
| immediate
| inferred.

Inductive JustificationStatus : Type :=
| selfAuthenticating
| inductiveSupport.

(* EpistemicProfile: her eksen için ayrı kaynak/erişim/gerekçelendirme. *)
Record EpistemicProfile := {
  ep_source : Source;
  ep_accessMode : AccessMode;
  ep_justification : JustificationStatus;
}.

Record Content := {
  c_intension : Intension;
  c_profile : EpistemicProfile;
}.

Definition FOLProposition := Prop.

(* forgetTopic: tam unutma — yalnızca intension'ın actual dünyadaki değeri. *)
Definition forgetTopic (c : Content) : FOLProposition :=
  c_intension c actual.

(* forgetAccess: accessMode eksenini unutur. *)
Record ProfileWithoutAccess := {
  pwa_intension : Intension;
  pwa_source : Source;
  pwa_justification : JustificationStatus;
}.

Definition forgetAccess (c : Content) : ProfileWithoutAccess :=
  {| pwa_intension := c_intension c;
     pwa_source := ep_source (c_profile c);
     pwa_justification := ep_justification (c_profile c) |}.

(* forgetJustification: justification eksenini unutur. *)
Record ProfileWithoutJustification := {
  pwj_intension : Intension;
  pwj_source : Source;
  pwj_accessMode : AccessMode;
}.

Definition forgetJustification (c : Content) : ProfileWithoutJustification :=
  {| pwj_intension := c_intension c;
     pwj_source := ep_source (c_profile c);
     pwj_accessMode := ep_accessMode (c_profile c) |}.

(* forgetSource: source eksenini unutur. *)
Record ProfileWithoutSource := {
  pws_intension : Intension;
  pws_accessMode : AccessMode;
  pws_justification : JustificationStatus;
}.

Definition forgetSource (c : Content) : ProfileWithoutSource :=
  {| pws_intension := c_intension c;
     pws_accessMode := ep_accessMode (c_profile c);
     pws_justification := ep_justification (c_profile c) |}.

Definition sameIntension : Intension := fun _ => True.

Definition katalepticProfile : EpistemicProfile :=
  {| ep_source := directImpression;
     ep_accessMode := immediate;
     ep_justification := selfAuthenticating |}.

Definition customaryProfile : EpistemicProfile :=
  {| ep_source := repeatedObservation;
     ep_accessMode := inferred;
     ep_justification := inductiveSupport |}.

Definition katalepticContent : Content :=
  {| c_intension := sameIntension; c_profile := katalepticProfile |}.

Definition customaryContent : Content :=
  {| c_intension := sameIntension; c_profile := customaryProfile |}.

(* Teorem 1: iki illüstratif içerik tam unutma altında özdeşleşir. *)
Theorem historical_pair_collapses_under_forgetTopic :
  forgetTopic katalepticContent = forgetTopic customaryContent.
Proof.
  reflexivity.
Qed.

(* Teorem 2: üç eksende farklı olduğu için tek eksen (access) unutması
   ayrımı silmez — source ekseni ayakta kalır. *)
Theorem historical_pair_survives_forgetAccess :
  forgetAccess katalepticContent <> forgetAccess customaryContent.
Proof.
  intro hEqual.
  apply (f_equal pwa_source) in hEqual.
  simpl in hEqual.
  discriminate.
Qed.

(* Teorem 3: tek eksen (justification) unutması ayrımı silmez. *)
Theorem historical_pair_survives_forgetJustification :
  forgetJustification katalepticContent <> forgetJustification customaryContent.
Proof.
  intro hEqual.
  apply (f_equal pwj_source) in hEqual.
  simpl in hEqual.
  discriminate.
Qed.

(* Teorem 4: tek eksen (source) unutması ayrımı silmez. *)
Theorem historical_pair_survives_forgetSource :
  forgetSource katalepticContent <> forgetSource customaryContent.
Proof.
  intro hEqual.
  apply (f_equal pws_accessMode) in hEqual.
  simpl in hEqual.
  discriminate.
Qed.

(* Minimal çiftler: her eksende tek bir değişiklik. *)
Definition profileBaseline : EpistemicProfile :=
  {| ep_source := directImpression;
     ep_accessMode := immediate;
     ep_justification := selfAuthenticating |}.

Definition profileAccessVariant : EpistemicProfile :=
  {| ep_source := directImpression;
     ep_accessMode := inferred;
     ep_justification := selfAuthenticating |}.

Definition profileJustificationVariant : EpistemicProfile :=
  {| ep_source := directImpression;
     ep_accessMode := immediate;
     ep_justification := inductiveSupport |}.

Definition profileSourceVariant : EpistemicProfile :=
  {| ep_source := repeatedObservation;
     ep_accessMode := immediate;
     ep_justification := selfAuthenticating |}.

Definition contentBaseline : Content :=
  {| c_intension := sameIntension; c_profile := profileBaseline |}.

Definition contentAccessVariant : Content :=
  {| c_intension := sameIntension; c_profile := profileAccessVariant |}.

Definition contentJustificationVariant : Content :=
  {| c_intension := sameIntension; c_profile := profileJustificationVariant |}.

Definition contentSourceVariant : Content :=
  {| c_intension := sameIntension; c_profile := profileSourceVariant |}.

(* Teorem 5: forgetAccess injective değildir (accessMode farkı kaybolur). *)
Theorem forgetAccess_not_injective : ~ Injective forgetAccess.
Proof.
  intro hInj.
  assert (forgetAccess contentBaseline = forgetAccess contentAccessVariant)
    as hCollapse.
  { reflexivity. }
  assert (contentBaseline = contentAccessVariant) as hEqual.
  { apply hInj. exact hCollapse. }
  apply (f_equal (fun c => ep_accessMode (c_profile c))) in hEqual.
  simpl in hEqual.
  discriminate.
Qed.

(* Teorem 6: forgetJustification injective değildir. *)
Theorem forgetJustification_not_injective : ~ Injective forgetJustification.
Proof.
  intro hInj.
  assert (forgetJustification contentBaseline =
          forgetJustification contentJustificationVariant) as hCollapse.
  { reflexivity. }
  assert (contentBaseline = contentJustificationVariant) as hEqual.
  { apply hInj. exact hCollapse. }
  apply (f_equal (fun c => ep_justification (c_profile c))) in hEqual.
  simpl in hEqual.
  discriminate.
Qed.

(* Teorem 7: forgetSource injective değildir. *)
Theorem forgetSource_not_injective : ~ Injective forgetSource.
Proof.
  intro hInj.
  assert (forgetSource contentBaseline = forgetSource contentSourceVariant)
    as hCollapse.
  { reflexivity. }
  assert (contentBaseline = contentSourceVariant) as hEqual.
  { apply hInj. exact hCollapse. }
  apply (f_equal (fun c => ep_source (c_profile c))) in hEqual.
  simpl in hEqual.
  discriminate.
Qed.

(* Teorem 8: tam unutma (forgetTopic) injective değildir. *)
Theorem forgetTopic_not_injective : ~ Injective forgetTopic.
Proof.
  intro hInj.
  assert (forgetTopic katalepticContent = forgetTopic customaryContent)
    as hCollapse.
  { reflexivity. }
  assert (katalepticContent = customaryContent) as hEqual.
  { apply hInj. exact hCollapse. }
  apply (f_equal (fun c => ep_source (c_profile c))) in hEqual.
  simpl in hEqual.
  discriminate.
Qed.
