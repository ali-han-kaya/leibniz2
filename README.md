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

## Skills

Kurulabilir Agent Skill'leri `skills/` altında tutulur. Bu tablo, her skill'in
kanonik yönergesini gösterir; `check-skills-index` kapısı dizin ile tabloyu
çift yönlü senkron tutar.

| Skill | Açıklama |
|---|---|
| `skills/verify-chain/SKILL.md` | K0–K17 fail-closed teslim doğrulama zinciri |
| `skills/reproducible-pdf-build/SKILL.md` | PDF determinism, SHA-256 sidecar ve SDE akışı |
| `skills/release-candidate-check/SKILL.md` | verify_mcp MCP sunucusu için release-candidate doğrulaması |


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
| 2026-08-26 | fix | (ci) lineage sidecar anti-cascade + plist --remove-extra (#39) | [`75bc326`](https://github.com/ali-han-kaya/leibniz2/commit/75bc326) |
| 2026-08-26 | chore | gate_jobs tam küme testi + status checks run summary tablosu | [`ebfeebd`](https://github.com/ali-han-kaya/leibniz2/commit/ebfeebd) |
| 2026-08-26 | test | config merge-pattern (prefixsiz) — K10 PASS kanıtı + advisory kontrat kapıları | [`da87429`](https://github.com/ali-han-kaya/leibniz2/commit/da87429) |
| 2026-08-26 | feat | (verify) K10 çift tespit + K12/K13 negatif senaryo kapıları | [`7fa4997`](https://github.com/ali-han-kaya/leibniz2/commit/7fa4997) |
| 2026-08-26 | refactor | (refs-trend) UNVERIFIED/bayat-artifact saf fonksiyonlar | [`35897ac`](https://github.com/ali-han-kaya/leibniz2/commit/35897ac) |
| 2026-08-26 | feat | (summary) durum panosuna K13 ayrı-step satırı + plist docs tazeleme | [`2f927fc`](https://github.com/ali-han-kaya/leibniz2/commit/2f927fc) |
| 2026-08-26 | feat | (render) Z3 teorem slayt üretici + sync testi (12/12 OK) | [`7333a55`](https://github.com/ali-han-kaya/leibniz2/commit/7333a55) |
| 2026-08-31 | fix | (verify) wire CI gates to required sidecars | [`3f27b90`](https://github.com/ali-han-kaya/leibniz2/commit/3f27b90) |
| 2026-08-31 | docs | (verify) inline code review findings and verdict | [`1c723be`](https://github.com/ali-han-kaya/leibniz2/commit/1c723be) |
| 2026-08-31 | docs | (verify) progress log for review-reception turn | [`5e3211d`](https://github.com/ali-han-kaya/leibniz2/commit/5e3211d) |
| 2026-08-31 | test | (verify) status_checks yaml-guard + abs WORKFLOW path | [`03bf219`](https://github.com/ali-han-kaya/leibniz2/commit/03bf219) |
| 2026-08-30 | chore | (verify) thread artifact publish (hooks+tests+docs) | [`5d9a6d2`](https://github.com/ali-han-kaya/leibniz2/commit/5d9a6d2) |
| 2026-08-30 | refactor | (verify) _locate_opencode dead fallback removal | [`ae515a0`](https://github.com/ali-han-kaya/leibniz2/commit/ae515a0) |
| 2026-08-30 | fix | (verify) untracked kaynak + mutlak yol duzeltmeleri | [`62ae4a8`](https://github.com/ali-han-kaya/leibniz2/commit/62ae4a8) |
| 2026-08-30 | perf | (preview) kompakt JSON serileştirme (api endpoints) | [`cf12a59`](https://github.com/ali-han-kaya/leibniz2/commit/cf12a59) |
| 2026-08-30 | feat | (verify) verify_mcp sunucu + Dockerfile + mirror temizliği | [`df8c5b7`](https://github.com/ali-han-kaya/leibniz2/commit/df8c5b7) |
| 2026-08-29 | chore | (verify) teslim zip'lerini güncel kaynaktan repack et | [`b69de33`](https://github.com/ali-han-kaya/leibniz2/commit/b69de33) |
| 2026-08-29 | fix | (verify) K21 SDE + skill gate parçaları + CI kapı düzeltmeleri | [`099ba80`](https://github.com/ali-han-kaya/leibniz2/commit/099ba80) |
| 2026-08-29 | fix | (verify) mirror kapsam + artifact sözleşmesi + coverage raporu | [`3918eab`](https://github.com/ali-han-kaya/leibniz2/commit/3918eab) |
| 2026-08-28 | feat | (verify) PDF skill reuse to K6 determinism gate | [`baf652a`](https://github.com/ali-han-kaya/leibniz2/commit/baf652a) |
| 2026-08-28 | feat | (verify) add reproducible PDF + skills index gates | [`1866ad8`](https://github.com/ali-han-kaya/leibniz2/commit/1866ad8) |
| 2026-09-08 | test | (verify) pin bibliography and review-compilation verification gates | [`4867776`](https://github.com/ali-han-kaya/leibniz2/commit/4867776) |
| 2026-09-08 | docs | (review) add reproducible review-compilation artifact (53pp) | [`bf78eee`](https://github.com/ali-han-kaya/leibniz2/commit/bf78eee) |
| 2026-09-08 | refactor | (dashboard) serve slides_z3 natively from PREVIEW_DIR | [`dcb5625`](https://github.com/ali-han-kaya/leibniz2/commit/dcb5625) |
| 2026-09-09 | test | (verify) harden tooling and gate tests for split verify hardenings | [`e24c87f`](https://github.com/ali-han-kaya/leibniz2/commit/e24c87f) |
| 2026-09-09 | ci | (verify) add fresh-clone HTTP smoke advisory job | [`2344a28`](https://github.com/ali-han-kaya/leibniz2/commit/2344a28) |
| 2026-09-09 | ci | (verify) harden ci-simulate tool installs with if: always() | [`2a31aad`](https://github.com/ali-han-kaya/leibniz2/commit/2a31aad) |
| 2026-09-09 | ci | (verify) make plist extra-profile drift self-healing (fail-closed) | [`c1975d5`](https://github.com/ali-han-kaya/leibniz2/commit/c1975d5) |
| 2026-09-09 | ci | (verify) gate Lean sorry/axiom check before lake build (K9) | [`10c0dd5`](https://github.com/ali-han-kaya/leibniz2/commit/10c0dd5) |
| 2026-09-09 | ci | (verify) add K12 plist scenario advisory step (K13 pattern) | [`aecb3b1`](https://github.com/ali-han-kaya/leibniz2/commit/aecb3b1) |
| 2026-09-09 | ci | (verify) harden install steps with if: always() | [`6862250`](https://github.com/ali-han-kaya/leibniz2/commit/6862250) |
| 2026-09-08 | fix | (verify) harden K9 lean pipeline and K15-K21 layer docs | [`6b13a14`](https://github.com/ali-han-kaya/leibniz2/commit/6b13a14) |
| 2026-09-08 | refactor | (dashboard) split preview.html JS into preview.js | [`a719f9e`](https://github.com/ali-han-kaya/leibniz2/commit/a719f9e) |
| 2026-09-08 | fix | (mcp) expose response_format enum via Literal | [`b62436c`](https://github.com/ali-han-kaya/leibniz2/commit/b62436c) |
| 2026-09-08 | fix | (mirror) make coverage clone-safe via git ls-files | [`c5066a2`](https://github.com/ali-han-kaya/leibniz2/commit/c5066a2) |
| 2026-09-08 | fix | (mirror) sync preview.js + run_summary modules via --list | [`42c3286`](https://github.com/ali-han-kaya/leibniz2/commit/42c3286) |
| 2026-09-06 | fix | (dashboard) add Vite type declarations and dependencies | [`9b9b9a8`](https://github.com/ali-han-kaya/leibniz2/commit/9b9b9a8) |
| 2026-09-05 | chore | (repo) ignore worktrees and document dashboard runs | [`3519e90`](https://github.com/ali-han-kaya/leibniz2/commit/3519e90) |
| 2026-09-05 | fix | (verify) write sidecars atomically | [`a7c4318`](https://github.com/ali-han-kaya/leibniz2/commit/a7c4318) |
| 2026-09-05 | fix | (mirror) restore sync_one copy path lost in 146943b partial staging | [`90b1742`](https://github.com/ali-han-kaya/leibniz2/commit/90b1742) |
| 2026-09-04 | fix | (mirror) make sync_one atomic with same-dir tmp + mv | [`90df9e6`](https://github.com/ali-han-kaya/leibniz2/commit/90df9e6) |
| 2026-09-04 | test | (verify) pin manifest-comment in the sidecar wiring contract | [`8ee1e06`](https://github.com/ali-han-kaya/leibniz2/commit/8ee1e06) |
| 2026-09-04 | fix | (verify) deliver all 7 pr_status_comment.js inputs to budget-comment | [`63908f3`](https://github.com/ali-han-kaya/leibniz2/commit/63908f3) |
| 2026-09-04 | fix | (verify) bind verdicts of sidecar-consuming required gates | [`87728f1`](https://github.com/ali-han-kaya/leibniz2/commit/87728f1) |
| 2026-09-04 | fix | (status-checks) mark lake-proof advisory to match required set | [`1fdb631`](https://github.com/ali-han-kaya/leibniz2/commit/1fdb631) |
| 2026-09-01 | perf | (preview) add View Transitions + Playwright smoke test | [`8514df2`](https://github.com/ali-han-kaya/leibniz2/commit/8514df2) |
| 2026-08-31 | fix | (refs-trend) write refs-trend.json atomically (tmp + os.replace) | [`bbe7837`](https://github.com/ali-han-kaya/leibniz2/commit/bbe7837) |
| 2026-08-31 | perf | (preview) cache loadTrend 30s + fix refs-trend path | [`4686936`](https://github.com/ali-han-kaya/leibniz2/commit/4686936) |
| 2026-09-08 | fix | (preview) compact JSON, auth, Host/Origin, shutdown, klayers | [`35ccc98`](https://github.com/ali-han-kaya/leibniz2/commit/35ccc98) |
| 2026-09-08 | docs | (changelog) sync changelog for split verify hardenings | [`076c576`](https://github.com/ali-han-kaya/leibniz2/commit/076c576) |
| 2026-09-09 | ci | (verify) deduplicate K10 bundle verdict into composite action | [`9c2f049`](https://github.com/ali-han-kaya/leibniz2/commit/9c2f049) |
| 2026-09-09 | docs | (changelog) resync after K10 dedup | [`6211d42`](https://github.com/ali-han-kaya/leibniz2/commit/6211d42) |
| 2026-09-09 | docs | (changelog) update changelog after history rewrite | [`3373956`](https://github.com/ali-han-kaya/leibniz2/commit/3373956) |
| 2026-09-10 | fix | (verify) flip K14 live contract to PASS after resync | [`c2adbf4`](https://github.com/ali-han-kaya/leibniz2/commit/c2adbf4) |
| 2026-09-09 | docs | update changelog for 94ca88e closure fixes | [`c6fdf97`](https://github.com/ali-han-kaya/leibniz2/commit/c6fdf97) |
| 2026-09-09 | fix | (ci) make check-unit-tests green in clean checkout | [`d445408`](https://github.com/ali-han-kaya/leibniz2/commit/d445408) |
| 2026-09-09 | fix | (ci) handle workflow directories in check_action_pins | [`986169a`](https://github.com/ali-han-kaya/leibniz2/commit/986169a) |
| 2026-09-10 | fix | (ci) fail-closed commit-msg gate + atomic sidecar writes | [`16b9144`](https://github.com/ali-han-kaya/leibniz2/commit/16b9144) |
| 2026-09-10 | fix | (verify) K14 one-unit — drift gate + registry resync (P0 clear) | [`62772d9`](https://github.com/ali-han-kaya/leibniz2/commit/62772d9) |
| 2026-09-09 | feat | (preview) merge history+refs-trend into one /api/trend fetch | [`1ac6a9a`](https://github.com/ali-han-kaya/leibniz2/commit/1ac6a9a) |
| 2026-09-09 | fix | (preview) canonicalize preview/verify dirs to abspath in main() | [`05aeca1`](https://github.com/ali-han-kaya/leibniz2/commit/05aeca1) |
| 2026-09-09 | test | (verify) add /api/* method contract and fix drift registrations | [`203edab`](https://github.com/ali-han-kaya/leibniz2/commit/203edab) |
| 2026-09-09 | test | (preview) land POST-only live-HTTP regression for /api/run-now | [`b415a0e`](https://github.com/ali-han-kaya/leibniz2/commit/b415a0e) |
| 2026-09-09 | test | (preview) add 8-thread hammer for _write_atomic torn-read guarantee | [`a2376df`](https://github.com/ali-han-kaya/leibniz2/commit/a2376df) |
| 2026-09-09 | test | (preview) add atomic-write contract tests for persist layer | [`aed7169`](https://github.com/ali-han-kaya/leibniz2/commit/aed7169) |
| 2026-09-09 | docs | (changelog) add rows for c44df67 rerun + 27f5c7f resync | [`f9a5306`](https://github.com/ali-han-kaya/leibniz2/commit/f9a5306) |
| 2026-09-09 | fix | (pre-commit) venv-guard check-doc-job-sync hook + contract test | [`af945d8`](https://github.com/ali-han-kaya/leibniz2/commit/af945d8) |
| 2026-09-09 | chore | (ci) trigger CI rerun for 27f5c7f gate verdicts | [`27989dc`](https://github.com/ali-han-kaya/leibniz2/commit/27989dc) |
| 2026-09-09 | docs | (changelog) resync after wiring flat-path contract fix | [`4d97c77`](https://github.com/ali-han-kaya/leibniz2/commit/4d97c77) |
| 2026-09-09 | test | (verify) extend derived-input contract to manifest-comment delivery | [`afb1d71`](https://github.com/ali-han-kaya/leibniz2/commit/afb1d71) |
| 2026-09-10 | fix | (verify) tolerate fresh-clone mtime skew in review freshness | [`3130d9b`](https://github.com/ali-han-kaya/leibniz2/commit/3130d9b) |
| 2026-09-10 | test | (verify) mock lean binary in check_lean_axioms tests | [`5cfbecb`](https://github.com/ali-han-kaya/leibniz2/commit/5cfbecb) |
| 2026-09-10 | fix | (ci) guard deck modules for missing PIL and install Pillow | [`b0d36e1`](https://github.com/ali-han-kaya/leibniz2/commit/b0d36e1) |
| 2026-09-10 | test | (verify) register repo-wide atomic-write guard | [`e115bd8`](https://github.com/ali-han-kaya/leibniz2/commit/e115bd8) |
| 2026-09-10 | docs | (changelog) resync table through c2adbf4 | [`b1337af`](https://github.com/ali-han-kaya/leibniz2/commit/b1337af) |
| 2026-09-10 | test | (verify) register atomic-write guard in hook coverage map | [`3b60999`](https://github.com/ali-han-kaya/leibniz2/commit/3b60999) |
| 2026-09-10 | docs | (changelog) resync table through 3130d9b | [`6272e66`](https://github.com/ali-han-kaya/leibniz2/commit/6272e66) |
| 2026-09-10 | docs | (changelog) resync table through hook coverage fix | [`14dd67e`](https://github.com/ali-han-kaya/leibniz2/commit/14dd67e) |
| 2026-09-10 | ci | (verify) install Lean in ci-simulate job for K9 replay parity | [`287913f`](https://github.com/ali-han-kaya/leibniz2/commit/287913f) |
| 2026-09-10 | docs | (changelog) resync table through ci-simulate lean install | [`f640f2e`](https://github.com/ali-han-kaya/leibniz2/commit/f640f2e) |
| 2026-09-10 | test | (verify) meta-guard github_scripts gates against fail-open | [`d9271b5`](https://github.com/ali-han-kaya/leibniz2/commit/d9271b5) |
| 2026-09-10 | docs | (changelog) resync table through gate meta-guard | [`9b60d7a`](https://github.com/ali-han-kaya/leibniz2/commit/9b60d7a) |
| 2026-09-10 | docs | (changelog) resync table through meta-guard unit | [`f063363`](https://github.com/ali-han-kaya/leibniz2/commit/f063363) |
| 2026-09-10 | docs | archive rc-review worktree brief and resync changelog | [`08d3c25`](https://github.com/ali-han-kaya/leibniz2/commit/08d3c25) |
| 2026-09-11 | test | (verify) fail-closed canonical-hash pin for cleanup_log.json | [`e2aaf86`](https://github.com/ali-han-kaya/leibniz2/commit/e2aaf86) |
| 2026-09-10 | docs | (triage) record 091635c CI failure root causes in findings.md | [`9bcd753`](https://github.com/ali-han-kaya/leibniz2/commit/9bcd753) |
| 2026-09-10 | fix | (verify) make review freshness gate fresh-clone-safe | [`9544cb4`](https://github.com/ali-han-kaya/leibniz2/commit/9544cb4) |
| 2026-09-10 | fix | (ci-audit) break advisory self-loop in deterministic gate | [`a345284`](https://github.com/ali-han-kaya/leibniz2/commit/a345284) |
| 2026-09-10 | test | (verify) add full-discover drift guard + register tests | [`8bac7f8`](https://github.com/ali-han-kaya/leibniz2/commit/8bac7f8) |
| 2026-09-11 | docs | (changelog) resync table through e2aaf86 canonical-hash pin | [`2a493ec`](https://github.com/ali-han-kaya/leibniz2/commit/2a493ec) |
| 2026-09-11 | fix | (verify) make status-checks importable without PyYAML and skip bare-runner | [`b227c2e`](https://github.com/ali-han-kaya/leibniz2/commit/b227c2e) |
| 2026-09-11 | fix | (docker) drop docker-scout step that requires a paid entitlement | [`d4f095e`](https://github.com/ali-han-kaya/leibniz2/commit/d4f095e) |
| 2026-09-11 | fix | (docker) single table-mode trivy gate with visible evidence | [`8f6e2a9`](https://github.com/ali-han-kaya/leibniz2/commit/8f6e2a9) |
| 2026-09-11 | fix | (docker) patch base-image setuptools and wheel in runtime stage | [`f9e088f`](https://github.com/ali-han-kaya/leibniz2/commit/f9e088f) |
| 2026-09-11 | fix | (docker) upgrade vendored setuptools to patched line | [`f690d3d`](https://github.com/ali-han-kaya/leibniz2/commit/f690d3d) |
| 2026-09-11 | fix | (docker) bookworm base pin + visible trivy findings table | [`f6734a0`](https://github.com/ali-han-kaya/leibniz2/commit/f6734a0) |
| 2026-09-11 | fix | (verify) surface advisory coe findings that could die unpublished | [`b129bed`](https://github.com/ali-han-kaya/leibniz2/commit/b129bed) |
| 2026-09-11 | refactor | (verify) single-source workflow contract fixture | [`616f5eb`](https://github.com/ali-han-kaya/leibniz2/commit/616f5eb) |
| 2026-09-11 | ci | (docker) land docker-security workflow with pinned actions | [`38e1a83`](https://github.com/ali-han-kaya/leibniz2/commit/38e1a83) |
| 2026-09-11 | fix | (design) land token sheet and wire dashboard to single source | [`1a0b32c`](https://github.com/ali-han-kaya/leibniz2/commit/1a0b32c) |
| 2026-09-12 | fix | (verify) dependency-closed delivery resync and mirror coverage set | [`831b941`](https://github.com/ali-han-kaya/leibniz2/commit/831b941) |
| 2026-09-12 | chore | (repo) ignore generated deck renders and agent temp dirs | [`963f690`](https://github.com/ali-han-kaya/leibniz2/commit/963f690) |

### Regresyon notları

| ID | Tarih | Kırılma | Kök neden | Düzeltme | Commit |
|---|---|---|---|---|---|
| R1 | 2026-08-19 | CI 0s/0 job boş run | YAML adım `}` + `uses:` aynı satıra yapıştı | satır ayrımı + actionlint | `d57a60c` |
| R2 | 2026-08-21 | summary yerelde yazılmıyor | `GITHUB_STEP_SUMMARY` env boştu | iki aşamalı write + validate | `2282925` |
| R3 | 2026-08-21 | pre-commit block (actionlint RC=1) | shellcheck info hints advisory iken fail | `lint_actionlint.sh` RC≤2 PASS | `ae55009` |
| R4 | 2026-08-21 | `listLabels is not a function` | Octokit `listLabels` → `listLabelsForRepo` | 4 dosya güncellendi | `309a14f` |
