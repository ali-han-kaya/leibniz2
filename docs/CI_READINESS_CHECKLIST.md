# Pre-Merge CI Readiness Checklist

CI/CD workflow değişikliklerini merge etmeden ÖNCE bu kontrol listesini
tamamla. Her madde, mevcut bir doğrulama komutuna bağlıdır — elle "gözle
baktım" yok, komut çıktısı kanıttır. Tüm komutlar repo kökünden çalıştırılır.

Desen kaynağı: `adobe/skills@appbuilder-cicd-pipeline` `references/checklist.md`
— bölümlere ayrılmış, komut bağlantılı, merge-öncesi hazır olma denetimi.

---

## Workflow Dosyaları (YAML)

- [ ] Workflow dosyaları `.github/workflows/` altında, repo kökünde
- [ ] **actionlint temiz** (TÜM workflow'lar, glob):
      ```bash
      bash _calisma/CIKTI/lint_actionlint.sh
      ```
      RC ≤ 2 PASS (advisory), RC > 2 FAIL. Yeni workflow dosyası eklenirse
      glob sayesinde otomatik kapsama girer.
- [ ] **python3/shell uyumluluğu** (her `shell: python3` adımı geçerli Python):
      ```bash
      python3 _calisma/CIKTI/check_python3_shell.py
      ```
- [ ] **Action pinleri** — her action `@<sha>` veya sabit sürüm tag'iyle pinli,
      `@main`/`@master` yok:
      ```bash
      python3 _calisma/CIKTI/check_action_pins.py --workflow .github/workflows
      ```
      (dizin modu: `.github/workflows/` altındaki tüm `*.yml`/`*.yaml`
      otomatik denetlenir — yeni workflow dosyası eklemek pin kapsamını
      otomatik genişletir; tek dosya için `--workflow …/verify.yml` verilir)
- [ ] **`scriptPath` yasağı** — github-script adımlarında `scriptPath:` input'u
      yok (yalnızca `script:`); `check_action_pins.py` bunu fail-closed yakalar.
- [ ] `verify.yml`'de YAML yapışıklığı yok (actionlint + CI advisory step çift kapı).

## Pre-commit Zinciri

- [ ] Tüm pre-commit hook'ları yeşil:
      ```bash
      pre-commit run --all-files
      ```
- [ ] **check-unit-tests** — birim test kapısı (59 test dosyası):
      ```bash
      bash _calisma/CIKTI/check_unit_tests_hook.sh
      ```
- [ ] **verify-delivery** (K1-K7 çekirdek, fail-closed):
      ```bash
      python3 _calisma/CIKTI/verify_delivery_hook.py --strict
      ```
- [ ] **check-repro-manifest --strict** (K13 self-test + unstaged-deps kapısı):
      ```bash
      python3 _calisma/CIKTI/check_repro_manifest_hook.py --strict
      ```
- [ ] **check-pattern-consistency --strict** (artifact pattern drift'i):
      ```bash
      python3 _calisma/CIKTI/check_pattern_consistency_hook.py --strict
      ```
- [ ] **verify-delivery-sde** (K21 SDE determinism guard):
      ```bash
      python3 _calisma/CIKTI/verify_delivery.py --dir _calisma/CIKTI --check-sde
      ```
- [ ] **check-plist-drift** (golden ↔ render, fazla-profil P0 fail-closed):
      ```bash
      python3 _calisma/CIKTI/check_plist_drift_hook.py
      ```
- [ ] **check-coverage-report** (tüm test/hook kapsamı):
      ```bash
      python3 _calisma/CIKTI/test_coverage_report.py
      ```
- [ ] **commit-msg-style** + **check-changelog-sync** (changelog otomatik senkron).

## Branch Protection / Required Checks

- [ ] Beklenen 9 check adı tek kaynaktan (`verify.yml` job `name:` alanları):
      ```bash
      python3 _calisma/CIKTI/status_checks.py
      ```
- [ ] **Canlı GitHub doğrulaması** — branch protection'daki required check
      listesi birebir eşleşiyor (eksik/fazla = drift, exit 1):
      ```bash
      python3 _calisma/CIKTI/status_checks.py --gh --repo <owner>/<repo>
      ```
- [ ] **Advisory kontratı** — tüm job adlarıyla required set arasındaki fark
      raporlanıyor, `advisory_contract.ok == true`:
      ```bash
      python3 _calisma/CIKTI/status_checks.py --gh --json
      ```
- [ ] Koruma kurulu (branch protection) — koruma yoksa `--gh` 404'ü güvenle
      atlar (ilk publish akışı), ama required check'ler kurulu olmalı.

## Verify Zinciri (K-katmanları)

- [ ] **Tam zincir** yerel PASS:
      ```bash
      python3 _calisma/CIKTI/verify_delivery.py --dir _calisma/CIKTI --full
      ```
      → `SONUÇ: PASS (P0=0, P1=0)` ve K-katman özetinde FAIL yok.
- [ ] K8 Z3 (`--symbolic-proof`), K9 Lean (`--lean-proof`: sorry/axiom +
      statement-safety + aksiyom analizi + lake build 8 teorem), K19 Coq
      (`--coq-proof`) — ilgili araç kurulu ortamda fail-closed PASS.
- [ ] K10 manifest digest — `--verify-manifest reproducibility/manifest.json`
      config.combined_sha256 dahil yeniden hesaplanıp doğrulanıyor.
- [ ] K18 daemon smoke (`--check-daemon`) + K20 launchctl (`--check-launchd`)
      — daemon üç endpoint HTTP 200, launchd profilleri canlı.

## Reproducibility & Doküman Senkronu

- [ ] **Canlı CI ↔ doküman senkronu** — doc'taki job/artifact listesi son CI
      run'ıyla birebir (yeni artifact eklenince doc güncellenene kadar uyarı):
      ```bash
      python3 _calisma/CIKTI/audit_live_ci_sync.py
      ```
- [ ] **Config ↔ CONFIG_BASENAMES senkronu** — "Bundle config snapshot"
      adımındaki her dosya manifest'te config olarak işaretli:
      ```bash
      python3 _calisma/CIKTI/check_config_sync.py
      ```
- [ ] **Referans tablosu ↔ .tex senkronu**:
      ```bash
      python3 _calisma/CIKTI/check_refs_table_sync.py
      ```
- [ ] **PUBLISH_SCENARIO artifact listesi ↔ `gen_repro_manifest.py`
      ARTIFACT_JOBS** çapraz doğrulaması yeşil:
      ```bash
      python3 -m unittest _calisma.CIKTI.test_doc_artifact_sync
      ```
- [ ] Reproducibility manifest'i CI'da yeniden üretilip SHA-256 sabitleniyor
      (K10 digest + reproducibility job).

## Güvenlik / Sırlar

- [ ] Workflow'larda hardcoded credential yok (secret referansları
      `${{ secrets.* }}`).
- [ ] `.env` / `.aio` gibi sır dosyaları `.gitignore`'da, commit history'de
      yok.
- [ ] **check-absolute-paths** — betiklerde ortama bağımlı mutlak yol yok:
      ```bash
      bash _calisma/CIKTI/check_absolute_paths.sh
      ```
- [ ] **shellcheck-hooks** — hook betikleri shellcheck temiz:
      ```bash
      bash _calisma/CIKTI/shellcheck_hooks.sh
      ```

## Canlı Doğrulama (push sonrası)

- [ ] Push edildi, CI run'ı başladı:
      ```bash
      gh run watch
      ```
- [ ] Tüm job'lar yeşil (12/12 veya güncel sayı), hiçbir job
      `if-no-files-found: error` ile düşmüyor.
- [ ] **Hiçbir job/step timeout'a düşmemiş** — failed job log'larında GitHub
      timeout marker'ı yok (fail-closed; herhangi bir eşleşme = job FAIL):
      ```bash
      gh run view --log-failed 2>/dev/null | grep -iE "has exceeded the|timed out after"
      ```
      Çıktı boş olmalı (timeout yok). Bir eşleşme çıkarsa o job gerçekten
      tam limitini aşmıştır — `verify.yml`'de ilgili job'ın `timeout-minutes`
      yükseltilir (örn. K9 lean-proof 15m).
- [ ] Beklenen artifact'lar yüklendi (python3-shell, precommit-logs,
      lineage-findings, reproducibility manifest dahil):
      ```bash
      python3 _calisma/CIKTI/audit_live_ci_sync.py --json
      ```
- [ ] Run sonrası `status_checks.py --gh --json` advisory kontratı hâlâ
      `ok: true`.
- [ ] PR merge edilebilir durumda (required check'ler yeşil, label-gate geçti).

---

## Not

- Her satırın kanıtı komut çıktısıdır; bir komut hata verirse madde işaretli
  sayılmaz (fail-closed).
- Bu listenin kendisi de doküman-artifact senkronuna tabidir — yeni bir
  doğrulama komutu eklenirse buraya da bağlanmalı (`audit_live_ci_sync.py`
  deseni).
