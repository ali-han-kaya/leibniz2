# GitHub ↔ GitHub dark/light design-token fark raporu

**Üretim:** `design-system/github/scripts/report_theme_diff.py` — bu dosya
ÜRETİLİR; `--check` diskteki kopyayı birebir doğrular (elle düzenleme = drift).

**Karşılaştırılan iki katman:**

| Katman | `theme` alanı | Yakalama | `dataColorMode` | `bgColorDefault` | `fgColorDefault` | computed custom property |
|---|---|---|---|---|---|---|
| dark (`raw.json`) | yok (bu alan 2026-10-11'de eklendi) | 2026-09-24 22:38:48 | — | — | — | — |
| light (`raw.light.json`) | light | 2026-10-11 12:04:25 | light | #fff | #1f2328 | 1990 |

> İki katman da github.com ana sayfasının **kısmi** computed-kök-değişken
> yakalamasıdır (tam Primer design sistemi değil). `--bgColor-default` /
> `--fgColor-default` yukarıdaki kanıt sütunlarıdır: extractor'ın isim
> filtresi onları `colors.cssVariables`a koymaz (bkz. `README.md` kapsam
> uyarısı), bu yüzden tema kanıtı `pageState` alanında taşınır. dark
> katmanında bu alan yoktur (yakalama `pageState`'ten önce alındı); dark
> tarafın tema kanıtı `README.md` §Snapshot ve `logo.background` değeridir.

**Kural eşitliği (canlı sayfaya bağlı, `--check` kapsamı dışında).** Aynı
betik dark tema ile koşturulduğunda commit'li `raw.json`'u birebir üretir:
`node scripts/capture_theme.mjs dark /tmp/raw.redark.json` sonrası
`colors.cssVariables` 304/304 isim ve değerde aynıdır (ölçüldü 2026-10-11);
bu ölçüm canlı sayfaya bağlı olduğu için raporun deterministik kısmına
yazılmaz, kapıya da bağlanmaz.

## Yönetici özeti

- dark **304** token, light **258** token; paylaşılan isim **208**.
- Paylaşılan 208 ismin **195**'i farklı değer taşır, **13**'i aynıdır.
- Yalnız dark'ta **96**, yalnız light'ta **50** isim var.
- **Aynı isim ≠ aynı rol:** paylaşılan isimlerin 195/208'i temaya göre değer
  değiştiriyor. İki katmanı aynı cascade'e import etmek 195 adda sessiz
  çakışma üretir; `check_github_tokens.py` bu iki katmanı ayrı dosyalarda
  fail-closed kilitler (`tokens.css` = dark, `tokens.light.css` = light).
- Ölçüm eşitliği: aynı betikle (`scripts/capture_theme.mjs`) yeniden alınan
  dark yakalama commit'li `raw.json`'u 304/304 birebir tekrar etti; light katman
  iki bağımsız kurulumda 258/258 aynı çıktı.

## Ölçüm tablosu

| Ölçüm | Değer |
|---|---|
| dark token | 304 |
| light token | 258 |
| paylaşılan isim | 208 |
| paylaşılan ve **aynı** değer | 13 |
| paylaşılan ve **farklı** değer | 195 |
| yalnız dark | 96 |
| yalnız light | 50 |
| light/dark oranı | 0.85 |

## Namespace bazında fark

| Namespace | dark | light | paylaşılan | aynı | farklı | dark-only | light-only |
|---|---|---|---|---|---|---|---|
| `avatar` | 1 | 0 | 0 | 0 | 0 | 1 | 0 |
| `avatarStack` | 0 | 1 | 0 | 0 | 0 | 0 | 1 |
| `base` | 82 | 92 | 71 | 5 | 66 | 11 | 21 |
| `bgColor` | 11 | 5 | 5 | 0 | 5 | 6 | 0 |
| `brand` | 65 | 35 | 28 | 7 | 21 | 37 | 7 |
| `button` | 6 | 6 | 5 | 0 | 5 | 1 | 1 |
| `buttonCounter` | 5 | 5 | 5 | 1 | 4 | 0 | 0 |
| `buttonKeybindingHint` | 5 | 5 | 5 | 0 | 5 | 0 | 0 |
| `codeMirror` | 1 | 1 | 1 | 0 | 1 | 0 | 0 |
| `color` | 24 | 16 | 13 | 0 | 13 | 11 | 3 |
| `contribution` | 7 | 8 | 6 | 0 | 6 | 1 | 2 |
| `control` | 3 | 3 | 2 | 0 | 2 | 1 | 1 |
| `controlTrack` | 0 | 1 | 0 | 0 | 0 | 0 | 1 |
| `data` | 20 | 16 | 13 | 0 | 13 | 7 | 3 |
| `diffBlob` | 6 | 2 | 2 | 0 | 2 | 4 | 0 |
| `display` | 18 | 14 | 10 | 0 | 10 | 8 | 4 |
| `header` | 1 | 0 | 0 | 0 | 0 | 1 | 0 |
| `highlight` | 1 | 1 | 1 | 0 | 1 | 0 | 0 |
| `label` | 38 | 37 | 33 | 0 | 33 | 5 | 4 |
| `overlay` | 1 | 1 | 1 | 0 | 1 | 0 | 0 |
| `prettylights` | 4 | 4 | 3 | 0 | 3 | 1 | 1 |
| `progressBar` | 2 | 2 | 2 | 0 | 2 | 0 | 0 |
| `reactionButton` | 2 | 1 | 1 | 0 | 1 | 1 | 0 |
| `selection` | 1 | 1 | 1 | 0 | 1 | 0 | 0 |
| `skeletonLoader` | 0 | 1 | 0 | 0 | 0 | 0 | 1 |

## Tema-duyarlılık sınıfları

- **Tüm paylaşılan isimleri değişen** namespace'ler (17): `bgColor`, `button`, `buttonKeybindingHint`, `codeMirror`, `color`, `contribution`, `control`, `data`, `diffBlob`, `display`, `highlight`, `label`, `overlay`, `prettylights`, `progressBar`, `reactionButton`, `selection`
- **Kısmen değişen** (3): `base`, `brand`, `buttonCounter`
- **Hiç değişmeyen** (0): —
- **Kesişimi olmayan** (5): `avatar`, `avatarStack`, `controlTrack`, `header`, `skeletonLoader`

Değişmeyen 13 isim (iki temada da aynı değer):

`--base-color-scale-lemon-4`, `--base-color-scale-orange-7`, `--base-color-scale-pink-2`, `--base-color-scale-red-6`, `--base-color-scale-red-7`, `--brand-Grid-column-bgColor-overlay`, `--brand-Icon-color-lemon`, `--brand-Label-color-green-blue-purple-1`, `--brand-Label-color-green-blue-purple-2`, `--brand-TextCursorAnimation-cursor-deleteColor`, `--brand-VideoPlayer-closedCaption-text-bgColor`, `--brand-button-subtle-bgColor-rest`, `--buttonCounter-danger-bgColor-hover`

## `base-color-scale-*` yapısal kayması

Aynı ölçek ailesinde iki tema **farklı adım kümelerini** taşıyor ve
paylaşılan adımların değerleri tema başına değişiyor — ör. `green-4`:
dark `#0fbf3e`, light `#23ea57`. Ölçülen eğilim: light'ın yalnız
kendisinde olan adımları `2` (9 hue), `8` (7 hue), `3` (3 hue); dark'ın yalnız kendisinde olanları `0` (4 hue), `5` (3 hue), `1` (1 hue).
Bu, adım numarasının iki temada **aynı rolü** taşıdığı varsayımını
çürütür: eşleme ancak açık gerekçeyle yapılabilir.

| Hue | dark adımları | light adımları | paylaşılan | dark-only adım | light-only adım |
|---|---|---|---|---|---|
| `blue` | 3 adet (6,7,9) | 6 adet (1,2,3,6,7,9) | 6,7,9 | — | 1,2,3 |
| `coral` | 8 adet (1,2,3,4,6,7,8,9) | 8 adet (1,2,3,4,6,7,8,9) | 1,2,3,4,6,7,8,9 | — | — |
| `gray` | 1 adet (4) | 0 adet () | — | 4 | — |
| `green` | 5 adet (4,6,7,8,9) | 5 adet (2,3,4,8,9) | 4,8,9 | 6,7 | 2,3 |
| `indigo` | 7 adet (1,3,4,5,6,7,9) | 8 adet (1,2,3,4,6,7,8,9) | 1,3,4,6,7,9 | 5 | 2,8 |
| `lemon` | 9 adet (0,1,2,3,4,6,7,8,9) | 9 adet (0,1,2,3,4,6,7,8,9) | 0,1,2,3,4,6,7,8,9 | — | — |
| `lime` | 8 adet (0,1,3,4,5,6,7,9) | 8 adet (1,2,3,4,6,7,8,9) | 1,3,4,6,7,9 | 0,5 | 2,8 |
| `orange` | 6 adet (1,3,4,6,7,9) | 8 adet (1,2,3,4,6,7,8,9) | 1,3,4,6,7,9 | — | 2,8 |
| `pink` | 10 adet (0,1,2,3,4,5,6,7,8,9) | 9 adet (1,2,3,4,5,6,7,8,9) | 1,2,3,4,5,6,7,8,9 | 0 | — |
| `purple` | 7 adet (0,1,4,5,6,7,9) | 9 adet (1,2,3,4,5,6,7,8,9) | 1,4,5,6,7,9 | 0 | 2,3,8 |
| `red` | 5 adet (1,3,6,7,9) | 7 adet (2,3,4,6,7,8,9) | 3,6,7,9 | 1 | 2,4,8 |
| `teal` | 5 adet (1,3,4,6,7) | 7 adet (1,2,3,4,6,7,8) | 1,3,4,6,7 | — | 2,8 |
| `yellow` | 8 adet (0,1,3,4,5,6,7,9) | 8 adet (1,2,3,4,6,7,8,9) | 1,3,4,6,7,9 | 0,5 | 2,8 |

## Palet sayımı tema-duyarsızdır (token katmanı duyarlıdır)

Element sayımıyla çıkan paletin ilk adımları iki temada neredeyse aynı
kalır (fark yalnız içerik/marka bölümünün ağırlığından gelir); yani tema
sinyali **palet sayımında değil, `colors.cssVariables` katmanındadır**:

| Sıra | dark | light |
|---|---|---|
| 1 | `#ffffff` (1525) | `#ffffff` (1528) |
| 2 | `#a4aea6` (194) | `#a4aea6` (194) |
| 3 | `#21262d` (26) | `#21262d` (26) |

## Farklı değer taşıyan isimler (tam liste, 195)

| Token | dark | light |
|---|---|---|
| `--base-color-scale-blue-6` | `#1530b7` | `#0055d5` |
| `--base-color-scale-blue-7` | `#082a8f` | `#0040a7` |
| `--base-color-scale-blue-9` | `#000839` | `#001c4d` |
| `--base-color-scale-coral-1` | `#fdb7a1` | `#ffcab8` |
| `--base-color-scale-coral-2` | `#fa9072` | `#ffa387` |
| `--base-color-scale-coral-3` | `#f66945` | `#ff7b56` |
| `--base-color-scale-coral-4` | `#ef4319` | `#fe4c25` |
| `--base-color-scale-coral-6` | `#a22710` | `#c53211` |
| `--base-color-scale-coral-7` | `#801e0f` | `#a22710` |
| `--base-color-scale-coral-8` | `#500a00` | `#801e0f` |
| `--base-color-scale-coral-9` | `#3c0000` | `#500a00` |
| `--base-color-scale-green-4` | `#0fbf3e` | `#23ea57` |
| `--base-color-scale-green-8` | `#0d3024` | `#0e4a2e` |
| `--base-color-scale-green-9` | `#0a241b` | `#0d3024` |
| `--base-color-scale-indigo-1` | `#b3c1fd` | `#d4dbff` |
| `--base-color-scale-indigo-3` | `#6a7df0` | `#8e9df7` |
| `--base-color-scale-indigo-4` | `#4a5ce5` | `#6b7bef` |
| `--base-color-scale-indigo-6` | `#232fb3` | `#2d3dd7` |
| `--base-color-scale-indigo-7` | `#212183` | `#262dae` |
| `--base-color-scale-indigo-9` | `#0d103f` | `#12144f` |
| `--base-color-scale-lemon-0` | `#fcf2a5` | `#fdf5b3` |
| `--base-color-scale-lemon-1` | `#f9e76a` | `#f5e36b` |
| `--base-color-scale-lemon-2` | `#f4da38` | `#f2da3b` |
| `--base-color-scale-lemon-3` | `#e4c411` | `#e1c50f` |
| `--base-color-scale-lemon-6` | `#876a04` | `#806803` |
| `--base-color-scale-lemon-7` | `#654d02` | `#614d01` |
| `--base-color-scale-lemon-8` | `#423101` | `#413200` |
| `--base-color-scale-lemon-9` | `#241900` | `#322400` |
| `--base-color-scale-lime-1` | `#dcff96` | `#e8fc97` |
| `--base-color-scale-lime-3` | `#b1e119` | `#d1f441` |
| `--base-color-scale-lime-4` | `#88b80f` | `#b2de28` |
| `--base-color-scale-lime-6` | `#3e5f0f` | `#698e17` |
| `--base-color-scale-lime-7` | `#22360b` | `#425e13` |
| `--base-color-scale-lime-9` | `#091d05` | `#182c01` |
| `--base-color-scale-orange-1` | `#fab580` | `#fcceab` |
| `--base-color-scale-orange-3` | `#ea7110` | `#f08a3a` |
| `--base-color-scale-orange-4` | `#d56101` | `#da7210` |
| `--base-color-scale-orange-6` | `#924100` | `#954502` |
| `--base-color-scale-orange-9` | `#3d1800` | `#471700` |
| `--base-color-scale-pink-1` | `#fcabe7` | `#ffc9f2` |
| `--base-color-scale-pink-3` | `#ed55ba` | `#ff80d2` |
| `--base-color-scale-pink-4` | `#e22d9f` | `#ff4ac0` |
| `--base-color-scale-pink-5` | `#ca2186` | `#ef2aa4` |
| `--base-color-scale-pink-6` | `#961c66` | `#ca2186` |
| `--base-color-scale-pink-7` | `#741550` | `#952866` |
| `--base-color-scale-pink-8` | `#520e39` | `#651643` |
| `--base-color-scale-pink-9` | `#30081f` | `#3d0a28` |
| `--base-color-scale-purple-1` | `#d3b3fe` | `#dbbffd` |
| `--base-color-scale-purple-4` | `#8b40f5` | `#9f51fa` |
| `--base-color-scale-purple-5` | `#6619e1` | `#8534f3` |
| `--base-color-scale-purple-6` | `#43179e` | `#6619e1` |
| `--base-color-scale-purple-7` | `#26115f` | `#43179e` |
| `--base-color-scale-purple-9` | `#0e022c` | `#160048` |
| `--base-color-scale-red-3` | `#fc5c5d` | `#ff8182` |
| `--base-color-scale-red-9` | `#33000d` | `#420011` |
| `--base-color-scale-teal-1` | `#99f1e8` | `#a4efe8` |
| `--base-color-scale-teal-3` | `#26ede2` | `#39dad2` |
| `--base-color-scale-teal-4` | `#10dcd4` | `#23b1ae` |
| `--base-color-scale-teal-6` | `#079695` | `#136061` |
| `--base-color-scale-teal-7` | `#047172` | `#024b4d` |
| `--base-color-scale-yellow-1` | `#f7d162` | `#ffe777` |
| `--base-color-scale-yellow-3` | `#db9d00` | `#fabf21` |
| `--base-color-scale-yellow-4` | `#be7d00` | `#db9d00` |
| `--base-color-scale-yellow-6` | `#834800` | `#a06100` |
| `--base-color-scale-yellow-7` | `#653200` | `#824800` |
| `--base-color-scale-yellow-9` | `#2a1000` | `#471f00` |
| `--bgColor-attention-emphasis` | `#9e6a03` | `#9a6700` |
| `--bgColor-draft-muted` | `#656c7633` | `#818b981f` |
| `--bgColor-open-emphasis` | `#238636` | `#1f883d` |
| `--bgColor-open-muted` | `#2ea04326` | `#dafbe1` |
| `--bgColor-sponsors-emphasis` | `#bf4b8a` | `#bf3989` |
| `--brand-Accordion-toggle-color-red` | `#fd8986` | `#cf2230` |
| `--brand-Card-background-overlay` | `#f2f5f30d` | `#f2f5f333` |
| `--brand-FrostedGlassVFX-bgColor` | `#9c9c9c1a` | `#ffffffb3` |
| `--brand-Icon-color-coral` | `#c53211` | `#e13f1b` |
| `--brand-Label-color-green-blue-start` | `#5fed83` | `#08872b` |
| `--brand-Label-color-lime` | `#cdf041` | `#92c219` |
| `--brand-Label-color-red-orange-end` | `#f08a3a` | `#b85b06` |
| `--brand-Label-color-teal` | `#61eee3` | `#197b7b` |
| `--brand-Label-color-yellow` | `#fabf21` | `#be7d00` |
| `--brand-Tabs-item-underline-rest` | `#fff` | `#000` |
| `--brand-Testimonial-quoteMarkBackground-lime` | `#142a08` | `#f3fec8` |
| `--brand-Testimonial-quoteMarkBackground-purple-red` | `#160048` | `#f0e5ff` |
| `--brand-Testimonial-quoteMarkColor-indigo` | `#8d9ff8` | `#4956e5` |
| `--brand-Testimonial-quoteMarkColor-pink-blue-end` | `#78bafe` | `#0377ff` |
| `--brand-button-subtle-bgColor-active` | `#ffffff3d` | `#00000036` |
| `--brand-button-subtle-bgColor-hover` | `#ffffff29` | `#0000001e` |
| `--brand-color-danger-muted` | `#5e021799` | `#ffaba899` |
| `--brand-color-neutral-muted` | `#7c8980fe` | `#c4ccc6fe` |
| `--brand-color-success-muted` | `#0d302499` | `#8cf2a699` |
| `--brand-color-success-subtle` | `#0e422cd9` | `#bfffd1` |
| `--brand-color-text-link-pressed` | `#a2daff` | `#002f7a` |
| `--button-danger-bgColor-active` | `#da3633` | `#a40e26` |
| `--button-invisible-bgColor-disabled` | `#0000` | `#fff0` |
| `--button-primary-bgColor-active` | `#2e9a40` | `#197935` |
| `--button-primary-bgColor-disabled` | `#105823` | `#95d8a6` |
| `--button-primary-bgColor-hover` | `#29903b` | `#1c8139` |
| `--buttonCounter-danger-bgColor-disabled` | `#da36330d` | `#cf222e0d` |
| `--buttonCounter-danger-bgColor-rest` | `#49020233` | `#cf222e1a` |
| `--buttonCounter-outline-bgColor-disabled` | `#1f6feb0d` | `#0969da0d` |
| `--buttonCounter-outline-bgColor-rest` | `#051d4d33` | `#0969da1a` |
| `--buttonKeybindingHint-danger-bgColor-active` | `#01040966` | `#1f232866` |
| `--buttonKeybindingHint-danger-bgColor-hover` | `#01040933` | `#1f232833` |
| `--buttonKeybindingHint-invisible-bgColor-active` | `#656c7640` | `#818b9826` |
| `--buttonKeybindingHint-primary-bgColor-disabled` | `#04260f1a` | `#002d111a` |
| `--buttonKeybindingHint-primary-bgColor-rest` | `#04260f33` | `#002d1133` |
| `--codeMirror-selection-bgColor` | `#388bfd66` | `#54aeff66` |
| `--color-ansi-cyan` | `#39c5cf` | `#1b7c83` |
| `--color-ansi-cyan-bright` | `#56d4dd` | `#3192aa` |
| `--color-ansi-green-bright` | `#56d364` | `#1a7f37` |
| `--color-ansi-yellow-bright` | `#e3b341` | `#633c01` |
| `--color-bg-discussions-row-emoji-box` | `#57606a` | `#d1d5da80` |
| `--color-marketing-icon-primary` | `#79c0ff` | `#218bff` |
| `--color-mktg-btn-shadow-outline` | `#ffffff40 0 0 0 1px inset` | `#00000026 0 0 0 1px inset` |
| `--color-prettylights-syntax-brackethighlighter-unmatched` | `#f85149` | `#82071e` |
| `--color-prettylights-syntax-markup-inserted-text` | `#aff5b4` | `#116329` |
| `--color-prettylights-syntax-markup-list` | `#f2cc60` | `#3b2300` |
| `--color-prettylights-syntax-meta-diff-range` | `#d2a8ff` | `#8250df` |
| `--color-prettylights-syntax-variable` | `#ffa657` | `#953800` |
| `--color-workflow-card-header-shadow` | `#1b1f230a` | `#0000` |
| `--contribution-default-bgColor-1` | `#033a16` | `#aceebb` |
| `--contribution-default-bgColor-2` | `#196c2e` | `#4ac26b` |
| `--contribution-default-bgColor-3` | `#2ea043` | `#2da44e` |
| `--contribution-halloween-bgColor-1` | `#fac68f` | `#f0db3d` |
| `--contribution-halloween-bgColor-2` | `#c46212` | `#ffd642` |
| `--contribution-winter-bgColor-4` | `#cae8ff` | `#0a3069` |
| `--control-checked-bgColor-active` | `#3685f3` | `#0757ba` |
| `--control-checked-bgColor-hover` | `#2a7aef` | `#0860ca` |
| `--data-auburn-color-emphasis` | `#a86f6b` | `#9d615c` |
| `--data-blue-color-emphasis` | `#0576ff` | `#006edb` |
| `--data-coral-color-emphasis` | `#e1430e` | `#d43511` |
| `--data-olive-color-emphasis` | `#7a8321` | `#64762d` |
| `--data-orange-color-emphasis` | `#984b10` | `#eb670f` |
| `--data-pine-color-emphasis` | `#18915e` | `#167e53` |
| `--data-pink-color-emphasis` | `#d34591` | `#ce2c85` |
| `--data-plum-color-emphasis` | `#b643ef` | `#a830e8` |
| `--data-plum-color-muted` | `#2a0e3f` | `#f8e5ff` |
| `--data-purple-color-muted` | `#211047` | `#f1e5ff` |
| `--data-teal-color-emphasis` | `#106c70` | `#179b9b` |
| `--data-yellow-color-emphasis` | `#895906` | `#b88700` |
| `--data-yellow-color-muted` | `#2e1a00` | `#ffec9e` |
| `--diffBlob-deletionNum-bgColor` | `#f851494d` | `#ffcecb` |
| `--diffBlob-hunkNum-bgColor-rest` | `#0c2d6b` | `#b6e3ff` |
| `--display-brown-bgColor-emphasis` | `#755e3e` | `#856d4c` |
| `--display-cyan-bgColor-emphasis` | `#036a8c` | `#007b94` |
| `--display-gray-bgColor-emphasis` | `#576270` | `#647182` |
| `--display-green-bgColor-emphasis` | `#2f6f37` | `#2c8141` |
| `--display-indigo-bgColor-emphasis` | `#514ed4` | `#5a61e7` |
| `--display-lemon-bgColor-emphasis` | `#786008` | `#866e04` |
| `--display-lime-bgColor-emphasis` | `#496c28` | `#527a29` |
| `--display-lime-bgColor-muted` | `#141f0f` | `#e3f2b5` |
| `--display-purple-bgColor-emphasis` | `#7730e8` | `#894ceb` |
| `--display-red-bgColor-emphasis` | `#c31328` | `#df0c24` |
| `--highlight-neutral-bgColor` | `#d2992266` | `#fff8c5` |
| `--label-auburn-bgColor-active` | `#543331` | `#d4b7b5` |
| `--label-blue-bgColor-active` | `#00378a` | `#75c8ff` |
| `--label-blue-bgColor-hover` | `#002766` | `#ade1ff` |
| `--label-brown-bgColor-hover` | `#342a1d` | `#dfd7c8` |
| `--label-coral-bgColor-active` | `#72220d` | `#fcab92` |
| `--label-coral-bgColor-hover` | `#51180b` | `#fecebe` |
| `--label-cyan-bgColor-active` | `#014156` | `#00d0fa` |
| `--label-green-bgColor-active` | `#214529` | `#54d961` |
| `--label-green-bgColor-hover` | `#182f1f` | `#9ceda0` |
| `--label-indigo-bgColor-active` | `#312c90` | `#b1b9fb` |
| `--label-indigo-bgColor-hover` | `#25215f` | `#d2d7fe` |
| `--label-lemon-bgColor-active` | `#4f3c02` | `#d8bd0e` |
| `--label-lemon-bgColor-rest` | `#291d00` | `#f7eea1` |
| `--label-lime-bgColor-active` | `#2c441d` | `#9bd039` |
| `--label-lime-bgColor-hover` | `#1f3116` | `#c7e580` |
| `--label-olive-bgColor-active` | `#374115` | `#b9c832` |
| `--label-olive-bgColor-hover` | `#252d10` | `#dbe170` |
| `--label-olive-bgColor-rest` | `#171e0b` | `#f0f0ad` |
| `--label-orange-bgColor-active` | `#632f0d` | `#fbaf74` |
| `--label-orange-bgColor-hover` | `#43200a` | `#fecfaa` |
| `--label-orange-bgColor-rest` | `#311708` | `#ffe7d1` |
| `--label-pine-bgColor-active` | `#0e4430` | `#1dd781` |
| `--label-pine-bgColor-hover` | `#0b3224` | `#80efb9` |
| `--label-pink-bgColor-active` | `#65244a` | `#f8a5cf` |
| `--label-pink-bgColor-hover` | `#451c35` | `#fdc9e2` |
| `--label-plum-bgColor-active` | `#5c1688` | `#e2a7fb` |
| `--label-plum-bgColor-hover` | `#40125e` | `#f0cdfe` |
| `--label-purple-bgColor-active` | `#481a9e` | `#d1b1fc` |
| `--label-purple-bgColor-hover` | `#31146b` | `#e6d2fe` |
| `--label-red-bgColor-active` | `#790c20` | `#fda5a7` |
| `--label-red-bgColor-hover` | `#58091a` | `#fecdcd` |
| `--label-teal-bgColor-active` | `#0a464d` | `#22d3c7` |
| `--label-yellow-bgColor-active` | `#5a3702` | `#ebb400` |
| `--overlay-backdrop-bgColor` | `#21283066` | `#c8d1da66` |
| `--prettylights-syntax-carriageReturn-bg` | `#b62324` | `#cf222e` |
| `--prettylights-syntax-markup-changed-bg` | `#5a1e02` | `#ffd8b5` |
| `--prettylights-syntax-markup-ignored-bg` | `#1158c7` | `#0550ae` |
| `--progressBar-bgColor-neutral` | `#656c76` | `#59636e` |
| `--progressBar-bgColor-severe` | `#bd561d` | `#bc4c00` |
| `--reactionButton-selected-bgColor-hover` | `#3a8cfd5c` | `#caecff` |
| `--selection-bgColor` | `#1f6febb3` | `#0969da33` |

## Yalnız dark'ta bulunan isimler (tam liste, 96)

| Token | dark |
|---|---|
| `--avatar-bgColor` | `#ffffff1a` |
| `--base-color-scale-gray-4` | `#58635b` |
| `--base-color-scale-green-6` | `#0d6731` |
| `--base-color-scale-green-7` | `#0e422c` |
| `--base-color-scale-indigo-5` | `#2d3dd7` |
| `--base-color-scale-lime-0` | `#edffc9` |
| `--base-color-scale-lime-5` | `#608a10` |
| `--base-color-scale-pink-0` | `#ffdbf7` |
| `--base-color-scale-purple-0` | `#eadbff` |
| `--base-color-scale-red-1` | `#feb2ae` |
| `--base-color-scale-yellow-0` | `#f8e3a1` |
| `--base-color-scale-yellow-5` | `#a06100` |
| `--bgColor-attention-muted` | `#bb800926` |
| `--bgColor-closed-muted` | `#f851491a` |
| `--bgColor-done-emphasis` | `#8957e5` |
| `--bgColor-done-muted` | `#ab7df826` |
| `--bgColor-severe-muted` | `#db6d281a` |
| `--bgColor-sponsors-muted` | `#db61a21a` |
| `--brand-Icon-background-blue` | `#c2edff` |
| `--brand-Icon-background-coral` | `#ffd5c7` |
| `--brand-Icon-background-default` | `#cdfcd9` |
| `--brand-Icon-background-indigo` | `#dbe3ff` |
| `--brand-Icon-background-orange` | `#ffe2cc` |
| `--brand-Icon-background-red` | `#ffd9d6` |
| `--brand-Icon-color-orange` | `#b35101` |
| `--brand-Icon-color-teal` | `#0bbab6` |
| `--brand-Label-color-green-blue-purple-3` | `#00ff46` |
| `--brand-Label-color-green-blue-purple-4` | `#8250df` |
| `--brand-Label-color-purple` | `#c08bfc` |
| `--brand-LogoSuite-color-control-hover` | `#5a5b7c` |
| `--brand-PricingOptions-actionsMessage-accentColor` | `#1095ff` |
| `--brand-PricingOptions-actionsMessage-borderColor` | `#0e4678` |
| `--brand-Testimonial-quoteMarkBackground-blue-purple` | `#052063` |
| `--brand-Testimonial-quoteMarkBackground-indigo` | `#161962` |
| `--brand-Testimonial-quoteMarkBackground-orange` | `#572400` |
| `--brand-Testimonial-quoteMarkBackground-red` | `#5e0217` |
| `--brand-Testimonial-quoteMarkBackground-teal` | `#024b4d` |
| `--brand-Testimonial-quoteMarkBackground-yellow` | `#471f00` |
| `--brand-TextCursorAnimation-cursor-color` | `#a665f9` |
| `--brand-Token-bgColor-hover-accent` | `#8cf2a6` |
| `--brand-button-primary-bgColor-rest` | `#08872b` |
| `--brand-button-secondary-bgColor-active` | `#ffffff42` |
| `--brand-button-secondary-borderColor-hover` | `#ffffff1f` |
| `--brand-button-secondary-borderColor-rest` | `#ffffff0f` |
| `--brand-color-danger-subtle` | `#fa383dd9` |
| `--brand-color-error-emphasis` | `#d31231` |
| `--brand-color-error-fg` | `#fa383d` |
| `--brand-color-text-emphasized` | `#23ea57` |
| `--brand-color-text-error` | `#ff8182` |
| `--brand-color-text-onEmphasis` | `#000` |
| `--brand-control-checkbox-border-checked` | `#077726` |
| `--brand-control-checkbox-border-checked-hover` | `#0000001f` |
| `--brand-control-radio-dot-checked-hover` | `#309a4d` |
| `--brand-videoPlayer-playButton-bgColor-rest` | `#0a50db` |
| `--brand-videoPlayer-range-bgColor-progress` | `#0377ff` |
| `--button-outline-bgColor-active` | `#0d419d` |
| `--color-ansi-blue` | `#58a6ff` |
| `--color-ansi-green` | `#3fb950` |
| `--color-ansi-magenta` | `#be8fff` |
| `--color-ansi-red` | `#ff7b72` |
| `--color-ansi-red-bright` | `#ffa198` |
| `--color-prettylights-syntax-constant-other-reference-link` | `#a5d6ff` |
| `--color-prettylights-syntax-markup-changed-text` | `#ffdfb6` |
| `--color-prettylights-syntax-markup-deleted-text` | `#ffdcd7` |
| `--color-prettylights-syntax-string-regexp` | `#7ee787` |
| `--color-project-gradient-out` | `#161b2200` |
| `--color-user-mention-fg` | `#d29922` |
| `--contribution-halloween-bgColor-4` | `#e3d04f` |
| `--control-checked-bgColor-rest` | `#1f6feb` |
| `--data-brown-color-emphasis` | `#94774c` |
| `--data-coral-color-muted` | `#351008` |
| `--data-lemon-color-emphasis` | `#977b0c` |
| `--data-lime-color-emphasis` | `#5f892f` |
| `--data-purple-color-emphasis` | `#975bf1` |
| `--data-red-color-emphasis` | `#eb3342` |
| `--data-red-color-muted` | `#3c0614` |
| `--diffBlob-additionNum-bgColor` | `#3fb9504d` |
| `--diffBlob-additionWord-bgColor` | `#2ea04366` |
| `--diffBlob-deletionWord-bgColor` | `#f8514966` |
| `--diffBlob-hunkLine-bgColor` | `#388bfd1a` |
| `--display-auburn-bgColor-emphasis` | `#87534f` |
| `--display-blue-bgColor-emphasis` | `#005bd1` |
| `--display-indigo-bgColor-muted` | `#1b183f` |
| `--display-olive-bgColor-emphasis` | `#5e681d` |
| `--display-pine-bgColor-emphasis` | `#14714c` |
| `--display-pink-bgColor-emphasis` | `#ac2f74` |
| `--display-pink-bgColor-muted` | `#2d1524` |
| `--display-plum-bgColor-emphasis` | `#9518d8` |
| `--header-bgColor` | `#151b23f2` |
| `--label-auburn-bgColor-hover` | `#3a2422` |
| `--label-blue-bgColor-rest` | `#001a47` |
| `--label-brown-bgColor-active` | `#483a28` |
| `--label-lemon-bgColor-hover` | `#372901` |
| `--label-yellow-bgColor-hover` | `#3d2401` |
| `--prettylights-syntax-markup-deleted-bg` | `#67060c` |
| `--reactionButton-selected-bgColor-rest` | `#388bfd33` |

## Yalnız light'ta bulunan isimler (tam liste, 50)

| Token | light |
|---|---|
| `--avatarStack-fade-bgColor-default` | `#c8d1da` |
| `--base-color-scale-blue-1` | `#bcecff` |
| `--base-color-scale-blue-2` | `#8dd6ff` |
| `--base-color-scale-blue-3` | `#5fb9ff` |
| `--base-color-scale-green-2` | `#8cf2a6` |
| `--base-color-scale-green-3` | `#5fed83` |
| `--base-color-scale-indigo-2` | `#b3c1fd` |
| `--base-color-scale-indigo-8` | `#212183` |
| `--base-color-scale-lime-2` | `#dcfa67` |
| `--base-color-scale-lime-8` | `#2c440b` |
| `--base-color-scale-orange-2` | `#f4a876` |
| `--base-color-scale-orange-8` | `#5c2300` |
| `--base-color-scale-purple-2` | `#c898fd` |
| `--base-color-scale-purple-3` | `#b870ff` |
| `--base-color-scale-purple-8` | `#26115f` |
| `--base-color-scale-red-2` | `#ffaba8` |
| `--base-color-scale-red-4` | `#fa4549` |
| `--base-color-scale-red-8` | `#730019` |
| `--base-color-scale-teal-2` | `#6ee5dc` |
| `--base-color-scale-teal-8` | `#083d3d` |
| `--base-color-scale-yellow-2` | `#ffd743` |
| `--base-color-scale-yellow-8` | `#653200` |
| `--brand-Accordion-toggle-color-end` | `#0d6731` |
| `--brand-Token-bgColor-hover-outline` | `#0000000f` |
| `--brand-color-neutral-emphasis` | `#77827a` |
| `--brand-color-neutral-subtle` | `#e4ebe6fe` |
| `--brand-color-success-emphasis` | `#0fbf3e` |
| `--brand-color-text-muted` | `#58635b` |
| `--brand-control-checkbox-fg-checked-disabled` | `#fff` |
| `--button-outline-bgColor-hover` | `#0969da` |
| `--color-ansi-magenta-bright` | `#a475f9` |
| `--color-ansi-yellow` | `#4d2d00` |
| `--color-prettylights-syntax-entity` | `#6639ba` |
| `--contribution-halloween-bgColor-3` | `#f68c41` |
| `--contribution-winter-bgColor-2` | `#54aeff` |
| `--control-danger-bgColor-active` | `#ffebe966` |
| `--controlTrack-bgColor-disabled` | `#818b98` |
| `--data-gray-color-emphasis` | `#808fa3` |
| `--data-green-color-emphasis` | `#30a147` |
| `--data-teal-color-muted` | `#c7f5ef` |
| `--display-green-bgColor-muted` | `#caf7ca` |
| `--display-orange-bgColor-emphasis` | `#b8500f` |
| `--display-teal-bgColor-emphasis` | `#127e81` |
| `--display-yellow-bgColor-emphasis` | `#946a00` |
| `--label-cyan-bgColor-hover` | `#7ae9ff` |
| `--label-cyan-bgColor-rest` | `#bdf4ff` |
| `--label-pine-bgColor-rest` | `#bff8db` |
| `--label-teal-bgColor-hover` | `#89ebe1` |
| `--prettylights-syntax-invalid-illegal-text` | `#d1242f` |
| `--skeletonLoader-bgColor` | `#818b981a` |

## Tüketici için sonuçlar

1. **Tek kaynak seç.** `tokens.css` (dark) ve `tokens.light.css` aynı
   cascade'e import edilirse 195 adda değer çakışır ve sıralama kazananı
   belirler — hangi temanın göründüğü import sırasına bağlı, kasıtlı bir
   karar olmaktan çıkar.
2. **Tema anahtarı `data-color-mode`.** Yakalama bunu kanıtlar: sayfa dark
   iken `--bgColor-default` `#0d1117`, `light` pinlendiğinde `#fff`.
3. **Yalnız farkları değil, küme farkını da hesaba kat.** Yalnız dark'ta
   96, yalnız light'ta 50 isim var; bir tema için yazılan bileşen diğerinde
   token'sız kalabilir.
4. **Semantik eşleme yapma.** `base-color-scale-*` örneği gösteriyor ki
   aynı adım numarası iki temada aynı rolü taşımıyor; otomatik yeniden
   adlandırma veya toplu değer eşlemesi yanlış eşleme üretir.

## Yeniden üretim

```bash
python3 design-system/github/scripts/check_github_tokens.py --sync   # iki katman
python3 design-system/github/scripts/report_theme_diff.py --check    # bu rapor

# yakalamayı yenile (evidence tooling; repo runtime bağımlılığı değil)
cd /tmp/gh-capture && npm install --no-save playwright@1.63.0 dembrandt@0.7.3
./node_modules/.bin/playwright install chromium
cp <repo>/design-system/github/scripts/capture_theme.mjs .
node capture_theme.mjs light <repo>/design-system/github/raw.light.json
```

## Kanıt dosyaları

- `design-system/github/raw.json`
- `design-system/github/raw.light.json`
- `design-system/github/tokens.css`
- `design-system/github/tokens.json`
- `design-system/github/tokens.light.css`
- `design-system/github/tokens.light.json`
- `design-system/github/scripts/capture_theme.mjs`
- `design-system/github/scripts/check_github_tokens.py`
- `design-system/github/scripts/report_theme_diff.py`
- `design-system/github/README.md`
