# Tectonic → TeXLive Göç Planı (2026-09-17)

**Kapsam:** V5 teslim PDF'i (`ingiliz_empirizmi_v3.pdf`), REVIEW derleme
PDF'i ve z3 slayt render'larının TeX motoru geçişi; Makefile/hook/CI
taşıma; `/ID` kalıntısının kabul raporu; iki motorun çıktı eşitliği
kanıtı.

**Ölçülmüş temel gerçekler** (bu planın tamamı 2026-09-16/17 deneylerine
dayanır; motorlar: tectonic 0.17.0, pdfTeX 3.141592653-2.6-1.40.29
TeX Live 2026/Homebrew, SDE=0):

| Kanıt | Değer |
|---|---|
| TeXLive tek-geçiş 2 bağımsız koşum | ham hash farklı; **kanonik (/ID nötr) hash birebir aynı**: `a75c3409…` (oturumlar arası 3+ ölçümde kararlı) |
| TeXLive 3-geçiş pipeline, 2 bağımsız koşum | kanonik hash birebir aynı: `544516b0…` (bağlamlar arası deterministik) |
| tectonic (SDE=0), bağlamlar arası | ham hash kararlı: `ad8fca69…` |
| Çapraz motor byte eşitliği | **MÜMKÜN DEĞİL** — kanonik hash'ler farklı (`47681218…` tectonic vs `544516b0…` TeXLive): font/ligatür/hinting farkları |
| İçerik eşitliği | hizalama (3 geçiş) sonrası sayfa 33 = 33; metin katmanı farkı yalnız **satır sonu heceleme kırılımları** (90 vs 380 token: hece parçaları ↔ bütün kelimeler) + glif-eşleme (\x01) kodlaması — içerik aynı |
| `/ID` kalıntısı | pdfTeX SDE ile bile her koşumda rastgele 64 baytlık trailer `/ID` üretir; `qpdf --static-id` (girdi /ID'sini korur) ve `--remove-metadata` (kendisi nondeterministik) gideremez — skill'in donmuş bulgusu tekrar doğrulandı |

**Sonuç (planın özü):** Geçişte doğrulama sözleşmesi **raw-hash eşitliği
değil**, üç katmanlı olmalı: (1) aynı motor içinde /ID-kanonik hash
kararlılığı, (2) sayfa/metin-içerik eşitliği, (3) heceleme/glif
farklarının kabul raporuyla belgelenmesi.

---

## Faz 0 — Ön koşullar (geçişin teknik sözleşmesi)

- [ ] **3-geçişli build zorunlu:** pdflatex tek geçişte çapraz referans/
  bib çözülmez (ölçüldü: 32 sayfa, 1.424 kelime eksik, `§??` gövdeleri) →
  tüm yeni target'lar **tam 3 geçiş** koşar ve son geçiş log'unda
  `Rerun to get` sayısı **0** olduğunu kanıtlar.
- [ ] Sözleşme sabitleri: `SOURCE_DATE_EPOCH` export (her iki motora),
  `TEXINPUTS="$TEXDIR//:"` (core_section gibi \input bağımlılıkları),
  `TEXMFOUTPUT="$PWD"`, `-output-directory` ile **kaynak dizinine asla
  yazma** (texlive_determinism_test.sh'teki GÜVENLİK notu).
- [ ] Motor sürüm kilidi dokümantasyonu: pdfTeX 3.141592653-2.6-1.40.29
  (TeX Live 2026); CI'da TeX Live sürümü adım çıktısına yazılır.

## Faz 1 — Makefile geçişi (`docs/Makefile.texlive`)

- [ ] `docs/Makefile.tectonic`'in ikizi olarak `docs/Makefile.texlive`
  eklenir; target'lar: `pdf` (3 geçiş), `check` (2 bağımsız 3-geçişli
  koşum + /ID-kanonik hash karşılaştırması + `Rerun=0` denetimi),
  `accept` (Faz 3 kabul raporu üretir), `clean`.
- [ ] `SOURCE_DATE_EPOCH ?= git log -1 --format=%ct` semantiği
  korunur (geçmiş commit'i yeniden üretme yeteneği).
- [ ] Eski `Makefile.tectonic` **kalır** (paralel yaşam, geri dönüş
  yolu); README'de her iki Makefile yan yana dokümante edilir.
- [ ] Kabul: `make -f docs/Makefile.texlive check` RC=0 ve kanonik hash
  `544516b0…` ile eşleşir.

## Faz 2 — Hook geçişi

- [ ] `texlive_determinism_hook.sh` birincil kapı olur: TeXLive+python3
  varken SKIP **yok** (bu makinede ölçüldü: PASS); tectonic ayağı bilgi
  amaçlı ikincil kalır. Verdict semantiği zaten dürüst: ham farklı +
  kanonik eşit + `residual=/ID` → PASS; kanonik farklı → FAIL.
- [ ] `texlive_determinism_test.sh`'e **3-geçiş modu** eklenir (mevcut
  tek-geçiş deneyi K6 hizalama gerçeğini yakalamaz); stub testleri
  (test_texlive_determinism_hook, test_texlive_determinism_id_residual)
  yeni akışa uyarlanır; `check-unit-tests` manifest + HOOK_COVERAGE
  senkronu yenilenir.
- [ ] `render_z3_slides.py` zaten `pdflatex → latex → tectonic` sırasını
  deniyor — koruyucu test eklenir: motor seçimi log'da görünür ve
  pdflatex varken tectonic'e düşmez.
- [ ] `check_review_freshness.py` / `check_bibliography_sync.py`
  doküman/metin yorumlarında "tectonic + qpdf" ifadeleri güncellenir
  (davranış değişmez; engine-agnostik kontrol).

## Faz 3 — `/ID` kalıntısı kabul raporu

- [ ] `docs/ID_RESIDUAL_ACCEPTANCE.md` (veya FINAL_RC_REPORT ekine)
  yazılır; içerik:
  - Kalıntının tanımı ve kök nedeni: pdfTeX `/ID` = trailer'da rastgele
    64 bayt; SDE `/CreationDate`/`/ModDate`'i sabitler, `/ID`'yi değil.
  - Ölçüm: iki koşum arasında **tek** fark bu 64 bayt (ölçüldü);
    qpdf `--static-id`/`--remove-metadata` ile giderilemez (donmuş
    bulgu + bu makinede tekrar ölçüldü).
  - **Kabul kararı:** teslim boru hattı `/ID`-kanonik hash'i
    (`/ID [<0…0> <0…0>]` normalizasyonu) determinism referansı olarak
    alır; raw hash yalnız bilgi.
  - Etki: zip/zip_lineage ve `PDF_METADATA_SIDECAR` deseninde raw-PDF
    hash'i artık motor değişiminde değişir → sidecar'lar `accept` target'ı
    ile **bilinçli yenilenir**; eski→yeni hash ikilisi rapora yazılır
    (tectonic `ad8fca69…`/`47681218…` → TeXLive `544516b0…`).
- [ ] Kabul raporu, `verify_delivery.py` --strict-determinism bayrağının
  yeni semantiğine referans verir (Faz 4).

## Faz 4 — Doğrulama zinciri güncellemesi

- [x] `verify_delivery.py` K6-DETERM yorum/davranışı: "tectonic
  non-deterministic" yorumu ölçüyle güncellenir (SDE ile
  deterministik; kalıntı /ID) — strict mod, /ID-kanonik karşılaştırmaya
  bağlanır.
  **Uygulandı (2026-10-01):** kanıt ve sözleşme
  `docs/ID_RESIDUAL_ACCEPTANCE.md` §4 satır 5 + §6; kapı
  `_calisma/CIKTI/verify_delivery.py` (`canonical_pdf_hashes`,
  `ledger_canonical_hashes`), kanonik uygulama
  `_calisma/CIKTI/pdf_id_canonical.py`, sözleşme testleri
  `_calisma/CIKTI/test_k6_determ_canonical.py` (17 test). Strict varsayılan
  açık; kapatma `--no-strict-determinism`.
- [ ] `check-zip-lineage-drift` + repack akışı: motor geçişi tek seferlik
  **bilinçli sidecar yenilemesi** ile işaretlenir (repack determinizm
  kapısı, yeni kanonik hash'i bekler).
  *Açık: teslim PDF'i henüz TeXLive ile yeniden derlenmedi; defterdeki
  "TeXLive-era teslim" satırı hâlâ `—`. Yenileme teslim paketini
  değiştirdiği için ayrı iş.*
- [ ] Tam batarya (130 dosya) + coverage/drift/sync senkron kapıları
  yeşile sabitlenir.

## Faz 5 — Dokümantasyon

- [x] `docs/TEX_RENDER_PIPELINE.md`: TeXLive-birincil akış; karşılaştırma
  tablosu ölçülmüş verilerle güncellendi (TeXLive bağımlılığı artık VAR —
  Homebrew/CI paketi). **Ölçülen sonuç:** `render_z3_slides.py` motoru
  `pdflatex → latex → tectonic` sırasıyla seçiyor ve TeXLive'li bu makinede
  `find_tex_engine()` = **`pdflatex`**, `find_pdf_to_png()` = **`convert`** —
  yani pratikte **Method 1** yürüyor; `tectonic` yalnız TeXLive yokken devreye
  giren düşüş yolu. Belgeye §6 eklendi: iki motorun **tam 64-hex** kanonik
  hash'leri, ölçülen çapraz-platform asimetrisi (ayrışan pdfTeX, tectonic
  değil) ve yüzeye göre motor seçimi. Önceki "TeXLive'siz" tezi düzeltildi.
  *Dürüstlük notu:* "TeXLive-birincil" **teslim artefaktı** için henüz
  doğru değil — teslim PDF'i hâlâ tectonic-era (kabul defteri §4 satır 5),
  yeniden derleme bilinçli yenileme olarak bekliyor.
- [x] `skills/reproducible-pdf-build/SKILL.md`: "future migration" bölümü
  **completed** işaretlendi (Status update + Step 5 başlığı + checklist);
  `/ID` kabul raporuna (`docs/ID_RESIDUAL_ACCEPTANCE.md`) referans verildi.
  Ayrıca **ölçümle çürütülmüş** alan dersi düzeltildi: kararsızlık
  `tectonic`'e değil pdfTeX'in rastgele trailer `/ID`'sidir; eski iddia
  "superseded" olarak işaretlendi.
- [x] README changelog: göç (`24a9b25`, `173a2f4`), kabul raporu ve hash
  geçişi satırları `update_changelog_hook.sh` ile senkron (gecikmeli/lag-one
  yazım sözleşmesi: tablo her commit'ten sonra tam bir commit geridedir).

## Faz 6 — CI geçişi

- [ ] `verify.yml`: determinism adımına TeXLive kurulumu
  (`texlive-latex-recommended texlive-latex-extra texlive-fonts-recommended`
  — kaynak paketin font/kitaplık ihtiyacına göre ayarlanır) +
  `TEXLIVE_BIN` ile deney koşumu; beklenen: CI'da kanonik hash
  `544516b0…` (font paketleri aynıysa) — **eşleşmezse** Faz 3 kabul
  raporu CI'ya özgü hash ikilisiyle genişletilir (ölçmeden varsayma).
- [ ] Dockerfile dokunulmaz (dashboard konteyneri TeX taşımıyor);
  docker-security Trivy gate'i etkilenmez.
- [ ] Kabul: 3 workflow (test-smoke, docker-security, verify-delivery)
  success — gerçek koşum kanıtıyla.

## Faz 7 — Geri dönüş planı

- [ ] Tek adım: `Makefile.tectonic` + eski sidecar'lar repo'da kalır;
  `git revert` ile Faz 1–6 commit'leri geri alınabilir.
- [ ] Paralel hash defteri (tectonic ↔ TeXLive kanonik hash ikilileri)
  kabul raporunda tutulur — iki motorlu dönem boyunca geçerli.

---

## Kanıt ekleri

- `docs/ci_simulate/texlive_determinism/texlive_determinism_report.txt`
  (2 bağımsız TeXLive koşumu: raw farklı, kanonik `a75c3409…` eşit,
  `residual=/ID`, verdict=PASS)
- Bu planın probe'ları (2026-09-17): tectonic kanonik `47681218…`;
  TeXLive 3-geçiş kanonik `544516b0…` ×2 bağımsız koşum; sayfa 33=33;
  metin farkı yalnız heceleme/glif eşlemesi.
- Skill donmuş bulgusu: `skills/reproducible-pdf-build/SKILL.md` §2
  (qpdf `--remove-metadata` kendisi nondeterministik — 3 koşum
  deneyi).
