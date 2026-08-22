# leibniz2 / coq_reduct - Metodolojik Kayıt - NİHAİ TESLİM

## TR - Ne Bu?

lean_reduct'in Coq analoğu. Bu dosya merkez tezi **ispatlamaz**, minimal
makine-kontrollü bir model üzerinden **illüstratif olarak gösterir**: Bazı
epistemik ayrımlar ekstansiyonel hedef dile giden unutma haritası altında
ayırt ediciliğini kaybedebilir.

**Model Fakirliği Notu:** `World := Unit` ifadesi kodda `Inductive World :
Type := | actual` olarak uygulanmıştır. Bu Unit ile izomorfik en fakir dünya
modelidir. Bilinçli tercih: Kaybın model zenginliğinden değil, `forget`
haritasının kendisinden kaynaklandığını göstermek - daha güçlü iddia.

### Teorem Tablosu

| # | Teorem | Ne İspatlar | Yöntem |
|---|--------|-------------|--------|
| 1 | historical_pair_collapses_under_forgetTopic | iki illüstratif içerik tam unutma altında özdeşleşir | reflexivity |
| 2 | historical_pair_survives_forgetAccess | üç eksende farklı olduğu için tek eksen unutması ayrımı silmez | f_equal+discriminate |
| 3 | historical_pair_survives_forgetJustification | aynı | f_equal+discriminate |
| 4 | historical_pair_survives_forgetSource | aynı | f_equal+discriminate |
| 5 | forgetAccess_not_injective | access haritası injective değil | injectivity+discriminate |
| 6 | forgetJustification_not_injective | justification haritası injective değil | injectivity+discriminate |
| 7 | forgetSource_not_injective | source haritası injective değil | injectivity+discriminate |
| 8 | forgetTopic_not_injective | tam unutma injective değil | injectivity+discriminate |

### Ne İspatlanıyor / İspatlanmıyor

| İspatlanan | İspatlanMAyan |
|---|---|
| Belirli 4 haritanın injective olmadığı (temsil kaybı) | Stoa katalepsis / Hume custom doğru yorumu |
| Kaybın World zenginliğinden değil haritadan geldiği | Herhangi metafizik/dini önerme |
| Minimal çiftlerin her eksende ayrık örnek verdiği | Modelin tarihsel metinlerle örtüştüğü (doğrulanmamış hermeneutik varsayım) |

**İllüstratif Not:** `katalepticProfile`, `customaryProfile` birer kod
etiketidir, tarihsel formalizasyon değildir.

**Etik Not - Hz. Muhammed Ahlakına Uygun Şeffaflık:** Sıdk (doğruyu eğmeme),
emanet (ispatlanmayanı ispatlandı dememe), zulümden kaçınma (kavramlara atıfta
adil). Tedlis, abartı, dini/metafizik istismar yoktur. Fail-closed:
ispatlanmayan şey ispatlandı denmemiştir.

## EN

Coq analog of lean_reduct. Illustrative, not formalization of Stoa/Hume.
World is poorest model (inductive actual ≃ Unit). 8 theorems machine-checked
by coqtop -compile, no stdlib dependency beyond the prelude, Injective defined
locally, proved by reflexivity / f_equal+discriminate. Representational-loss
result, not existence proof.

## Build (fail-closed, K19)

```bash
cd _calisma/coq_reduct
coqtop --version            # "The Coq Proof Assistant, version 8.18.x" olmalı
coqtop -compile Content.v   # 8 teorem PASS; .vo geçici dizine yazılır
```

Doğrulama kapıları (verify_delivery.py K19, --coq-proof):
1. `coq-version` dosyası (`8.18`) ile `coqtop --version` major.minor uyumu —
   yanlış sürüm derleme yerine kapıda yakalanır (fail-closed).
2. `admit` / `Admitted` / top-level `Axiom` / `Parameter` taraması — proof gap
   varsa P0 (fail-closed).
3. `coqtop -compile` — derleme başarısızsa P0.

coqtop kurulu değilse P0 (fail-closed). `--full`'a DAHİL DEĞİLDİR (coqtop
kurulu olmayan ortamlar için); `--coq-proof` ile açıkça koşulur.
