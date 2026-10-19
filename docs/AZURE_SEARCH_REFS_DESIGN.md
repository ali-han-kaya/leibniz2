# Azure Search Refs — Faz 0 Tasarımı

- **Durum:** Implemented (Faz 0 — sözleşmeler ve iskelet; referans çıkarımı Faz 1)
- **Tarih:** 2026-10-06
- **Kapsam:** `refs-index.json` üretici, artifact sözleşmesi, mock tabanlı senkron süiti
- **Kısıt:** Ağ yok — Faz 0 bileşenleri hiçbir ağ çağrısı yapmaz (TDD, mock tabanlı)

## 1. Amaç

Azure Search için reference index'i üretecek bileşenlerin **sözleşmesini** kurmak:
üretici → artifact → senkron kapısı (gate) zincirini, gerçek bir arama servisi ya da
git ağ katmanı olmadan, fail-closed bir kapı arkasında doğrulamak. Faz 0 çıktısı
"index dolu" varsaymaz; artifact **var**, **şemaya uyar**, kapı **bozuk veriyi
geçirmez** — bunu kanıtlar.

## 2. Bileşenler

| Bileşen | Konum (commit'li) | Rol |
|---|---|---|
| `gen_refs_index.py` | repo kökü | Artifact üretici: `refs-index.json` yazar |
| `_calisma/CIKTI/refs-index.json` | artifact | Üretilen reference index (izlenir dosya) |
| `test_beta_battery_gate.py` | repo kökü | Mock senkron süiti: artifact + şema kapısı |

Akış: `gen_refs_index.py` çalışır → `refs-index.json` yazılır → battery gate dosyanın
varlığını ve `refs` anahtarını doğrular → PASS. Gate, üreticiyi çağırmaz (üretim
adımı ayrı ve bilinçlidır); böylece bozuk/eksik artifact'ı tespit eder, üretimi tetikleyip
gizlemez.

## 3. Veri sözleşmesi (JSON şeması)

```json
{
  "generated_at": "<ISO-8601, UTC, Z eki>",
  "refs": [],
  "source": "azure-search"
}
```

- `generated_at` — üretimin UTC zaman damgası (RFC 3339 biçimi, `Z` eki).
- `refs` — reference kayıtları. **Faz 0'da bilinçli olarak boş**; kapı `refs` anahtarının
  varlığını şart koşar, doluluğu **koşmaz** (ölçülmemiş "dolu" PASS yok).
- `source` — kaynak etiketi; ileride birden çok indeks kaynağını ayırmak için.

Sözleşme iki yerde sabitlenir: üreticinin yazdığı anahtar kümesi ve battery gate'in
kullandığı okuma kümesi. Yeni bir anahtar eklendiğinde her iki taraf ve şema testi
aynı commit'te güncellenmelidir.

## 4. TDD döngüsü

1. **Kırmızı:** artifact yokken gate → `AssertionError` ("refs-index.json yok").
   Bozuk JSON (geçersiz sözdizimi) gate'in `json.loads` adımında patlamalı —
   fail-closed.
2. **Yeşil:** `python3 gen_refs_index.py` → artifact yazılır → gate PASS.
3. **Geriye dönüş kontrolü:** artifact elle bozulursa (anahtar silinirse) gate tekrar
   kırmızıya döner; kapı her koşulda "ölçülen" PASS verir.

## 5. Ağ yok politikası

Faz 0'da senkron, uzak sistemle konuşmaz: `test_beta_battery_gate.py` yalnızca yerel
artifact'ı okur ve sahte (mock) veriyle şemayı sınar. Üretici de ağ kullanmaz —
git/ataman ağ katmanı Faz 1'e devredilmiştir. Bu, CI'da deterministik koşu ve
her ortamda aynı sonucu garanti eder.

## 6. Bilinen sınırlar (Faz 1'e devredilenler)

- **`refs[]` boş** — gerçek referans çıkarımı (commit/pip/PyPI kaynakları) Faz 1 işidir;
  kapı doluluk varsaymaz.
- **Zaman damgası gürültüsü:** her yeniden üretim `generated_at`'ı değiştirir →
  salt-zaman farkı olarak git churn üretir. Faz 1'de deterministik zaman
  (commit zamanı ya da `SOURCE_DATE_EPOCH`) değerlendirilmeli.
- **Üreteç ve gate repo kökünde;** `_calisma/CIKTI/` altına taşınması ve gate'in
  `check_unit_tests.list` + `HOOK_COVERAGE` kayıtları (unittest'e dönüştürülmesi)
  açık iş kalemi.
- `datetime.utcnow()` Py 3.12+ üzerinde deprecated uyarısı verir; `datetime.now(timezone.utc)`
  ile değiştirilmeli.

## 7. İlişkili yüzeyler (bu tur, faz dışı)

Aynı turda bağlanan gözetim yüzeyleri (Faz 0'ın parçası değil, tek commit'te geldiler):
`/api/health` ve `/api/a11y` uçları + dashboard'daki verdict/summary paneli
(artifact JSON'dan okur, fail-closed: kanıt yoksa rozet yeşil olmaz).
