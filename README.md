# Stoic-Hume V5 — Teslim ve Doğrulama Deposu

Bu repo, *What an Extensional First-Order Formalization Leaves
Underdetermined: Stoic Katalepsis and Humean Custom* (V5, 2026-08-17)
teslimini ve onu doğrulayan fail-closed araç zincirini içerir.

## İçerik

| Yol | İçerik |
|---|---|
| `.github/workflows/verify.yml` | GitHub Actions kapısı — her push'ta `verify` + `symbolic` job'ları; raporlar artifact olarak yüklenir |
| `_calisma/CIKTI/verify_delivery.py` | Tek komutluk doğrulama (K1–K8: sidecar → checksum → manifest → script → PDF/referans → hijyen → Z3 ispatı) + bütçe kalkanı + `--check-references` |
| `_calisma/CIKTI/symbolic_proof_z3.py` | Teoremlerin Z3 ile sembolik ispatı (12/12, P4-d/P4-e dahil) |
| `_calisma/CIKTI/*.zip` + `.sha256` | Ana taşıma birimi (`TESLIM_KLASOR…`) ve iç teslim (`TESLIM_V5_FINAL…`) |
| `_calisma/CIKTI/*.md` | Denetim raporları (M0 denetim, referans kanıt, sembolik ispat) |
| `_calisma/lean_reduct/` | reduct-invariance lemmasının Lean 4 formalizasyonu (derlenmiş, exit 0) |
| `_calisma/repack_delivery.py` · `sync_docs.py` | Zincir yeniden üretimi ve belge senkronu yardımcıları |
| `.pre-commit-config.yaml` | Commit öncesi fail-closed kapı |

## Doğrulama (tek komut)

```bash
# Bütünlük + içerik kapısı (stdlib-only)
python3 _calisma/CIKTI/verify_delivery.py --dir _calisma/CIKTI

# + Z3 sembolik ispat (z3-solver gerekir)
python3 _calisma/CIKTI/verify_delivery.py --dir _calisma/CIKTI --symbolic-proof
```

Exit kodu: `0` = PASS, `1` = FAIL (fail-closed), `2` = ortam hatası.
Çevrimiçi referans denetimi: `--check-references` (CrossRef/SEP).

## Reproducibility manifest — config artifact bölümü

`gen_repro_manifest.py` (CI `reproducibility` job'ı) artifact'ları hash'leyip
`manifest.json` + `manifest.txt` + `manifest.sha256` üretir. `config/` önekli
artifact'lar ayrıca bir **config bölümü** olarak işaretlenir; `combined_sha256`
bu dosyaların hangi sürümünün kullanıldığını tek hash ile özetler.

### manifest.json (config bölümü)

`config.files` anahtarları sıralıdır; değerler dosyaların tam SHA-256'sıdır.
Örnek (iki config dosyası: `effective_config.json` + `gen_config.json`):

```json
{
  "config": {
    "files": {
      "config/effective_config.json": "ddd95c59dea17217143690da01a992376573dc06a7dd5e998dc5347786f5cccb",
      "config/gen_config.json": "f741e59ac91662e4e738e3f7907b6dc20e5c4223c8f6aac35e7955fc5e66eada"
    },
    "combined_sha256": "ffcdf1aa8097b4442163a3609238ccbe8910e853900922cd3ea054e7053425ce"
  }
}
```

### combined_sha256 hesabı (deterministik)

Anahtarlar sıralanır, her girdi `"{rel}\0{sha256}\n"` olarak birleştirilir ve
SHA-256 alınır (formül `verify_delivery.py --verify-manifest` K10'da birebir
aynı şekilde **yeniden hesaplanarak** doğrulanır):

```python
import hashlib

config_files = {  # config.files (yukarıdaki örnek)
    "config/effective_config.json": "ddd95c59dea17217143690da01a992376573dc06a7dd5e998dc5347786f5cccb",
    "config/gen_config.json": "f741e59ac91662e4e738e3f7907b6dc20e5c4223c8f6aac35e7955fc5e66eada",
}
combined = hashlib.sha256(
    "".join(f"{rel}\0{config_files[rel]}\n" for rel in sorted(config_files)).encode()
).hexdigest()
# → ffcdf1aa8097b4442163a3609238ccbe8910e853900922cd3ea054e7053425ce
```

### manifest.txt (insan-okur bölüm)

```
========================================================================
CONFIG ARTIFACT (ayrı bölüm)
========================================================================
FILE                                                    SHA-256
------------------------------------------------------------------------
config/effective_config.json                            ddd95c59dea17217143690da01a992376573dc06a7dd5e998dc5347786f5cccb
config/gen_config.json                                  f741e59ac91662e4e738e3f7907b6dc20e5c4223c8f6aac35e7955fc5e66eada
------------------------------------------------------------------------
config_combined_sha256: ffcdf1aa8097b4442163a3609238ccbe8910e853900922cd3ea054e7053425ce
========================================================================
```

### Denetim (fail-closed)

`python3 _calisma/CIKTI/verify_delivery.py --verify-manifest reproducibility/manifest.json`
(K10) şunları denetler — uyuşmazlık P1 → exit 1:

- `files` içindeki her SHA-256 gerçek dosyayla yeniden hash'lenir.
- `config.files` girdileri `files` ile tutarlı olmalıdır.
- `config.combined_sha256`, `config.files`'tan yukarıdaki formülle yeniden
  hesaplanıp kayıtlı değerle eşleşmelidir.
- `effective_config.json`'un `cli_overrides` kaydı, aynı config bundle'ındaki
  `verify_delivery.config.json` ile tutarlı olmalıdır: `file_value` dosya
  değeriyle eşleşmeli, `override` bayrağı `cli_given and cli_value != file_value`
  olmalı ve `effective` (override varsa `cli_value`, yoksa `file_value`) ile
  uyuşmalıdır. İkisi de `combined_sha256` ile sabitlendiğinden bu denetim,
  cli_overrides'ın manifest'teki config.combined_sha256 ile tutarlılığını kanıtlar.

Teslim kaynak dizinleri (`_calisma/TESLIM/`, `_calisma/V5_ICERIK/`,
`_calisma/TOOLKIT/`) kasıtlı olarak commit edilmez — içerik zip'lerin
içindedir ve `unzip` ile yeniden üretilebilir.

## Değişiklik Geçmişi (repo-level changelog)

> Her satır `git show <commit>` ile denetlenebilir. Yayın öncesi denetim:
> [`docs/PRE_PUSH_DENETIM_RAPORU.md`](docs/PRE_PUSH_DENETIM_RAPORU.md).
> Yayın senaryosu: [`docs/PUBLISH_SCENARIO.md`](docs/PUBLISH_SCENARIO.md).

| Tarih | Kategori | Değişiklik | Commit |
|---|---|---|---|
| 2026-08-17 | teslim | İlk teslim: V5 zip + sidecar + manifest + verify_delivery.py (K1-K7) | `a3544d8` |
| 2026-08-17 | ispat | Z3 sembolik ispat (12/12) + `symbolic_proof_z3.py` | `a3544d8` |
| 2026-08-17 | ispat | Lean 4 reduct-invariance (8 teorem, Mathlib-free) | `a3544d8` |
| 2026-08-18 | ci | GitHub Actions workflow (3 kapı: verify + Z3 + lake build) | `a3544d8` |
| 2026-08-18 | ci | Bütçe kalkanı + `verify_delivery.config.json` + statik raporlar | `5d62685` |
| 2026-08-18 | ci | Reproducibility manifest (K10, SHA-256 + manifest.sha256) | `5d62685` |
| 2026-08-18 | history | Test-marker commit'leri squash ile ezildi (`d863977`/`991473d`) | `0fab281` |
| 2026-08-18 | ci | `--check-references` (CrossRef/SEP çevrimiçi) | `a3544d8` |
| 2026-08-18 | publish | `PUBLISH_SCENARIO.md` + `publish_wrapper.sh` (tek komut) | `a3544d8` |
| 2026-08-18 | publish | `status_checks.py` — required check adları workflow'dan tek kaynaktan | `b4f0f6c` |
| 2026-08-18 | ci | Repack determinism + sidecar sync (`repack_delivery.py --verify`) | `60a8aed` |
| 2026-08-19 | ci | K0 stale-zip taraması (recursive, `_calisma/` altı) | `e3aa72a` |
| 2026-08-19 | ci | K11 config drift (`gen_config.py --dry-run`) | `a3544d8` |
| 2026-08-19 | ci | K12 plist drift (macOS advisory) | `231844e` |
| 2026-08-19 | ci | K13 commit-msg gate + `setup_commit_hooks.sh` | `18ce1df` |
| 2026-08-19 | ci | K14 cleanup katmanı (silme/taşıma kayıtları) | `716da90` |
| 2026-08-19 | ci | K15 history.jsonl ↔ `.sha256` sidecar | `a3544d8` |
| 2026-08-19 | ci | K16 github-scripts self-test (mock fixture'lar) | `18ce1df` |
| 2026-08-19 | publish | `--ci-simulate` modu (`publish_wrapper.sh`) | `a309b23` |
| 2026-08-19 | refs | Çevrimiçi referans denetimi 54/54 (OpenLibrary + CrossRef + SEP) | `0057e22` |
| 2026-08-20 | ci | `consolidate_summary.py` (run summary 5 bölüm → tek kaynak) | `91af275` |
| 2026-08-20 | ci | `PRECOMMIT_RAPORU.json` + JSON Schema doğrulaması | `683b3f7` |
| 2026-08-20 | ci | actionlint pre-commit + CI advisory (YAML yapışık yakalama) | `0f458b5` |
| 2026-08-20 | ci | `check-action-pins` (action major pinleme, downgrade kapısı) | `1f84ba4` |
| 2026-08-20 | ci | `check_absolute_paths.sh` (mutlak yol commit'leri bloke) | `8116715` |
| 2026-08-20 | ci | `shellcheck_hooks.sh` (POSIX sh hook betikleri) | `ae55009` |
| 2026-08-21 | publish | Branch protection GH API ile kuruldu (8 required check) | `dc9ab4f` |
| 2026-08-21 | ci | `status_checks.py --gh` fail-closed (protection yoksa exit 1) | `df92ada` |
| 2026-08-21 | ci | `simulate_verify_job.sh` — `GITHUB_STEP_SUMMARY` + env-snapshot validation | `2282925` |
| 2026-08-21 | ci | precheck-report → reproducibility manifest (SHA-256) | `694b367` |
| 2026-08-21 | docs | add repo-level changelog + regression notes to README | `b07f5f4` |
| 2026-08-21 | feat | (ci) git log'dan otomatik changelog üret (gen_changelog.py) | `4286b4a` |
| 2026-08-21 | fix | (ci) changelog hook'u auto-sync yap (update-config deseni) | `5d5daf2` |
| 2026-08-21 | feat | (publish) --verify-checks bağımsız AŞAMA 1 doğrulama modu | `e15d0f4` |
| 2026-08-21 | docs | §9 oturum 3 denetim kaydı | `c6a221c` |
| 2026-08-21 | feat | (ci) --dry-run-summary regresyon kapısı (test_dryrun_summary.py) | `b5327e5` |
| 2026-08-21 | refs | V5n satırını refs-trend changelog'una işle (54→56) | `4216895` |
| 2026-08-21 | refs | Della Rocca 2010'ı Handle System API ile doğrula (V5t) | `a124e66` |
| 2026-08-21 | feat | (ci) K17 mirror sync kapısı (sync_verify_mirror.sh --check) | `7c3ab53` |
| 2026-08-21 | feat | (preview) update_preview.sh --bootstrap tek adım modu | `169a6c8` |
| 2026-08-21 | feat | fresh_clone_setup.sh — tek komutta TCC-safe ortam kurulumu | `ee772b6` |
| 2026-08-21 | feat | fresh_clone_setup.sh — tek komutta TCC-safe ortam kurulumu | `a09f1a2` |
| 2026-08-21 | fix | (ci) mirror'a eksik github_scripts'i ekle (K16 launchd rotası) | `e1abea6` |
| 2026-08-21 | feat | (ci) daemon-modu HTTP 200 testini advisory job olarak ekle | `be60442` |
| 2026-08-21 | feat | (ci) preview mirror'ı sync_verify_mirror.sh'e kat (adım 2+4) | `c57bb90` |
| 2026-08-21 | feat | (preview) refs trend grafiğine by_source yığılmış alan serisi | `4c41069` |
| 2026-08-21 | feat | (preview) refs trend noktalarına hover tooltip ekle | `78a3076` |
| 2026-08-21 | feat | (ci) action_runtimes.json'u repro manifest'ine kat (SHA-256) | `683333d` |
| 2026-08-21 | feat | (ci) action_pins.json'u manifest CONFIG bölümüne kat (SHA-256) | `800d76e` |
| 2026-08-21 | feat | --bump modu (WARN pin'lerini otomatik yükselt) | `e6abee6` |
| 2026-08-21 | docs | AŞAMA 1 (b) adım 9'a merge-engeli smoke notu ekle | `f632f20` |
| 2026-08-21 | fix | precheck (e) — status_checks --gh smoke'u fail-closed kapı yap | `ce0f633` |
| 2026-08-21 | docs | changelog — ce0f633 satırını işle | `245a0ac` |
| 2026-08-21 | fix | (ci) precheck'e administration:read — smoke CI'da koşsun | `8d10118` |
| 2026-08-21 | fix | status_checks --gh 404 ile yetki hatasını ayır (UNREADABLE) | `3226656` |
| 2026-08-21 | feat | (ci) precheck job'ına status_checks --gh --json sidecar'ı ekle | `d6b58a6` |
| 2026-08-21 | feat | (preview) /guide.html rotası + mirror senkronu | `d184c3c` |
| 2026-08-21 | feat | render_screens PNG uretimini mock HTML ile dogrula | `0a4f32b` |
| 2026-08-21 | feat | canli CI denetimini audit_live_ci_sync.py'ye cevir | `799409c` |
| 2026-08-21 | fix | audit kendini karsilastirmasin — CI yanlis-pozitif duzeltildi | `1499b93` |
| 2026-08-21 | docs | denetim bulgusunu changelog + REFERANS_KANIT_DENETIMI'ne isle | `031ed0f` |
| 2026-08-21 | docs | status_checks --gh canli dogrulamasini senaryoya isle | `7012f96` |
| 2026-08-21 | feat | publish_wrapper --incremental (INCREMENTAL push tek komut) | `1bbd2e5` |
| 2026-08-21 | docs | refs-trend changelog'una V5o satırı (11 UNVERIFIED → 56/56) | `bed5f67` |
| 2026-08-21 | feat | ia_ol_fallback_evidence.py (5 IA kaynağın kanıtı) | `a8fadb0` |
| 2026-08-21 | feat | python3-shell denetimini manifest'e SHA-256 ile sabitle | `1f9706f` |
| 2026-08-21 | docs | PUBLISH_SCENARIO artifact listesine python3-shell eklendi | `845206a` |
| 2026-08-21 | refactor | check_python3_shell çoklu workflow denetimi | `1491551` |
| 2026-08-21 | feat | audit_refs_trend.py (trend satırları ↔ kaynak artifact denetimi) | `c6ff4e1` |
| 2026-08-21 | feat | Lagree/Millican/Schmitt/Fine icin LoC katalog kaniti (V5w) | `7bc8363` |
| 2026-08-21 | docs | refs-trend changelog'una V5p satiri (OCLC/LCCN + Xunzi HT) | `3548341` |
| 2026-08-21 | docs | V5q changelog satırı + §2 tablo doğrulaması | `db61c80` |

### Regresyon notları

| ID | Tarih | Kırılma | Kök neden | Düzeltme | Commit |
|---|---|---|---|---|---|
| R1 | 2026-08-19 | CI 0s/0 job boş run | YAML adım `}` + `uses:` aynı satıra yapıştı | satır ayrımı + actionlint | `d57a60c` |
| R2 | 2026-08-21 | summary yerelde yazılmıyor | `GITHUB_STEP_SUMMARY` env boştu | iki aşamalı write + validate | `2282925` |
| R3 | 2026-08-21 | pre-commit block (actionlint RC=1) | shellcheck info hints advisory iken fail | `lint_actionlint.sh` RC≤2 PASS | `ae55009` |
| R4 | 2026-08-21 | `listLabels is not a function` | Octokit `listLabels` → `listLabelsForRepo` | 4 dosya güncellendi | `309a14f` |
