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

**Durum (2026-09-30):** dört kalem de kapandı. 3.–4. kalemler önceki tura,
1.–2. kalemler bu tura aittir; 1.–2. kalemlerin **çalışma-zamanı PASS
ölçümü** artık tazelendi (koşum kanıtı aşağıda) ve `DETERMINISM_PASSES`
default'u 3'e çevrildi (Faz 4 re-baseline'ı) — tek-geçiş modu
`DETERMINISM_PASSES=1` ile hâlâ seçilebilir.

- [x] `texlive_determinism_hook.sh` birincil kapı olur: TeXLive+python3
  varken SKIP **yok**; tectonic ayağı bilgi amaçlı ikincil kalır. Verdict
  semantiği dürüst: ham farklı + kanonik eşit + `residual=/ID` → PASS;
  kanonik farklı → FAIL. **Ölçüm (2026-09-30, bu makine):** `TEXLIVE_BIN=/opt/homebrew/bin
  bash texlive_determinism_test.sh` → rc=0, `passes=3`, tectonic
  `ad8fca69…`, TeXLive kanonik `544516b0…` ×2 bağımsız koşum birebir eşit,
  `residual=/ID`, `verdict=PASS`; kanıt `logs/texlive_determinism_report.txt`
  (CI artifact'ı) + stdout'a da basılır.
- [x] `texlive_determinism_test.sh`'e **3-geçiş modu** eklendi ve artık
  **varsayılan** (tek-geçiş deneyi K6 hizalama gerçeğini yakalamıyor: çapraz
  ref/bib ancak çok geçişte çözülür). Son-log `Rerun to get` kalmadığı
  fail-closed denetlenir (`texlive_run1/2_rerun_left=0`; ölçümde 0). Stub
  testleri yeni akışa uyarlandı
  (test_texlive_determinism_id_residual **8 test** yeşil: default 3-geçiş +
  env ile tek-geçiş + rerun fail-closed yolları).
- [x] `render_z3_slides.py` zaten `pdflatex → latex → tectonic` sırasını
  deniyor — **koruyucu test eklendi**
  (`test_render_z3_slides.TestEngineSelection`, 9 test): öncelik
  pdflatex > latex > tectonic; pdflatex kuruluyken tectonic'e DÜŞÜLMEZ;
  seçim `Araçlar: LaTeX=...` satırında log'lanır; motor/PDF→PNG aracı
  yoksa fail-closed (rc=2). Makine kurulumundan bağımsız ölçüm: sahte
  PATH + `rz.shutil` yaması. **4 mutasyonun 4'ü yakalandı** ve bu kanıt artık
  KALICI: `TestEngineSelectionMutationGuard` (2 test) her koşumda
  `render_z3_slides.py`'nin geçici bir kopyasına sıra-ters /
  latex-düşürülmüş / fail-open mutasyonlarını uygular ve koruyucunun KIRMIZI
  düştüğünü doğrular (mutasyon kaçarsa test fail — sessiz motor kayması geri
  gelemez). `test_render_z3_slides.py` toplam 23 test.
- [x] `check_review_freshness.py` / `check_bibliography_sync.py`
  doküman/metin yorumlarında "tectonic + qpdf" ifadeleri **güncellendi**
  (davranış değişmedi — iki kapı da rc=0; 39 sözleşme testi yeşil):
  artık "LaTeX derleme (motor-agnostik: tectonic ya da TeXLive) + qpdf"
  deniyor, kapının motordan bağımsız olduğu açıkça yazılı.

## Faz 3 — `/ID` kalıntısı kabul raporu

**Durum (2026-09-30):** kapandı. Rapor `docs/ID_RESIDUAL_ACCEPTANCE.md`
olarak yazıldı (2026-09-20, `24a9b25`); bu turda planın istediği **eski→yeni
motor hash ikilisi** §5'e açıkça yazıldı ve `accept` artık kabul kanıtını
**gerçek üreticiye** delege ediyor — `docs/Makefile.texlive`'in `accept`
target'ı `_calisma/CIKTI/gen_id_residual_acceptance.py`'yi çağırıyor:
rapor ayrıştırılır (verdict=PASS + rerun=0 ×2 + run1=run2), kanonik hash §4
defterinde aranır, **defter satırı ölçülen alanlardan üretilir**
(`LEDGER=update`; `residual=none` → ham-hash fallback). Önceden Makefile
yalnız `sed`+`grep` ile elle yazılmış satırı okuyordu.

- [x] `docs/ID_RESIDUAL_ACCEPTANCE.md` (veya FINAL_RC_REPORT ekine)
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
- [x] Kabul raporu, `verify_delivery.py` --strict-determinism bayrağının
  yeni semantiğine referans verir (Faz 4) — §6 mezhep: strict mod
  `/ID`-kanonik karşılaştırmaya bağlanır ve K6-DETERM'in "tectonic
  non-deterministic" yorumu §1–2 ölçümüyle güncellenir.

Kanıt (2026-09-30): `test_gen_id_residual_acceptance.py` 24 test (kanonik
fallback, kanıt tutarsızlığı fail-closed, defter üretimi + idempotans,
varsayılan mod salt-okunur); `test_makefile_texlive.py` 15 test (accept
üreticiye bağlı + `LEDGER` güncelleme yolu); `make … accept` gerçek motorlarla
rc=0 verip defter satırı 4'ün `544516b0…` önekini kabul ediyor.

## Faz 4 — Doğrulama zinciri güncellemesi

**Durum (2026-09-30, 2. tur):** 1. ve 2. kalem kapandı; 3. kalem açık.
Kanonik çekirdek `_calisma/CIKTI/id_canonical.py`'ye çıkarıldı (verify +
repack + K14 tek kaynak) ve `--strict-determinism` artık pre-commit hook'u +
CI (`verify.yml --full`) düzeyinde **ETKİN**.

- [x] `verify_delivery.py` K6-DETERM yorum/davranışı ölçüyle güncellendi:
  "tectonic non-deterministic" teşhisi kaldırıldı (SDE ile motor
  deterministik; tek kalıntı `/ID`), strict mod **`/ID`-kanonik hash'e**
  bağlandı. Ortak çekirdek: `_calisma/CIKTI/id_canonical.py` (verify +
  repack + K14 aynı normalizasyon + defter çözümlemesi). Yeni yardımcılar:
  `canonical_pdf_sha256` (`/ID` çiftini `<0…0>`'a indirger; desen yoksa ham
  hash — fail-safe), `resolve_id_residual_ledger` (tokens/error/source; env →
  repo docs → mirror-drop), `k6_determ_verdict` (saf karar fonksiyonu;
  sidecar kanonik uyuşmazlığı da strict'te P1). Semantik: default'ta ham +
  metadata-stripped + kanonik bilgi olarak raporlanır (P1 yok);
  `--strict-determinism` ile kanonik hash defterde kayıtlı değilse **P1** +
  remedy (`make … accept LEDGER=update`), defter/PDF okunamıyorsa
  fail-closed P1. **metadata-stripped karşılaştırması artık P1 nedeni
  değil**: qpdf `--remove-metadata`'nın kendisi kararsız (teslim PDF'i
  üzerinde ölçüldü: 3 koşum → 3 farklı hash `38fc668c…`/`747334c4…`/`0de3124d…`,
  gate koşumunda 4. değer `de8be5a0…`). Defter tarafı: teslim PDF'inin
  kanoniği `d4f67e39…` §4 teslim tablosuna ölçülerek yazıldı (3× kararlı).
  **Doğrulama:** `test_k6_determ_canonical.py` 20 test (kanonik `/ID`
  nötrleme + içerik farkı gizlenmez + fail-safe + defter kümesi + strict
  kararları + kaynak sözleşmesi + ortak çekirdek `TestIdCanonicalModule`),
  4/4 mutasyon yakalandı;
  `verify_delivery.py --dir _calisma/CIKTI --strict-determinism` →
  **rc=0, P0=0, P1=0**, çıktı: "K6-DETERM: canonical=d4f67e39… kabul
  defterinde kayıtlı".
  **Etkinleştirme (bu tur):** bayrak artık gerçekten AÇIK — pre-commit
  `verify_delivery_hook.py` iç çağrısına ve CI `verify.yml` `--full`
  adımına `--strict-determinism` eklendi; hook DEPS'ine `id_canonical.py` +
  `docs/ID_RESIDUAL_ACCEPTANCE.md` de girdi (stage edilmemişse uyarı).
- [x] `check-zip-lineage-drift` + repack akışı: motor geçişi tek seferlik
  **bilinçli sidecar yenilemesi** ile işaretlenir. Uygulandı:
  - Kabul defterinin "Teslim sidecar'ı geçiş kaydı" tablosunda **kanonik
    kolonu** var; strict kapı bu deftere bağlı.
  - `repack_delivery.py` motor-geçişinde sidecar'ı bilinçli yeniler ve
    yazmadan ÖNCE `check_ledger_entry` ile yeni kanonik hash'i defterde
    arar — kayıtsızsa **fail-closed** durur (exit 1; remedy: `make … accept
    LEDGER=update`). Sidecar artık `# canonical:` (determinizm referansı) ve
    `# renewal: <tarih> — gerekçe` satırlarını taşır.
  - `check_zip_lineage_drift.py` (K14) commit anında sidecar `# canonical:`
    referansını defterle karşılaştırır: kayıtsız → **P0**; `# canonical:`
    satırı yoksa (yenileme beklemede) INFO — engellemez.
  - Kanıt: `test_repack_verify.py::CheckLedgerEntryTests` (kayıtlı→PASS,
    kayıtsız→remedy'li FAIL, defter okunamaz→fail-closed),
    `test_check_zip_lineage_drift.py::TestSidecarCanonical` +
    `TestVerifyDeliveryConstantParity`; canlı repoda `check_zip_lineage_drift.py`
    rc=0 (sidecar yenilemesi beklemede → INFO).
- [ ] Tam batarya (130 dosya) + coverage/drift/sync senkron kapıları
  yeşile sabitlenir.

## Faz 5 — Dokümantasyon

- [ ] `docs/TEX_RENDER_PIPELINE.md`: tectonic varyantı yerine
  TeXLive-birincil akış; karşılaştırma tablosu ölçülmüş verilerle
  güncellenir (TeXLive bağımlılığı artık VAR — Homebrew/CI paketi).
- [ ] `skills/reproducible-pdf-build/SKILL.md`: "future migration"
  bölümü "completed" işaretlenir; `/ID` kabul raporuna referans.
- [ ] README changelog: göç, kabul raporu ve hash geçişi satırı
  (`update_changelog_hook.sh` ile senkron).

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

### Faz 4 trend re-baseline'ı (2026-09-30)

Deney default'u 3-geçişe çevrilince trend kaydı da yeni baza bağlandı:

- `record_determinism_trend.py` kayıt şemasına **`passes`** alanı eklendi;
  eski satırlar (alan yok) 1 kabul edilir. Uzlaşma değişmezi artık
  kaynak + platform + **geçiş modu** kapsamlıdır: 1-geçiş ve 3-geçiş
  kanonikleri tanım gereği farklı olduğundan mod değişimi **sahte ihlal
  üretmez** (not olarak yazılır: "geçiş modu değişti 1 → 3 … bilinçli
  re-baseline"), ama aynı mod içindeki sapma yine FAIL'dir. Çok-geçiş
  ölçümü, `rerun_left=0 ×2` kanıtı olmadan kaydedilmez (fail-closed).
  `residual=none` (ham hash'ler baştan eşit) raporunda kanonik alanlar
  yoktur → kanonik = ham fallback'i
  (`gen_id_residual_acceptance.py` ile aynı kural).
- **Ölçüm:** gerçek 3-geçiş koşumu `docs/ci_simulate/…` raporuna yazıldı ve
  `--update` ile kaydedildi: satır 6 = `2026-09-30 / darwin / passes=3 /
  tectonic ad8fca69… / texlive 544516b0…`. `--check` → **rc=0**; notlar:
  çapraz-platform tectonic eşitliği + geçiş-modu re-baseline'ı. Mod
  kapsaması olmasa bu satır uzlaşma ihlali gibi görünürdü (aynı
  platform+kaynak, farklı kanonik) — kanıt: `_passes` filtreleri.
- **Test:** `test_record_determinism_trend.py` 22 test yeşil (passes
  çıkarımı + kanıtlanmamış çok-geçiş reddi + `residual=none` fallback +
  mod-kapsamlı uzlaşma + `_mode_note`).

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
