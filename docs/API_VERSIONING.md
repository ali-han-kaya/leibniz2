# Dashboard API Sürümleme ve Deprecation Politikası

Kapsam: preview dashboard'ın `/api/*` yüzeyi (tek kaynak:
`_calisma/CIKTI/test_api_method_contract.py` içindeki `API_CONTRACT`
tablosu; makine-okunur şema: `_calisma/CIKTI/openapi.json` — üretici
`gen_openapi.py`).

## Sürümleme modeli

- **Tek-sürüm, uyumlu-evrim:** Dashboard tek-kullanıcılı, localhost-öncelikli
  bir yüzeydir; URL-sürümlemesi (`/v1/...`) getirilmez. Uyumluluk
  **davranış-sözleşmesiyle** taşınır: yöntem-matrisi
  (`test_api_method_matrix.py`), hata-ayrımı (405 = bilinçli red + Allow,
  404 = bilinmeyen yol/dağıtım-dışı POST, 501 = tanımsız metot) ve
  yanıt-şekilleri pre-commit'te pinlidir.
- **Şema-sürümü:** `openapi.json` → `info.version` **MAJOR.MINOR.PATCH**
  taşır:
  - PATCH: dokümantasyon/açıklama değişikliği (davranış aynı).
  - MINOR: **geriye-uyumlu** ekleme (yeni yanıt-alanı, yeni endpoint).
  - MAJOR: **kırıcı** değişiklik (alan kaldırma/anlam-değişimi, yöntem
    kısıtlaması, durum-kodu değişimi).
- **Dış-bildirim:** `PREVIEW_API_VERSION` env'i sunucu-sürümünü dışarıdan
  bildirmek için ayrılmıştır (health/latest yanıtlarına sürüm-alanı
  eklenmeden önceki aşamada insan-ops kullanımı içindir).

## Deprecation politikası (iki-adım, fail-closed)

Bir uç veya alan deprecated edilirken **iki sürüm** kuralı uygulanır:

1. **Duyuru sürümü (N):** Şemada `deprecated: true` + **`x-deprecated-since`**
   (duyuru sürümü) + **`x-sunset`** (kaldırma hedef sürümü/tarihi) İKİLİSİ
   birlikte konur. İkisiz `deprecated` işareti şema-yapan test tarafından
   reddedilir (`test_openapi_schema.py::test_deprecation_requires_both_fields`)
   — sessiz borç-gizleme yok.
2. **Kaldırma sürümü (x-sunset):** Uç/alan kaldırılır; `API_CONTRACT`
   güncellenir, şema yeniden üretilir (`python3 _calisma/CIKTI/gen_openapi.py`)
   ve davranış-testleri yeni gerçeklikle hizalanır. Kaldırılan ucun adı
   bilinçli olarak **yeniden kullanılmaz** (yeni anlam = yeni ad).

### Şablon

```yaml
/api/ornek:
  get:
    deprecated: true
    x-deprecated-since: "1.2.0"   # duyuru sürümü
    x-sunset: "2.0.0"             # kaldırma hedefi (MAJOR)
    responses:
      200: { $ref: '#/components/...' }
```

## Değişiklik-akışı (checkpoint)

1. `API_CONTRACT` + davranış-testleri güncelle (aynı commit).
2. `python3 _calisma/CIKTI/gen_openapi.py` → `openapi.json` yenile
   (`--check` ile drift'i pre-commit'e doğrulat).
3. Kırıcı değişiklikte `info.version` MAJOR + bu dokümanda kayıt.
4. pre-commit zinciri: yöntem-matrisi + şema-drift testleri yeşil olmadan
   commit çıkmaz.

## Şu anki durum

- Sürüm: **1.0.0** (ilk şema; kırıcı değişiklik yok).
- Deprecated uç: **yok**.
- Yöntem-sözleşmesi: GET-only okuma uçları, POST-only `run-now`/`stop`
  (405 + Allow: POST), SSE `run`/`run-stream`; desteklenmeyen metotlar 501.
