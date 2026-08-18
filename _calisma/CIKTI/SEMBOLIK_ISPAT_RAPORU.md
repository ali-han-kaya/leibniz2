# Sembolik İspat Raporu — Stoic-Hume V5 Formal Çekirdek

**Araç:** Z3 (z3-solver 5.1.0.0, Python 3.9.6, proje-içi venv `_calisma/.venv_z3`)
**Betik:** `_calisma/CIKTI/symbolic_proof_z3.py` — çalıştırıldı, `exit=0` (tümü PASS)
**Tarih:** 2026-08-17

Bu rapor, `core_section.tex` §2'deki biçimsel çekirdeğin teoremlerini
**sonlu Boolean parçalanışının (16 satır) ötesine** taşır: Z3 ile iddialar
**tüm yapılar** (her domain, her yüklem yorumu) üzerinden test edilmiştir.
Aşağıdaki her `UNSAT`/`SAT` değeri betiğin gerçek çıktısıdır, tahmin yoktur.

---

## 1. Yöntem ve sağlamlık (soundness) koşulları

| Parça | Sınıf | Z3 sonucu ne anlama gelir |
|---|---|---|
| L₀ (Prop 1, bridge, karakterizasyon) | ∃\*∀\*, fonksiyon sembolü yok → **Bernays–Schönfinkel** | Karar verilebilir sınıf. `UNSAT` = **gerçek geçerlilik ispatı** (buluşsal değil). `SAT` = sesli (sound) karşı-model. |
| L⁺ (Prop 2, `custFact`/`nonjustFact` fonksiyonlu) | fonksiyonlu fragment | Yalnızca `SAT` (tanık model) istendi; SAT sonucu her zaman seslidir. |

- **UNSAT** satırları: `¬formül` doyurulamaz → `formül` geçerli → gerektirme **ispatlandı**.
- **SAT** satırları: Z3 somut bir model (tanık/karşı-model) döndürür → gerektirmenin **reddi** ispatlandı.
- `reduct-invariance` lemması (tüm L₀-formülleri üzerinde) sözdizimi/semantik
  hakkında ikinci-dereceden bir önermedir; Z3 bunu değil, onun **örneklerini**
  ve model-çifti tanığını doğrular. Lemma'nın genel kanıtı kağıttaki yapısal
  tümevarım olarak kalır (doğru olarak).

---

## 2. Sonuç tablosu (10 kontrol — gerçek çıktı)

| ID | İddia | Beklenen | Alınan | Sonuç |
|---|---|---|---|---|
| P1-a | `T₂ ∧ M₀ ⊨ T₁` | UNSAT | UNSAT | ✅ ispatlandı |
| P1-b | `T₁ ∧ M₀ ⊭ T₂` (karşı-model var) | SAT | SAT | ✅ karşı-model |
| P2 | `T₁ ∧ B₀ ⊨ T₂` (M₀ üzerinde, bridge collapse) | UNSAT | UNSAT | ✅ ispatlandı |
| P3-a | çift düzeyinde `(T₁∧¬T₂) → ⋆` | UNSAT | UNSAT | ✅ ispatlandı |
| P3-b | çift düzeyinde `⋆ → (T₁∧¬T₂)` | UNSAT | UNSAT | ✅ ispatlandı |
| P4-a | global `(T₁∧M₀∧¬T₂) → ⋆` | UNSAT | UNSAT | ✅ ispatlandı |
| P4-b | global `⋆ → (T₁∧M₀∧¬T₂)` | **SAT** | SAT | ⚠️ iff'in ters yönü **geçersiz** |
| P4-c | `⋆ ∧ ¬T₁` doyurulabilir | SAT | SAT | ⚠️ ⋆, T₁'i bile ima etmez |
| P5 | özdeş L₀-reduct'li, G'si farklı iki admissibl model | SAT | SAT | ✅ tanık bulundu |
| P5-note | `Just=true` taban modeli O₃ yüzünden admissibl değil | UNSAT | UNSAT | ✅ spec §9 notu doğru |

---

## 3. Doğrulanan teoremler (finite-check'in ötesinde, genel kanıt)

1. **Proposition 1 — birinci yön.** `T₂ ∧ M₀ ⊨ T₁`, tüm yapılar üzerinde
   geçerlidir (P1-a UNSAT).
2. **Proposition 1 — ikinci yön.** `T₁ ∧ M₀ ⊭ T₂`; Z3'ün döndürdüğü
   karşı-model kağıttaki **tek karşı-model** `(Causal=F, Custom=T, Bel=T,
   Just=T)` ile birebir örtüşür:
   `Custom(b0)=T, Bel(b0,c0)=T, Just(b0,c0)=T, Causal(b0,c0)=F`.
3. **Bridge collapse.** `T₁ ∧ B₀ ⊨ T₂` (M₀ üzerinde) geçerlidir (P2 UNSAT).
4. **Proposition 2 — implicit definability failure.** `Custom(b0)=T`,
   `Just(b0,c0)=F` tabanında iki admissibl model inşa edildi:
   - `atom1 = G₁(custFact(b0), nonjustFact(b0,c0)) = True`
   - `atom2 = G₂(custFact(b0), nonjustFact(b0,c0)) = False`
   - ortak L₀-reduct (paylaşılan yüklemler) ve `M₀a=M₀b=O₁..O₃=True` her iki
     modelde doğrulandı. G atomu L₀ üzerinde **implicit olarak tanımlanamaz**.
5. **O₃ disiplini (spec §9 notu).** `Just=true` taban modelinde `G₁` atomu
   doyurulamaz (UNSAT): `O₂` gereği `Obtains(nonjustFact)=False` olur, `O₃`
   `G₁`'i engeller. Spec'teki "Just=true O₃'ü ihlal eder" notu doğrudur.

---

## 4. BULGU — global "iff" karakterizasyonu tek yönlüdür (finite-check'in göremediği)

`core_section.tex` (bridge-collapse kanıtı) ve `L0_Lplus_spec.md` §6 şunu iddia
eder:

> "over M₀, a model separates T₁ from T₂ **if and only if** M ⊨ ⋆"
> `M ⊨ T₁ ∧ M₀ ∧ ¬T₂  ⟺  M ⊨ ⋆`

Z3 bu iki yönü ayrı ayrı test etti:

- **(→) DOĞRU** (P4-a UNSAT): `T₁ ∧ M₀ ∧ ¬T₂ → ⋆` geçerlidir.
- **(←) YANLIŞ** (P4-b SAT): `⋆ → (T₁ ∧ M₀ ∧ ¬T₂)` geçerli **değildir**.
  Z3'ün karşı-modeli: `M₀a=True, M₀b=True, ⋆=True, ¬T₂=True, T₁=False`.
  Yani ⋆ doğruyken T₁ yanlış olabilir — ⋆ bir çiftte ayrışmayı garantilerken,
  başka bir çiftte `Causal∧Just` yoluyla T₁'i bozabilir.
- **Daha keskin** (P4-c SAT): `⋆ ∧ ¬T₁` doyurulabilir. ⋆, T₁'i **bile**
  ima etmez (iki ayrı `(b,c)` çifti yeterli).

**Neden finite-check göremedi:** 16 satırlık tablo **tek bir (b,c) çifti**
üzerinde kuruludur; orada T₁ yalnızca o çiftte değerlendirilir ve "iff" gerçekten
tutar (P3-a, P3-b ikisi de UNSAT). Global iddia ise **çok-çiftli modeller**
hakkındadır; kağıdın kanıtındaki *"the claim follows by vacuous quantification
over the remaining pairs"* cümlesi tam burada kayar: "remaining pairs" üzerindeki
niceleme T₁ için boş değildir.

### Doğru önermeler (Z3 ile kanıtlı)

1. **Çift düzeyinde iff (kağıdın fiilen kanıtladığı şey):**
   sabit bir `(b,c)` çiftinde `(T₁∧¬T₂) ⟺ ⋆` — P3-a ve P3-b UNSAT.
2. **Global tek yön:**
   `M ⊨ (T₁ ∧ M₀ ∧ ¬T₂) → M ⊨ ⋆` — P4-a UNSAT.
3. **Global doğru iff (önerilen düzeltme):**
   `M ⊨ (T₁ ∧ M₀ ∧ ¬T₂) ⟺ M ⊨ (T₁ ∧ M₀ ∧ ⋆)`.
   Yani ayrışma tam olarak "⋆ **ve** T₁" ile yakalanır; T₁ bileşeni kağıt
   metninde düşmüştür.

---

## 5. Düzeltme (UYGULANDI — 2026-08-17, V5g)

`core_section.tex` bridge-collapse kanıtındaki cümle:

> "...a model separates T₁ from T₂ if and only if M ⊨ ⋆"

şöyle değiştirilmeli (iki seçenek, ikisi de Z3 ile kanıtlı):

- **(a) çift düzeyine indir:** "at a fixed pair (b,c), T₁ and T₂ differ
  (T₁ true at the pair, T₂ false at the pair) **if and only if** ⋆ holds at
  that pair"; ve global iddia için yalnızca `(→)` yönünü ifade et.
- **(b) global iff'i düzelt:** "over M₀, M ⊨ T₁ ∧ ¬T₂ **if and only if**
  M ⊨ T₁ ∧ ⋆".

Aynı satır `L0_Lplus_spec.md` §6'daki `⟺` ifadesi de düzeltildi. Uygulanan
sürüm: çift düzeyinde iff + global tek yön + global doğru eşdeğerlik
`T₁∧M₀∧¬T₂ ⟺ T₁∧M₀∧(⋆)` (Z3 P4-d/P4-e UNSAT ile yeniden doğrulandı).
`core_section.tex` "vacuous quantification" cümlesi kaldırıldı, kanıt iki yönü
ayrı ayrı gösteriyor. PDF `tectonic 0.17.0` ile yeniden derlendi (33 sayfa,
214 755 B); MANIFEST + checksum + zip zinciri yeniden üretildi;
`verify_delivery.py` PASS (P0=0, P1=0).

Bu düzeltme makalenin tezini **zayıflatmaz** — aksine, iff'in doğru biçimini
kaydederek sonucu güçlendirir ve hakemin yakalayabileceği bir skop hatasını
giderir.

---

## 6. Sınırlar (şeffaflık)

- **Lean kullanılmadı.** Lean, biçimsel semantiği ve bu model-kuramsal
  sonuçları tam biçimselleştirmek için ayrı ve ağır bir projedir (elan/lake
  + kütüphane + elle ispat). Buradaki gerektirme düzeyindeki iddialar için
  doğru araç Z3'tür; UNSAT sonuçları L₀ fragmanında (Bernays–Schönfinkel)
  karar-verilebilir olduğundan birer kanıttır.
- Z3, `reduct-invariance` lemmasının *tümevarımsal* genel kanıtını üretmez;
  onun örneklerini ve model-çifti tanığını doğrular (rapor §1).
- Bu ispat L₀/L⁺ **resmî çekirdeği** hakkındadır; tarihsel okuma iddialarını
  değil, biçimsel gerektirmeleri kapsar.
- Çıktı dosyaları: `_calisma/CIKTI/symbolic_proof_z3.py` + bu rapor.
  Venv `_calisma/.venv_z3` proje içindedir, global kurulum yapılmadı.
- **V5l/V5m determinism notu (2026-08-18):** tectonic/qpdf byte-deterministik
  olmadığından PDF ve zip'lerin byte-düzeyinde yeniden üretilebilirliği bilinen
  bir sınırdır (MANIFEST V5k/V5l; deney `qpdf_determinism_experiment.py` ile
  yeniden üretilebilir). Bu rapordaki Z3 sonuçları (UNSAT/SAT) biçimsel İÇERİK
  hakkındadır ve derleme/repack tekrarlanabilirliğinden bağımsızdır.
