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
| 2026-09-11 | fix | (docker) drop docker-scout step that requires a paid entitlement | [`43af1fb`](https://github.com/ali-han-kaya/leibniz2/commit/43af1fb) |
| 2026-09-11 | fix | (docker) single table-mode trivy gate with visible evidence | [`2590023`](https://github.com/ali-han-kaya/leibniz2/commit/2590023) |
| 2026-09-11 | fix | (docker) patch base-image setuptools and wheel in runtime stage | [`206d218`](https://github.com/ali-han-kaya/leibniz2/commit/206d218) |
| 2026-09-11 | fix | (docker) upgrade vendored setuptools to patched line | [`1add3d4`](https://github.com/ali-han-kaya/leibniz2/commit/1add3d4) |
| 2026-09-11 | fix | (docker) bookworm base pin + visible trivy findings table | [`54d563d`](https://github.com/ali-han-kaya/leibniz2/commit/54d563d) |
| 2026-09-11 | fix | (verify) surface advisory coe findings that could die unpublished | [`5fac15c`](https://github.com/ali-han-kaya/leibniz2/commit/5fac15c) |
| 2026-09-11 | refactor | (verify) single-source workflow contract fixture | [`57ebe32`](https://github.com/ali-han-kaya/leibniz2/commit/57ebe32) |
| 2026-09-11 | ci | (docker) land docker-security workflow with pinned actions | [`85a07c5`](https://github.com/ali-han-kaya/leibniz2/commit/85a07c5) |
| 2026-09-11 | fix | (design) land token sheet and wire dashboard to single source | [`edb0640`](https://github.com/ali-han-kaya/leibniz2/commit/edb0640) |
| 2026-09-11 | docs | (changelog) resync table through e2aaf86 canonical-hash pin | [`d37a45f`](https://github.com/ali-han-kaya/leibniz2/commit/d37a45f) |
| 2026-09-11 | test | (verify) fail-closed canonical-hash pin for cleanup_log.json | [`9e4c8ea`](https://github.com/ali-han-kaya/leibniz2/commit/9e4c8ea) |
| 2026-09-10 | feat | (verify) reproducibility gates + verify_mcp + dashboard perf/security hardeni... | [`e6572d1`](https://github.com/ali-han-kaya/leibniz2/commit/e6572d1) |
| 2026-09-12 | fix | (review) rebuild review compilation after the delivery resync | [`f8a1fa0`](https://github.com/ali-han-kaya/leibniz2/commit/f8a1fa0) |
| 2026-09-12 | fix | (docker) upgrade base-image libpcre2 for the trivy gate | [`5bf6ebe`](https://github.com/ali-han-kaya/leibniz2/commit/5bf6ebe) |
| 2026-09-12 | docs | (changelog) resync table and prune stale rows | [`4c483d4`](https://github.com/ali-han-kaya/leibniz2/commit/4c483d4) |
| 2026-09-12 | fix | (verify) make advisory comment scripts crash-safe on bad sidecars | [`1d8f1ec`](https://github.com/ali-han-kaya/leibniz2/commit/1d8f1ec) |
| 2026-09-12 | feat | (changelog) add safe stale-row pruning | [`26f6a19`](https://github.com/ali-han-kaya/leibniz2/commit/26f6a19) |
| 2026-09-12 | chore | (repo) ignore generated deck renders and agent temp dirs | [`ed08874`](https://github.com/ali-han-kaya/leibniz2/commit/ed08874) |
| 2026-09-12 | fix | (verify) dependency-closed delivery resync and mirror coverage set | [`e694216`](https://github.com/ali-han-kaya/leibniz2/commit/e694216) |
| 2026-09-11 | fix | (verify) status-checks importable on bare runners without PyYAML | [`6b4c021`](https://github.com/ali-han-kaya/leibniz2/commit/6b4c021) |
| 2026-09-12 | docs | (changelog) resync table after the review and trivy fixes | [`534b468`](https://github.com/ali-han-kaya/leibniz2/commit/534b468) |
| 2026-09-12 | fix | (verify) pin the V5m lineage generation to its owning commit | [`ba088ad`](https://github.com/ali-han-kaya/leibniz2/commit/ba088ad) |
| 2026-09-12 | docs | (changelog) resync table through ba088ad | [`cfcaf91`](https://github.com/ali-han-kaya/leibniz2/commit/cfcaf91) |
| 2026-09-13 | fix | (verify) resolve review-freshness times from the file's own repo | [`16d4e06`](https://github.com/ali-han-kaya/leibniz2/commit/16d4e06) |

### Regresyon notları

| ID | Tarih | Kırılma | Kök neden | Düzeltme | Commit |
|---|---|---|---|---|---|
| R1 | 2026-08-19 | CI 0s/0 job boş run | YAML adım `}` + `uses:` aynı satıra yapıştı | satır ayrımı + actionlint | `d57a60c` |
| R2 | 2026-08-21 | summary yerelde yazılmıyor | `GITHUB_STEP_SUMMARY` env boştu | iki aşamalı write + validate | `2282925` |
| R3 | 2026-08-21 | pre-commit block (actionlint RC=1) | shellcheck info hints advisory iken fail | `lint_actionlint.sh` RC≤2 PASS | `ae55009` |
| R4 | 2026-08-21 | `listLabels is not a function` | Octokit `listLabels` → `listLabelsForRepo` | 4 dosya güncellendi | `309a14f` |
