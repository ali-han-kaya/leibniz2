# Lean 4 İspat Raporu — reduct-invariance lemması

**Dosya:** `_calisma/lean_reduct/ReductInvariance.lean` (self-contained, Mathlib'siz)
**Araç:** Lean 4.33.0 (arm64-apple-darwin) — `lean ReductInvariance.lean` → **exit 0** (hata yok)
**Tarih:** 2026-08-17

Bu formalizasyon, `core_section.tex`'teki `lem:reduct-invariance` lemmasını
makine tarafından denetlenen bir **yapısal tümevarım** kanıtına taşır. Z3 bu
önermeyi üretemez: Z3 bir karar/satisfiability motorudur ve L₀ fragmanındaki
*gerektirmeleri* ispatlar; bu lemma ise **sözdizimi düzeyinde** ("her L₀-formülü
için") ikinci-dereceden bir ifadedir ve yalnızca tümevarımla kanıtlanabilir.

---

## 1. Biçimselleştirilen ifade

Kağıttaki lemma:

> M₁⁺, M₂⁺ ∈ 𝒦, özdeş L₀-reduct ile. O halde her L₀-cümlesi φ için
> M₁⁺ ⊨ φ ⟺ M₂⁺ ⊨ φ.

Lean'de iki teorem:

1. `reduct_invariance` (ana lemma, *açık formüller için daha güçlü*):
   ```lean
   theorem reduct_invariance (M1 M2 : L0Structure Imp Cont Ep) (h : L0Agree M1 M2) :
     ∀ (φ : Formula) (e : Env Imp Cont Ep), Realize M1 φ e ↔ Realize M2 φ e
   ```
2. `reduct_invariance_sentences` (cümle düzeyi — kağıdın tam ifadesi):
   ```lean
   theorem reduct_invariance_sentences ... (φ : Formula) :
     (∀ e, Realize M1 φ e) ↔ (∀ e, Realize M2 φ e)
   ```

## 2. Modelleme kararları (şeffaflık)

| Öğe | Formalizasyon | Not |
|---|---|---|
| L₀ sıraları | soyut tipler `Imp`, `Cont`, `Ep` | yapı parametreleri |
| L₀ yüklemleri | `L0Structure`: 9 yüklem (`Kat`…`StoicEp`) | extensional yorum |
| L₀ sözdizimi | `Formula` — 9 atom + 5 Boole + 6 sıralı niceleyici (20 kurucu) | değişkenler `Nat` ad-uzayı |
| doyum | `Realize : Formula → Env → Prop` (Tarski) | yalnızca L₀ sembollerine başvurur |
| "özdeş reduct" | `L0Agree M1 M2` — 9 yüklemin noktasal `↔` eşitliği | extensional doğruluk kavramı |
| L⁺ zenginleşmesi | **bilinçli olarak yok** | `Realize` hiçbir L⁺ sembolüne başvurmadığı için zenginleşme L₀-doğruluğunu etkileyemez; lemma L₀-reduct'e indirgenir |

## 3. Kanıt yapısı

`induction φ` — 20 kurucunun tamamı üzerinden:

- **Atomik (9):** `h.kat`, `h.rep`, … doğrudan `L0Agree`'den gelir.
- **Boolean (5):** `¬`, `∧`, `∨`, `→`, `↔` için `ih`'ler ile `constructor`
  (ileri/geri yön ayrı ayrı).
- **Niceleyiciler (6):** `∀x`/`∃x`; `ih`'ın ortam-güncelleme
  `{e with imp := update e.imp k x}` üzerine uygulanması + `forall`/`exists`
  yönleri. Bu, kağıttaki "quantified cases follow because the relevant domains
  and interpretations are the same" cümlesinin biçimsel karşılığıdır.

## 4. Z3 ile iş bölümü

| | Z3 (`symbolic_proof_z3.py`) | Lean 4 (`ReductInvariance.lean`) |
|---|---|---|
| Nesne | L₀/L⁺ **gerektirmeleri** (Prop 1, bridge, karakterizasyon, Prop 2 tanığı) | **sözdizimi** üzerinden tümevarım (reduct-invariance) |
| Yöntem | karar prosedürü (EPR/Bernays–Schönfinkel: UNSAT = geçerlilik) | yapısal tümevarım + tip denetimi |
| Sonuç | 12/12 ispat (P4-d/P4-e dahil) | teorem `reduct_invariance` derlendi, exit 0 |

İkisi birlikte kağıdın §2 biçimsel çekirdeğini **iki** bağımsız düzeyde
doğrular: Z3 içerik teoremlerini, Lean ise o teoremlerin dayandığı
meta-teoremi (reduct-invariance) kanıtlar.

## 5. Doğrulama

```text
$ lean ReductInvariance.lean
reduct_invariance {Imp Cont Ep : Type} (M1 M2 : L0Structure Imp Cont Ep)
  (h : L0Agree M1 M2) (φ : Formula) (e : Env Imp Cont Ep) :
  Realize M1 φ e ↔ Realize M2 φ e
reduct_invariance_sentences ... :
  (∀ (e : Env Imp Cont Ep), Realize M1 φ e) ↔ ∀ (e : Env Imp Cont Ep), Realize M2 φ e
$ echo $?
0
```

Kurulum: `elan` + `leanprover/lean4:stable` (v4.33.0), Homebrew `elan-init`
üzerinden; proje-içi değil ama standart `~/.elan` kurulumu, sudo yok.

**Sürüm notu (V5l/V5m, 2026-08-18):** bu ispat içerik hakkındadır;
tectonic/qpdf byte-non-determinizminin PDF/zip tekrarlanabilirliğine getirdiği
bilinen sınır (MANIFEST V5k/V5l; `qpdf_determinism_experiment.py` ile yeniden
üretilebilir) bu teoremin doğruluğunu etkilemez.

---

## 6. İkinci çekirdek — Sınır İspatı (illüstratif, 8 teorem)

**Sürüm notu (V5s, 2026-08-22):** bu raporun ana konusu `ReductInvariance.lean`
(meta-teorem, yapısal tümevarım) iken, repoda **ikinci** bir Lean çekirdeği
daha vardır: `_calisma/lean_reduct/Content.lean` (`Leibniz2Reduct`, 8 teorem).
Yukarıdaki §2-§5'in aksine bu çekirdek **illüstratiftir** — Stoa/Hume
formalizasyonu DEĞİLDİR; gösterdiği şey, bazı epistemik ayrımların ekstansiyonel
hedef dile giden unutma haritası altında ayırt ediciliğini kaybedebildiğidir
(temsil kaybı teoremi, varlık teoremi değil). `World = actual` bilinçli en fakir
modeldir: kaybın model zenginliğinden değil haritanın kendisinden geldiğini
göstermek için. `kataleptic-`/`customary-` tanımları kod etiketidir, tarihsel
yorum değildir.

### 6.1 İspatlanan 8 teorem

| # | Teorem | Ne ispatlar | Yöntem |
|---|--------|-------------|--------|
| 1 | `historical_pair_collapses_under_forgetTopic` | tam unutma iki içeriği özdeşleştirir | rfl |
| 2 | `historical_pair_survives_forgetAccess` | tek eksen unutması ayrımı silmez | cases |
| 3 | `historical_pair_survives_forgetJustification` | aynı | cases |
| 4 | `historical_pair_survives_forgetSource` | aynı | cases |
| 5 | `forgetAccess_not_injective` | access haritası injective değil | cases+congrArg |
| 6 | `forgetJustification_not_injective` | justification haritası injective değil | cases+congrArg |
| 7 | `forgetSource_not_injective` | source haritası injective değil | cases+congrArg |
| 8 | `forgetTopic_not_injective` | tam unutma injective değil | cases+congrArg |

### 6.2 Z3 ↔ Lean eşleşmesi (MAP.md sözleşmesi)

| Z3 (`symbolic_proof_z3.py`) | Lean (`Content.lean`) |
|---|---|
| `forget_all` | `forgetTopic` (tam unutma) |
| `forget_access` | `forgetAccess` |
| `forget_justification` | `forgetJustification` |
| `forget_source` | `forgetSource` |

İnvariant: 8 teoremin Z3'teki karşı-örneği ile Lean'deki rfl/cases ispatı **aynı
çökmeyi** gösterir. Eşleşme `MAP.md`'de sabitlenmiştir; diverge olmaması için
korunmalıdır.

### 6.3 lake build kanıtı

```text
$ cd _calisma/lean_reduct && lake clean && lake build --wfail
✔ [2/4] Built Leibniz2Reduct.Content
✔ [3/4] Built Leibniz2Reduct
Build completed successfully.      # exit 0
$ echo $?
0
```

- Araç: leanprover/lean4:v4.14.0 (`lean-toolchain`), süre ~1.1s (<5s beklenen)
- Mathlib bağımlılığı yoktur; `Injective` yerel tanımlıdır
- CI'da K9 kapısı (`verify` job'ı `--full` içinde) aynı derlemeyi fail-closed
  koşar; shim kopyası `Content.lean` (kök) ile birebir aynıdır (8/8 teorem)
- Qpdf byte-non-determinizm sınırı (V5l/V5m) bu çekirdeği de etkilemez —
  ispat makine-kontrollüdür, derleme çıktısı yeniden üretilebilirdir
