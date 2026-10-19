# Negative-test contract taslağı (2026-10-15 kararları)

**STATÜ: TASLAK — bağlanmamıştır.** Bu belge hiçbir kodu, hook'u veya testi
değiştirmez; mevcut kapıları gevşemez. Makine-okunur **kanonik kaynak**
[NEGATIVE_TEST_VECTORS.json](NEGATIVE_TEST_VECTORS.json) dosyasıdır (22
vektör); bu Markdown onun insan-okunur özeti ve karar gerekçeleridir.
Hiçbir CLI bu fixture'ı henüz okumuyor — implementasyon ayrıca karar
gerektirir.

Kaynak ADR'ler (bu dizinde):

| ADR | Konu |
|-----|------|
| [ADR_LATEX_SURFACE_GRAPH_SCOPING.md](ADR_LATEX_SURFACE_GRAPH_SCOPING.md) | LaTeX yüzey grafik scoping |
| [ADR_K9_LAKE_LOG_CONTRACT.md](ADR_K9_LAKE_LOG_CONTRACT.md) | K9 lake log kapsül contract'i |
| [ADR_PDF_PER_PAGE_DETERMINISM.md](ADR_PDF_PER_PAGE_DETERMINISM.md) | PDF sayfa-bazlı determinizm |
| [ADR_COVERAGE_DISCOVERY_TRACKED_ONLY.md](ADR_COVERAGE_DISCOVERY_TRACKED_ONLY.md) | Test keşfi `git ls-files` üyeliği |
| [ADR_DASHBOARD_EQUATIONS_TAB.md](ADR_DASHBOARD_EQUATIONS_TAB.md) | Denklem galerisi sekmesi kontrast/tema |

## 1. Mevcut + yeşil + mutasyon-kanıtlı (şimdi kırmızıya gidebilir)**LaTeX yüzey scoping** (`test_check_latex_surface.py` **untracked** —
`.gitignore`'da değil ama hiç `git add` edilmemiş; kapı yalnız bu worktree'de
yaşar. Script `check_latex_surface.py` de HEAD'de yok, hatta hook/adım
bağlantısı (`.pre-commit-config.yaml`, `verify.yml`) de commit'siz — üçü
**birlikte** commit edilmeli, tek başına bağlantı ya da tek başına script
fresh clone'da fail-closed kırılır):

- Vektor `LTX-01`: aynı grafik içi dup etiket → bulgu, exit 1.
  Kanıt: **M1** — dup tanımı eklenince gate kırmızı, kaldırınca yeşil.
- Vektor `LTX-03`: manuskript kopyaları arası (rep-pdf vs typo) aynı etiket →
  **0 bulgu**, exit 0. Kanıt: **M3**.
- Vektor `LTX-04`: çözülmeyen `\input{ad deneme}` → `input_missing`, exit 1.
  Kanıt: **M2**. Yorum satırındaki `\input`/`\ref` bulgu üretmez (aynı test).
- Vektor `LTX-05`: makro hedefli input (`\makro{sec:report}`) → fail-closed
  bulgu. Kanıt: **M4**.
- Vektor `LTX-02` (aynı dosyada dup) ve `LTX-06` (CLI exit/kırmızı + `--json`)
  yeşil, mutasyon kanıtı yok.

## 2. Yeşil ama test dosyaları commit'siz (CI'da çalışmaz)

Bu vektörlerin test dosyaları worktree'de var, **tracked değil** → CI HEAD
checkout'unda hiç görünmez (ADR_COVERAGE_DISCOVERY kuralının kendi ikizi;
§1'deki LaTeX kapısı da aynı kaderi paylaşır).
Yerel battery'de koşarlar:

- `K9-01..K9-04`: `[K9-LAKE] PASS/FAIL` → PASS/FAIL; kısmi log (yalnız
  `START`) → fail-closed FAIL; yan dosya yok → `MISSING` advisory
  (`test_run_summary_k9.py`).
- `PDF-01..PDF-02`: ham `/ID` farkı canonical'da eşit (residual `/ID`);
  içerik farkı canonical'dan geçemez (`test_canvas_determinism.py`).
- `EQ-01..EQ-02`: sekme/panel/manifest 16 kart/sunucu rotası sözleşmeleri ve
  satır içi handler yasağı (`test_equation_gallery_tab.py`,
  `InlineEventHandlerContractTests`).

İzlek: bu dosyalar commit edilmedikçe "yeşil" dediğimiz şey yalnızca local
anlam taşır — kasıtlı olarak ayrıca kırmızıya çevrilmediler (oturumun
kapsamı: kod değişikliği yok).

## 3. Ya tracked + yeşil kapı (drift ailesi)

- `K9-05`: merge pattern'den `ARTIFACT_JOBS` kaydı düşer →
  `summary_pattern_drift` DRIFT, exit 1, `--json` stdout tek JSON
  (`test_summary_pattern_drift.py`, tracked).
- `K9-06`: workflow upload adı `PUBLISH_SCENARIO`'da/`ARTIFACT_JOBS`'ta
  yok → `check_workflow_artifact_docs` FAIL, exit 1
  (`test_doc_artifact_sync.py`, tracked).
- `COV-03`: check modunda testi olmayan dosya açıkta → exit 1
  (`TestCheckMode`, tracked).

## 4. TASLAK — henüz hiçbir testte yok (bağlanmamış)

- `PDF-03`: **per-page hash omurgası yok.** Mevcut gate yalnızca
  tüm-dosya canonical + hibrit `SOURCE_DATE_EPOCH`'u kapsar; N. sayfa
  bazında iki build karşılaştırması yapacak harness/CLI **yok**. Vektor,
  ileride kurulacak aracın kanonik bekleyişini yazar: sayfa hash farkı →
  exit 1 + aday sayfa listesi.
- `COV-01`: untracked test dosyası keşisten **dışlanır** (local == CI)
  — mevcut 4 kesif testi yalnızca şu anki ağaçta outcome pin'ler.
- `COV-02`: `git` çalışamazsa glob fallback devreye girer, keşif sıfırlanmaz
  — hiçbir test git-hata yolunu kapsamaz.
- `EQ-03`: denklem kartı `:hover` rengi AA düşerse kırmızı — hiçbir gate
  hover durumu basmaz; ayrıca `check_tokens` (10 s timeout) ile gerçek gate
  (5 s) süre farkı ADR'de tartışıldı.
- `EQ-04`: açık temada sekme-spesifik kontrast — a11y gate sayfa seviyesinde
  light renk kontrastını yakalar, sekme ayrımı yok.

## 5. Bağlama kuralları (ileride test yazan için)

1. Bu belgedeki taslak vektör bir `test_*.py`'ye taşındığında ilgili vektörün
   `wired` alanı `true`, `test` alanı unittest kimliği, `status` alanı
   `green` olur ve ADR'deki ilgili "kapı yok" cümlesi güncellenir.
2. Test dosyası **tracked değilse** `tracked: false` kalır — CI'da koşmadığı
   sürece "kapı" sayılmaz (bu, ADR_COVERAGE_DISCOVERY_*'nin ana dersi).
3. "Yeşil" iddiası için mutasyon kanıtı (`evidence: mutation Mx`) eklenmesi
   tavsiye edilir; kanıtsız yeşil yalnızca `green` statüsüyle iddia edilir.
4. Hiçbir kapı gevşetilemez, hiçbir assert yumuşatılamaz; taslak satırı
   yalnızca **eklentidir**.
