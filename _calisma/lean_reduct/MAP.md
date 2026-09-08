# Z3 <-> Lean Eşleşmesi

Z3: forget_all <-> Lean: forgetTopic (tam unutma)
Z3: forget_access <-> Lean: forgetAccess
Z3: forget_justification <-> Lean: forgetJustification
Z3: forget_source <-> Lean: forgetSource

İnvariant: 8 teoremin Z3'teki karşı-örneği ile Lean'deki rfl/cases ispatı aynı çökmeyi gösterir.

Diverge olmaması için bu dosya korunmalı.

## STATEMENT CONTRACT

historical_pair_collapses_under_forgetTopic : forgetTopic katalepticContent = forgetTopic customaryContent
historical_pair_survives_forgetAccess : forgetAccess katalepticContent ≠ forgetAccess customaryContent
historical_pair_survives_forgetJustification : forgetJustification katalepticContent ≠ forgetJustification customaryContent
historical_pair_survives_forgetSource : forgetSource katalepticContent ≠ forgetSource customaryContent
forgetAccess_not_injective : ¬ Injective forgetAccess
forgetJustification_not_injective : ¬ Injective forgetJustification
forgetSource_not_injective : ¬ Injective forgetSource
forgetTopic_not_injective : ¬ Injective forgetTopic
