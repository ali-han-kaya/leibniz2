# Test-inventory contract taslağı (2026-10-15 envanter kararları)

**STATÜ: TASLAK — bağlanmamıştır.** Bu belge hiçbir kodu, hook'u, listeyi
veya workflow'u değiştirmez; mevcut kapıları gevşemez. Amaç: bu oturumda
kararlaştırılan **envanter gerçeğini** (hangi test dosyası nerede koşar,
hangi kapı hangi yüzeyi tarar) tek yerde, kanıtlanabilir biçimde
sabitlemektir. Her `tracked` iddiası `git ls-files --error-unmatch` ile
2026-10-15'te doğrulanmıştır; commit edilmemiş dosyalar bu tabloya
**untracked** olarak girer ve CI HEAD checkout'unda **görünmez**.

## 1. Test dosyası envanteri (bu oturumun kararları)

**Tracked — CI HEAD'de de koşar** (battery + `check_unit_tests.list`
üyeliği gerçek):

| Dosya | Karar rolü |
|---|---|
| `test_summary_pattern_drift.py` | merge-pattern drift kapısı (K9-05 vektörü) |
| `test_doc_artifact_sync.py` | artifact↔doc senkron kapısı (K9-06 vektörü) |
| `test_test_coverage_report.py` | keşif/üyelik/CheckMode kapısı (COV-03 vektörü) |
| `test_consolidate_summary.py` | K-özet konsolidasyon kapısı |

**Untracked — yalnız yerel battery** (CI HEAD'de hiç çalışmaz; "yeşil"
burada local anlam taşır; kasıtlı olarak ayrıca kırmızıya çevrilmedi):

| Dosya | Karar rolü |
|---|---|
| `test_lease_token_fuzz.py` | token sızıntısı özniteliği (fuzz; spec-modeli) |
| `test_token_delivery_contract.py` | token_delivery rc haritası (0/1/2/3) |
| `test_check_latex_surface.py` | LaTeX yüzey gate'i (M1-M4 mutasyon-kanıtlı) |
| `test_equation_gallery_tab.py` | denklem galerisi sekmesi sözleşmeleri |
| `test_canvas_determinism.py` | canonical PDF/kanvas determinizm (K20 testi) |
| `test_run_summary_k9.py` | K9 lake-log kapsül renderer'ı |
| `test_determinism_trend_canvas.py` | determinizm-trend canvas kaydı |
| `test_preview_screenshot_gate.py` | inline-handler yasağı + CLS/screenshot kapıları |

## 2. CI entegrasyon kararları (envanterin bağlanma kuralları)

1. **Yeni test dosyası** için `check_unit_tests.list`'e elle giriş
   YAPILMAZ — commit anında auto-sync hook'u keşiften (ve o anki
   `git ls-files` üyeliğinden) listeyi günceller. Üyelik kontrolü
   **dosya sistemine değil `git ls-files`'a** göre yapılır: untracked
   test + listede adı = 3.12+ üzerinde exit 5, 3.9-3.11 üzerinde sessiz
   sıfır-test "PASS" (AGENTS'taki çift-tuzak).
2. **`test_token_delivery_contract.py` battery'ye girer** (commit'te);
   `token_delivery.py` CLI'sını subprocess ile çağırır — battery ortamında
   ağ gerekmez (air-gap guard yereldir), süre ~0.2 s.
3. **`token-delivery` workflow'ü** ayrı dosyadır ve test envanterine
   yalnızca CLI üzerinden dokunur (fuzz suite'i `token_delivery.py`
   içinden koşar). Coverage record kuralı ("kayıt var olan ve testi
   gerçekten koşan bir job'ı adlandırmalı") bu iş için şimdilik **uygulanmaz
  **: iş required check değildir ve `CI_JOB_COVERAGE`'a kaydedilmemiştir;
   required yapılacaksa kaydın `token-delivery` job'ı gerçekten varken
   eklenmesi gerekir.
4. **Phantom kapı notu:** `docs/README.md`'nin pinlediği
   `test_docs_index.py` hiçbir branch'te yok; docs indeks güncellemesi
   bu taslak için de kapı değildir (untracked dosyalar indekste zaten
   görünmez).
5. **Coverage gate (HOOK_COVERAGE)** yeni `test_*.py` eklenince
   fail-closed olarak bir kez kırmızıya dönebilir (staging yarısında) —
   commit'i tekrarlamak kuraldır; `token_delivery.py` (test'siz modül)
   için kapsam kaydı gerekip gerekmediği commit anında coverage raporuyla
   görülür.

## 3. Taslak → bağlı geçiş kuralları (ileride bu dosyayı yazan için)

1. Bir untracked test dosyası **commit edildiğinde** tablodaki satırı
   `tracked` sınıfına taşınır; kanıt: `git ls-files --error-unmatch` rc=0.
2. Tabloya yeni satır eklenirken kanıt aynı oturumda tazelenir (dosya
   adı + ls-files çıktısı); kanıtsız `tracked` iddiası yazılmaz — bu
   oturumda bir kez tersi oldu (LaTeX testi "tracked" sanılıyordu, `git
   show HEAD:` ile çürütüldü) ve kayıt düzeltildi.
3. "Yeşil" iddiası için mutasyon kanıtı (`evidence: mutation Mx`)
   eklenmesi tavsiye edilir; kanıtsız yeşil yalnızca `green` statüsüyle
   iddia edilir.
4. Bu envanter bir makine-okunur JSON'a (veya `NEGATIVE_TEST_VECTORS.json`
   benzeri kanonik fixture'a) taşınırsa: JSON tek kaynak olur, bu Markdown
   özet olur; geçiş ayrı karardır — bu taslak bunu **önermez**, yalnızca
   kapıyı bırakır.
5. Hiçbir kapı gevşetilemez, hiçbir assert yumuşatılamaz; taslak satırı
   yalnızca **eklentidir**.
