# Z3 <-> Coq Eşleşmesi

Z3: forget_all <-> Coq: forgetTopic (tam unutma)
Z3: forget_access <-> Coq: forgetAccess
Z3: forget_justification <-> Coq: forgetJustification
Z3: forget_source <-> Coq: forgetSource

İnvariant: 8 teoremin Z3'teki karşı-örneği ile Coq'daki rfl/discriminate ispatı
aynı çökmeyi gösterir (Coq: reflexivity / f_equal+simpl+discriminate).

Diverge olmaması için bu dosya korunmalı.
