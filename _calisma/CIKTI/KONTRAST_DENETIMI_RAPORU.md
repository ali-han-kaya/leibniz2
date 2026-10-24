# Kontrast denetimi — Vercel + pano (koyu/açık)

Statik WCAG 2.1 ölçümü (`design-system/scripts/report_token_contrast.py`).
Tarayıcı yok; `var()` zinciri, `color-mix(in srgb, …)` türevleri ve alfa
bindirmesi çözülür. Eşikler: metin **4.5** (AA), büyük metin/UI **3.0**
(WCAG 1.4.11), AAA **7.0** (raporlanır, bloklamaz).

## Girdiler (sha256)

| Kaynak | sha256 |
|---|---|
| `design-system/tokens.css` | `947fd89b8b164d40` |
| `design-system/vercel/theme.css` | `2f1516587b4d9fd6` |
| `design-system/vercel/tokens.css` | `5a04b9822a383ada` |

## Revizyon tabanı (`HEAD`)

| Kaynak | Çalışma ağacı ↔ HEAD |
|---|---|
| `design-system/tokens.css` | **FARKLI** ⚠️ (ölçüm çalışma ağacından; commit'li palet sapıyor) |
| `design-system/vercel/theme.css` | **ref'te yok** ⚠️ (commit'siz dosya) |
| `design-system/vercel/tokens.css` | **ref'te yok** ⚠️ (commit'siz dosya) |

## Özet

- ölçülen çift: **150** · çözülemeyen: 0
- **gerekli** eşik altında: **36** · yalnız uyarı (dekoratif ayırıcı): 13
- `kind=text` çiftlerinden AA (4.5) altında: **35**
- birebir aynı renk çifti (görünmez ayırıcı riski): **1**
- beyan↔ölçüm sapması: **0**
- Vercel varyantının ilan edilmiş istisnaları (koyu tabandan gelir): `--ok`, `--warn`, `--tint-ok-bg`, `--tint-warn-bg`

## Pano — koyu (`:root`)

44 çift · rol eşiği altında 3

| Ön plan | Arka plan | Tür | Oran | Eşik | AA metin | AAA |
|---|---|---|---|---|---|---|
| `--border` | `--surface-2` | ui | **1.25** ⚠️ | 3.0 | ❌ | — |
| `--border` | `--surface-1` | ui | **1.42** ⚠️ | 3.0 | ❌ | — |
| `--border` | `--bg` | ui | **1.55** ⚠️ | 3.0 | ❌ | — |
| `--muted` | `--surface-2` | text | **4.95** ✅ | 4.5 | ✅ | — |
| `--accent` | `--tint-accent-bg` (üzerine: `--surface-1`) | text | **5.32** ✅ | 4.5 | ✅ | — |
| `--ok` | `--tint-ok-bg` (üzerine: `--surface-1`) | text | **5.33** ✅ | 4.5 | ✅ | — |
| `--warn` | `--tint-warn-bg` (üzerine: `--surface-1`) | text | **5.37** ✅ | 4.5 | ✅ | — |
| `--muted` | `--surface-1` | text | **5.62** ✅ | 4.5 | ✅ | — |
| `--budget` | `--tint-budget-bg` (üzerine: `--surface-1`) | text | **5.65** ✅ | 4.5 | ✅ | — |
| `--err` | `--tint-err-bg` (üzerine: `--surface-1`) | text | **5.79** ✅ | 4.5 | ✅ | — |
| `--accent` | `--tint-accent-bg` (üzerine: `--bg`) | text | **5.96** ✅ | 4.5 | ✅ | — |
| `--ok` | `--tint-ok-bg` (üzerine: `--bg`) | text | **5.96** ✅ | 4.5 | ✅ | — |
| `--ok` | `--surface-2` | text | **5.99** ✅ | 4.5 | ✅ | — |
| `--warn` | `--tint-warn-bg` (üzerine: `--bg`) | text | **6.00** ✅ | 4.5 | ✅ | — |
| `--accent` | `--surface-2` | text | **6.03** ✅ | 4.5 | ✅ | — |
| `--warn` | `--surface-2` | text | **6.03** ✅ | 4.5 | ✅ | — |
| `--err` | `--surface-2` | text | **6.04** ✅ | 4.5 | ✅ | — |
| `--budget` | `--surface-2` | text | **6.04** ✅ | 4.5 | ✅ | — |
| `--muted` | `--bg` | text | **6.15** ✅ | 4.5 | ✅ | — |
| `--budget` | `--tint-budget-bg` (üzerine: `--bg`) | text | **6.31** ✅ | 4.5 | ✅ | — |
| `--err` | `--tint-err-bg` (üzerine: `--bg`) | text | **6.39** ✅ | 4.5 | ✅ | — |
| `--ok` | `--surface-1` | text | **6.81** ✅ | 4.5 | ✅ | — |
| `--accent` | `--surface-1` | text | **6.85** ✅ | 4.5 | ✅ | — |
| `--accent` | `--surface-1` | ui | **6.85** ✅ | 3.0 | ✅ | — |
| `--warn` | `--surface-1` | text | **6.85** ✅ | 4.5 | ✅ | — |
| `--err` | `--surface-1` | text | **6.86** ✅ | 4.5 | ✅ | — |
| `--budget` | `--surface-1` | text | **6.86** ✅ | 4.5 | ✅ | — |
| `--ok` | `--bg` | text | **7.44** ✅ | 4.5 | ✅ | ✅ |
| `--accent` | `--bg` | text | **7.49** ✅ | 4.5 | ✅ | ✅ |
| `--on-accent` | `--accent` | text | **7.49** ✅ | 4.5 | ✅ | ✅ |
| `--accent` | `--bg` | ui | **7.49** ✅ | 3.0 | ✅ | ✅ |
| `--warn` | `--bg` | text | **7.49** ✅ | 4.5 | ✅ | ✅ |
| `--err` | `--bg` | text | **7.50** ✅ | 4.5 | ✅ | ✅ |
| `--budget` | `--bg` | text | **7.50** ✅ | 4.5 | ✅ | ✅ |
| `--fg-dimmed` | `--surface-2` | text | **8.10** ✅ | 4.5 | ✅ | ✅ |
| `--fg-dimmed` | `--surface-1` | text | **9.21** ✅ | 4.5 | ✅ | ✅ |
| `--fg-dimmed` | `--bg` | text | **10.07** ✅ | 4.5 | ✅ | ✅ |
| `--paper-ink` | `--paper` | text | **12.66** ✅ | 4.5 | ✅ | ✅ |
| `--fg` | `--surface-2` | text | **12.88** ✅ | 4.5 | ✅ | ✅ |
| `--fg` | `--surface-1` | text | **14.64** ✅ | 4.5 | ✅ | ✅ |
| `--fg` | `--code-bg` | text | **14.64** ✅ | 4.5 | ✅ | ✅ |
| `--fg` | `--header-start` | text | **14.64** ✅ | 4.5 | ✅ | ✅ |
| `--fg` | `--bg` | text | **16.00** ✅ | 4.5 | ✅ | ✅ |
| `--fg` | `--header-end` | text | **16.00** ✅ | 4.5 | ✅ | ✅ |

## Pano — açık (`:root[data-theme="light"]`)

44 çift · rol eşiği altında 12

| Ön plan | Arka plan | Tür | Oran | Eşik | AA metin | AAA |
|---|---|---|---|---|---|---|
| `--border` | `--surface-2` | ui | **1.31** ⚠️ | 3.0 | ❌ | — |
| `--border` | `--bg` | ui | **1.49** ⚠️ | 3.0 | ❌ | — |
| `--border` | `--surface-1` | ui | **1.68** ⚠️ | 3.0 | ❌ | — |
| `--warn` | `--surface-2` | text | **3.63** ❌ | 4.5 | ❌ | — |
| `--warn` | `--tint-warn-bg` (üzerine: `--bg`) | text | **3.67** ❌ | 4.5 | ❌ | — |
| `--warn` | `--tint-warn-bg` (üzerine: `--surface-1`) | text | **4.08** ❌ | 4.5 | ❌ | — |
| `--ok` | `--surface-2` | text | **4.10** ❌ | 4.5 | ❌ | — |
| `--warn` | `--bg` | text | **4.10** ❌ | 4.5 | ❌ | — |
| `--ok` | `--tint-ok-bg` (üzerine: `--bg`) | text | **4.12** ❌ | 4.5 | ❌ | — |
| `--muted` | `--surface-2` | text | **4.17** ❌ | 4.5 | ❌ | — |
| `--accent` | `--surface-2` | text | **4.33** ❌ | 4.5 | ❌ | — |
| `--accent` | `--tint-accent-bg` (üzerine: `--bg`) | text | **4.37** ❌ | 4.5 | ❌ | — |
| `--ok` | `--tint-ok-bg` (üzerine: `--surface-1`) | text | **4.59** ✅ | 4.5 | ✅ | — |
| `--warn` | `--surface-1` | text | **4.63** ✅ | 4.5 | ✅ | — |
| `--budget` | `--surface-2` | text | **4.64** ✅ | 4.5 | ✅ | — |
| `--ok` | `--bg` | text | **4.65** ✅ | 4.5 | ✅ | — |
| `--muted` | `--bg` | text | **4.73** ✅ | 4.5 | ✅ | — |
| `--budget` | `--tint-budget-bg` (üzerine: `--bg`) | text | **4.81** ✅ | 4.5 | ✅ | — |
| `--err` | `--tint-err-bg` (üzerine: `--bg`) | text | **4.85** ✅ | 4.5 | ✅ | — |
| `--accent` | `--tint-accent-bg` (üzerine: `--surface-1`) | text | **4.87** ✅ | 4.5 | ✅ | — |
| `--accent` | `--bg` | text | **4.90** ✅ | 4.5 | ✅ | — |
| `--accent` | `--bg` | ui | **4.90** ✅ | 3.0 | ✅ | — |
| `--err` | `--surface-2` | text | **5.06** ✅ | 4.5 | ✅ | — |
| `--ok` | `--surface-1` | text | **5.24** ✅ | 4.5 | ✅ | — |
| `--budget` | `--bg` | text | **5.26** ✅ | 4.5 | ✅ | — |
| `--muted` | `--surface-1` | text | **5.33** ✅ | 4.5 | ✅ | — |
| `--budget` | `--tint-budget-bg` (üzerine: `--surface-1`) | text | **5.37** ✅ | 4.5 | ✅ | — |
| `--err` | `--tint-err-bg` (üzerine: `--surface-1`) | text | **5.41** ✅ | 4.5 | ✅ | — |
| `--accent` | `--surface-1` | text | **5.53** ✅ | 4.5 | ✅ | — |
| `--on-accent` | `--accent` | text | **5.53** ✅ | 4.5 | ✅ | — |
| `--accent` | `--surface-1` | ui | **5.53** ✅ | 3.0 | ✅ | — |
| `--err` | `--bg` | text | **5.73** ✅ | 4.5 | ✅ | — |
| `--budget` | `--surface-1` | text | **5.93** ✅ | 4.5 | ✅ | — |
| `--fg-dimmed` | `--surface-2` | text | **6.12** ✅ | 4.5 | ✅ | — |
| `--err` | `--surface-1` | text | **6.47** ✅ | 4.5 | ✅ | — |
| `--fg-dimmed` | `--bg` | text | **6.93** ✅ | 4.5 | ✅ | — |
| `--fg-dimmed` | `--surface-1` | text | **7.82** ✅ | 4.5 | ✅ | ✅ |
| `--fg` | `--surface-2` | text | **11.49** ✅ | 4.5 | ✅ | ✅ |
| `--fg` | `--code-bg` | text | **11.49** ✅ | 4.5 | ✅ | ✅ |
| `--fg` | `--header-end` | text | **11.94** ✅ | 4.5 | ✅ | ✅ |
| `--fg` | `--bg` | text | **13.01** ✅ | 4.5 | ✅ | ✅ |
| `--fg` | `--surface-1` | text | **14.68** ✅ | 4.5 | ✅ | ✅ |
| `--paper-ink` | `--paper` | text | **14.68** ✅ | 4.5 | ✅ | ✅ |
| `--fg` | `--header-start` | text | **14.68** ✅ | 4.5 | ✅ | ✅ |

## Vercel varyantı (pano açık rolleriyle, `:root[data-theme="vercel"]`)

44 çift · rol eşiği altında 27

| Ön plan | Arka plan | Tür | Oran | Eşik | AA metin | AAA |
|---|---|---|---|---|---|---|
| `--border` | `--surface-2` | ui | **1.00** ⚠️ | 3.0 | ❌ | — |
| `--border` | `--surface-1` | ui | **1.05** ⚠️ | 3.0 | ❌ | — |
| `--border` | `--bg` | ui | **1.25** ⚠️ | 3.0 | ❌ | — |
| `--ok` | `--tint-ok-bg` (üzerine: `--surface-1`) | text | **1.89** ❌ | 4.5 | ❌ | — |
| `--warn` | `--tint-warn-bg` (üzerine: `--surface-1`) | text | **1.89** ❌ | 4.5 | ❌ | — |
| `--warn` | `--surface-2` | text | **2.01** ❌ | 4.5 | ❌ | — |
| `--ok` | `--surface-2` | text | **2.03** ❌ | 4.5 | ❌ | — |
| `--warn` | `--surface-1` | text | **2.11** ❌ | 4.5 | ❌ | — |
| `--ok` | `--surface-1` | text | **2.12** ❌ | 4.5 | ❌ | — |
| `--warn` | `--tint-warn-bg` (üzerine: `--bg`) | text | **2.22** ❌ | 4.5 | ❌ | — |
| `--ok` | `--tint-ok-bg` (üzerine: `--bg`) | text | **2.22** ❌ | 4.5 | ❌ | — |
| `--warn` | `--bg` | text | **2.52** ❌ | 4.5 | ❌ | — |
| `--ok` | `--bg` | text | **2.54** ❌ | 4.5 | ❌ | — |
| `--accent` | `--tint-accent-bg` (üzerine: `--surface-1`) | text | **3.12** ❌ | 4.5 | ❌ | — |
| `--budget` | `--tint-budget-bg` (üzerine: `--surface-1`) | text | **3.16** ❌ | 4.5 | ❌ | — |
| `--err` | `--tint-err-bg` (üzerine: `--surface-1`) | text | **3.29** ❌ | 4.5 | ❌ | — |
| `--accent` | `--surface-2` | text | **3.59** ❌ | 4.5 | ❌ | — |
| `--budget` | `--surface-2` | text | **3.59** ❌ | 4.5 | ❌ | — |
| `--err` | `--surface-2` | text | **3.65** ❌ | 4.5 | ❌ | — |
| `--accent` | `--tint-accent-bg` (üzerine: `--bg`) | text | **3.68** ❌ | 4.5 | ❌ | — |
| `--budget` | `--tint-budget-bg` (üzerine: `--bg`) | text | **3.74** ❌ | 4.5 | ❌ | — |
| `--budget` | `--surface-1` | text | **3.76** ❌ | 4.5 | ❌ | — |
| `--accent` | `--surface-1` | text | **3.76** ❌ | 4.5 | ❌ | — |
| `--accent` | `--surface-1` | ui | **3.76** ✅ | 3.0 | ❌ | — |
| `--err` | `--surface-1` | text | **3.83** ❌ | 4.5 | ❌ | — |
| `--err` | `--tint-err-bg` (üzerine: `--bg`) | text | **3.87** ❌ | 4.5 | ❌ | — |
| `--fg-dimmed` | `--surface-2` | text | **4.07** ❌ | 4.5 | ❌ | — |
| `--fg-dimmed` | `--surface-1` | text | **4.26** ❌ | 4.5 | ❌ | — |
| `--accent` | `--bg` | text | **4.50** ✅ | 4.5 | ✅ | — |
| `--budget` | `--bg` | text | **4.50** ✅ | 4.5 | ✅ | — |
| `--on-accent` | `--accent` | text | **4.50** ✅ | 4.5 | ✅ | — |
| `--accent` | `--bg` | ui | **4.50** ✅ | 3.0 | ✅ | — |
| `--err` | `--bg` | text | **4.58** ✅ | 4.5 | ✅ | — |
| `--fg-dimmed` | `--bg` | text | **5.10** ✅ | 4.5 | ✅ | — |
| `--muted` | `--surface-2` | text | **6.79** ✅ | 4.5 | ✅ | — |
| `--muted` | `--surface-1` | text | **7.12** ✅ | 4.5 | ✅ | ✅ |
| `--muted` | `--bg` | text | **8.52** ✅ | 4.5 | ✅ | ✅ |
| `--fg` | `--surface-2` | text | **14.30** ✅ | 4.5 | ✅ | ✅ |
| `--fg` | `--surface-1` | text | **14.99** ✅ | 4.5 | ✅ | ✅ |
| `--fg` | `--code-bg` | text | **14.99** ✅ | 4.5 | ✅ | ✅ |
| `--fg` | `--header-end` | text | **14.99** ✅ | 4.5 | ✅ | ✅ |
| `--fg` | `--bg` | text | **17.94** ✅ | 4.5 | ✅ | ✅ |
| `--paper-ink` | `--paper` | text | **17.94** ✅ | 4.5 | ✅ | ✅ |
| `--fg` | `--header-start` | text | **17.94** ✅ | 4.5 | ✅ | ✅ |

## Vercel aynası (kendi ışık yakalaması, 19 token)

18 çift · rol eşiği altında 7

| Ön plan | Arka plan | Tür | Oran | Eşik | AA metin | AAA |
|---|---|---|---|---|---|---|
| `--color-gray-alpha-400` | `--color-background-100` | ui | **1.19** ⚠️ | 3.0 | ❌ | — |
| `--color-gray-200` | `--color-background-100` | ui | **1.20** ⚠️ | 3.0 | ❌ | — |
| `--color-gray-300` | `--color-background-100` | ui | **1.25** ⚠️ | 3.0 | ❌ | — |
| `--color-gray-500` | `--color-background-100` | ui | **1.65** ⚠️ | 3.0 | ❌ | — |
| `--color-gray-600` | `--color-background-100` | large | **2.37** ❌ | 3.0 | ❌ | — |
| `--ship-text` | `--color-background-100` | text | **3.06** ❌ | 4.5 | ❌ | — |
| `--color-gray-700` | `--color-background-100` | large | **3.24** ✅ | 3.0 | ❌ | — |
| `--ds-focus-color` | `--color-gray-200` | ui | **3.71** ✅ | 3.0 | ❌ | — |
| `--geist-console-text-color-pink` | `--color-background-100` | text | **3.91** ❌ | 4.5 | ❌ | — |
| `--color-gray-800` | `--color-background-100` | large | **4.12** ✅ | 3.0 | ❌ | — |
| `--ds-focus-color` | `--color-background-100` | ui | **4.44** ✅ | 3.0 | ❌ | — |
| `--develop-text` | `--color-background-100` | text | **4.50** ✅ | 4.5 | ✅ | — |
| `--preview-text` | `--color-background-100` | text | **4.50** ✅ | 4.5 | ✅ | — |
| `--geist-console-text-color-blue` | `--color-background-100` | text | **4.55** ✅ | 4.5 | ✅ | — |
| `--geist-console-text-color-purple` | `--color-background-100` | text | **7.07** ✅ | 4.5 | ✅ | ✅ |
| `--color-gray-900` | `--color-background-100` | text | **8.52** ✅ | 4.5 | ✅ | ✅ |
| `--color-gray-1000` | `--color-background-100` | text | **17.94** ✅ | 4.5 | ✅ | ✅ |
| `--geist-console-text-color-default` | `--color-background-100` | text | **21.00** ✅ | 4.5 | ✅ | ✅ |

## Öne çıkanlar

- **dashboard-dark**: gerekli 41 çiftin 0'ı eşik altında → ✅ geçti
- **dashboard-light**: gerekli 41 çiftin 9'u eşik altında → ❌ kaldı
- **vercel-mirror**: gerekli 14 çiftin 3'ü eşik altında → ❌ kaldı
- **vercel-variant**: gerekli 41 çiftin 24'ü eşik altında → ❌ kaldı
- En düşük gerekli oran: **1.89** — vercel-variant · `--ok` → `--tint-ok-bg` (üzerine `--surface-1`)
- AA (4.5) sınırına pinli metin çifti: **5** → vercel-variant `--accent`/`--bg` (4.50), vercel-variant `--budget`/`--bg` (4.50), vercel-variant `--on-accent`/`--accent` (4.50), vercel-mirror `--develop-text`/`--color-background-100` (4.50), vercel-mirror `--preview-text`/`--color-background-100` (4.50)
- Paletin kendi beyanıyla uyuşmayan ölçüm: **0**

## Paletin kendi iddiaları (beyan ↔ ölçüm)

| Palet | Çift | Beyan | Ölçüm | Sonuç |
|---|---|---|---|---|
| dashboard-dark | `--fg-dimmed / --bg` | ≥ 4.50:1 | **10.07**:1 | ✅ |
| dashboard-dark | `--err / --tint-err-bg` | 5.78:1 | **5.79**:1 | ✅ |
| dashboard-dark | `--on-accent / --accent` | 7.49:1 | **7.49**:1 | ✅ |
| dashboard-light | `--fg-dimmed / --bg` | ≥ 4.50:1 | **6.93**:1 | ✅ |
| dashboard-light | `--on-accent / --accent` | 5.53:1 | **5.53**:1 | ✅ |

## Bulgular

### Gerekli eşik altı (36)

| Palet | Çift | Tür | Ölçüm | Eşik | Not |
|---|---|---|---|---|---|
| vercel-variant | `--ok` → `--tint-ok-bg` (üzerine `--surface-1`) | text | **1.89** | 4.5 | --ok / kendi tint'i (yüzey-1 üzerine) |
| vercel-variant | `--warn` → `--tint-warn-bg` (üzerine `--surface-1`) | text | **1.89** | 4.5 | --warn / kendi tint'i (yüzey-1 üzerine) |
| vercel-variant | `--warn` → `--surface-2` | text | **2.01** | 4.5 | --warn / --surface-2 |
| vercel-variant | `--ok` → `--surface-2` | text | **2.03** | 4.5 | --ok / --surface-2 |
| vercel-variant | `--warn` → `--surface-1` | text | **2.11** | 4.5 | --warn / --surface-1 |
| vercel-variant | `--ok` → `--surface-1` | text | **2.12** | 4.5 | --ok / --surface-1 |
| vercel-variant | `--warn` → `--tint-warn-bg` (üzerine `--bg`) | text | **2.22** | 4.5 | --warn / kendi tint'i (bg üzerine) |
| vercel-variant | `--ok` → `--tint-ok-bg` (üzerine `--bg`) | text | **2.22** | 4.5 | --ok / kendi tint'i (bg üzerine) |
| vercel-mirror | `--color-gray-600` → `--color-background-100` | large | **2.37** | 3.0 | ipucu/ikincil ton — büyük metin varsayımı (AA 3.0) |
| vercel-variant | `--warn` → `--bg` | text | **2.52** | 4.5 | --warn / --bg |
| vercel-variant | `--ok` → `--bg` | text | **2.54** | 4.5 | --ok / --bg |
| vercel-mirror | `--ship-text` → `--color-background-100` | text | **3.06** | 4.5 | üretim (ship) kırmızısı — beyaz üzerinde metin |
| vercel-variant | `--accent` → `--tint-accent-bg` (üzerine `--surface-1`) | text | **3.12** | 4.5 | --accent / kendi tint'i (yüzey-1 üzerine) |
| vercel-variant | `--budget` → `--tint-budget-bg` (üzerine `--surface-1`) | text | **3.16** | 4.5 | --budget / kendi tint'i (yüzey-1 üzerine) |
| vercel-variant | `--err` → `--tint-err-bg` (üzerine `--surface-1`) | text | **3.29** | 4.5 | --err / kendi tint'i (yüzey-1 üzerine) |
| vercel-variant | `--accent` → `--surface-2` | text | **3.59** | 4.5 | --accent / --surface-2 |
| vercel-variant | `--budget` → `--surface-2` | text | **3.59** | 4.5 | --budget / --surface-2 |
| dashboard-light | `--warn` → `--surface-2` | text | **3.63** | 4.5 | --warn / --surface-2 |
| vercel-variant | `--err` → `--surface-2` | text | **3.65** | 4.5 | --err / --surface-2 |
| dashboard-light | `--warn` → `--tint-warn-bg` (üzerine `--bg`) | text | **3.67** | 4.5 | --warn / kendi tint'i (bg üzerine) |
| vercel-variant | `--accent` → `--tint-accent-bg` (üzerine `--bg`) | text | **3.68** | 4.5 | --accent / kendi tint'i (bg üzerine) |
| vercel-variant | `--budget` → `--tint-budget-bg` (üzerine `--bg`) | text | **3.74** | 4.5 | --budget / kendi tint'i (bg üzerine) |
| vercel-variant | `--budget` → `--surface-1` | text | **3.76** | 4.5 | --budget / --surface-1 |
| vercel-variant | `--accent` → `--surface-1` | text | **3.76** | 4.5 | --accent / --surface-1 |
| vercel-variant | `--err` → `--surface-1` | text | **3.83** | 4.5 | --err / --surface-1 |
| vercel-variant | `--err` → `--tint-err-bg` (üzerine `--bg`) | text | **3.87** | 4.5 | --err / kendi tint'i (bg üzerine) |
| vercel-mirror | `--geist-console-text-color-pink` → `--color-background-100` | text | **3.91** | 4.5 | konsol pembe |
| vercel-variant | `--fg-dimmed` → `--surface-2` | text | **4.07** | 4.5 | --fg-dimmed / --surface-2 |
| dashboard-light | `--warn` → `--tint-warn-bg` (üzerine `--surface-1`) | text | **4.08** | 4.5 | --warn / kendi tint'i (yüzey-1 üzerine) |
| dashboard-light | `--ok` → `--surface-2` | text | **4.10** | 4.5 | --ok / --surface-2 |
| dashboard-light | `--warn` → `--bg` | text | **4.10** | 4.5 | --warn / --bg |
| dashboard-light | `--ok` → `--tint-ok-bg` (üzerine `--bg`) | text | **4.12** | 4.5 | --ok / kendi tint'i (bg üzerine) |
| dashboard-light | `--muted` → `--surface-2` | text | **4.17** | 4.5 | --muted / --surface-2 |
| vercel-variant | `--fg-dimmed` → `--surface-1` | text | **4.26** | 4.5 | --fg-dimmed / --surface-1 |
| dashboard-light | `--accent` → `--surface-2` | text | **4.33** | 4.5 | --accent / --surface-2 |
| dashboard-light | `--accent` → `--tint-accent-bg` (üzerine `--bg`) | text | **4.37** | 4.5 | --accent / kendi tint'i (bg üzerine) |

### Dekoratif ayırıcılar (uyarı: 1.4.11 kapsamı dışı, 13)

Bunlar WCAG 1.4.11'in zorunlu kıldığı *bileşen/state* sınırları değil; ayırıcı okunurluğu için yine de bilgi değeri taşır:

- vercel-variant · `--border` → `--surface-2`: **1.00** (< 3.0) — düğme kenarlığı (yüzey-2) — dekoratif
- vercel-variant · `--border` → `--surface-1`: **1.05** (< 3.0) — kart kenarlığı — dekoratif
- vercel-mirror · `--color-gray-alpha-400` → `--color-background-100`: **1.19** (< 3.0) — alfa kenarlık — dekoratif (alfa beyaza bindirilir)
- vercel-mirror · `--color-gray-200` → `--color-background-100`: **1.20** (< 3.0) — yüzey ayrımı — dekoratif
- dashboard-dark · `--border` → `--surface-2`: **1.25** (< 3.0) — düğme kenarlığı (yüzey-2) — dekoratif
- vercel-variant · `--border` → `--bg`: **1.25** (< 3.0) — ayırıcı kenarlık — dekoratif
- vercel-mirror · `--color-gray-300` → `--color-background-100`: **1.25** (< 3.0) — yüzey kenarı — dekoratif
- dashboard-light · `--border` → `--surface-2`: **1.31** (< 3.0) — düğme kenarlığı (yüzey-2) — dekoratif
- dashboard-dark · `--border` → `--surface-1`: **1.42** (< 3.0) — kart kenarlığı — dekoratif
- dashboard-light · `--border` → `--bg`: **1.49** (< 3.0) — ayırıcı kenarlık — dekoratif
- dashboard-dark · `--border` → `--bg`: **1.55** (< 3.0) — ayırıcı kenarlık — dekoratif
- vercel-mirror · `--color-gray-500` → `--color-background-100`: **1.65** (< 3.0) — ayırıcı/kenar — dekoratif
- dashboard-light · `--border` → `--surface-1`: **1.68** (< 3.0) — kart kenarlığı — dekoratif

### Birebir aynı renk (1 çift)

- vercel-variant · `--border` → `--surface-2`: **1.00** — düğme kenarlığı (yüzey-2) — dekoratif
## Denetlenmeyen token'lar (gerekçeli)

| Palet | Token | Gerekçe |
|---|---|---|
| vercel-mirror | `--geist-selection-text-color` | seçim yüzeyi (selection background) yakalanmadı; metin tonu yalnız o yüzeyin üzerinde anlamlıdır |


## Sınırlamalar

- **Vercel koyu paleti bu depoda yok**: yakalama yalnız ışık temasıdır
  (19 token). Vercel için koyu denetim yapılamaz; `vercel-variant`
  satırları panonun açık rolleriyle okunur.
- Ölçüm **statiktir**: yalnız token değerleri karşılaştırılır;
  `mix-blend-mode`, gradyan, görsel (image) arka plan ve gerçek punto
  dikkate alınmaz. Render edilen DOM için runtime axe kapısı
  (`a11y_gate.py`, `color-contrast`) tamamlayıcıdır.
- Ölçüm **çalışma ağacı** dosyalarına karşıdır; yukarıdaki sha256
  hangi içeriğin ölçüldüğünü pinler. Revizyon tablosundaki `FARKLI`/
  `ref'te yok` kayıtları raporun commit'li paletten saptığını gösterir.
- Yarı saydam yüzeyler eşleşmede bildirilen `over` yuvasına bindirilir;
  başka bir yüzey üzerinde oran değişir (her iki yüzey de listelenir).

