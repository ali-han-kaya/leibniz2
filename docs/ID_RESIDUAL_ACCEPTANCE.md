# /ID Kalıntısı Kabul Raporu — TeXLive Göçü (Faz 3)

**Plan:** `docs/TEXLIVE_MIGRATION_PLAN.md` (Faz 3) · **Tarih:** 2026-09-20
**Kapsam:** `ingiliz_empirizmi_v3.pdf` derleme determinizminin kabul
referansının tanımı, ölçümleri ve hash geçiş defteri.
**Bağlı rapor:** `docs/FINAL_RC_REPORT.md` (TeXLive determinizm bölümü).

## 1. Kalıntının tanımı ve kök nedeni

pdfTeX her koşumda PDF trailer'ına rastgele bir belge kimliği yazar:

```
/ID [<32-hex> <32-hex>]
```

`SOURCE_DATE_EPOCH` (SDE) `/CreationDate` ve `/ModDate` alanlarını
sabitler ancak `/ID`'yi **sabitlemez** — SDE=0 ile bile iki koşumun ham
bayt-akışı farklıdır. Ölçülen tek fark bu trailer `/ID` satırıdır;
`/ID` dışındaki tüm baytlar birebir aynıdır (§2).

## 2. Ölçüm (2026-09-16/17 deneyleri; 2026-09-20'de tekrar doğrulandı)

| Deney | Sonuç |
|---|---|
| pdfTeX tek-geçiş, 2 bağımsız koşum (SDE=0) | ham hash farklı (`da868c13…` ↔ `014bed9a…`); `/ID` örnekleri `1DAE9033…` ↔ `106F825B…` — **tek fark `/ID`** |
| Kanonik normalizasyon (aynı koşumlar) | `/ID [<0…0> <0…0>]` ile nötrlenince kanonik hash ×2 birebir aynı: `a75c3409…` |
| pdfTeX 3-geçiş pipeline, 2 bağımsız koşum (SDE=0) | kanonik `544516b0d9d2f4c12b05b512b79b31ad238e82d3ca3aff81166a6bac1914f597` ×2 birebir aynı (`make -f docs/Makefile.texlive check` kabul değeri) |
| tectonic 0.17.0 (SDE=0), bağlamlar arası | ham hash kararlı: `ad8fca69…` (kararlı olduğundan raw = kanonik) |
| qpdf 12.4.0 `--static-id` | girdi `/ID`'sini korur; kalıntıyı gideremez (skill donmuş bulgusu + bu makinede tekrar ölçüldü) |
| qpdf 12.4.0 `--remove-metadata` | kendisi nondeterministik (V5l: aynı girdi 3 koşum 3 farklı çıktı `b090ac01…`/`429984da…`/`509a47a6…`) — kalıntıyı gideremez |

Kanonikleştirme uygulaması: `canonical_sha` —
`_calisma/CIKTI/texlive_determinism_test.sh` (`/ID` çiftini
`<0…0>` çiftine indirger; desen eşleşmezse ham hash döner — fail-safe:
hiçbir fark gizlenmez).

## 3. Kabul kararı

1. Teslim boru hattı determinizm referansı **`/ID`-kanonik hash**'tir
   (`/ID [<0…0> <0…0>]` normalizasyonu). Ham hash yalnız bilgi amaçlıdır.
2. Aynı motor + aynı kaynak + aynı SDE içinde kanonik hash'in koşumlar
   arası birebir eşitliği determinizmin kanıtıdır.
3. **Çapraz-motor kanonik eşitlik beklenmez** (font/ligatür/hinting
   farkları — ölçüldü). Motor geçişi kanonik hash değişimi olarak §4
   defterine yazılır; hata olarak raporlanmaz.

## 4. Hash geçiş defteri (tectonic ↔ TeXLive)

> Plan Faz 7: bu defter iki motorlu dönem boyunca geçerli kalır. Kanonik
> hash yalnız `/ID`'yi nötrler; `/Info` tarihleri kanonikte kalır, dolayısıyla
> kanonik hash **SDE'ye bağlıdır** — defter satırları SDE bağlamını taşır.
> Yeni bağlam (CI, font paketi) → **yeni satır**; eskisinin üzerine asla
> yazma (Faz 6 çıkış yolu: `make accept` yeni hash'i görünce defterde
> arar, yoksa fail-closed eder).

| # | Motor / sürüm | Geçiş | SDE | Ham (bilgi) | Kanonik (referans) | Ölçüm |
|---|---|---|---|---|---|---|
| 1 | tectonic 0.17.0 | 1 | 0 | `ad8fca69d4e4a2e1d67e497c8a7449f22c8564f5e9b3790d0b6f85d90d318e1b` (bağlamlar arası kararlı; raw = kanonik) | `ad8fca69d4e4a2e1d67e497c8a7449f22c8564f5e9b3790d0b6f85d90d318e1b` | ci_simulate + trend baseline (darwin, 2026-09-17) |
| 2 | tectonic 0.17.0 | 3-geçiş pipeline | 0 | — (plan probe'u) | `47681218…` (plan-donmuş önek) | planın probe'ları (2026-09-17) |
| 3 | pdfTeX 3.141592653-2.6-1.40.29 (TeX Live 2026/Homebrew) | 1 | 0 | koşum-başına değişken (`da868c13…`/`014bed9a…`) | `a75c340911801273b38be6ffb51a34820764b8f812d528dd2705d64117f1aa00` | ci_simulate 2× koşum + trend baseline |
| 4 | pdfTeX 3.141592653-2.6-1.40.29 | 3 | 0 | koşum-başken değişken (`/ID`) | `544516b0d9d2f4c12b05b512b79b31ad238e82d3ca3aff81166a6bac1914f597` | `make check` 2× bağımsız koşum (Faz 1 kabul; 2026-09-20 tekrar ×2) |
| 5 | **teslim artefaktı** `TESLIM_V5_FINAL_2026-08-17/.../ingiliz_empirizmi_v3.pdf` | teslim öncesi derleme | SDE kaydı yok (derleme tarihi belgelenmemiş) | `74b2cdbdb18fafbf5b3c87570c92f1500e7580469bcf4295b09734116df0779f` (teslimde donmuş) | `d4f67e39fd0ef77e8f294ca2195bb1fc784716234d0675ab88a4fd8695263a6a` | 2026-10-01 K6-DETERM ölçümü — **bu satır K6-DETERM strict karşılaştırmasının okuduğu referanstır** (§6) |

### Satır 5 neden ayrı? (2026-10-01 ölçümü)

Teslimdeki PDF, defterdeki dört ölçümün **hiçbirine** eşit değil:
kanonik hash'i `d4f67e39…`, yani ne tectonic 1-geçiş (`ad8fca69…`) ne
tectonic 3-geçiş (`47681218…` önek) ne pdfTeX 1-geçiş (`a75c3409…`) ne
de pdfTeX 3-geçiş (`544516b0…`). Defter protokolü gereği (yeni bağlam →
**yeni satır**, eskisinin üzerine yazma) teslim artefaktı kendi satırını
aldı; üstüne yazılmadı.

Aynı gün pdfTeX 3-geçiş satırı da yeniden doğrulandı:
`SOURCE_DATE_EPOCH=0 make -f docs/Makefile.texlive check` → iki bağımsız
koşumun kanonik hash'i `544516b0…` (birebir aynı), `residual=/ID`,
`verdict=PASS`. Yani satır 4 hâlâ üretilebilir; teslim PDF'i yalnızca
**henüz TeXLive ile yeniden derlenmemiş** bir artefakt (aşağıdaki
"TeXLive-era teslim" satırı hâlâ `—`).

Bu ikisi birbirine bağlı: teslim yeniden derlendiğinde satır 5'in hash'i
kaybolacak değil — kanonik hash değişecek ve o değişim **bilinçli** olarak
yeni bir satır + sidecar yenilemesi olacak (aşağıdaki protokol).

### Teslim sidecar'ı geçiş kaydı (`PDF_METADATA_SIDECAR` deseni)

| Dönem | Ham PDF (bilgi) | Metadata-stripped | Durum |
|---|---|---|---|
| tectonic-era teslim (V5l; mevcut) | `74b2cdbdb18fafbf5b3c87570c92f1500e7580469bcf4295b09734116df0779f` | `50263bcf60f9ae176ac417f025bffbcae4fd0ab6044566672827bee861f83732` | yanındaki sidecar: `ingiliz_empirizmi_v3.pdf.metadata.sha256` |
| TeXLive-era teslim | — (Faz 4 repack akışı kanıtlayınca buraya yazılır) | — | beklemede (bilinçli yenileme) |

## 5. Etki ve yenileme protokolü

- zip/zip_lineage ve `PDF_METADATA_SIDECAR` desenindeki ham-PDF hash'i
  motor değişiminde değişir → motor geçişi **tek seferlik bilinçli
  sidecar yenilemesi** ile işaretlenir. V5l kuralı zaten bunu güvenli
  kılar: repack sidecar'ı yalnız ham hash değişince yeniler; bu kola
  yalnız geçiş dokunur.
- `make -f docs/Makefile.texlive accept`: önce `check`'i koşturur (taze
  2× koşum kanıtı), sonra kanonik hash'i §4 defterinde arar. Defterde
  yoksa fail-closed: yeni bağlam → deftere bilinçli satır eklenir,
  sahte kabul üretilmez.

## 6. Faz 4 uygulaması: `--strict-determinism` semantiği (2026-10-01)

**Eski gerekçe yanlıştı.** MANIFEST V5k ve K6-DETERM yorumu “tectonic
0.17.0 byte-deterministic değildir, bu yüzden strict kapalı” diyordu.
Ölçüm bunu tersine çevirdi:

| İddia (eski) | Ölçüm (2026-10-01) |
|---|---|
| motor non-deterministic | motor `SOURCE_DATE_EPOCH` ile **deterministik**; aynı kaynak + aynı SDE → kanonik hash iki bağımsız koşumda birebir aynı (`544516b0…`, `make check` SDE=0) |
| belirsizlik metadata-stripped hash’te | belirsizlik **pdfTeX trailer `/ID`**’de; kanonik görünümde nötrleniyor (§1-2) |
| strict, metadata-stripped hash’e açılabilir | **hayır** — `qpdf --remove-metadata` **kendisi** nondeterministik: aynı teslim PDF’inde 3 koşum → `2042ba8b…` / `7f9125d0…` / `c9b9890d…`, hiçbiri sidecar’daki `50263bcf…` ile eşleşmedi. Strict buna uygulansaydı kapı **her koşumda yanlış pozitif** üretirdi |

**Uygulanan sözleşme (Faz 4):**

1. K6-DETERM iki yüzeyi ayrı raporlar:
   - `stripped` (qpdf) → **yalnız BİLGİ**. Kararsız olduğu ölçüldüğü için
     strict karşılaştırmaya **giremez**.
   - `canonical` (`/ID` nötrlü) → **strict**. Uygulama tek kaynaktır
     (`_calisma/CIKTI/pdf_id_canonical.py`); shell determinism betiği de
     aynı modülü okur — regex’in iki kopyası iki gerçeklik yaratırdı.
2. Strict karşılaştırma **bu defterin §4 tablosunun “Kanonik (referans)”
   sütununa** karşı yapılır. Hash’i kod değil doküman taşır; kısaltılmış
   önekler (`47681218…`) kabul edilmez, yalnız ölçülmüş tam 64-hex.
3. **Varsayılan açık**: `--strict-determinism` default `True`;
   `--no-strict-determinism` ile kapatılır (yalnız teşhis).
4. Hash defterde yoksa **P1 (fail-closed)** + çıkış yolu yazılır:
   `make -f docs/Makefile.texlive accept`. Defter okunamaz/boşsa da P1 —
   “kapı yok” hiçbir koşulda yeşil sayılmaz.

Bugün teslim artefaktı `d4f67e39…` = §4 satır 5 → kapı yeşil. Teslim
yeniden derlenirse hash değişir ve kapı **kırmızıya düşerek** zorunlu
“bilinçli yeni satır + sidecar yenilemesi” adımına sokar; sessizce
geçmez.

## 7. Geri dönüş (Faz 7)

`docs/Makefile.tectonic` ve eski sidecar'lar repo'da kalır; Faz 1-6
commit'leri `git revert` ile geri alınabilir. Bu defter geri dönüşte de
iki motorlu dönemin kanıt kaydı olarak durur.
