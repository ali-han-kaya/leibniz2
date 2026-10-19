# docs/ — Dizin (Diátaxis haritası)

> **Amaç:** `docs/` altındaki her belgeyi *hangi kadranda durduğu* ve *kim
> tarafından okunduğu* bilgisiyle tek sayfada göstermek. Bu sayfa belgeleri
> açıklamaz, onlara işaret eder — bir bulma kapısıdır. Öncesinde bir belgeyi
> bulmanın tek yolu kök `README.md` changelog satırını gözle taramaktı.
>
> **Pin:** Bu sayfa `_calisma/CIKTI/test_docs_index.py` ile fail-closed
> doğrulanır: yeni bir belge eklenip buraya işlenmezse, burada artık var
> olmayan bir belge kalırsa ya da `Uçuşta` bölümündeki bir belge main'e
> girerse kapı kırmızı olur.

## Nasıl okunur

- **Kadran = belgenin birincil amacı** (Diátaxis: öğrenme / görev / bilgi /
  anlayış). Bir belge birden çok işe yarıyorsa birincil kadrana yerleştirilir,
  ikincil işi hücre metninde anılır.
- Bu deponun belgelerinin çoğu **kayıttır**: olay, denetim, karar, teslim
  raporu. Diátaxis'in dört kadranı *ürün dokümanı* içindir; kayıtlar o
  ihtiyaçların hiçbirine hizmet etmediği için **uydurma kadran ataması
  yapılmaz** — ayrı bölümlerde toplanırlar (`Kayıt ve karar belgeleri`,
  `Süreç belgeleri`).
- **Kod/kapı bağı** sütunu belgeyi *okuyan* kodu/kapıyı gösterir: o yol
  değişirse belge de birlikte değişmelidir. `—` ise belge yalnız insan
  içindir.
- **Kapsam:** kadran tabloları `git ls-files docs/` (HEAD = `main`) kümesinden
  türetilir. Diskte olup main'de izlenmeyen taslaklar `Uçuşta` bölümündedir;
  üretilmiş/ignore'lu ağaçlar en sonda anılır.
- `Uçuşta` satırları bilinçli olarak **bağlantı değil**, repo-göreli yol
  (ters tırnak) olarak yazılır: bu dalda o dosyalar yoktur, bağlantı 404
  verirdi.
- Uçuşta olan `docs/FIRST_RUN_TUTORIAL.md` §7 bazı belgeleri
  *okuyucu-niyeti* ekseninde başka kadranlara koyar; bu sayfa belgenin kendi
  kapsamını esas alır.

## Kadran seçici

| Ne arıyorsunuz | Kadran | Bölüm |
|---|---|---|
| Depoyu ilk kez kurup uçtan uca koşturmak | Tutorial | main'de yok — bkz. [Uçuşta](#uçuşta-mainde-izlenmiyor) |
| Bir görevi yapmak (commit öncesi kapı, publish, dashboard, deploy, arıza) | How-to | [How-to](#how-to) |
| Bir sözleşmeyi aramak (sürüm matrisi, olay şeması, kabul defteri) | Reference | [Reference](#reference) |
| Neden böyle olduğunu anlamak (motor determinizmi, yama deseni, kök neden) | Explanation | [Explanation](#explanation) |
| Ne oldu / ne karar verildi | Kayıt | [Kayıt ve karar belgeleri](#kayıt-ve-karar-belgeleri) |
| İş nasıl planlandı, tasarım neydi | Süreç | [Süreç belgeleri](#süreç-belgeleri-plan-ve-tasarım-spec) |

## Tutorial

*Öğrenme-yönelimli: yeni gelen birinin adım adım ilerlediği anlatı.*

main'de izlenen bir öğretici belge **yok**. Bunun için yazılmış tek metin
uçuşta olan `docs/FIRST_RUN_TUTORIAL.md`'dir (clone → ilk `verify` → ilk
dashboard, `Diátaxis: Tutorial` beyanıyla); main'e girdiğinde bu bölüme
taşınmalıdır.

## How-to

*Görev-yönelimli: "şunu nasıl yaparım" — adımlar, komutlar, kontrol listeleri.*

| Belge | Ne verir | Kod/kapı bağı |
|---|---|---|
| [LOCAL_VERIFICATION_HOWTO.md](LOCAL_VERIFICATION_HOWTO.md) | Kapıları CI ile aynı parametrelerle lokalde koşmak: tek komut, tam zincir, CI simülasyonu, arıza tablosu (§4), kapı tablosu (§5). Kendi beyanı: `Diátaxis: How-to`. | — |
| [RUN_DASHBOARD.md](RUN_DASHBOARD.md) | Temiz kopyadan preview server + dashboard ayağa kaldırma (bare Python / Docker / launchd üç yol), `/api` yüzeyi probu, React prototipi. | `_calisma/CIKTI/preview_server.py` |
| [PUBLISH_SCENARIO.md](PUBLISH_SCENARIO.md) | Yayın ve push senaryosu: tek komut (`publish_wrapper.sh`), CI-simulate provası, artımlı günlük döngü, regresyon notları (R1–R3), job kategorileri tablosu. | `check_doc_job_sync.py`, `check_doc_wrapper_sync.py`, `check_workflow_artifact_docs.py`, `audit_live_ci_sync.py`, `verify.yml` |
| [CI_READINESS_CHECKLIST.md](CI_READINESS_CHECKLIST.md) | CI/CD workflow değişikliğini merge etmeden önce taranacaklar: YAML kuralları, pre-commit zinciri, branch protection, K-katmanları, sırlar. | — |
| [CI_GATE_TRIAGE.md](CI_GATE_TRIAGE.md) | Kırmızı `verify` koşumunu adım adım kök nedene indirmek (hangi adım koştu → izlenmeyen bağımlılık → mirror sözleşmesi); bilinen tuzak: göreli-yol taramaları sessizce boş döner. | — |
| [VERCEL_DEPLOYMENT.md](VERCEL_DEPLOYMENT.md) | Vercel'de canlı dashboard: `/api` adaptörü, deploy yolu ve runtime gerekleri, canlı üretim kanıtı, VCS-kapsam kararı (§1/§3 tasarım-karar bölümleridir). | `api/_adapter.py`, `.github/workflows/vercel-preview-deploy.yml` |
| [branch-protection-guide/README.md](branch-protection-guide/README.md) | GitHub UI'da branch protection kurulumu: 8 adım, ekran görüntüleri + tek dosyalık HTML kılavuz (`PUBLISH_SCENARIO.md` AŞAMA 1(b)'ye bağlanır). | — |
| [perf/README.md](perf/README.md) | Performans iddialarını tekrar koşulabilir kılan harness'lar (`load_history` önbelleği): betik + ham çıktı + repro komutu; gerçek `history.jsonl` ile ölçüm, sentetik fixture yok. | `docs/perf/profile_load_history.py`, `_calisma/CIKTI/preview_server.py` |

## Reference

*Bilgi-yönelimli: tanımlar, alan listeleri, sözleşmeler — baştan sona okunmaz, aranır.*

| Belge | Ne verir | Kod/kapı bağı |
|---|---|---|
| [HOOK_ENV_MATRIX.md](HOOK_ENV_MATRIX.md) | Hook'ların koştuğu araç sürümleri ve doğrulama komutları; `verify_delivery.py` probe'unun tek kaynağı. | `check_hook_env_matrix.py`, `check_mirror_coverage.py`, `Dockerfile` |
| [SERVER_EVENT_LOG.md](SERVER_EVENT_LOG.md) | `server_events.jsonl`: konum, şema, rotasyon politikası + canlı çökme/kurtarma kanıtı. | `preview_server.py`, `test_server_events.py`, `apps/dashboard-next/lib/preview.ts` |
| [CLAIM_EVIDENCE_MATRIX.md](CLAIM_EVIDENCE_MATRIX.md) | Makale içerik iddiaları ↔ hesaplamalı kanıt eşlemesi (kabul yüklemleri + holdout kuralı). | — |
| [ID_RESIDUAL_ACCEPTANCE.md](ID_RESIDUAL_ACCEPTANCE.md) | `/ID` kalıntısının kabulü: kök neden, ölçüm, kabul kararı ve tectonic ↔ TeXLive hash geçiş defteri. | `pdf_id_canonical.py`, `test_id_residual_acceptance_doc.py`, `_calisma/CIKTI/REFERANS_KANIT_DENETIMI.md` |
| [BROWSER_QA_TOOLING.md](BROWSER_QA_TOOLING.md) | Tarayıcı-QA aracı seçimi (Orca embedded browser ↔ agent-browser) senaryo-matrisi + doğrulama kaydı ve sınırlılıkları. Kendi beyanı: `Diátaxis: Reference / scenario-matrix`. | — |
| [AZURE_SEARCH_REFS_DESIGN.md](AZURE_SEARCH_REFS_DESIGN.md) | Azure Search refs yüzeyinin kısa tasarım notu: üretici `gen_refs_index.py` → `refs-index.json`. | — |

## Explanation

*Anlayış-yönelimli: "neden böyle" — kararların arkasındaki ölçüm ve gerekçe.*

| Belge | Ne verir | Kod/kapı bağı |
|---|---|---|
| [TEX_RENDER_PIPELINE.md](TEX_RENDER_PIPELINE.md) | Denklem → görsel hattı: klasik TeXLive akışı ↔ tectonic düşüş yolu, ne zaman hangisi, ölçülmüş motor karşılaştırması (§2/§3 alan-alan sözleşme tablolarıdır). | `rca_report.py`, `test_k6_determ_canonical.py`, `_calisma/REVIEW/build_review_pdf.sh` |
| [DOCKER_SECURITY_PATCHING.md](DOCKER_SECURITY_PATCHING.md) | Trivy fail-closed yama döngüsü: üç katman, tetikleme yüzeyleri (ölçülen asimetri), npm `overrides` deseni, CVE defteri. | `Dockerfile`, `github_scripts/trivy_sarif_pr_comment.js`, `rca_report.py`, `.pre-commit-config.yaml` |
| [RCA_REPACK_SIDECAR_DRIFT.md](RCA_REPACK_SIDECAR_DRIFT.md) | INC-4 kök neden: teslim zip'i kaynakla senkron değildi — iki katmanlı sözleşme, neden geç fark edildi, önlemler. | `rca_report.py`, `test_rca_report.py` |
| [RUN_STREAM_REPLAY_TAIL_DESIGN.md](RUN_STREAM_REPLAY_TAIL_DESIGN.md) | Run-stream replay kuyruğu tasarımı + SSE-flood ölçümü (belge bunu "kod değişikliği YAPILMADI" diye işaretler). | — |
| [KNOWN_INCIDENTS.md](KNOWN_INCIDENTS.md) | Bilinen CI olayları, belirti → kök neden → kesin çözüm → önlem düzeninde (INC-N); benzer belirtilerin tanınması için. | `rca_report.py`, `test_rca_report.py` |

## Kayıt ve karar belgeleri

*Kadran dışı: ne olduğunun ve ne karar verildiğinin kaydı. Diátaxis'in dört kadranından hiçbiri değildir; tarihli anlık görüntülerdir, güncellenmez.*

| Belge | Ne verir | Kod/kapı bağı |
|---|---|---|
| [FINAL_RC_REPORT.md](FINAL_RC_REPORT.md) | RC raporu: kapatılan P0'lar, ölçülen kanıtlar, açık borçlar, karar; kapsam dökümü `FULL_SCOPE_AUDIT_2026-09-17.md`'de. | `test_id_residual_acceptance_doc.py` |
| [FULL_SCOPE_AUDIT_2026-09-17.md](FULL_SCOPE_AUDIT_2026-09-17.md) | Tam kapsam denetimi: taranan katmanlar, kapatılan borçlar (R3/R6/a11y turları), kalan riskler, kanıt dizini. | `test_security_cron_schedule.py` |
| [PRE_PUSH_DENETIM_RAPORU.md](PRE_PUSH_DENETIM_RAPORU.md) | Push öncesi denetim: CI'ı yeşile götüren üç kırılmanın kaydı + branch-protection/CI güçlendirmesi (oturum 2). | `ci_stats.py`, `gen_ci_trend.py`, `check_absolute_paths.sh` |
| [MERGE_DECISION_reword-working_to_main.md](MERGE_DECISION_reword-working_to_main.md) | `reword-working` → `main` birleştirme kararı: topoloji ve sayılar, commit-bazlı değerlendirme, çakışma çözümü, riskler. | — |
| [COMMIT_MSG_BLOCK_EVIDENCE.md](COMMIT_MSG_BLOCK_EVIDENCE.md) | Hook'ların BLOKE kanıtı: gerçek kötü başlık/format denemeleri ve birebir çıktılar. | `gen_commit_msg_evidence.py`, `.github/workflows/verify.yml` |
| [DEPLOY_EVIDENCE.md](DEPLOY_EVIDENCE.md) | Deploy kanıt-defteri (tarih × HEAD × koşum sonuçları) + bayatlık kapısı (haftalık cron). | `deploy_evidence.py`, `.github/workflows/ci-rca-comment.yml` |
| [DOCKER_SECURITY_GATE_MERGE_REPORT.md](DOCKER_SECURITY_GATE_MERGE_REPORT.md) | PR #65–#69 docker-güvenlik birleşik teslim raporu: beş birim, test sayısı ilerlemesi, zincir kanıtı. | `test_gated_schedules.py` |
| [TEXLIVE_FAZ1_3_MERGE_REPORT.md](TEXLIVE_FAZ1_3_MERGE_REPORT.md) | TeXLive Faz 1-3 (PR #52) teslim raporu: dört birim + merge sırasında bulunan üç sessiz hata. | — |
| [HISTORY_CLEANUP.md](HISTORY_CLEANUP.md) | History temizliği kaydı: ezilen noise commit'ler, yöntem, adli iz, önleme + preview-server legacy temizliği. | `.gitmessage` |

## Süreç belgeleri (plan ve tasarım spec)

*Kadran dışı: işin nasıl yürütüleceğinin planı/spec'i. Repo konvansiyonu gereği yürütülmüş planlar bile işaretsiz (checkbox'sız) kalır.*

| Belge | Ne verir | Kod/kapı bağı |
|---|---|---|
| [TEXLIVE_MIGRATION_PLAN.md](TEXLIVE_MIGRATION_PLAN.md) | Tectonic → TeXLive göçü Faz 0–7: her fazın sözleşmesi, kanıt ekleri, geri dönüş planı. | `texlive_determinism_test.sh` |
| [HATHITRUST_ROADMAP.md](HATHITRUST_ROADMAP.md) | HathiTrust katalog hattı: dört kaynağın kitap-bazlı engelleri ve çözüm önerileri. | — |
| [superpowers/plans/2026-08-30-preview-compact-json-publish.md](superpowers/plans/2026-08-30-preview-compact-json-publish.md) | Compact-JSON publish işi: global kısıtlar + görev listesi (taze doğrulama → tek commit → push). | — |
| [superpowers/plans/2026-09-17-a11y-gate-implementation.md](superpowers/plans/2026-09-17-a11y-gate-implementation.md) | a11y-gate uygulama planı T1–T7: axe-core vendor, kapı config'i, `a11y_gate.py`, CI job'ı. | `a11y_gate.py`, `test_a11y_gate.py` |
| [superpowers/plans/2026-09-19-dev-bootstrap.md](superpowers/plans/2026-09-19-dev-bootstrap.md) | `dev_bootstrap.sh` uygulama planı: kısıtlar, görevler, taze-kopya kurulumu, öz-denetim kaydı. | — |
| [superpowers/plans/2026-09-23-a11y-gate-implementation.md](superpowers/plans/2026-09-23-a11y-gate-implementation.md) | a11y-gate kalan-kapsam planı: rapor-verdict sözleşmesi, job-summary sözleşmesi, tarayıcı-E2E turu. | `verify.yml`, `a11y_gate.py` |
| [superpowers/plans/pr42-body.md](superpowers/plans/pr42-body.md) | PR #42 gövdesi: niyet, commit listesi, doğrulama, bilinen takip işleri. | — |
| [superpowers/specs/2026-09-17-a11y-gate-design.md](superpowers/specs/2026-09-17-a11y-gate-design.md) | a11y-gate onaylı tasarımı: mimari, veri akışı sözleşmesi, raporlama yüzeyleri, fail-closed hata yönetimi. | `.github/workflows/verify.yml`, `a11y_gate.py` |

## İzlenen md dışı dosyalar

*Bu dizinde belge olmayan ama sözleşmeye giren dosyalar.*

| Yol | Ne |
|---|---|
| `docs/Makefile.texlive`, `docs/Makefile.tectonic` | PDF üretim hattının iki motor-makefile'ı (TeXLive / tectonic); `TEX_RENDER_PIPELINE.md` ve `ID_RESIDUAL_ACCEPTANCE.md` bunlara dayanır. |
| `docs/publish_wrapper.sh`, `docs/publish_precheck.sh` | `PUBLISH_SCENARIO.md`'nin koştuğu yayın/ön-kontrol betikleri. |
| `docs/branch-protection-guide/guide.html`, `render_screens.py`, `test_render_screens.py`, `step-0N-*.png` (8 adım) | Branch-protection kılavuzunun HTML render'ı, üreticisi, testleri ve ekran görüntüleri. |
| `docs/determinism_trend/determinism_trend.jsonl` | Kanonik PDF hash'lerinin haftalık trend kaydı (`determinism-trend` workflow'u yazar). |
| `docs/superpowers/specs/2026-09-17-a11y-gate-dataflow.excalidraw` | a11y-gate tasarımındaki veri akışı şemasının kaynak dosyası. |

## Uçuşta (main'de izlenmiyor)

*Bu dalda yok, main'e henüz girmemiş. Aşağıdaki yollar bağlantı değildir; çoğu `land/migration-gates-2026-09-30` hattında durur. Biri main'e girdiğinde yukarıdaki kadran tablolarına taşınmalı — taşınmazsa `test_docs_index.py` kırmızı olur.*

| Belge | Önerilen kadran | Hangi dalın ağacında |
|---|---|---|
| `docs/FIRST_RUN_TUTORIAL.md` | Tutorial | `land/migration-gates-2026-09-30` (+`feat/github-site-sample`) — main'deki tutorial boşluğunu doldurur |
| `docs/PDF_DETERMINISM_EXPLAINED.md` | Explanation | `land/migration-gates-2026-09-30` (+`feat/github-site-sample`) |
| `docs/PREVIEW_API_REFERENCE.md` | Reference | `feat/github-site-sample` (+`land/migration-gates-2026-09-30`) |
| `docs/API_VERSIONING.md` | Reference | `land/migration-gates-2026-09-30` (+`feat/github-site-sample`) |
| `docs/TREND_CHART_READ_PATH.md` | Explanation | `land/migration-gates-2026-09-30` |
| `docs/VERIFY_JOB_CHECKLIST.md` | How-to | `land/migration-gates-2026-09-30` |
| `docs/READER_TEST_PROTOCOL.md` | How-to | `land/migration-gates-2026-09-30` (+`feat/github-site-sample`) |
| `docs/AI_SERVICE_EVAL.md` | Kayıt | `land/migration-gates-2026-09-30` (+`feat/github-site-sample`); en yeni sürümü hiçbir dalda değil (detached worktree) |
| `docs/UNCOMMITTED-INVENTORY.md` | Kayıt | `land/migration-gates-2026-09-30` |
| `docs/HAKEM_INCELEME_RAPORU_2026-09-27.md` | Kayıt | `land/migration-gates-2026-09-30` |
| `docs/OTURUM_OZETI_2026-09-27.md` | Kayıt | `land/migration-gates-2026-09-30` |
| `docs/SKILL_SURFACE_INVENTORY.md` | Kayıt | `land/migration-gates-2026-09-30` |
| `docs/a11y_preview_scan_2026-09-24.md` | Kayıt | `land/migration-gates-2026-09-30` (+`feat/github-site-sample`) |
| `docs/archive/rc-review-20260831/review_dispatch.md` | Kayıt (arşiv) | `land/migration-gates-2026-09-30` |
| `docs/archive/rc-review-20260831/run.md` | Kayıt (arşiv) | `land/migration-gates-2026-09-30` |
| `docs/superpowers/plans/2026-09-24-a11y-gate-implementation.md` | Süreç | `land/migration-gates-2026-09-30` (+`feat/github-site-sample`) |
| `docs/ADR-0001-pinokio-launcher-javascript.md` | Kayıt (karar) | `feat/github-site-sample` — Pinokio launcher betikleri JS kalır (Go/Python/shell reddedildi) |
| `docs/superpowers/specs/2026-10-14-trend-verification-design.md` | Süreç | hiçbir dalda yok — yalnız çalışma kopyasında (trend doğrulama zincirinin tasarım kaydı) |
| `docs/SKILL_TOUR_MARATHON.md` | Kayıt | hiçbir dalda yok — yalnız çalışma kopyasında |
| `docs/ARCHIL_ENV_NOTE.md` | Reference | hiçbir dalda yok — yalnız çalışma kopyasında |

> Not: "Hangi dalın ağacında" sütunu `git ls-tree` ile ölçüldü — dosyanın o
dalın ağacında *bulunduğunu* söyler, dalın main'e alınacağını değil. Main'e
ilk giren dal kazanır; satır o zaman kadran tablosuna taşınır.

## Üretilmiş ve izlenmeyen dizinler

- `docs/ci_simulate/` — koşum başına üretilen CI kanıt raporları (gitignore'lu;
  `TEXLIVE_FAZ1_3_MERGE_REPORT.md`, `RCA_REPACK_SIDECAR_DRIFT.md` gibi
  belgeler buradaki raporlara atıf yapar; kalıcı kayıt `docs/determinism_trend/`
  ve ilgili rapor belgeleridir).
- `docs/determinism_trend/` — izlenen; içeriği md dışı tabloda.
- `docs/superpowers/` — plan/spec alt ağacı; izlenen dosyalar yukarıda,
  arşivdeki `archive/` alt ağacı ise uçuşta bölümünde.

## Bu dizini kim günceller

1. `docs/` altına izlenen bir `.md` ekleyip bu sayfaya işlemezseniz
   `_calisma/CIKTI/test_docs_index.py` kırmızı olur (eksik satır).
2. Bir belge silinirse/yeniden adlandırılırsa dizindeki satır bayatlar ve
   kapı yine kırmızı olur — satır `Uçuşta`'ya değil, doğru bölüme taşınır.
3. `Uçuşta` bölümündeki bir belge main'e girdiğinde kadran tablosuna
   taşınmalıdır (kapı bunu da denetler).
