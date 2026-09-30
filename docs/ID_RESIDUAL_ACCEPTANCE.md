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
| qpdf 12.4.0 `--remove-metadata` | kendisi nondeterministik (V5l: aynı girdi 3 koşum 3 farklı çıktı `b090ac01…`/`429984da…`/`509a47a6…`; 2026-09-30'da teslim PDF'i üzerinde YENİDEN ölçüldü: `38fc668c…`/`747334c4…`/`0de3124d…`; aynı gün `verify_delivery.py` koşumu 4. farklı değeri üretti: `de8be5a0…`) — kalıntıyı gideremez |
| Teslim PDF'inin kanonik hash'i (2026-09-30) | `/ID` nötrlenince 3× ölçümde birebir aynı: `d4f67e39fd0ef77e8f294ca2195bb1fc784716234d0675ab88a4fd8695263a6a` (ham `74b2cdbd…` koşum/araç bağımlı değil) |

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
> arar, yoksa fail-closed eder). Satırlar **elle yazılmaz**: ölçülen
> alanlardan `make -f docs/Makefile.texlive accept LEDGER=update`
> (yani `_calisma/CIKTI/gen_id_residual_acceptance.py`) üretir.

| # | Motor / sürüm | Geçiş | SDE | Ham (bilgi) | Kanonik (referans) | Ölçüm |
|---|---|---|---|---|---|---|
| 1 | tectonic 0.17.0 | 1 | 0 | `ad8fca69d4e4a2e1d67e497c8a7449f22c8564f5e9b3790d0b6f85d90d318e1b` (bağlamlar arası kararlı; raw = kanonik) | `ad8fca69d4e4a2e1d67e497c8a7449f22c8564f5e9b3790d0b6f85d90d318e1b` | ci_simulate + trend baseline (darwin, 2026-09-17) |
| 2 | tectonic 0.17.0 | 3-geçiş pipeline | 0 | — (plan probe'u) | `47681218…` (plan-donmuş önek) | planın probe'ları (2026-09-17) |
| 3 | pdfTeX 3.141592653-2.6-1.40.29 (TeX Live 2026/Homebrew) | 1 | 0 | koşum-başına değişken (`da868c13…`/`014bed9a…`) | `a75c340911801273b38be6ffb51a34820764b8f812d528dd2705d64117f1aa00` | ci_simulate 2× koşum + trend baseline |
| 4 | pdfTeX 3.141592653-2.6-1.40.29 | 3 | 0 | koşum-başına değişken (`/ID`) | `544516b0d9d2f4c12b05b512b79b31ad238e82d3ca3aff81166a6bac1914f597` | `make check` 2× bağımsız koşum (Faz 1 kabul; 2026-09-20 tekrar ×2) |

### Teslim sidecar'ı geçiş kaydı (`PDF_METADATA_SIDECAR` deseni)

| Dönem | Ham PDF (bilgi) | Metadata-stripped | Kanonik `/ID`-nötr (referans) | Durum |
|---|---|---|---|---|
| tectonic-era teslim (V5l; mevcut) | `74b2cdbdb18fafbf5b3c87570c92f1500e7580469bcf4295b09734116df0779f` | `50263bcf60f9ae176ac417f025bffbcae4fd0ab6044566672827bee861f83732` | `d4f67e39fd0ef77e8f294ca2195bb1fc784716234d0675ab88a4fd8695263a6a` | yanındaki sidecar: `ingiliz_empirizmi_v3.pdf.metadata.sha256`; kanonik referans 2026-09-30'da 3× ölçüldü (kararlı) |
| TeXLive-era teslim | — (Faz 4 repack akışı kanıtlayınca buraya yazılır) | — | — | beklemede (bilinçli yenileme) |

Kanonik kolon **strict kapının referansıdır**: `verify_delivery.py
--strict-determinism`, teslim PDF'inin `/ID`-kanonik hash'ini bu defterde
arar; bulamazsa P1 verir ve `make -f docs/Makefile.texlive accept
LEDGER=update` ile bilinçli yenileme ister.

Defter çözümlemesi + `/ID` normalizasyonu **ortak çekirdektedir**
(`_calisma/CIKTI/id_canonical.py`): aday sırası `ID_RESIDUAL_LEDGER` env →
`<repo>/docs/ID_RESIDUAL_ACCEPTANCE.md` → script yanındaki mirror kopyası.
`verify_delivery.py`, `_calisma/repack_delivery.py` ve K14
(`check_zip_lineage_drift.py`) aynı modülü kullanır (kopya regex/defter
yoktur). Motor geçişi/yeniden paketleme bu satırı **güncellemeden** geçemez
(Faz 4): repack yeni kanoniği yazmadan önce defterde arar (fail-closed),
K14 de commit anında sidecar `# canonical:` referansını defterle
karşılaştırır.

## 5. Etki ve yenileme protokolü

- **Motor geçişi hash ikilisi (eski → yeni):** tectonic (0.17.0) tek-geçiş
  `ad8fca69…` / 3-geçiş `47681218…` → TeXLive/pdfTeX tek-geçiş
  `a75c3409…` / 3-geçiş `544516b0…`. Kanonik eşitlik beklenmez (§3); ikili
  yalnız defterde kayıtlıdır, hata olarak raporlanmaz.
- zip/zip_lineage ve `PDF_METADATA_SIDECAR` desenindeki ham-PDF hash'i
  motor değişiminde değişir → motor geçişi **tek seferlik bilinçli
  sidecar yenilemesi** ile işaretlenir. V5l kuralı zaten bunu güvenli
  kılar: repack sidecar'ı yalnız ham hash değişince yeniler; bu kola
  yalnız geçiş dokunur. Yenilemede sidecar artık **dört satır** taşır:
  `<stripped>  …` + `# raw:` + **`# canonical:`** (determinizm referansı) +
  **`# renewal: <tarih> — gerekçe`**. `repack_delivery.py` yeni kanoniği
  yazmadan ÖNCE `check_ledger_entry` ile defterde arar; kayıtlı değilse
  fail-closed durur (exit 1) — önce `accept LEDGER=update` koşmalıdır. Bu
  sidecar sözleşmesi `verify_delivery.py` K6-DETERM (sidecar ↔ PDF kanoniği
  uyuşmazsa strict'te P1) ve K14 kapısıyla birlikte kapanır.
- `make -f docs/Makefile.texlive accept`: önce `check`'i koşturur (taze
  2× bağımsız 3-geçiş ölçümü), sonra kanıtı **gerçek üreticiye** verir:
  `_calisma/CIKTI/gen_id_residual_acceptance.py` raporu ayrıştırır
  (verdict=PASS + rerun=0 ×2 + run1=run2), kanonik hash'i §4 defterinde
  arar. Defterde yoksa fail-closed — sahte kabul üretilmez. Yeni bağlam
  için satır ÖLÇÜLEN alanlardan **`LEDGER=update`** ile üretilir; defter
  satırı elle yazılmaz.

## 6. Faz 4 — `--strict-determinism` semantiği (UYGULANDI 2026-09-30)

`verify_delivery.py` K6-DETERM artık **`/ID`-kanonik hash** üzerine
kuruludur (`canonical_pdf_sha256` = `/ID` çiftini `<0…0>`'a indirgeyen
SHA-256; desen yoksa ham hash — fail-safe):

- **Bilgi (default):** ham, metadata-stripped ve kanonik hash'ler
  raporlanır; P1 üretilmez. `--json` çıktısında `pdf_hash.canonical`.
- **Strict (`--strict-determinism`):** kanonik hash §4 defterinde kayıtlı
  değilse **P1** + remedy (`make … accept LEDGER=update`); defter
  okunamıyorsa ya da PDF okunamıyorsa fail-closed P1 (referanssız
  determinizm iddiası üretilmez).
- **metadata-stripped hash artık P1 nedeni DEĞİL.** Eski yorum "tectonic
  non-deterministic olduğundan strict karşılaştırma her repack'te yanlış
  pozitif üretir" idi; ölçüm bu teşhisi düzeltir: (a) motor SDE ile
  deterministiktir, tek kalıntı `/ID`'dir (§1-2); (b) qpdf
  `--remove-metadata`'nın **kendisi** nondeterministiktir (§2 tablosu:
  aynı girdi 3 koşum → 3 farklı hash `38fc668c…`/`747334c4…`/`0de3124d…`).
  Yani stripped hash karşılaştırması her koşumda tanım gereği "drift"
  verir — karar buna bağlanamaz, yalnız bilgi olarak raporlanır.
- Bu bölümün eski sözü ("strict mod `/ID`-kanonik karşılaştırmaya
  bağlanır; karşılaştırma §4 defterindeki kanonik referansa karşı
  yapılır") yerine getirildi ve bayrak artık **ETKİN** (Faz 4, 2026-09-30):
  pre-commit `verify_delivery_hook.py` iç çağrısı ile CI `verify.yml`
  `--full` adımı `--strict-determinism` ile koşar. MANIFEST V5k'nin
  çekincesi (metadata-stripped karşılaştırması her repack'te yanlış
  pozitif üretir) artık geçersizdir: strict karşılaştırma **kararlı
  `/ID`-kanonik hash** üzerindedir ve bu hash §4 defterinde kayıtlıdır —
  teslim PDF'i hâlâ tectonic-era (üstteki satır 1) olsa da strict geçer.
  V5k notu üretilmiş `MANIFEST.txt` içinde tarihsel kayıt olarak durur
  (teslim zip hash'i sabit kalsın diye dosya değiştirilmez).
- **Sidecar ↔ PDF kanonik uyuşmazlığı** strict modda **P1**'dir: repack'in
  yazdığı `# canonical:` satırı (sidecar) teslim PDF'inden yeniden
  hesaplanan kanonikle aynı olmalıdır — ayrı düşerse yenileme/senkron eksik
  demektir. `# canonical:` satırı yoksa (henüz yenilenmemiş tectonic-era
  sidecar) yalnız bilgi düzeyinde raporlanır (K14 de INFO verir).

## 7. Geri dönüş (Faz 7)

`docs/Makefile.tectonic` ve eski sidecar'lar repo'da kalır; Faz 1-6
commit'leri `git revert` ile geri alınabilir. Bu defter geri dönüşte de
iki motorlu dönemin kanıt kaydı olarak durur.
