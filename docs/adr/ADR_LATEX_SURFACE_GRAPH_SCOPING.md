# ADR: LaTeX yüzey gate — graf-scoped label çoğalması ve disk-varlıklı input çözümü

**Durum:** Kabul edildi (2026-10-15 — `_calisma/CIKTI/check_latex_surface.py`'de uygulandı;
bu ADR yazıldığı an worktree'dedir, commit edilmemiştir).

**Bağlam:**

- Kapı zaten `\ref`↔`\label` eşleşmesini **input grafiğiscoped** (root +
  `\input`/`\include` zinciri) denetliyordu: alakasız bir manuscript kopyasının
  label'ı eksik referansı maskeliyordu (kapı dokümantasyonunun kendi sözleşmesi).
- Gerçek tracked .tex yüzeyi (11 dosya) ölçüldü: **44 çoğalan label adının
  tamamı** iki bağımsız manuscript kopyası arasında
  (`_calisma/V5_ICERIK/.../core_section.tex` ↔ `_calisma/sde_experiment/core_section.tex`).
  Bunlar LaTeX'in "multiply defined" hatası DEĞİLDİR — hiçbir tek belge ikisini
  birden dahil etmez. Var olmayan eksik-input hedefi ise sıfırdı.
- `SurfaceFile.inputs` hedefleri ofsetsiz `str` olarak saklanıyordu; bulgular
  konumlu olamıyordu.

**Karar:**

1. **`label_duplicate`:** Çoğalan label bulgusu yalnızca **tek bir input
   grafiğinin içinde** üretilir (ikinci ve sonraki tanımlar; detay ilk tanımı
   `dosya:satır` biçiminde anar). İki bağımsız manuscript kopyası aynı label'ı
   tanımlayabilir — scoping `label_missing` ile birebir aynı ilkedir.
2. **`input_missing`:** `\input`/`\include` hedefinin **disk varlığı** esas alınır
   (tarama üyeliği değil). Üretilmiş ama tracked olmayan bir `.tex` hedefi
   LaTeX için çözümlenebilirdir; kapı onu bulgu sayılmaz.
3. **Makro hedefler fail-closed:** `\input{\chapters}` gibi `\` içeren hedefler
   statik çözülemez → ayrı `input_missing` bulgusu ("makro hedef; sabit yol
   kullanın"). Sessizce kontrol dışı bırakılmış bir include = gizli build kırığı.
4. `SurfaceFile.inputs` offset taşır: `tuple[tuple[str, int], ...]` — bulgular
   satır/sütunludur.

**Sonuçlar:**

- Gerçek ağaç gate'i temiz kalır (44 cross-copy label elenir); aynı graph'ta
  çoğalan label derhal kırmızıdır.
- Yeni yasak: makro ile verilen input hedefleri (gerçek yüzeyde sıfır kullanım).
- İleride bir kök belge iki kopyayı birden `\input` ederse dup bulgusu üretilir
  — bu bilinçli davranıştır (gerçek multiply-defined durumu).

**Reddedilen alternatifler:**

- *Global dup taraması:* 44 meşru çoğalma yüzünden kapı kalıcı kırmızı olurdu;
  manuscript kopyalama akışını (donmuş teslim kopyası ↔ experiment kopyası)
  cezalandırırdı. Mutasyon M3 ile scoping'in asla boş olmadığı kanıtlandı.
- *Tarama-üyeliği ile input çözümü:* tracked-olmayan üretilmiş hedefler sahte
  bulgu üretirdi.

**Kapı bağı:** hook `check-latex-surface` (pre-commit + verify.yml); sözleşme
testleri `_calisma/CIKTI/test_check_latex_surface.py` (12 test).
