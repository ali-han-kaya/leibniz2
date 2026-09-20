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
| 4 | pdfTeX 3.141592653-2.6-1.40.29 | 3 | 0 | koşum-başına değişken (`/ID`) | `544516b0d9d2f4c12b05b512b79b31ad238e82d3ca3aff81166a6bac1914f597` | `make check` 2× bağımsız koşum (Faz 1 kabul; 2026-09-20 tekrar ×2) |

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

## 6. Faz 4 referansı: `--strict-determinism` yeni semantiği

- Bugün (tectonic-era): `verify_delivery.py` K6-DETERM, qpdf
  metadata-stripped hash drift'ini bilgi düzeyinde raporlar;
  `--strict-determinism` OFF (MANIFEST V5k notu).
- Faz 4'te: strict mod `/ID`-kanonik karşılaştırmaya bağlanır ve
  K6-DETERM'in "tectonic non-deterministic" yorumu bu raporun ölçümüyle
  güncellenir (SDE ile deterministik; kalıntı `/ID` — §1-2). Strict
  karşılaştırma §4 defterindeki kanonik referansa karşı yapılır.

## 7. Geri dönüş (Faz 7)

`docs/Makefile.tectonic` ve eski sidecar'lar repo'da kalır; Faz 1-6
commit'leri `git revert` ile geri alınabilir. Bu defter geri dönüşte de
iki motorlu dönemin kanıt kaydı olarak durur.
