# İddia–Kanıt Matrisi (V5 RC)

Bu kayıt, makaledeki içerik iddiaları ile hesaplamalı kanıtların kapsamını
ayırır. `PASS` yalnızca ilgili birincil kayıt yeniden üretildiğinde kullanılır;
ölçülmemiş, çevrimiçi doğrulanamamış veya yalnızca yorum olan noktalar
`BEYAN`/`ÖLÇÜLMEDİ` olarak kalır.

| ID | İddia / nesne | Birincil kanıt | Yeniden üretim kapısı | Sınır / sınıflandırma |
|---|---|---|---|---|
| C1 | Extensional birinci-derece modelin gözlem eşdeğerliği ayırımı bırakabilmesi | `core_section.tex`, `L0_Lplus_spec.md`, `core_formal_model_check.py` | `verify_delivery.py --full` + core model check | Matematiksel model sonucu; Stoacı/Humean tarihsel gerçeklik iddiası değildir |
| C2 | Boolean önerme ve bridge-collapse karakterizasyonu | `symbolic_proof_z3.py`, frozen Z3 çıktısı, P4-d/P4-e kayıtları | K8 symbolic/Z3 kapısı | Z3 modeli formel iddiayı sınar; doğal dil yorumunu tek başına kanıtlamaz |
| C3 | Forget-map / reduct-invariance yardımcı lemması | `_calisma/lean_reduct/` kaynakları ve `MAP.md` | K9 Lean lake build + sorry/axiom denetimi | Yardımcı formalizasyon; tam tarihsel doktrin formalizasyonu değildir |
| C4 | Bibliyografik kimlik ve künyeler | `refs-online/`, CrossRef/OpenLibrary/SEP kanıt kayıtları | `--check-references` ve refs-trend | Çevrimiçi erişim başarısızsa kayıt UNVERIFIED kalır; başarı iddiası üretilmez |
| C5 | Teslim PDF'si kaynak TeX'ten üretilmiştir | `ingiliz_empirizmi_v3.tex`, PDF, manifest ve provenance | PDF kaynak-tazelik + sayfa + manifest kapıları | PDF içeriği ile kaynak eşleşmesi kanıtlanır; yorum kalitesi ölçülmez |
| C6 | Yeniden paketleme bütünlüğü | iki ZIP ve `.sha256` sidecar'ları | `repack_delivery.py --verify` | Sidecar yokluğu/uyuşmazlığı FAIL; eski günlük PASS kanıtı sayılmaz |
| C7 | K0–K21 katmanlarının durumu | `klayers.json`, latest/run kayıtları | fail-closed layer/status kapıları | SKIP, PASS değildir; katman ölçülmediyse bilinmiyor olarak raporlanır |
| C8 | Dashboard canlı gözlemi | `preview_server.py`, `/api/latest`, `/api/run`, `/api/run-now` | HTTP/API/SSE/browser smoke | Dashboard kanıtı doğrulama çalışmasının kendisi değildir; yalnızca görünürlük katmanıdır |

## Kabul yüklemleri

- `P0=0`, `P1=0`, gerekçesiz negatif sayım `0` ve BELİRSİZ kalıntı `0` olmadan
  `FINAL` verilmez.
- Yerel geçiş, temiz checkout/CI geçişi yerine yazılamaz; iki kanıt ayrı
  alanlarda tutulur.
- Aynı ID değişmiş metinle tekrar kullanılamaz; yeni sürüm yeni kayıt veya
  açık revizyon bağlantısı taşır.
- PDF determinism bir varsayım değildir. TeXLive + `SOURCE_DATE_EPOCH` ile
  doğrulanana dek build determinism sonucu `ÖLÇÜLMEDİ`/proxy olarak raporlanır.
- Her çevrimiçi referans için kaynak, erişim zamanı, yanıt ve eşleşme sonucu
  saklanır; yoksa `UNVERIFIED` yazılır.

## Holdout kuralı

Düzeltme üretiminde kullanılan test ve fixture'lar kabul sonucunu tek başına
belirlemez. Bağımsız negative-case testleri (eksik sidecar, bozuk hash,
method mismatch, başarısız hook ve eski review) release kapısında ayrıca
çalıştırılır.
