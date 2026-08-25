# Stoic-Hume V5 — Teslim ve Doğrulama Deposu

[![CI status](https://github.com/ali-han-kaya/leibniz2/actions/workflows/verify.yml/badge.svg)](https://github.com/ali-han-kaya/leibniz2/actions/workflows/verify.yml)
[![pre-commit](https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit&logoColor=white)](https://pre-commit.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

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

## _calisma/lean_reduct — Sınır İspatı Çekirdeği (illüstratif, Mathlib-free)

Bu modül Stoa/Hume formalizasyonu **DEĞİLDİR**. İspatlanan: 4 forget
haritasının injective olmadığı (temsil kaybı teoremi — varlık teoremi
değil). `World = actual` bilinçli en fakir modeldir: kaybın model
zenginliğinden değil, unutma haritasının kendisinden geldiğini göstermek
için.

| # | Teorem | Ne ispatlar | Yöntem |
|---|--------|-------------|--------|
| 1 | `historical_pair_collapses_under_forgetTopic` | tam unutma iki içeriği özdeşleştirir | rfl |
| 2-4 | `historical_pair_survives_forget{Access,Justification,Source}` | tek eksen unutması ayrımı silmez | cases |
| 5-8 | `forget{Access,Justification,Source,Topic}_not_injective` | 4 haritanın hiçbiri injective değil | cases+congrArg |

Mathlib bağımlılığı yoktur (`Injective` yerel tanımlı). `kataleptic-` /
`customary-` etiketli tanımlar illüstratif kod etiketleridir, tarihsel
formalizasyon değildir; ispatlanmayan şey ispatlandı denmez (fail-closed).

```bash
cd _calisma/lean_reduct
lake clean && lake build --wfail   # <5s, toolchain leanprover/lean4:v4.14.0
```

CI'da K9 kapısı (`verify` job'ı, `--full` içinde) aynı derlemeyi
fail-closed koşar; Z3 <-> Lean eşleşmesi `MAP.md`'de sabitlenmiştir
(diverge olmaması için korunur).

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
| 2026-08-17 | teslim | İlk teslim: V5 zip + sidecar + manifest + verify_delivery.py (K1-K7) | [`a3544d8`](https://github.com/ali-han-kaya/leibniz2/commit/a3544d8) |
| 2026-08-17 | ispat | Z3 sembolik ispat (12/12) + `symbolic_proof_z3.py` | [`a3544d8`](https://github.com/ali-han-kaya/leibniz2/commit/a3544d8) |
| 2026-08-17 | ispat | Lean 4 reduct-invariance (8 teorem, Mathlib-free) | [`a3544d8`](https://github.com/ali-han-kaya/leibniz2/commit/a3544d8) |
| 2026-08-18 | ci | GitHub Actions workflow (3 kapı: verify + Z3 + lake build) | [`a3544d8`](https://github.com/ali-han-kaya/leibniz2/commit/a3544d8) |
| 2026-08-18 | ci | Bütçe kalkanı + `verify_delivery.config.json` + statik raporlar | [`5d62685`](https://github.com/ali-han-kaya/leibniz2/commit/5d62685) |
| 2026-08-18 | ci | Reproducibility manifest (K10, SHA-256 + manifest.sha256) | [`5d62685`](https://github.com/ali-han-kaya/leibniz2/commit/5d62685) |
| 2026-08-18 | history | Test-marker commit'leri squash ile ezildi (`d863977`/`991473d`) | [`0fab281`](https://github.com/ali-han-kaya/leibniz2/commit/0fab281) |
| 2026-08-18 | ci | `--check-references` (CrossRef/SEP çevrimiçi) | [`a3544d8`](https://github.com/ali-han-kaya/leibniz2/commit/a3544d8) |
| 2026-08-18 | publish | `PUBLISH_SCENARIO.md` + `publish_wrapper.sh` (tek komut) | [`a3544d8`](https://github.com/ali-han-kaya/leibniz2/commit/a3544d8) |
| 2026-08-18 | publish | `status_checks.py` — required check adları workflow'dan tek kaynaktan | [`b4f0f6c`](https://github.com/ali-han-kaya/leibniz2/commit/b4f0f6c) |
| 2026-08-18 | ci | Repack determinism + sidecar sync (`repack_delivery.py --verify`) | [`60a8aed`](https://github.com/ali-han-kaya/leibniz2/commit/60a8aed) |
| 2026-08-19 | ci | K0 stale-zip taraması (recursive, `_calisma/` altı) | [`e3aa72a`](https://github.com/ali-han-kaya/leibniz2/commit/e3aa72a) |
| 2026-08-19 | ci | K11 config drift (`gen_config.py --dry-run`) | [`a3544d8`](https://github.com/ali-han-kaya/leibniz2/commit/a3544d8) |
| 2026-08-19 | ci | K12 plist drift (macOS advisory) | [`231844e`](https://github.com/ali-han-kaya/leibniz2/commit/231844e) |
| 2026-08-19 | ci | K13 commit-msg gate + `setup_commit_hooks.sh` | [`18ce1df`](https://github.com/ali-han-kaya/leibniz2/commit/18ce1df) |
| 2026-08-19 | ci | K14 cleanup katmanı (silme/taşıma kayıtları) | [`716da90`](https://github.com/ali-han-kaya/leibniz2/commit/716da90) |
| 2026-08-19 | ci | K15 history.jsonl ↔ `.sha256` sidecar | [`a3544d8`](https://github.com/ali-han-kaya/leibniz2/commit/a3544d8) |
| 2026-08-19 | ci | K16 github-scripts self-test (mock fixture'lar) | [`18ce1df`](https://github.com/ali-han-kaya/leibniz2/commit/18ce1df) |
| 2026-08-19 | publish | `--ci-simulate` modu (`publish_wrapper.sh`) | [`a309b23`](https://github.com/ali-han-kaya/leibniz2/commit/a309b23) |
| 2026-08-19 | refs | Çevrimiçi referans denetimi 54/54 (OpenLibrary + CrossRef + SEP) | [`0057e22`](https://github.com/ali-han-kaya/leibniz2/commit/0057e22) |
| 2026-08-20 | ci | `consolidate_summary.py` (run summary 5 bölüm → tek kaynak) | [`91af275`](https://github.com/ali-han-kaya/leibniz2/commit/91af275) |
| 2026-08-20 | ci | `PRECOMMIT_RAPORU.json` + JSON Schema doğrulaması | [`683b3f7`](https://github.com/ali-han-kaya/leibniz2/commit/683b3f7) |
| 2026-08-20 | ci | actionlint pre-commit + CI advisory (YAML yapışık yakalama) | [`0f458b5`](https://github.com/ali-han-kaya/leibniz2/commit/0f458b5) |
| 2026-08-20 | ci | `check-action-pins` (action major pinleme, downgrade kapısı) | [`1f84ba4`](https://github.com/ali-han-kaya/leibniz2/commit/1f84ba4) |
| 2026-08-20 | ci | `check_absolute_paths.sh` (mutlak yol commit'leri bloke) | [`8116715`](https://github.com/ali-han-kaya/leibniz2/commit/8116715) |
| 2026-08-20 | ci | `shellcheck_hooks.sh` (POSIX sh hook betikleri) | [`ae55009`](https://github.com/ali-han-kaya/leibniz2/commit/ae55009) |
| 2026-08-21 | publish | Branch protection GH API ile kuruldu (8 required check) | [`dc9ab4f`](https://github.com/ali-han-kaya/leibniz2/commit/dc9ab4f) |
| 2026-08-21 | ci | `status_checks.py --gh` fail-closed (protection yoksa exit 1) | [`df92ada`](https://github.com/ali-han-kaya/leibniz2/commit/df92ada) |
| 2026-08-21 | ci | `simulate_verify_job.sh` — `GITHUB_STEP_SUMMARY` + env-snapshot validation | [`2282925`](https://github.com/ali-han-kaya/leibniz2/commit/2282925) |
| 2026-08-21 | ci | precheck-report → reproducibility manifest (SHA-256) | [`694b367`](https://github.com/ali-han-kaya/leibniz2/commit/694b367) |
| 2026-08-21 | docs | add repo-level changelog + regression notes to README | [`b07f5f4`](https://github.com/ali-han-kaya/leibniz2/commit/b07f5f4) |
| 2026-08-21 | feat | (ci) git log'dan otomatik changelog üret (gen_changelog.py) | [`4286b4a`](https://github.com/ali-han-kaya/leibniz2/commit/4286b4a) |
| 2026-08-21 | fix | (ci) changelog hook'u auto-sync yap (update-config deseni) | [`5d5daf2`](https://github.com/ali-han-kaya/leibniz2/commit/5d5daf2) |
| 2026-08-21 | feat | (publish) --verify-checks bağımsız AŞAMA 1 doğrulama modu | [`e15d0f4`](https://github.com/ali-han-kaya/leibniz2/commit/e15d0f4) |
| 2026-08-21 | docs | §9 oturum 3 denetim kaydı | [`c6a221c`](https://github.com/ali-han-kaya/leibniz2/commit/c6a221c) |
| 2026-08-21 | feat | (ci) --dry-run-summary regresyon kapısı (test_dryrun_summary.py) | [`b5327e5`](https://github.com/ali-han-kaya/leibniz2/commit/b5327e5) |
| 2026-08-21 | refs | V5n satırını refs-trend changelog'una işle (54→56) | [`4216895`](https://github.com/ali-han-kaya/leibniz2/commit/4216895) |
| 2026-08-21 | refs | Della Rocca 2010'ı Handle System API ile doğrula (V5t) | [`a124e66`](https://github.com/ali-han-kaya/leibniz2/commit/a124e66) |
| 2026-08-21 | feat | (ci) K17 mirror sync kapısı (sync_verify_mirror.sh --check) | [`7c3ab53`](https://github.com/ali-han-kaya/leibniz2/commit/7c3ab53) |
| 2026-08-21 | feat | (preview) update_preview.sh --bootstrap tek adım modu | [`169a6c8`](https://github.com/ali-han-kaya/leibniz2/commit/169a6c8) |
| 2026-08-21 | feat | fresh_clone_setup.sh — tek komutta TCC-safe ortam kurulumu | [`ee772b6`](https://github.com/ali-han-kaya/leibniz2/commit/ee772b6) |
| 2026-08-21 | feat | fresh_clone_setup.sh — tek komutta TCC-safe ortam kurulumu | [`a09f1a2`](https://github.com/ali-han-kaya/leibniz2/commit/a09f1a2) |
| 2026-08-21 | fix | (ci) mirror'a eksik github_scripts'i ekle (K16 launchd rotası) | [`e1abea6`](https://github.com/ali-han-kaya/leibniz2/commit/e1abea6) |
| 2026-08-21 | feat | (ci) daemon-modu HTTP 200 testini advisory job olarak ekle | [`be60442`](https://github.com/ali-han-kaya/leibniz2/commit/be60442) |
| 2026-08-21 | feat | (ci) preview mirror'ı sync_verify_mirror.sh'e kat (adım 2+4) | [`c57bb90`](https://github.com/ali-han-kaya/leibniz2/commit/c57bb90) |
| 2026-08-21 | feat | (preview) refs trend grafiğine by_source yığılmış alan serisi | [`4c41069`](https://github.com/ali-han-kaya/leibniz2/commit/4c41069) |
| 2026-08-21 | feat | (preview) refs trend noktalarına hover tooltip ekle | [`78a3076`](https://github.com/ali-han-kaya/leibniz2/commit/78a3076) |
| 2026-08-21 | feat | (ci) action_runtimes.json'u repro manifest'ine kat (SHA-256) | [`683333d`](https://github.com/ali-han-kaya/leibniz2/commit/683333d) |
| 2026-08-21 | feat | (ci) action_pins.json'u manifest CONFIG bölümüne kat (SHA-256) | [`800d76e`](https://github.com/ali-han-kaya/leibniz2/commit/800d76e) |
| 2026-08-21 | feat | --bump modu (WARN pin'lerini otomatik yükselt) | [`e6abee6`](https://github.com/ali-han-kaya/leibniz2/commit/e6abee6) |
| 2026-08-21 | docs | AŞAMA 1 (b) adım 9'a merge-engeli smoke notu ekle | [`f632f20`](https://github.com/ali-han-kaya/leibniz2/commit/f632f20) |
| 2026-08-21 | fix | precheck (e) — status_checks --gh smoke'u fail-closed kapı yap | [`ce0f633`](https://github.com/ali-han-kaya/leibniz2/commit/ce0f633) |
| 2026-08-21 | docs | changelog — ce0f633 satırını işle | [`245a0ac`](https://github.com/ali-han-kaya/leibniz2/commit/245a0ac) |
| 2026-08-21 | fix | (ci) precheck'e administration:read — smoke CI'da koşsun | [`8d10118`](https://github.com/ali-han-kaya/leibniz2/commit/8d10118) |
| 2026-08-21 | fix | status_checks --gh 404 ile yetki hatasını ayır (UNREADABLE) | [`3226656`](https://github.com/ali-han-kaya/leibniz2/commit/3226656) |
| 2026-08-21 | feat | (ci) precheck job'ına status_checks --gh --json sidecar'ı ekle | [`d6b58a6`](https://github.com/ali-han-kaya/leibniz2/commit/d6b58a6) |
| 2026-08-21 | feat | (preview) /guide.html rotası + mirror senkronu | [`d184c3c`](https://github.com/ali-han-kaya/leibniz2/commit/d184c3c) |
| 2026-08-21 | feat | render_screens PNG uretimini mock HTML ile dogrula | [`0a4f32b`](https://github.com/ali-han-kaya/leibniz2/commit/0a4f32b) |
| 2026-08-21 | feat | canli CI denetimini audit_live_ci_sync.py'ye cevir | [`799409c`](https://github.com/ali-han-kaya/leibniz2/commit/799409c) |
| 2026-08-21 | fix | audit kendini karsilastirmasin — CI yanlis-pozitif duzeltildi | [`1499b93`](https://github.com/ali-han-kaya/leibniz2/commit/1499b93) |
| 2026-08-21 | docs | denetim bulgusunu changelog + REFERANS_KANIT_DENETIMI'ne isle | [`031ed0f`](https://github.com/ali-han-kaya/leibniz2/commit/031ed0f) |
| 2026-08-21 | docs | status_checks --gh canli dogrulamasini senaryoya isle | [`7012f96`](https://github.com/ali-han-kaya/leibniz2/commit/7012f96) |
| 2026-08-21 | feat | publish_wrapper --incremental (INCREMENTAL push tek komut) | [`1bbd2e5`](https://github.com/ali-han-kaya/leibniz2/commit/1bbd2e5) |
| 2026-08-21 | docs | refs-trend changelog'una V5o satırı (11 UNVERIFIED → 56/56) | [`bed5f67`](https://github.com/ali-han-kaya/leibniz2/commit/bed5f67) |
| 2026-08-21 | feat | ia_ol_fallback_evidence.py (5 IA kaynağın kanıtı) | [`a8fadb0`](https://github.com/ali-han-kaya/leibniz2/commit/a8fadb0) |
| 2026-08-21 | feat | python3-shell denetimini manifest'e SHA-256 ile sabitle | [`1f9706f`](https://github.com/ali-han-kaya/leibniz2/commit/1f9706f) |
| 2026-08-21 | docs | PUBLISH_SCENARIO artifact listesine python3-shell eklendi | [`845206a`](https://github.com/ali-han-kaya/leibniz2/commit/845206a) |
| 2026-08-21 | refactor | check_python3_shell çoklu workflow denetimi | [`1491551`](https://github.com/ali-han-kaya/leibniz2/commit/1491551) |
| 2026-08-21 | feat | audit_refs_trend.py (trend satırları ↔ kaynak artifact denetimi) | [`c6ff4e1`](https://github.com/ali-han-kaya/leibniz2/commit/c6ff4e1) |
| 2026-08-21 | feat | Lagree/Millican/Schmitt/Fine icin LoC katalog kaniti (V5w) | [`7bc8363`](https://github.com/ali-han-kaya/leibniz2/commit/7bc8363) |
| 2026-08-21 | docs | refs-trend changelog'una V5p satiri (OCLC/LCCN + Xunzi HT) | [`3548341`](https://github.com/ali-han-kaya/leibniz2/commit/3548341) |
| 2026-08-21 | docs | V5q changelog satırı + §2 tablo doğrulaması | [`db61c80`](https://github.com/ali-han-kaya/leibniz2/commit/db61c80) |
| 2026-08-21 | docs | HathiTrust katalog yol haritası (4 telifli kitap) | [`fa43551`](https://github.com/ali-han-kaya/leibniz2/commit/fa43551) |
| 2026-08-21 | feat | refs-online VERSION JSON'a ht_ids_summary ekle | [`efdd45a`](https://github.com/ali-han-kaya/leibniz2/commit/efdd45a) |
| 2026-08-21 | docs | bilinen CI olayları kaydı (KNOWN_INCIDENTS.md) | [`cf82c25`](https://github.com/ali-han-kaya/leibniz2/commit/cf82c25) |
| 2026-08-21 | docs | PUBLISH_SCENARIO canli durum tablosu guncelle | [`9f2516e`](https://github.com/ali-han-kaya/leibniz2/commit/9f2516e) |
| 2026-08-21 | refactor | persist sidecar testlerini test_preview_server.py'ye tasi | [`f1aab1d`](https://github.com/ali-han-kaya/leibniz2/commit/f1aab1d) |
| 2026-08-21 | feat | start_preview.sh — rebuild + start + health tek komut | [`cfa9139`](https://github.com/ali-han-kaya/leibniz2/commit/cfa9139) |
| 2026-08-22 | feat | update_preview.sh --status alt komutu | [`aacad00`](https://github.com/ali-han-kaya/leibniz2/commit/aacad00) |
| 2026-08-22 | feat | K18 launchctl durum katmani | [`efcb8bb`](https://github.com/ali-han-kaya/leibniz2/commit/efcb8bb) |
| 2026-08-22 | feat | plist-check artifact'ini reproducibility manifest'e dahil et | [`ecba674`](https://github.com/ali-han-kaya/leibniz2/commit/ecba674) |
| 2026-08-22 | docs | changelog auto-sync — plist-check manifest entry | [`62216d9`](https://github.com/ali-han-kaya/leibniz2/commit/62216d9) |
| 2026-08-22 | ci | plist-check run summary'de profiles sidecar tablosu | [`e9f6acf`](https://github.com/ali-han-kaya/leibniz2/commit/e9f6acf) |
| 2026-08-22 | ci | plist-check run summary'de profiles sidecar tablosu | [`deda5de`](https://github.com/ali-han-kaya/leibniz2/commit/deda5de) |
| 2026-08-22 | other | _calisma/CIKTI: run_summary_refs_trend.py CLI tutarlılık testleri | [`ff1e9c1`](https://github.com/ali-han-kaya/leibniz2/commit/ff1e9c1) |
| 2026-08-22 | ci | add pattern drift summary to reproducibility job run summary (#9) | [`328f8fc`](https://github.com/ali-han-kaya/leibniz2/commit/328f8fc) |
| 2026-08-22 | fix | (repro) PROVENANCE section labels merged vs prefixed vs absent (#10) | [`5b78b18`](https://github.com/ali-han-kaya/leibniz2/commit/5b78b18) |
| 2026-08-22 | ci | add check-pattern-consistency pre-commit hook (#11) | [`0440d82`](https://github.com/ali-han-kaya/leibniz2/commit/0440d82) |
| 2026-08-22 | ci | add K15 history sidecar check to daemon advisory job (#12) | [`84ee113`](https://github.com/ali-han-kaya/leibniz2/commit/84ee113) |
| 2026-08-22 | feat | (dashboard) show K15 history sidecar SHA-256 in /api/latest (#13) | [`dab8ecd`](https://github.com/ali-han-kaya/leibniz2/commit/dab8ecd) |
| 2026-08-22 | feat | (dashboard) overlay duration/budget trend from refs-trend.json (#14) | [`121a987`](https://github.com/ali-han-kaya/leibniz2/commit/121a987) |
| 2026-08-22 | feat | (refs-trend) add duration/budget threshold warning layer (#15) | [`86b4edc`](https://github.com/ali-han-kaya/leibniz2/commit/86b4edc) |
| 2026-08-22 | feat | (dashboard) add color legend to live run stream section (#16) | [`eaef526`](https://github.com/ali-han-kaya/leibniz2/commit/eaef526) |
| 2026-08-22 | feat | (dashboard) add findings panel showing P0/P1 detail rows (#17) | [`f413d97`](https://github.com/ali-han-kaya/leibniz2/commit/f413d97) |
| 2026-08-22 | ci | add colorizeLine rules regression test + pre-commit hook (#18) | [`f481ea5`](https://github.com/ali-han-kaya/leibniz2/commit/f481ea5) |
| 2026-08-22 | feat | (repro) add UNIT TESTS artifact section to manifest (#19) | [`cb7b06d`](https://github.com/ali-han-kaya/leibniz2/commit/cb7b06d) |
| 2026-08-22 | ci | parse unit test failures and post as PR comment | [`d3284b7`](https://github.com/ali-han-kaya/leibniz2/commit/d3284b7) |
| 2026-08-22 | fix | (ci) extract unit-test-failure comment to .js file | [`28e0789`](https://github.com/ali-han-kaya/leibniz2/commit/28e0789) |
| 2026-08-22 | fix | (ci) accept require+eval pattern in github-script test | [`d5a26cd`](https://github.com/ali-han-kaya/leibniz2/commit/d5a26cd) |
| 2026-08-22 | ci | unit test failure PR comment (#20) | [`167443a`](https://github.com/ali-han-kaya/leibniz2/commit/167443a) |
| 2026-08-22 | feat | (dashboard) live findings panel from stream P0/P1 lines (#21) | [`9f0a532`](https://github.com/ali-han-kaya/leibniz2/commit/9f0a532) |
| 2026-08-22 | fix | (dashboard) add startup resilience to preview tab (#22) | [`2bb8fb1`](https://github.com/ali-han-kaya/leibniz2/commit/2bb8fb1) |
| 2026-08-22 | other | revert(plist): remove legacy preview-server profile, keep single-profile (#23) | [`71106f8`](https://github.com/ali-han-kaya/leibniz2/commit/71106f8) |
| 2026-08-22 | fix | (verify) K14 _resolve_canon path under --dir repo root (#24) | [`fb69a40`](https://github.com/ali-han-kaya/leibniz2/commit/fb69a40) |
| 2026-08-22 | feat | (dashboard) add refs/PDF info to replay summary line (#25) | [`e19f7b7`](https://github.com/ali-han-kaya/leibniz2/commit/e19f7b7) |
| 2026-08-22 | test | (colorize) add replay summary coloring unit tests (#26) | [`093bd32`](https://github.com/ali-han-kaya/leibniz2/commit/093bd32) |
| 2026-08-22 | feat | (repro) add RUN LOGS section to reproducibility manifest (#27) | [`5a5d391`](https://github.com/ali-han-kaya/leibniz2/commit/5a5d391) |
| 2026-08-22 | feat | (dashboard) add compact run history list (#28) | [`a3111c4`](https://github.com/ali-han-kaya/leibniz2/commit/a3111c4) |
| 2026-08-22 | feat | (refs-trend) unverified series + stale artifact warning (#29) | [`f5d9c32`](https://github.com/ali-han-kaya/leibniz2/commit/f5d9c32) |
| 2026-08-22 | fix | (refs) correct Fine 2012 identifiers (wrong LCCN/ISBN) | [`398a148`](https://github.com/ali-han-kaya/leibniz2/commit/398a148) |
| 2026-08-22 | feat | (dashboard) add z3_passed/z3_total to run-history API | [`a05aad3`](https://github.com/ali-han-kaya/leibniz2/commit/a05aad3) |
| 2026-08-22 | feat | (dashboard) add K9 Lean to run-history API and trend graph | [`ce861e8`](https://github.com/ali-han-kaya/leibniz2/commit/ce861e8) |
| 2026-08-22 | feat | (verify) add lean_ok/lean_detail to history.jsonl record | [`e28c83f`](https://github.com/ali-han-kaya/leibniz2/commit/e28c83f) |
| 2026-08-22 | feat | (refs-trend) add z3_passed/z3_total to duration_budget section | [`8d669ea`](https://github.com/ali-han-kaya/leibniz2/commit/8d669ea) |
| 2026-08-22 | fix | (plist) KeepAlive SuccessfulExit=false to prevent restart race | [`aae9b0f`](https://github.com/ali-han-kaya/leibniz2/commit/aae9b0f) |
| 2026-08-22 | fix | (tests) green local suite — jsonschema skip, Fine 2012 OL source | [`54e7377`](https://github.com/ali-han-kaya/leibniz2/commit/54e7377) |
| 2026-08-22 | ci | (verify) K13 repro-manifest as separate advisory step + sidecar | [`f9dcb1c`](https://github.com/ali-han-kaya/leibniz2/commit/f9dcb1c) |
| 2026-08-22 | fix | (verify) harden K13 repro-manifest self-test with negative scenarios | [`ed0427d`](https://github.com/ali-han-kaya/leibniz2/commit/ed0427d) |
| 2026-08-22 | test | (refs-trend) section unit tests for parse/stats/duration-budget | [`d89964b`](https://github.com/ali-han-kaya/leibniz2/commit/d89964b) |
| 2026-08-22 | test | (repro) cross-validate config.combined_sha256 with K10 gate | [`ff029ae`](https://github.com/ali-han-kaya/leibniz2/commit/ff029ae) |
| 2026-08-22 | feat | (precommit) unstaged-deps pre-check for check-repro-manifest hook | [`3995fc9`](https://github.com/ali-han-kaya/leibniz2/commit/3995fc9) |
| 2026-08-22 | fix | (plist) restore two-profile management, sync tests to reality | [`0d29fd8`](https://github.com/ali-han-kaya/leibniz2/commit/0d29fd8) |
| 2026-08-22 | feat | (plist) K12 out-of-scope INFO line in audit trail | [`e78d906`](https://github.com/ali-han-kaya/leibniz2/commit/e78d906) |
| 2026-08-22 | test | (plist) real end-to-end extra-file scenario for check_plist_drift | [`bebc0cf`](https://github.com/ali-han-kaya/leibniz2/commit/bebc0cf) |
| 2026-08-22 | feat | (protection) K1-K14 job rename + 9 required check sync | [`d3de002`](https://github.com/ali-han-kaya/leibniz2/commit/d3de002) |
| 2026-08-22 | feat | (protection) advisory contract — all jobs vs required diff check | [`9195b63`](https://github.com/ali-han-kaya/leibniz2/commit/9195b63) |
| 2026-08-22 | test | (repro) doc artifact list vs ARTIFACT_JOBS sync | [`bccc815`](https://github.com/ali-han-kaya/leibniz2/commit/bccc815) |
| 2026-08-22 | feat | (dashboard) budget limit from effective config, not hardcoded 30 | [`4dc133d`](https://github.com/ali-han-kaya/leibniz2/commit/4dc133d) |
| 2026-08-22 | feat | (dashboard) red BÜTÇE AŞIMI banner above trend panel | [`0ab782c`](https://github.com/ali-han-kaya/leibniz2/commit/0ab782c) |
| 2026-08-22 | feat | (dashboard) tooltip budget line shows limit under/over status | [`8e455c2`](https://github.com/ali-han-kaya/leibniz2/commit/8e455c2) |
| 2026-08-22 | docs | (readme) add _calisma/lean_reduct boundary-proof section | [`5b1b90d`](https://github.com/ali-han-kaya/leibniz2/commit/5b1b90d) |
| 2026-08-22 | docs | (lean) add V5s note to K9 report for 8-theorem boundary core | [`9b81196`](https://github.com/ali-han-kaya/leibniz2/commit/9b81196) |
| 2026-08-22 | feat | (verify) K9 lake build --wfail gate for 8-theorem boundary core | [`d359b35`](https://github.com/ali-han-kaya/leibniz2/commit/d359b35) |
| 2026-08-22 | feat | (precommit) check-unit-tests hook for 5 new gate test files | [`d77aca7`](https://github.com/ali-han-kaya/leibniz2/commit/d77aca7) |
| 2026-08-22 | test | (summary) row-level content checks for lineage + K-layer sections | [`cafab86`](https://github.com/ali-han-kaya/leibniz2/commit/cafab86) |
| 2026-08-22 | docs | (M0) K16/K14 mirror-launchd PATH fixes katman raporu | [`4ac1787`](https://github.com/ali-han-kaya/leibniz2/commit/4ac1787) |
| 2026-08-22 | feat | (smoke) dashboard PASS'ini tek komutla yeniden üreten smoke testi | [`00ecfd3`](https://github.com/ali-han-kaya/leibniz2/commit/00ecfd3) |
| 2026-08-22 | docs | (scenario) launchd minimal PATH + mirror sync sınır notu | [`836c52b`](https://github.com/ali-han-kaya/leibniz2/commit/836c52b) |
| 2026-08-22 | feat | (skills) reproducible-pdf-build installable skill | [`5557a48`](https://github.com/ali-han-kaya/leibniz2/commit/5557a48) |
| 2026-08-22 | feat | (skills) verify-chain — K0-K17 fail-closed zincir skill'i | [`67226f3`](https://github.com/ali-han-kaya/leibniz2/commit/67226f3) |
| 2026-08-22 | feat | coq_reduct modülü + K19 coqtop fail-closed kapısı | [`86203ae`](https://github.com/ali-han-kaya/leibniz2/commit/86203ae) |
| 2026-08-22 | fix | (scripts) unify manifest + config-drift override display format | [`d29d766`](https://github.com/ali-han-kaya/leibniz2/commit/d29d766) |
| 2026-08-22 | feat | (cross-check) cross-validate index.json vs VERSION JSON override | [`66e573a`](https://github.com/ali-han-kaya/leibniz2/commit/66e573a) |
| 2026-08-22 | ci | manifest'te OVERRIDES bolumu — cli_overrides_version.json | [`93fce5b`](https://github.com/ali-han-kaya/leibniz2/commit/93fce5b) |
| 2026-08-22 | ci | K16 negatif kontrol — override'sizken yorumda uyari YOK | [`b0071f3`](https://github.com/ali-han-kaya/leibniz2/commit/b0071f3) |
| 2026-08-22 | ci | override-trend — CLI override zaman serisi (refs-trend deseni) | [`950cbbc`](https://github.com/ali-han-kaya/leibniz2/commit/950cbbc) |
| 2026-08-22 | other | dash: CLI override panel'i — son run'un override durumu | [`6f2797d`](https://github.com/ali-han-kaya/leibniz2/commit/6f2797d) |
| 2026-08-22 | other | dash: K-layer panel — tum rozetler d.layers tek kaynak | [`27542eb`](https://github.com/ali-han-kaya/leibniz2/commit/27542eb) |
| 2026-08-22 | ci | layers slot in LATEST + SSE snapshot plumbing tests | [`6a4d2af`](https://github.com/ali-han-kaya/leibniz2/commit/6a4d2af) |
| 2026-08-22 | docs | M0 raporuna V5t notu — K-layer panel (K0-K17 individual badges) | [`425bfff`](https://github.com/ali-han-kaya/leibniz2/commit/425bfff) |
| 2026-08-22 | docs | V5y — Fine 2012 OCLC + HT 0 kayit notu | [`b44a102`](https://github.com/ali-han-kaya/leibniz2/commit/b44a102) |
| 2026-08-22 | other | verify: HT API format unit tests — data[ident].records locked | [`3361b4c`](https://github.com/ali-han-kaya/leibniz2/commit/3361b4c) |
| 2026-08-22 | other | verify: refs-trend kapsam satiri — 61/61 + 54 gecersiz | [`8ef125a`](https://github.com/ali-han-kaya/leibniz2/commit/8ef125a) |
| 2026-08-22 | fix | config-drift override tek kaynak — summary.txt satiri | [`5e837f7`](https://github.com/ali-han-kaya/leibniz2/commit/5e837f7) |
| 2026-08-22 | other | verify: cli_overrides warning → fail-closed config-drift gate | [`e590e70`](https://github.com/ali-han-kaya/leibniz2/commit/e590e70) |
| 2026-08-22 | fix | config-drift override-only cift baslik engellendi | [`337a8d1`](https://github.com/ali-han-kaya/leibniz2/commit/337a8d1) |
| 2026-08-22 | other | verify: budget bar compute — budget_scan.js (pure) + 67 Node tests | [`049e9a0`](https://github.com/ali-han-kaya/leibniz2/commit/049e9a0) |
| 2026-08-22 | other | dash: budget sparkline — son N run'in butce mini grafigi | [`c003151`](https://github.com/ali-han-kaya/leibniz2/commit/c003151) |
| 2026-08-22 | other | dash: budget bar limit cizgisi + yuzde etiketi | [`d85213a`](https://github.com/ali-han-kaya/leibniz2/commit/d85213a) |
| 2026-08-22 | other | verify: config artefact merge pattern'e dahil — config/ oneki yok | [`e68a3c3`](https://github.com/ali-han-kaya/leibniz2/commit/e68a3c3) |
| 2026-08-22 | other | verify: config artefact merge pattern'e dahil — config/ oneki yok | [`a44b4f1`](https://github.com/ali-han-kaya/leibniz2/commit/a44b4f1) |
| 2026-08-22 | ci | config snapshot ↔ CONFIG_BASENAMES sync gate | [`9636a7c`](https://github.com/ali-han-kaya/leibniz2/commit/9636a7c) |
| 2026-08-22 | ci | add config_artifact_basenames to schema, K10 fail-closed drift check | [`d7ca27a`](https://github.com/ali-han-kaya/leibniz2/commit/d7ca27a) |
| 2026-08-23 | ci | override run [CLI override] satirlarini OVERRIDE_RAPORU.json'a tasi | [`fa9b7a4`](https://github.com/ali-han-kaya/leibniz2/commit/fa9b7a4) |
| 2026-08-23 | docs | PRE_PUSH_DENETIM_RAPORU e §9 CI run trend tablosu ekle | [`8e71025`](https://github.com/ali-han-kaya/leibniz2/commit/8e71025) |
| 2026-08-23 | ci | ci-simulate raporu .freebuff/sim'a; ci_stats.py scripti | [`4e44c26`](https://github.com/ali-han-kaya/leibniz2/commit/4e44c26) |
| 2026-08-23 | ci | CI-SIMULATE'i advisory job olarak her push'a ekle | [`f95df4a`](https://github.com/ali-han-kaya/leibniz2/commit/f95df4a) |
| 2026-08-23 | ci | ci-simulate job'unda elan PATH'ini inline export et | [`a80daa0`](https://github.com/ali-han-kaya/leibniz2/commit/a80daa0) |
| 2026-08-23 | ci | tum_sapmalar_comment.js'i repo'ya al (K16 battery CI'da ENOENT) | [`246b0e4`](https://github.com/ali-han-kaya/leibniz2/commit/246b0e4) |
| 2026-08-23 | ci | pre-existing test kirilmalarini kapat (mirror + battery desen) | [`4eeb0a5`](https://github.com/ali-han-kaya/leibniz2/commit/4eeb0a5) |
| 2026-08-23 | ci | verify job Install Lean adimina da inline PATH export ekle | [`8b0d6c1`](https://github.com/ali-han-kaya/leibniz2/commit/8b0d6c1) |
| 2026-08-23 | docs | PUBLISH_SCENARIO CI-SIMULATE bolumunu guncel yollarla senkronla | [`fb025a1`](https://github.com/ali-han-kaya/leibniz2/commit/fb025a1) |
| 2026-08-23 | ci | simulate_verify_job summary.md'ye readonly assertion ekle | [`5bf2037`](https://github.com/ali-han-kaya/leibniz2/commit/5bf2037) |
| 2026-08-23 | ci | summary Annotations format uyumluluk kontrolu | [`ea40214`](https://github.com/ali-han-kaya/leibniz2/commit/ea40214) |
| 2026-08-23 | feat | (protection) required check 9→12 (commit-msg, config-sync, ci-sim) | [`54e4d4c`](https://github.com/ali-han-kaya/leibniz2/commit/54e4d4c) |
| 2026-08-23 | fix | (verify) K10 overrides.combined_sha256 yeniden hesaplama + P1 | [`49b8114`](https://github.com/ali-han-kaya/leibniz2/commit/49b8114) |
| 2026-08-23 | fix | (scripts) config_diff yok-sa da bayat yorumu sil (state-sync) | [`914a221`](https://github.com/ali-han-kaya/leibniz2/commit/914a221) |
| 2026-08-23 | feat | (scripts) PR status'a repro-manifest PASS/FAIL bölümü ekle | [`dbb1bd2`](https://github.com/ali-han-kaya/leibniz2/commit/dbb1bd2) |
| 2026-08-23 | fix | (verify) K10 precheck_report.combined_sha256 yeniden hesapla | [`45c546b`](https://github.com/ali-han-kaya/leibniz2/commit/45c546b) |
| 2026-08-23 | docs | PRE_PUSH §8.5 — K10 precheck_report doğrulaması kaydı | [`5e85593`](https://github.com/ali-han-kaya/leibniz2/commit/5e85593) |
| 2026-08-23 | fix | (verify) K10 absent precheck — hayalet bölüme P1, yoksa PASS | [`469bd7d`](https://github.com/ali-han-kaya/leibniz2/commit/469bd7d) |
| 2026-08-23 | feat | (scripts) precheck --verify-checks + verify_checks birim testi | [`6cb70a1`](https://github.com/ali-han-kaya/leibniz2/commit/6cb70a1) |
| 2026-08-23 | feat | (scripts) verify-checks JSON sidecar + CI advisory adımı | [`71dbecc`](https://github.com/ali-han-kaya/leibniz2/commit/71dbecc) |
| 2026-08-23 | fix | (scripts) precheck smoke öncesi changelog senkronu (chicken-and-egg) | [`0bc915f`](https://github.com/ali-han-kaya/leibniz2/commit/0bc915f) |
| 2026-08-23 | docs | changelog — precheck smoke senkronu satırı (0bc915f) | [`76b0a55`](https://github.com/ali-han-kaya/leibniz2/commit/76b0a55) |
| 2026-08-23 | test | (scripts) update_changelog_hook birim kapısı (drift/stage/hata) | [`d210be3`](https://github.com/ali-han-kaya/leibniz2/commit/d210be3) |
| 2026-08-23 | feat | (scripts) branch protection tek-komut kurulum | [`7b78e0f`](https://github.com/ali-han-kaya/leibniz2/commit/7b78e0f) |
| 2026-08-23 | docs | V5z — bugünkü canlı 61/61 doğrulaması (2026-08-23) | [`35d9221`](https://github.com/ali-han-kaya/leibniz2/commit/35d9221) |
| 2026-08-23 | fix | (verify) refs HTTP retry 2→3 (IA SSL handshake flaky UNVERIFIED) | [`8a0220e`](https://github.com/ali-han-kaya/leibniz2/commit/8a0220e) |
| 2026-08-23 | feat | (dashboard) refs-trend tam kapsam rozeti (bugünkü 61/61) | [`b1353e6`](https://github.com/ali-han-kaya/leibniz2/commit/b1353e6) |
| 2026-08-23 | feat | (changelog) gen_changelog.py'ye --tag-regex kategori filtreleme | [`b86401f`](https://github.com/ali-han-kaya/leibniz2/commit/b86401f) |
| 2026-08-23 | feat | (ci) changelog drift advisory job | [`5aba283`](https://github.com/ali-han-kaya/leibniz2/commit/5aba283) |
| 2026-08-23 | feat | (changelog) --link modu ekle | [`f31049a`](https://github.com/ali-han-kaya/leibniz2/commit/f31049a) |
| 2026-08-23 | docs | (changelog) tabloları f31049a'ya senkronla | [`798052b`](https://github.com/ali-han-kaya/leibniz2/commit/798052b) |
| 2026-08-23 | refactor | (changelog) tek kaynak — README changelog, PUBLISH işaretçi | [`cad671b`](https://github.com/ali-han-kaya/leibniz2/commit/cad671b) |
| 2026-08-23 | docs | README'ye CI/pre-commit/license rozetleri + LICENSE | [`0879c1c`](https://github.com/ali-han-kaya/leibniz2/commit/0879c1c) |
| 2026-08-23 | feat | (scripts) --bootstrap'a opsiyonel --start (launchctl aynı komutta) | [`e594ff0`](https://github.com/ali-han-kaya/leibniz2/commit/e594ff0) |
| 2026-08-23 | feat | (ci) mirror-check job'una bootstrap smoke adımı | [`20b93b6`](https://github.com/ali-han-kaya/leibniz2/commit/20b93b6) |
| 2026-08-23 | feat | (verify) K17 --mirror-auto-sync — bayat mirror'ı otomatik senkronla | [`c307b47`](https://github.com/ali-han-kaya/leibniz2/commit/c307b47) |
| 2026-08-23 | feat | (verify) K17 --full zincirine dahil — mirror boşsa otomatik kur | [`6a74938`](https://github.com/ali-han-kaya/leibniz2/commit/6a74938) |
| 2026-08-23 | other | manifest: mirror-check'i download pattern'e ekle, K17 SHA-256 sabitle | [`165f28d`](https://github.com/ali-han-kaya/leibniz2/commit/165f28d) |
| 2026-08-23 | other | pattern-drift: mirror-check'i EXCLUDED'a ekle (prefixed indirme) | [`41776fa`](https://github.com/ali-han-kaya/leibniz2/commit/41776fa) |
| 2026-08-23 | other | dashboard: mirror sync paneli (K17 + BAYAT listesi), TCC SKIP | [`e6a570e`](https://github.com/ali-han-kaya/leibniz2/commit/e6a570e) |
| 2026-08-23 | other | manifest: daemon-http artifact'ını pattern'e ekle, SHA-256 sabitle | [`d8451a4`](https://github.com/ali-han-kaya/leibniz2/commit/d8451a4) |
| 2026-08-23 | other | K18: daemon smoke --full'a fail-closed bağla, K20 renumber | [`d58d5e3`](https://github.com/ali-han-kaya/leibniz2/commit/d58d5e3) |
| 2026-08-23 | other | K18 daemon smoke: SSE + run-now endpoint'leri de 200 ile doğrula | [`8430f99`](https://github.com/ali-han-kaya/leibniz2/commit/8430f99) |
| 2026-08-23 | other | fresh_clone_setup: --check'e daemon rotası denetimi ekle (K18 smoke) | [`a8cdf74`](https://github.com/ali-han-kaya/leibniz2/commit/a8cdf74) |
| 2026-08-23 | other | update_preview: plist'e PreStart kontrolü ekle (preview_prestart.py) | [`5c71a39`](https://github.com/ali-han-kaya/leibniz2/commit/5c71a39) |
| 2026-08-23 | other | fresh_clone_setup: agent mirror'ıyla karşılaştır, bayatlığı raporla | [`8c1a68a`](https://github.com/ali-han-kaya/leibniz2/commit/8c1a68a) |
| 2026-08-23 | other | test_mirror: K17 kapsamına preview runtime dosyalarını kat (uçtan uca) | [`a0110c2`](https://github.com/ali-han-kaya/leibniz2/commit/a0110c2) |
| 2026-08-23 | other | preview_server: restart'ta önbelleklenmiş son run'ı yükle (UNKNOWN yok) | [`306c203`](https://github.com/ali-han-kaya/leibniz2/commit/306c203) |
| 2026-08-23 | other | test_mirror: kapsamı runtime dosyalarına genişlet (zip/config/lean) | [`b2e86b5`](https://github.com/ali-han-kaya/leibniz2/commit/b2e86b5) |
| 2026-08-23 | ci | mirror kapsam denetimi (--list ↔ repo dosya kümesi) ekle | [`7e15d44`](https://github.com/ali-han-kaya/leibniz2/commit/7e15d44) |
| 2026-08-24 | ci | fresh_clone_setup --check-ci advisory job ekle | [`3590d09`](https://github.com/ali-han-kaya/leibniz2/commit/3590d09) |
| 2026-08-24 | docs | run.md 'How to reproduce' bölümünü fresh_clone_setup.sh'e taşı | [`10d9ad7`](https://github.com/ali-han-kaya/leibniz2/commit/10d9ad7) |
| 2026-08-24 | other | mirror: fresh_clone/update_preview/test'i FILES'e ekle (43 dosya) | [`d09efc7`](https://github.com/ali-han-kaya/leibniz2/commit/d09efc7) |
| 2026-08-24 | ci | ci_fresh_clone_test.sh fresh clone simülasyonu ekle | [`ac8555c`](https://github.com/ali-han-kaya/leibniz2/commit/ac8555c) |
| 2026-08-24 | other | refs-online: archive_group özeti ekle (archive+loc+hathitrust=25) | [`564d6ac`](https://github.com/ali-han-kaya/leibniz2/commit/564d6ac) |
| 2026-08-24 | other | verify: OL timeout UNVERIFIED için outer retry ekle | [`958d5ba`](https://github.com/ali-han-kaya/leibniz2/commit/958d5ba) |
| 2026-08-24 | docs | REFERANS_KANIT'e V5aa notu — CI OL timeout + retry belgelendi | [`da94017`](https://github.com/ali-han-kaya/leibniz2/commit/da94017) |
| 2026-08-24 | other | refs-trend: V5r + V5aa changelog satırları ve sıralama testi ekle | [`3c83bb2`](https://github.com/ali-han-kaya/leibniz2/commit/3c83bb2) |
| 2026-08-24 | other | refs-trend: V5p-V5w kapsam & by_source özet tablosu ekle | [`bc55056`](https://github.com/ali-han-kaya/leibniz2/commit/bc55056) |
| 2026-08-24 | other | audit: changelog siralama denetimi ekle (exit 1 on drift) | [`5cd79e1`](https://github.com/ali-han-kaya/leibniz2/commit/5cd79e1) |
| 2026-08-24 | other | verify: worldcat_check ekle — OCLC'yi WorldCat kataloguna cozer | [`97f7a25`](https://github.com/ali-han-kaya/leibniz2/commit/97f7a25) |
| 2026-08-24 | other | ia_ol_fallback: kanit tablosuna tiklanabilir LoC URL'leri ekle | [`0259025`](https://github.com/ali-han-kaya/leibniz2/commit/0259025) |
| 2026-08-24 | docs | V5s/V5r OL fallback notlarini V5w isaretiyle guncelle | [`e5fcf40`](https://github.com/ali-han-kaya/leibniz2/commit/e5fcf40) |
| 2026-08-24 | other | refs-trend: kapsam gecis dipnotu ekle (54/49 56/26 61/61) | [`26bb80c`](https://github.com/ali-han-kaya/leibniz2/commit/26bb80c) |
| 2026-08-24 | docs | V5w canli run dogrulamasi ekle (hathitrust=1, 61/61 PASS) | [`bdf0699`](https://github.com/ali-han-kaya/leibniz2/commit/bdf0699) |
| 2026-08-24 | other | audit: by_source dagilim denetimi ekle (hathitrust/archive/perseus) | [`6310c0a`](https://github.com/ali-han-kaya/leibniz2/commit/6310c0a) |
| 2026-08-24 | other | audit: changelog rendered denetimi ekle (CHANGELOG keyword eslesme) | [`a4220df`](https://github.com/ali-han-kaya/leibniz2/commit/a4220df) |
| 2026-08-24 | other | refs-trend: kapsam degisim isaretcisi ekle (V5 notu satir bazli) | [`8ef2c8d`](https://github.com/ali-han-kaya/leibniz2/commit/8ef2c8d) |
| 2026-08-24 | other | audit: refs-trend.md ozet dipnot denetimi ekle (56/56 yerel dogrulama) | [`5561365`](https://github.com/ali-han-kaya/leibniz2/commit/5561365) |
| 2026-08-24 | other | manifest: audit-refs-trend'i reproducibility'ye dahil et (SHA-256) | [`5fe39c0`](https://github.com/ali-han-kaya/leibniz2/commit/5fe39c0) |
| 2026-08-24 | fix | summary_pattern_drift EXCLUDED'a audit-refs-trend ekle | [`2878923`](https://github.com/ali-han-kaya/leibniz2/commit/2878923) |
| 2026-08-24 | history | audit_refs_trend alanini history.jsonl'e ekle | [`fa2e6de`](https://github.com/ali-han-kaya/leibniz2/commit/fa2e6de) |
| 2026-08-24 | other | audit: --offline mod ekle (yerel dizinden tekrarlanabilir kosu) | [`d714000`](https://github.com/ali-han-kaya/leibniz2/commit/d714000) |
| 2026-08-24 | ci | test-smoke.yml ile glob modu smoke test'i ekle | [`c95f762`](https://github.com/ali-han-kaya/leibniz2/commit/c95f762) |
| 2026-08-24 | ci | actionlint'i tum .github/workflows/*.yml dosyalarina genelle | [`a1119d5`](https://github.com/ali-han-kaya/leibniz2/commit/a1119d5) |
| 2026-08-24 | docs | PRE_PUSH_DENETIM_RAPORU'na python3-shell artifact drift'ini isle | [`e0aaeb4`](https://github.com/ali-han-kaya/leibniz2/commit/e0aaeb4) |
| 2026-08-24 | other | audit: artifact-doc drift e2e kapisi + self-exclusion fix | [`0c43da7`](https://github.com/ali-han-kaya/leibniz2/commit/0c43da7) |
| 2026-08-24 | other | precommit: hook kimliklerini (hook id) PRECOMMIT_RAPORU'na isle | [`71bb362`](https://github.com/ali-han-kaya/leibniz2/commit/71bb362) |
| 2026-08-24 | other | audit: python3-shell artifact varligini sabit kap yaptim | [`5388d77`](https://github.com/ali-han-kaya/leibniz2/commit/5388d77) |
| 2026-08-24 | other | verify: K13'e python3-shell mock + üretici-hatasi senaryosu ekle | [`a42512f`](https://github.com/ali-han-kaya/leibniz2/commit/a42512f) |
| 2026-08-24 | other | verify: REPRO_ARTIFACT_JOBS override python3-shell kapsamini dogrula | [`beebcdf`](https://github.com/ali-han-kaya/leibniz2/commit/beebcdf) |
| 2026-08-24 | other | verify: ia_ol_fallback_evidence'i K6'ya bagla, ayri bolum goster | [`1ef0e2d`](https://github.com/ali-han-kaya/leibniz2/commit/1ef0e2d) |
| 2026-08-24 | docs | refs-trend'de 56/56 milestone + REFERANS §5.3 referansi | [`f2ed319`](https://github.com/ali-han-kaya/leibniz2/commit/f2ed319) |
| 2026-08-24 | other | verify: refs-online UNVERIFIED gecis ozet tablosu (54/49→56/26→61/61) | [`683d071`](https://github.com/ali-han-kaya/leibniz2/commit/683d071) |
| 2026-08-24 | other | verify: CHANGELOG siralama determinizm testi ekle | [`c53fcda`](https://github.com/ali-han-kaya/leibniz2/commit/c53fcda) |
| 2026-08-24 | other | verify: K6 61/61 sonucunu ozet ciktiya tek bakista ekle | [`418714b`](https://github.com/ali-han-kaya/leibniz2/commit/418714b) |
| 2026-08-24 | other | verify: fallback bolumu total_online'i 66'ya sismesin (61 kal) | [`cee1c4a`](https://github.com/ali-han-kaya/leibniz2/commit/cee1c4a) |
| 2026-08-24 | docs | bayat 56/56 referanslarini guncel 61 ile senkronla | [`3d53d03`](https://github.com/ali-han-kaya/leibniz2/commit/3d53d03) |
| 2026-08-24 | other | verify: publish_wrapper --incremental'i 4 adimli doc dongusuyle kapila | [`bf6a1d2`](https://github.com/ali-han-kaya/leibniz2/commit/bf6a1d2) |
| 2026-08-24 | other | verify: enforce_is_on 404 ilk publish guvenli atlama smoke kapisi | [`c10f478`](https://github.com/ali-han-kaya/leibniz2/commit/c10f478) |
| 2026-08-24 | docs | §12 --incremental doc-sync + enforce_is_on 404 dansi | [`7696024`](https://github.com/ali-han-kaya/leibniz2/commit/7696024) |
| 2026-08-24 | docs | HISTORY_CLEANUP'a preview-server legacy.label temizligini isle | [`fc7e7da`](https://github.com/ali-han-kaya/leibniz2/commit/fc7e7da) |
| 2026-08-24 | other | .freebuff/run.md: redirect stale inline startup to --start command | [`b1c2b63`](https://github.com/ali-han-kaya/leibniz2/commit/b1c2b63) |
| 2026-08-24 | other | plist: rename multi-profile tests to legacy compat class | [`80e1311`](https://github.com/ali-han-kaya/leibniz2/commit/80e1311) |
| 2026-08-24 | other | dashboard: add refs_by_source summary cards with colored left borders | [`6a0e67b`](https://github.com/ali-han-kaya/leibniz2/commit/6a0e67b) |
| 2026-08-24 | other | dashboard: unify by_source colors + tooltip breakdown + legend counts | [`379c31d`](https://github.com/ali-han-kaya/leibniz2/commit/379c31d) |
| 2026-08-24 | other | dashboard: enhance ro-sources table with colored rows and bar charts | [`cb86c5f`](https://github.com/ali-han-kaya/leibniz2/commit/cb86c5f) |
| 2026-08-24 | other | dashboard: show Lean PASS/FAIL colored dot in run history list | [`1c215a2`](https://github.com/ali-han-kaya/leibniz2/commit/1c215a2) |
| 2026-08-24 | other | dashboard: add Lean PASS rate % axis to trend graph (5th axis) | [`8bdfa74`](https://github.com/ali-han-kaya/leibniz2/commit/8bdfa74) |
| 2026-08-24 | test | build_replay_events refs_verified/refs_total/pdf_pages coverage | [`d5c7cba`](https://github.com/ali-han-kaya/leibniz2/commit/d5c7cba) |
| 2026-08-24 | test | fix colorize_rules count=4 (setRhFilter + initLoad + SSE) | [`b6fa617`](https://github.com/ali-han-kaya/leibniz2/commit/b6fa617) |
| 2026-08-24 | other | dashboard: split PDF pages and refs into separate metrics cards | [`c69351c`](https://github.com/ali-han-kaya/leibniz2/commit/c69351c) |
| 2026-08-24 | other | dashboard: fmtDuration for replay summary line (1m30s format) | [`b3b5da8`](https://github.com/ali-han-kaya/leibniz2/commit/b3b5da8) |
| 2026-08-24 | other | dashboard: run history PASS/FAIL/P0 filter buttons | [`04cfd19`](https://github.com/ali-han-kaya/leibniz2/commit/04cfd19) |
| 2026-08-24 | other | dashboard: click run-history row to load stdout | [`24b9905`](https://github.com/ali-han-kaya/leibniz2/commit/24b9905) |
| 2026-08-24 | other | dashboard: auto-refresh run history on SSE snapshot/update | [`376fade`](https://github.com/ali-han-kaya/leibniz2/commit/376fade) |
| 2026-08-24 | docs | HISTORY_CLEANUP §7.5'i 9→6 required check olarak guncelle | [`5c42d4e`](https://github.com/ali-han-kaya/leibniz2/commit/5c42d4e) |
| 2026-08-24 | docs | HISTORY_CLEANUP'a pre-existing CI hatalarini §7 olarak ekle | [`7a354dc`](https://github.com/ali-han-kaya/leibniz2/commit/7a354dc) |
| 2026-08-24 | ci | add if:always() to full-verification step, lineage warn | [`0524f6a`](https://github.com/ali-han-kaya/leibniz2/commit/0524f6a) |
| 2026-08-24 | other | dashboard: animated Lean FAIL warning (fail-pulse + alert bubble) | [`240e5ad`](https://github.com/ali-han-kaya/leibniz2/commit/240e5ad) |
| 2026-08-24 | other | K14: _resolve_canon path birim testleri (mirror, subdir, repo-root) | [`a51ce2a`](https://github.com/ali-han-kaya/leibniz2/commit/a51ce2a) |
| 2026-08-24 | other | PRE_PUSH_DENETIM_RAPORU.md: §13 PR #22/#23/#24 ekle | [`29222db`](https://github.com/ali-han-kaya/leibniz2/commit/29222db) |
| 2026-08-24 | other | plist: gen_plist_golden.py + birim testleri (golden drift kapisi) | [`2723569`](https://github.com/ali-han-kaya/leibniz2/commit/2723569) |
| 2026-08-24 | other | dashboard: service worker ile Freebuff webview cache bypass | [`4392e3e`](https://github.com/ali-han-kaya/leibniz2/commit/4392e3e) |
| 2026-08-24 | other | dashboard: BUILD_TS dinamik timestamp ile Electron cache bypass | [`82f27b6`](https://github.com/ali-han-kaya/leibniz2/commit/82f27b6) |
| 2026-08-24 | other | dashboard: BUILD_TS dinamik timestamp ile Electron cache bypass | [`412ed49`](https://github.com/ali-han-kaya/leibniz2/commit/412ed49) |
| 2026-08-24 | ci | pip + pre-commit cache to verify and ci-simulate jobs | [`7192014`](https://github.com/ali-han-kaya/leibniz2/commit/7192014) |
| 2026-08-24 | ci | pip + pre-commit cache to verify and ci-simulate jobs | [`aac0aa8`](https://github.com/ali-han-kaya/leibniz2/commit/aac0aa8) |
| 2026-08-24 | feat | K15 history check --full zincirinde (auto-discover history.jsonl) | [`ba2ae59`](https://github.com/ali-han-kaya/leibniz2/commit/ba2ae59) |
| 2026-08-24 | test | (manifest) daemon-http section tests cover history.jsonl + .sha256 | [`ef70504`](https://github.com/ali-han-kaya/leibniz2/commit/ef70504) |
| 2026-08-24 | test | (coverage) unified aggregator (71 files, 1463 tests, 11 hooks) | [`d007548`](https://github.com/ali-han-kaya/leibniz2/commit/d007548) |
| 2026-08-24 | ci | (K15) history sidecar fail-closed P1 (continue-on-error kaldirildi) | [`c377973`](https://github.com/ali-han-kaya/leibniz2/commit/c377973) |
| 2026-08-24 | feat | (pattern) --fix flag for auto-adding missing artifacts to pattern | [`b4fd760`](https://github.com/ali-han-kaya/leibniz2/commit/b4fd760) |
| 2026-08-24 | test | (smoke) 22-hook unified smoke test (all hooks, 40s, fail-closed) | [`19efc37`](https://github.com/ali-han-kaya/leibniz2/commit/19efc37) |
| 2026-08-24 | ci | (pattern-drift) advisory job for merge pattern vs ARTIFACT_JOBS drift | [`80a6ebe`](https://github.com/ali-han-kaya/leibniz2/commit/80a6ebe) |
| 2026-08-24 | feat | (dashboard) pattern drift paneli — /api/latest + live preview | [`65fd87b`](https://github.com/ali-han-kaya/leibniz2/commit/65fd87b) |
| 2026-08-24 | docs | stash-aware hook behavior for check-repro-manifest | [`3566f57`](https://github.com/ali-han-kaya/leibniz2/commit/3566f57) |
| 2026-08-24 | docs | block evidence for action-pins, plist-drift, verify-delivery | [`e8d93d2`](https://github.com/ali-han-kaya/leibniz2/commit/e8d93d2) |
| 2026-08-24 | fix | (hooks) pattern drift error shows line number + artifact name | [`62f1a72`](https://github.com/ali-han-kaya/leibniz2/commit/62f1a72) |
| 2026-08-25 | fix | (mirror) sw.js in PREVIEW_RUNTIME + lazy yaml import for CI | [`43e80a9`](https://github.com/ali-han-kaya/leibniz2/commit/43e80a9) |
| 2026-08-25 | fix | (tests) skip daemon HTTP E2E tests in CI (port unavailable) | [`d6e83ff`](https://github.com/ali-han-kaya/leibniz2/commit/d6e83ff) |
| 2026-08-25 | fix | (refs) exponential backoff for OL retries + CI daemon smoke guard | [`6aebe4d`](https://github.com/ali-han-kaya/leibniz2/commit/6aebe4d) |
| 2026-08-25 | feat | (hooks) check-refs-table-sync — §2 table ↔ code lists fail-closed | [`59fbb6e`](https://github.com/ali-han-kaya/leibniz2/commit/59fbb6e) |
| 2026-08-25 | docs | (refs) V5q evidence table for Sextus ia_ids + Della Rocca | [`b1e47dc`](https://github.com/ali-han-kaya/leibniz2/commit/b1e47dc) |
| 2026-08-25 | test | (consolidate) line-based content checks for pre-commit + K0 | [`a67aacc`](https://github.com/ali-han-kaya/leibniz2/commit/a67aacc) |
| 2026-08-25 | test | (consolidate) file-sink (GITHUB_STEP_SUMMARY) line-based checks | [`ad370d6`](https://github.com/ali-han-kaya/leibniz2/commit/ad370d6) |
| 2026-08-25 | fix | (k18) guard uses VD_SKIP_K18 env, not generic CI | [`ad30a4b`](https://github.com/ali-han-kaya/leibniz2/commit/ad30a4b) |
| 2026-08-25 | fix | (ci) set VD_SKIP_K18 in CI-SIMULATE job too | [`ca22460`](https://github.com/ali-han-kaya/leibniz2/commit/ca22460) |
| 2026-08-25 | ci | run check-unit-tests hook separately, log to precommit-logs | [`e9772cc`](https://github.com/ali-han-kaya/leibniz2/commit/e9772cc) |
| 2026-08-25 | feat | (gates) check-unit-tests listesini manifest ile otomatik senkronla | [`d1ed10c`](https://github.com/ali-han-kaya/leibniz2/commit/d1ed10c) |
| 2026-08-25 | docs | (lean) K9 CI elan kurulumunu §6.3'e not et | [`b5f5d16`](https://github.com/ali-han-kaya/leibniz2/commit/b5f5d16) |
| 2026-08-25 | feat | (k9) lean yokken lake alt-kapisini atlayan --lean-only | [`830da22`](https://github.com/ali-han-kaya/leibniz2/commit/830da22) |
| 2026-08-25 | feat | (k9) §6.3 lake kanıtını canlı üreten check-lake-evidence hook'u | [`5dc1767`](https://github.com/ali-han-kaya/leibniz2/commit/5dc1767) |
| 2026-08-25 | feat | (dashboard) trend tooltip'lerini birleştir, budget rengi | [`4dce134`](https://github.com/ali-han-kaya/leibniz2/commit/4dce134) |
| 2026-08-25 | fix | (ci) mirror kapsamına auto-sync + lake-evidence dosyaları | [`31dea00`](https://github.com/ali-han-kaya/leibniz2/commit/31dea00) |
| 2026-08-25 | feat | (dashboard) BÜTÇE AŞIMI şeridine genişletilebilir run listesi | [`c5d2958`](https://github.com/ali-han-kaya/leibniz2/commit/c5d2958) |

### Regresyon notları

| ID | Tarih | Kırılma | Kök neden | Düzeltme | Commit |
|---|---|---|---|---|---|
| R1 | 2026-08-19 | CI 0s/0 job boş run | YAML adım `}` + `uses:` aynı satıra yapıştı | satır ayrımı + actionlint | `d57a60c` |
| R2 | 2026-08-21 | summary yerelde yazılmıyor | `GITHUB_STEP_SUMMARY` env boştu | iki aşamalı write + validate | `2282925` |
| R3 | 2026-08-21 | pre-commit block (actionlint RC=1) | shellcheck info hints advisory iken fail | `lint_actionlint.sh` RC≤2 PASS | `ae55009` |
| R4 | 2026-08-21 | `listLabels is not a function` | Octokit `listLabels` → `listLabelsForRepo` | 4 dosya güncellendi | `309a14f` |
