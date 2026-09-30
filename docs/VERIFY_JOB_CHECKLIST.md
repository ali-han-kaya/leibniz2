# verify.yml — yeni job ekleme kontrol listesi

Bu belge `verify.yml`'e job eklerken/değiştirirken **elle tutulması gereken
yüzeyleri** ve her birini **hangi kapının yakaladığını** listeler. Amaç: bir
job'un yarısını eklemek (job var; kararı, artifact kaydı veya dokümanı yok)
sessizce merge edilemesin.

> **Tek karar dosyası: `_calisma/CIKTI/workflow_contract.py`.**
> Required-vs-advisory kararı ve artifact kapsam kararları — `GATE_EXCLUDE`,
> `MERGE_PATTERN_EXCLUDED`, `DOC_ONLY_ADVISORY`, `UPLOAD_EXCEPTIONS` — yalnızca
> orada tanımlanır ve her üyenin gerekçesi satır yanında yaşar.
> `status_checks.py`, `gen_repro_manifest.py` ve testler **oradan içe aktarır,
> kopya taşımaz**. `verify.yml` job'un kendisidir; diğer yüzeyler ya türetilir
> (`status_checks.gate_jobs()` → required check adları) ya da aşağıdaki
> meta-test'lerce pin'lenir.

## 1) Karar ağacı (önce bunu yanıtla)

| Soru | Evet ise | Hayır ise |
|---|---|---|
| Merge'i bloke etmeli mi? | Required: `GATE_EXCLUDE`'ya **ekleme**; adı required pin'ine gir | Advisory/PR-only: `workflow_contract.GATE_EXCLUDE`'ya gerekçesiyle ekle |
| Artifact üretiyor mu? | Üçlü kayıt (§2.2) + bundle kararı | — |
| Başka job'ın artifact'ını tüketiyor mu? | `download-artifact` değerlendirmeden **önce** + `DELIVERIES` satırı (§2.5) | — |
| `logs/*.json` sidecar'ı yazıp okuyor mu? | `LOGS_SIDECAR_*` sözleşmesi (§2.6) | — |
| Herhangi bir adımda `continue-on-error: true` var mı? | Her upload adımı `if: always()` + coe tablosu satırı (§2.7) | — |
| Yeni bir `test_*.py` ekliyor mu? | `HOOK_COVERAGE` kaydı (§2.9) — manifest otomatik senkronlanır | — |

Required set **türetilir** (`gate_jobs()`), ama testler beklenen kümeyi pin'ler:
yeni bir job ne required'a ne `GATE_EXCLUDE`'ya girerse `check-unit-tests` kırmızı
olur ve her commit `--no-verify` gerektirir. Bu bir **policy** kararıdır, test
düzeltmesi değil.

## 2) Dosya dosya

### 2.1 Job'un kendisi — `.github/workflows/verify.yml`

- `id` (kebab-case), `name:` (branch protection check adının **tek kaynağı**),
  `runs-on`, `permissions`, `timeout-minutes` (zorunlu), `needs:` (gerekiyorsa).
- Kurulum adımları (`apt`/`pip`) `if: always()` taşımalı — bir üst adım düşerse
  araç kurulmadan koşup **sahte** K-katmanı P1'i üretmesin.
- Yeni `uses:` action'ı `action_pins.json`'a kaydedilir; ref izinli kalıba
  uymalı — `^v(\d+)(\.\d+){0,2}$` (major ya da semver etiketi). `@main`,
  `@master`, `@latest` ve çıplak SHA **reddedilir** (2026 tag-compromise sınıfı).
- **Kapı:** `test_workflow_timeouts` (`every named job has timeout`),
  `test_workflow_install_hardening`, pre-commit `check-action-pins`,
  CI job *Action runtime check (node24)* (`check_action_runtimes.py`),
  `lint_actionlint.sh` / `test_actionlint_gate`.

### 2.2 Üretilen artifact — tek kaynak + iki kayıt

Üç yüzey **aynı commit'te** hizalanır:

1. `verify.yml` `Upload …` adımı (artifact `name:`).
2. `docs/PUBLISH_SCENARIO.md` → `**Artifact listesi (N):**` bölümündeki giriş
   **ve `N` sayısı**.
3. `_calisma/CIKTI/gen_repro_manifest.py` → `ARTIFACT_JOBS`
   (`artifact → üreten job`), ya da bilinçli istisna:
   `workflow_contract.MERGE_PATTERN_EXCLUDED` / `UPLOAD_EXCEPTIONS` /
   `DOC_ONLY_ADVISORY`.

Bundle'a (reproducibility manifest'ine) girecek artifact ayrıca `verify.yml`
reproducibility job'ının **merge pattern**'ine yazılır.

- **Kapılar:** `check_workflow_artifact_docs.py` (workflow ↔ doc ↔ ARTIFACT_JOBS
  üçlüsü), `test_doc_artifact_sync`, `check_pattern_consistency.py`,
  `test_gen_repro_manifest.TestWorkflowPatternCoverage`.
- Külliyat: bir artifact'ı doc'ta bırakıp `ARTIFACT_JOBS`'a yazmamak
  `test_doc_artifact_sync`'i; `ARTIFACT_JOBS`'a yazıp merge pattern'e
  eklememek `check_pattern_consistency`'yi düşürür.

### 2.3 Job'un dokümanı — `docs/PUBLISH_SCENARIO.md`

- `**Job kategorileri (N job = X required + Y advisory + Z PR-only):**`
  tablosuna satır (`| sıra | A|B|C|D | <job name> | … |`) **ve başlıktaki N**
  güncellenir. Kategori = karar (§1).
- **Kapı:** `test_doc_job_sync` — tablo ↔ verify.yml `name:` iki yönlü
  karşılaştırma + başlık sayacı.

### 2.4 Required seti (yalnız required ise)

- `_calisma/CIKTI/test_status_checks.py` `TestGateJobs` pin'leri: tam küme +
  `len(required) == job sayısı − len(GATE_EXCLUDE)` sayacı.
- GitHub branch protection listesi ayrıca güncellenir; `status_checks.py --gh`
  workflow ↔ GitHub eşleşmesini ve merge engelini doğrular.
- **Kapı:** `test_status_checks` (`test_gate_jobs_exact_set_includes_label_gate`,
  `test_count_matches_workflow_minus_excludes`).

### 2.5 Sidecar tüketen kapı

- Değerlendirme adımından **önce** ilgili artifact'ı indiren bir
  `actions/download-artifact` adımı olmalı (aksi halde kapı eksik girdiyle
  vacuous PASS verir = fail-open).
- Required kapı, bağlandığı verdict'i adımında tüketmeli (ör. refs-trend,
  preview-reload-smoke).
- **Kapı:** `test_ci_sidecar_wiring` (`DELIVERIES`,
  `test_deliveries_precede_evaluation`, `TestRequiredGateVerdictBinding`) ve
  yorum job'ları için `test_*_inputs_delivered`.

### 2.6 `logs/*.json` sidecar'ı

- Workflow'da geçen her `logs/*.json` yolu ya bir upload `path:` claim'i ya da
  en az bir parser tarafından kapsanmalı; sözleşme
  `test_advisory_coe_surfacing.LOGS_SIDECAR_UPLOADS / _EXPORTS / _PRODUCERS /
  _PARSERS` tablolarına yazılır (upload claim'i **gerçekten** o yolu kapsamalı,
  parser'lar workflow'dan ≤1 atlamada erişilebilir olmalı).
- **Kapı:** `test_advisory_coe_surfacing.TestLogsSidecarSurfacing`
  (`test_every_workflow_sidecar_is_declared` — yorum satırları sayılmaz).

### 2.7 Advisory job (`continue-on-error`)

- Job'un **her upload adımı** `if: always()` taşımalı: coe bir adım düşse bile
  bulgu yayınlanmalı, yoksa bulgu runner'da ölür (maskelenir).
- `docs/PUBLISH_SCENARIO.md` coe denetim tablosuna satır eklenir
  (`# / Job / adım / çıktı / tüketici / hüküm` + dağılım sayacı). Bu tablo
  **makine tarafından pin'lenmez** (bkz. §5) — elle güncellenir.
- **Kapı:** `test_advisory_coe_surfacing.TestUploadAlwaysInCoeJobs`
  (`test_every_upload_in_coe_jobs_is_always` — offenders `job:adım` olarak
  listelenir).

### 2.8 Sıra / bağımlılık uyarısı

`needs:` zinciri, üst job kırmızı olduğunda alt **required** job'ların
`skipped` düşmesine yol açar; branch protection `skipped`'i karşılanmış saymaz.
Kanıt: 2026-09-12, `5524362` push run'ında K1-K19 kırmızı olduğu için
`config-drift`, `config-sync`, `reports` **hiç değerlendirilmedi**.

### 2.9 Yeni test dosyası / hook kapsamı

Bir `_calisma/CIKTI/test_*.py` eklerken **üç yüzey** vardır; ikisi otomatik,
biri elle:

1. `_calisma/CIKTI/check_unit_tests.list` — **otomatik**. `check_unit_tests_hook.sh`
   commit'ten önce `sync_check_unit_tests.py --update` koşar ve manifest'i
   stage eder; yeni dosya kendiliğinden girer, silinen çıkar.
2. `HOOK_COVERAGE` (`_calisma/CIKTI/test_coverage_report.py`) — **elle**. Dosya
   en az bir hook'a atanmalı (bu checklist gibi kapı/contract testleri için
   `"check-unit-tests"` listesi). Atanmazsa `check-coverage-report`
   (`test_coverage_report.py --check`) commit'i bloke eder ve eksik dosyayı
   adıyla listeler.
3. `.pre-commit-config.yaml` — **yalnız yeni bir hook** ekleniyorsa. Yeni bir
   test dosyası mevcut `check-unit-tests` hook'uyla kapsanıyorsa buraya
   dokunulmaz.

- **Kapılar:** `check-coverage-report`, `test_gate_coverage_sync.py`,
  `test_test_coverage_report.py`, `ci_full_discover_drift_guard.py` (kayıtlı
  batarya ↔ tam `unittest discover` sapması: kayıtsız test sessizce yeşil
  geçemez — 2026-09-12'de tam discover'da kırmızı olan bir dosya
  `pytest` seçimi yüzünden 8 turdur yeşil raporlanıyordu).
- **Bu belgenin kendisi pin'lidir:** `test_verify_job_checklist.py` — belgede
  adı geçen her repo yolu ve gate var olmalı; her kayıt yüzeyi hem belgede
  anılmalı hem de iddia ettiği dosyada **gerçekten** tanımlı olmalı;
  `workflow_contract.py`'deki her karar kümesi belgede anılmalı (ters yön).

## 3) Doğrulama (tek komut seti)

```bash
PY=_calisma/.venv_z3/bin/python

# Sözleşme kümesi + doc/artifact/job pin'leri (tek süreç; düz import sırası
# sorunlarından etkilenmemek için modülleri birlikte koşun)
"$PY" -m unittest \
  _calisma.CIKTI.test_workflow_contract \
  _calisma.CIKTI.test_doc_job_sync \
  _calisma.CIKTI.test_doc_artifact_sync \
  _calisma.CIKTI.test_status_checks \
  _calisma.CIKTI.test_workflow_timeouts \
  _calisma.CIKTI.test_workflow_install_hardening \
  _calisma.CIKTI.test_ci_sidecar_wiring \
  _calisma.CIKTI.test_advisory_coe_surfacing \
  _calisma.CIKTI.test_gen_repro_manifest \
  _calisma.CIKTI.test_audit_live_ci_sync \
  _calisma.CIKTI.test_verify_job_checklist

# Tekil denetçiler
"$PY" _calisma/CIKTI/check_workflow_artifact_docs.py
"$PY" _calisma/CIKTI/check_pattern_consistency.py
"$PY" _calisma/CIKTI/check_action_pins.py
"$PY" _calisma/CIKTI/status_checks.py --json > /dev/null

# Tam batarya (kayıtlı liste; yeni test dosyası otomatik girer)
bash _calisma/CIKTI/check_unit_tests_hook.sh
```

`audit-live-ci` (advisory) aynı sözleşmeyi **canlı run** üzerinde denetler:
`doc_live_sync` PASS olmalı (doc'ta olup canlıda olmayan / canlıda olup doc'ta
olmayan artifact = drift). Kapı kırmızıysa önce `failure_pattern` bölümüne
bakın — başka bir workflow'un tutarlı kırmızısı bu advisory'i kendi başına
düşürür (doc drift'i olmadan).

## 4) Kanıt — checklist nasıl doğrulandı

2026-09-12'de `5524362` HEAD'inden bir scratch worktree'de (`/tmp/jobcheck`)
sahte bir job eklenip her varyantta ilgili kapılar koşuldu; mutasyonlar geri
alındı. Gözlenen davranış (§2 ile birebir):

| Varyant | Yakalayan kapı ve mesaj |
|---|---|
| Yeni job + upload, doc/ARTIFACT_JOBS yok | `test_doc_job_sync` (`every workflow job documented`), `test_audit_live_ci_sync.TestE2EArtifactDocSync` (yeni upload ↔ doc), `check_workflow_artifact_docs` (`… PUBLISH_SCENARIO listesinde yok`), `test_status_checks` (küme + sayaç) |
| ARTIFACT_JOBS'a eklenip merge pattern'e eklenmemesi | `check_pattern_consistency` (`Eksik (satır …): pattern'de yok ama ARTIFACT_JOBS'da var: …`), `test_gen_repro_manifest.TestWorkflowPatternCoverage`, `test_doc_artifact_sync` |
| `timeout-minutes` yok | `test_workflow_timeouts.test_every_named_job_has_timeout` |
| coe adım + `if: always()`'sız upload | `test_advisory_coe_surfacing.test_every_upload_in_coe_jobs_is_always` (`['<job>:Upload …']`) |
| Yeni `logs/*.json` sidecar'ı, sözleşmede yok | `test_advisory_coe_surfacing.test_every_workflow_sidecar_is_declared` (liste) |
| Mutable ref `uses: some/action@main` | `check_action_pins` (`pin yok — yeni action action_pins.json'a eklenmeli (--update)`), `check_action_runtimes` |

## 5) Bilinen boşluklar (dürüstçe)

- **`test_verify_job_checklist.py` envanteri elle yazılır:** bu test belgenin
  §2 başlıklarını, yüzey tablosunu (`SURFACES`) ve kapı ailesini
  (`GATE_FAMILY`) pin'ler; belgeye adı geçen yeni bir **yüzey** eklenirse
  test tablosuna da satır eklenmelidir. Ters yön makinedir: `workflow_contract.py`'a
  yeni bir karar kümesi eklemek belgeyi güncellemeden **kırmızı olur**.
- **coe tablosu pin'siz:** §2.7'deki sıra/sayı tablosunu doğrulayan bir meta-test
  yok; `continue-on-error: true` sayısı ile tablo satırları elle senkron tutulur.
- **Job-seviyesi `continue-on-error`** `test_every_upload_in_coe_jobs_is_always`
  tarafından görülmez (sözleşme adım-seviyesi coe sayar). Repo konvansiyonu
  adım-seviyesidir; job-seviyesi kullanılacaksa bu kapı genişletilmelidir.
- **Kategorik olarak sıra `B → A` taşınan** bir job (advisory'den required'a)
  sadece §2.4 pin'lerini değil, GitHub branch protection listesini de
  gerektirir; bunu yalnız `status_checks.py --gh` (admin izni) doğrular.
