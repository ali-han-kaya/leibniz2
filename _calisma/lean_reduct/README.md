# leibniz2 / lean_reduct - Metodolojik Kayıt - NİHAİ TESLİM

## TR - Ne Bu?

Bu dosya merkez tezi **ispatlamaz**, minimal makine-kontrollü bir model üzerinden **illüstratif olarak gösterir**: Bazı epistemik ayrımlar ekstansiyonel hedef dile giden unutma haritası altında ayırt ediciliğini kaybedebilir.

**Model Fakirliği Notu:** `World := Unit` ifadesi kodda `inductive World where | actual` olarak uygulanmıştır. Bu Unit ile izomorfik en fakir dünya modelidir. Bilinçli tercih: Kaybın model zenginliğinden değil, `forget` haritasının kendisinden kaynaklandığını göstermek - daha güçlü iddia.

### Teorem Tablosu

| # | Teorem | Ne İspatlar | Yöntem |
|---|--------|-------------|--------|
| 1 | historical_pair_collapses_under_forgetTopic | iki illüstratif içerik tam unutma altında özdeşleşir | rfl |
| 2 | historical_pair_survives_forgetAccess | üç eksende farklı olduğu için tek eksen unutması ayrımı silmez | cases |
| 3 | historical_pair_survives_forgetJustification | aynı | cases |
| 4 | historical_pair_survives_forgetSource | aynı | cases |
| 5 | forgetAccess_not_injective | access haritası injective değil | cases+congrArg |
| 6 | forgetJustification_not_injective | justification haritası injective değil | cases+congrArg |
| 7 | forgetSource_not_injective | source haritası injective değil | cases+congrArg |
| 8 | forgetTopic_not_injective | tam unutma injective değil | cases+congrArg |

### Ne İspatlanıyor / İspatlanmıyor

| İspatlanan | İspatlanMAyan |
|---|---|
| Belirli 4 haritanın injective olmadığı (temsil kaybı) | Stoa katalepsis / Hume custom doğru yorumu |
| Kaybın World zenginliğinden değil haritadan geldiği | Herhangi metafizik/dini önerme |
| Minimal çiftlerin her eksende ayrık örnek verdiği | Modelin tarihsel metinlerle örtüştüğü (doğrulanmamış hermeneutik varsayım) |

**İllüstratif Not:** `katalepticProfile`, `customaryProfile` birer kod etiketidir, tarihsel formalizasyon değildir.

**Etik Not - Hz. Muhammed Ahlakına Uygun Şeffaflık:** Sıdk (doğruyu eğmeme), emanet (ispatlanmayanı ispatlandı dememe), zulümden kaçınma (kavramlara atıfta adil). Tedlis, abartı, dini/metafizik istismar yoktur. Fail-closed: ispatlanmayan şey ispatlandı denmemiştir.

## EN

Same: illustrative, not formalization of Stoa/Hume. World is poorest model (inductive actual ≃ Unit). 8 theorems machine-checked, Mathlib-free, Injective defined locally, proved by cases. Representational-loss result, not existence proof.

## Build

```bash
cd _calisma/lean_reduct
rm -rf .lake lake-manifest.json
lake build --wfail
```
Expected <5s after toolchain. Toolchain: leanprover/lean4:v4.14.0
