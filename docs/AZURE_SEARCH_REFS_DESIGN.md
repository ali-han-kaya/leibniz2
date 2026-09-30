# Azure AI Search hibrit-arama ile Referans-Doğrulama Entegrasyonu (Tasarım)

> K6 (`verify_delivery.py --check-references`) akışının çözümleme-katmanını Azure AI
> Search **hibrit aramaya** (keyword + vector + semantic ranking) taşıma tasarımı.
> İlkeler: (1) **hüküm-otoritesi yerel kalır** — Azure yalnız çözümleme/sıralama yapar,
> (2) her yeni yüzey tek-kaynak zincirine bağlanır, (3) bozulma dürüst bildirilir,
> sessiz-PASS yoktur. Fiyatlar Eylül-2026 liste-yaklaşımı (teyit edilmeli).

## 1. Bugünkü akış (taşınan yüzey)

| Bileşen | Konum | Rol |
|---|---|---|
| `REFERENCE_*` listeleri | `verify_delivery.py:310+` | 64-girişlik tek-kaynak (doi/url/tex_needle/needle) |
| Çevrimiçi denetim | `run_reference_audit` | kanonik kaynağa HTTP + needle-dogrulama, bütçe 260s, havuz 4, retry 3 |
| Çıktı | `references_online.json` | koşum-kanıtı; `audit_refs_trend.py` + trend-dosyası tüketir |
| Bijection-kapısı | `check_refs_table_sync.py` | 64 satır tablo ↔ kod-anahtarı, çift-yönlü, fail-closed |

Ağrı-noktası: needle-eşleştirme **birebir-metin**. `TABLE_OVERRIDES` tablosunun varlığı
bu sınıfın kanıtı (aksan `Lagrée↔Lagree`, edisyon-sökmeleri `Norton&Norton 2000 =
Treatise`, cilt-yılı `Bury 1935 = Loeb vol. II`) — hibrit-arama bu sınıfı kalıcı-çözüm
yapar, override-artıkları değil.

## 2. Indeks şeması (`infra/refs-index.json` — üretilir, elle tutulmaz)

Tek-kaynak zinciri: `REFERENCE_*` → `gen_refs_index.py` → şema + 64 doc-yüklemesi.
Aynı üretici şemayı yazar; diskteki şema ↔ yeniden-üretim drift'i fail-closed.

```jsonc
{
  "name": "refs-verify",
  "fields": [
    { "name": "key",            "type": "Edm.String", "key": true },
    { "name": "source_type",    "type": "Edm.String", "filterable": true },  // crossref|sep|openlibrary|archive|url|perseus|known
    { "name": "title",          "type": "Edm.String", "searchable": true },
    { "name": "container",      "type": "Edm.String", "searchable": true },  // container_needle
    { "name": "authors_year",   "type": "Edm.String", "searchable": true },  // "Artemov, S. (2008)"
    { "name": "doi",            "type": "Edm.String", "filterable": true },
    { "name": "url",            "type": "Edm.String" },
    { "name": "volume",         "type": "Edm.String", "filterable": true },
    { "name": "tex_needle",     "type": "Edm.String" },   // kanonik bağ, arama-değil
    { "name": "last_status",    "type": "Edm.String", "filterable": true }, // DUZELTILDI|NOT|...
    { "name": "last_checked",   "type": "Edm.DateTimeOffset", "filterable": true },
    { "name": "embedding",      "type": "Collection(Edm.Single)",
      "dimensions": 1536, "vectorSearchProfile": "refs-hnsw" }
  ],
  "vectorSearch": {
    "algorithms": [ { "name": "refs-hnsw-alg", "kind": "hnsw" } ],
    "profiles":   [ { "name": "refs-hnsw", "algorithmConfigurationName": "refs-hnsw-alg" } ]
  },
  "semantic": {
    "configurations": [ {
      "name": "refs-semantic",
      "prioritizedFields": {
        "titleField":   { "fieldName": "title" },
        "contentFields": [ { "fieldName": "container" }, { "fieldName": "authors_year" } ]
      }
    } ]
  }
}
```

Sorgu-yüzeyi (tek fonksiyon, `resolve_reference(fragment)`): hibrit sorgu
(`VectorizedQuery` + `search_text`, RRF füzyon) + `semantic` yapılandırma; eşiği
(aşağıda 4.3) geçen ilk sonucu döndürür. Embedding: `text-embedding-3-small`
(64 doc ≈ 6.4k token ≈ **$0.0001**; yalnız referans-değişiminde yeniden).

## 3. Maliyet (aylık, yaklaşık — teyit edilmeli)

| Kalem | Tüketim | Maliyet |
|---|---|---|
| AI Search katmanı — **Free** | 64 doc, ~1 MB, 3 indeks kotası, SLA yok | **$0** |
| AI Search katmanı — **Basic** | 1 replika/1 bölüm, SLA'lı; CI-bağımlılığı için | **~$75** |
| Semantic ranker | ~2-4k sorgu/ay (günlük koşum × 64) | Free-bant içinde / ~$0.03-0.06 |
| Embedding (OpenAI) | yalnız re-index (~ayda bir) | ~$0 |
| **Mevcut akış** | urllib doğrudan-HTTP | **$0** |

**Dürüst değerlendirme:** 64-doc ölçeğinde kullanım-maliyeti önemsizdir; taban-fiyat
katman-kirasıdır. Free-katmanla dogfood → CI bu yola **bağlanmadan** Basic'e geç.
Değer-teklifi maliyet-tasarrufu değil, **çözümleme-kalitesi** (needle-kırılganlığının
giderilmesi) + edisyon/aksan varyantlarının otomatik eşleşmesidir — mevcut akış zaten $0.

## 4. Fail-closed strateji

### 4.1 Hüküm-otoritesi değişmez
Azure **asla** "referans doğrulandı" demez. Çözümleme: fragment → `{key, score}`;
sonra mevcut kanonik HTTP-needle denetimi koşar. Azure cevabı = doğru girdiyi
*bülbü*, doğrulaması yine yerelde. Dolayısıyla AI Search'ün tüm arızaları
çözümleme-kalitesini düşürür, hüküm-sağlamlığını değil.

### 4.2 Bozulma sözleşmesi (dürüst-degradasyon)
| Durum | Davranış | Kayıt |
|---|---|---|
| AI Search erişilemez / auth-hatası | birebir-needle yoluna düş (bugünkü davranış), hüküm-yolunu etkilemez | `references_online.json`'a `"resolution": "degraded-fallback"` |
| Sonuç boş / eşik-altı | birebir-needle yolu zaten birincil | `"resolution": "exact-needle"` |
| İki yol da çözümlemez | **P1** bulgu (fail-closed) | mevcut K6 bulgu-akışı |
| Şema/senkron drift | **P1** bulgu; koşum açılmaz | yeni kapı (4.3) |

`--hybrid-resolution` bayrağı opsiyoneldir; bayraksız koşum bugünkü davranışın birebiridir
(opsiyonel-arac-degradasyon kuralı, `pdfinfo` deseni — ama çözümleme-başarısızlığı
P1 üretir, çünkü iki yol da denendikten sonrasıdır).

### 4.3 Yeni kapılar (repo gelenekleriyle)

| Kapı | Sözleşme | Fail-closed kanıtı (test-süiti, mock-SearchClient — ağ yok) |
|---|---|---|
| `test_refs_index_schema.py` | diskteki `infra/refs-index.json` == üreticinin yeniden-üretimi; alan-sonu sürükleme = fail | drift-örneği → P1 |
| senkron-kapısı (genişleme) | `check_refs_table_sync.py` zincirine üçüncü halka: kod ↔ tablo ↔ **indeks-doc count == 64** | 63-doc indeks → fail |
| degradasyon-testi | erişilemez-servis → rc değişmez, `degraded-fallback` kaydı, hüküm-yolu yeşil | mock-timeout → rc0 + kayıt |
| eşik-testi | eşik-altı skor asla kanonik-dogru sayılmaz; düşük-skor + needle-uyuşmazlığı → mevcut bulgu | sahte-yüksek-skor enjeksiyonu → yine bulgu |
| sır-hijyeni | endpoint/key yalnız env (`AZURE_SEARCH_ENDPOINT/KEY`) — K7 taramasına zaten takılır | kodda literal-key → P0 |

Bütçe-değişmezleri korunur: hibrit-yol da `REFERENCE_AUDIT_BUDGET_S=260` ve
`REFERENCE_HTTP_RETRIES=3` tavanına tabidir (arama-adımı ayrı kısa bütçe: 30s).

## 5. Faz planı (TEXLIVE_MIGRATION_PLAN deseni)

| Faz | İçerik | Kapı |
|---|---|---|
| 0 | `gen_refs_index.py` üreticisi + şema-artifaktı + senkron-süiti (mock-only, $0, ağ-yok) | şema-drift + 64-bijection |
| 1 | `resolve_reference()` + degradasyon-sözleşmesi; `--hybrid-resolution` bayrağı; degradasyon/eşik-testleri | mock-süit yeşil |
| 2 | Canlı Free-katman dogfood (elle); çözümleme-kalitesi raporu (TABLE_OVERRIDES'ten kaçının çözülmesi) | insan-kanıt + karşılaştırma-tablosu |
| 3 | CI-bağlantısı (secret via env, Basic-katman kararı) + dashboard panel-işaretçi (`resolution` alanı) | zincir + K7 |

## 6. Açık kararlar (kullanıcıya)

1. **Katman:** Free-dogfood önce (öneri), CI-bağımlılık anında Basic (~$75/ay).
2. **Semantic ranker:** Faz 2'de A/B gerekli mi — 64-doc'ta kazanç marjinal olabilir.
3. Bu tasarım, Azure'daki Container Apps planından (`.azure/deployment-plan.md`)
   bağımsız ama uyumlu: dağıtılırsa endpoint/secret managed-identity'ye terfi eder.
