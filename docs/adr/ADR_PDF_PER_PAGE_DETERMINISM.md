# ADR: Sayfa-bazlı PDF determinizm doğrulaması (plate-book)

**Durum:** Kabul edildi (2026-10-15 — prosedür olarak uygulandı; kod/kapı
değişikliği YOK, yeniden üretim + doğrulama raporu niteliğindedir).

**Bağlam:**

- `incidental_proof_book.pdf` (7 sayfa) `incidental_proof_plate02.pdf`
  (satır 73: `\platepage{...plate02.pdf}` gömülü) taze PDF'iyle yeniden
  derlenmeliydi.
- Tüm-dosya kanonik hash (`/ID`-nötr) determinizmi kanıtlar ama **hangi sayfanın**
  saptığını göstermez; teslim kalitesi için sayfa-level kanıt gerekir.
- `canvas_determinism_test.sh` harness'ı resmi kapı; onun dışına rapor yazmak
  ayrı sözleşme kararıdır.

**Karar:**

1. **SDE sabitleme:** Her iki bağımsız koşum da `SOURCE_DATE_EPOCH=1700000000`
   (kitap başlığının kendi build tarifi ile birebir). SDE motor'a explicit
   iletilir; aksi halde motor güncel zamanı gömer.
2. **Sayfa-bazlı hash:** `qpdf --empty --deterministic-id --pages <pdf> N --`
   ile sayfa N ayrıştırılır, SHA-256 alınır; iki koşumun aynı sayfası karşılaştırılır
   (7/7 eşitlik). `--deterministic-id` sayfa PDF'inin kendi `/ID`'sini
   SDE-stabil üretir — split kalıntısı değil içerik ölçülür.
3. **Yerleştirilen artifact yeniden doğrulanır:** `canvas/` altındaki kitap,
   doğrulanmış run1 çıktısıdır; yerleştirme sonrası dosyanın7/7 sayfası tekrar
   ayrıştırılıp aynı hash'lerle teyit edilir (in-place doğrulama).
4. **Resmi harness çapraz koşumu:** `TEX_SOURCE=<book.tex> canvas_determinism_test.sh`
   ayrıca PASS (rc=0, residual=none) — resmi kapı ile prosedür aynı sonucu verir.
5. **Rapor konumu:** Doğrulama raporu `/tmp`'de tutulur; `docs/ci_simulate/`
   altına **resmi rapor dosyası eklenmez** (ara artifact yazmak ayrı sözleşme
   kararıdır; mevcut `incidental_proof_plate02_report.txt` hash'leriyle
   birebir tutarlılık korunur).

**Sonuçlar:**

- Kitap determinizmi sayfa-level kanıtla sabit: ör. sayfa3
  `e06e336b2106f6c5…` (her iki koşum + in-place); tam PDF ham hash bile eşit
  (`b7384472cb32…` — SDE `/ID`'yi de sabitledi).
- Gelecekteki sayfa sapmaları hangi yaprakta olduğunu göstererek raporlanır.
- Hash'ler **içerik-seviyesindedir** (qpdf ayrıştırma), rasterize görüntü hash'i değil.

**Reddedilen alternatifler:**

- *Yalnız tam-dosya hash:* sapma durumunda kusurlu yaprak izole edilemez.
- *Rasterize (pdftoppm) hash:* görüntüleme araç bağımlılığı getirir; kapı
  metin/vektör içeriğini değil raster sonucu ölçerdi.

**Kapı bağı (dokunulmadı):** `test_canvas_determinism.py` (stub-tectonic),
`test_determinism_trend_canvas.py` — yeniden üretim bu kapıları etkilemedi
(11/11 yeşil).
