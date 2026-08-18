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
