# RCA — teslim zip'i kaynakla senkron değildi (INC-4)

**Tarih:** 2026-10-05
**Olay kaydı:** `docs/KNOWN_INCIDENTS.md` → INC-4
**Kapsam:** yalnız repack/sidecar kök nedeni (kapının ölçüm hataları ayrı konudur)
**Durum:** ✅ Kök neden giderildi ve ölçüldü

## 1. Özet

`main`'e push, tek bir zorunlu kontrol kırmızı olduğu için reddedildi:
**Repack determinism + verify (sidecar sync)**. Job log'unda tek dosya sapıyordu —
teslim zip'inin içindeki `ingiliz_empirizmi_v3.tex` kopyası kaynaktan küçüktü.
Yani teslim artifact'ı, onu üreten kaynaktan **eskiydi**.

İki ayrı katman birlikte bu olayı üretti:

1. **Kayma (drift):** son repack çalıştığı tarihten sonra TeX kaynağı değişmiş,
   ama zip yeniden üretilmemişti.
2. **Sözleşleşme katmanı:** zip tazelendiğinde, kayıt defterleri
   (`zip_lineage.json`, `cleanup_log.json`) de **aynı commit'te** güncellenmek
   zorundadır. Aksi halde K14 `check_zip_lineage_drift.py` kırmızıya döner.

İkinci katman, ilk denemeyi (yalnız repack) geçersiz kıldı.

## 2. Olay zinciri

| Zaman | Olay | Kanıt |
|---|---|---|
| 2026-09-30 | main temizliği: ağaç yeniden kuruldu (`origin/main` = `df94b8e`) | `docs/HISTORY_CLEANUP.md` |
| 2026-10-02 | **Son başarılı repack** (`8beca13`) — kaynakla senkron | `8beca13` |
| 2026-10-03 | **Kaynak değişti**: `ingiliz_empirizmi_v3.tex` düzeltmesi (`5a1a981`) — repack koşmadı | `5a1a981` |
| 2026-10-05 | Yerel main `b79b66e` (origin/main'in 14 ilerisi) push edildi → **GH006** | push reddi |
| 2026-10-05 | Pre-fix doğrulama: verify-delivery `37257949738` → Repack job **failure**, K1–K19 yeşil | run `37257949738` |
| 2026-10-05 | İlk onarım denemesi (yalnız repack, `8b01dd3`) → K14 kırmızı | yerel koşu |
| 2026-10-05 | Kesin onarım: `3f7f88f` (repack + registry resync, tek commit) | `3f7f88f` |
| 2026-10-05 | Push geçti: `77d05e3`, ardından `b1f5f1e`, `d566be2` | main geçmişi |

Anahtar sıra: **`8beca13` (repack) → `5a1a981` (kaynak)**. Repack, kaynağın
değişmesinden sonra hiç çalışmadı.

## 3. Kök neden

### 3.1 Birincil: artifact üretimi kaynak değişikliğine bağlı değil

Teslim zip'i **elle**, "son teslim" anında üretilen bir çıktıdır. Depoda onu
kaynağa bağlayan bir bağımlılık yoktur: `ingiliz_empirizmi_v3.tex` değiştiğinde
hiçbir şey "zip'i yeniden üret" demiyor. Bu yüzden kayma, yalnızca
zorunlu kontrollerin *repack'i sonuç olarak karşılaştırmasıyla* görünür hale
geliyor — yani hata ancak push denendiğinde ortaya çıkıyor.

Kanıtlanmış ölçüm (pre-fix): kaynak **76846 B**, zip içi kopya **76478 B**
(−368 B). Tek dosyada, tek yönde, tam "eski üretim" imzası.

### 3.2 İkincil: iki katmanlı sözleşme, tek adımda kapatılmıyor

`check_zip_lineage_drift.py` (K14) şunu zorunlu tutar:

- `zip_lineage.json`: üretilen nesil ↔ canlı dış zip
- `cleanup_log.json`: kanonik hash'ler ↔ canlı zip

Bu kayıt defterleri zip'e **göre** anlamlıdır. Zip'i tazeleyip defterleri
ayrı commit'te bırakmak, defterleri kasıtlı olarak bayatlatır — yani "zip'i
tazele" adımının kendisi K14'ü kırmızıya düşürür. Doğru birim: **zip + iki
kayıt defteri, tek commit**.

## 4. Neden geç fark edildi

- Kaynak değişikliği (`5a1a981`) bir **içerik** commit'i; repack bir **build**
  adımı. İkisi arasındaki bağı hiçbir hook zorlamıyor.
- `Delivery verification — K1-K19` yeşildi: teslim mantığı doğru, artifact
  bayat. Yani yeşil kontrol "her şey yolunda" izlenimi veriyordu; sapmayı
  yalnız repack işi görüyordu.
- 30 Eylül temizliği `origin/main`'i 14 commit geriye bıraktı; yerel main
  ancak o noktada push denemesiyle zorunlu kontrollerle karşılaştı.

## 5. Çözüm ve ölçülebilir kanıt

`3f7f88f` tek commit'te iki katmanı birlikte kapatıyor:

| Kanıt | Değer |
|---|---|
| `TESLIM_V5_FINAL_2026-08-17.zip` boyutu | 473464 → **473658 B** |
| `TESLIM_KLASOR_V5_2026-08-17.zip` boyutu | 511887 → **512086 B** |
| İç zip SHA-256 (V5_FINAL) | `b37f45cf0860d3a9770cbf41994de4ca71e468e5701a678cb1aae9d65b677cc8` |
| CI'ın beklediği hash | `b37f45cf0860d3a9…` → **birebir aynı** |
| İç zip SHA-256 (KLASOR) | `541e59f21702db049d7326b4f5c2d6699fe84e1987c1601aa3565f5912f73c3d` |
| Yerel `ci_replay` | 2/2 zip byte-identical, P0=0 / P1=0 |
| Push sonrası | `77d05e3`, `b1f5f1e`, `d566be2` → GH006 yok |

Hash eşleşmesi, düzeltmenin "rastgele başarılı" değil **deterministik** olduğunun
kanıtıdır: yerelde aynı komut aynı baytı üretti.

## 6. Önlemler ve kalan risk

**Uygulanan önlemler**

- Zorunlu kontrol zinciri boş kalmadı: push üç turda da geçti; sapma tek
  kontrol adıyla doğrudan bildiriliyor.
- Teslim kanıtı artık sürümleniyor: `docs/DEPLOY_EVIDENCE.md` her main HEAD'i
  için dört workflow koşumunu kaydeder ve `deploy_evidence.py --check` haftalık
  job'da tazeliğini fail-closed doğrular.

**Kalan risk (bilinçli olarak kapatılmadı)**

Kaynak → artifact bağı hâlâ insan zincirine bağlı: bugün bir TeX değişikliği
repack'i kendiliğinden tetiklemiyor. Bu, "post-commit hook + repack'i tek
commit'e zincirleme" ya da pre-commit'te kaynak→artifact bağı kuran bir kapı
gerektirir; bu RCA kapsam dışıdır (olayın kendisi çözülmüştür).

## 7. Kanıt dizini

- Olay: `docs/KNOWN_INCIDENTS.md` → INC-4
- Pre-fix koşu: run `37257949738` (Repack failure)
- Düzeltme: `3f7f88f`
- Sonrası: run `37315900932` (K1–K19 + Repack yeşil), run `37317331833`
  (`deploy-evidence` kapısı SUCCESS)
