# Lokal Doğrulama Rehberi

> **Diátaxis: How-to guide** — Problem-yönelimli. Amacı: CI'da kırmızı almadan
> *önce*, deponun kendi kapılarını lokalde aynı parametrelerle koşmak.
> Öğretici değil (yeni-gelen için bkz. README "Doğrulama" bölümü), referans da
> değil (kapı satır-içi sözlüğü için bkz. `docs/HOOK_ENV_MATRIX.md`).

## 0. Ön koşullar

- Repo kökünde olun: `cd $(git rev-parse --show-toplevel)`. Bu rehberdeki
  tüm göreli yollar köke göre yazılmıştır.
- Python 3.9+ (sistem python3 yeterli — kapılar stdlib-only tasarlanmıştır).
- `pre-commit` kurulu (`pip install pre-commit`); git hook'ları bağlanmış
  (`pre-commit install` — fresh-clone kurulumunun 3. adımı).
- Z3 yalnızca sembolik ispat kapısı için gerekir: `pip install z3-solver`
  (K9/K10 dışındaki kapılar Z3'süz koşar).

## 1. En hızlı döngü — tek komut

Commit'ten önce tek kapıyı koşmak için:

```bash
python3 _calisma/CIKTI/verify_delivery.py
```

Çıktının son satırı kapı dilidir: `verdict: PASS` ya da `verdict: FAIL` +
bulgular. Bu, CI'daki K1–K14 zincirinin lokal koşumudur (env bağımsız,
stdlib-only). Bütçe/referans gibi ağ gerektiren modüller parametreyle
açılır (`--budget 30`, `--refs-out …`); varsayılan koşum offline'dır.

## 2. Tam zincir — pre-commit'i commit'e kadar koşmak

Depodaki `.pre-commit-config.yaml` 40+ kapıyı sıralar (verify-delivery,
action-pins, actionlint, sync, mirror-coverage, plist-drift, repro-manifest…).
Lokalde birebir aynı zincir yalnızca gerçek bir commit anında koşar:

```bash
git add -A && git commit -m "test: lokal zincir koşumu"
```

Zincir kırmızıysa commit düşmez; hook çıktısındaki `hook id:` satırı hangi
kapının kırıldığını söyler. Düzeltip aynı komutu tekrarlayın.
(Not: bazı kapılar dosyaları otomatik düzenler — "Files were modified by this
hook" uyarısı alırsanız dosyaları tekrar `git add` edip commit'i yineleyin.)

## 3. CI'ı lokal simüle etmek

CI'da koşan işin aynısını lokalde üretmek için iki araç vardır:

```bash
# unit testler (CI'daki unittest discover ile aynı keşif)
python3 -m unittest discover -s _calisma/CIKTI -p "test_*.py"

# workflow sözdizimi + action pinleri + runtime gate
bash _calisma/CIKTI/lint_actionlint.sh
python3 _calisma/CIKTI/check_action_pins.py
python3 _calisma/CIKTI/check_action_runtimes.py
```

Ağaç senkronizasyonu (test listesi ↔ HOOK_COVERAGE tutarlılığı):

```bash
python3 _calisma/CIKTI/sync_check_unit_tests.py --check   # rc=0 gerekli
# bozuksa: --update ile liste yenilenir, sonra farkı gözden geçirin
```

## 4. Yaygın arızalar

| Belirti | Kök neden | Çözüm |
|---|---|---|
| `check-unit-tests: N/M test dosyası BAŞARISIZ` | Unstaged kaynak, hook'un stash'lediği ağaçta eski sürümle koşuldu | İlgili kaynak dosyayı stage edin (`git add`) ve commit'i tekrarlayın |
| `commit-msg: HATA — başlık N karakter (sınır: 72)` | Başlık 72 karakteri aştı | Konuyu kısaltın; kural `.gitmessage` içinde |
| `Changelog sync` dosyayı değiştirdi, commit düştü | Hook README changelog tablosunu otomatik güncelledi | `git add README.md` + commit'i yineleyin (repo deseni) |
| `sync --check` rc=1: "YENİ keşfedilen test dosyası" | Yeni `test_*.py` listeye alınmamış | `sync_check_unit_tests.py --update` |
| `verify-delivery` FAIL: K-bağımsız bulgu | ZIP/PDF/manifest gerçek veri sorunu | `verdict` satırındaki K-koduyla ilgili bölümü `docs/FINAL_RC_REPORT.md`'de arayın |
| actionlint FAIL: workflow sözdizimi | `.github/workflows/*.yml` düzenlendi | `bash _calisma/CIKTI/lint_actionlint.sh` çıktısındaki satırı düzeltin |

## 5. Kapı tablosu (başvuru)

Her kapının satır-içi açıklaması, gerekli araç sürümü ve env matrisi:
`docs/HOOK_ENV_MATRIX.md`. CI koşumlarının kök-neden triyajı için:
`docs/CI_GATE_TRIAGE.md`. Bu rehberdeki komutların CI karşılıkları
`.github/workflows/verify.yml` içinde ada göre eşleşir.

## 6. check-unit-tests manifesti — EXCLUDE sınıflandırması (2026-10-28)

Kural: bir test manifest (`_calisma/CIKTI/check_unit_tests.list`, pre-commit
`check-unit-tests` hook'u) dışında kalacaksa gerekçe **commit sırasında
koşamıyor olması**dır; "yavaş" tek başına gerekçe değildir. Tek kaynak
`sync_check_unit_tests.py` içindeki `EXCLUDE` / `EXCLUDE_HOOKS` /
`EXCLUDE_CI_JOBS` kümeleridir; aşağıdaki tablo o kaynağın 2026-10-28
ölçümüyle alınmış fotoğrafıdır (süreler bu makinede, `discover -p` ya da
modül koşumuyla).

Sınıflar: **A** kendi ortamını kurar (manifest'te koşar) · **B** kendi
pre-commit hook'u var (hafif, hook zaten koşar) · **C** dış ortam bağımlı
(launchctl/macOS servisi, canlı sunucu, tarayıcı, ağ → CI job'ı).

| Test | Sınıf | Gereken ortam | Ölçüm | Neden manifest'te değil | Koşma yeri |
|---|---|---|---|---|---|
| `test_check_bibliography_sync.py` | B | yok | 1.0s | `check-bibliography-sync` hook'u zaten koşuyor | hook |
| `test_check_config_sync.py` | B | yok | 0.1s | `check-config-sync` hook'u | hook |
| `test_check_plist_drift.py` | B+C | launchctl (macOS) | 0.1s | `check-plist-drift` hook'u | hook |
| `test_check_refs_table_sync.py` | B | yok | 0.1s | `check-refs-table-sync` hook'u | hook |
| `test_check_review_freshness.py` | B | yok | 0.7s | `check-review-freshness` hook'u | hook |
| `test_colorize_rules.py` | B | yok | 0.1s | `check-colorize-rules` hook'u | hook |
| `test_doc_artifact_sync.py` | B | yok | 0.1s | `check-doc-artifact-sync` hook'u | hook |
| `test_dryrun_summary.py` | B | yok | 0.2s | `check-dryrun-summary` hook'u | hook |
| `test_gen_config.py` | B | yok | 0.1s | `update-config` hook'u | hook |
| `test_gen_plist_golden.py` | B+C | launchctl (macOS) | 0.8s | `check-plist-drift` hook'u | hook |
| `test_gen_repro_manifest.py` | B | yok | 4.6s | `check-repro-manifest` hook'u | hook |
| `test_github_scripts_battery.py` | B | node | 5.2s | `verify-delivery-github-scripts` hook'u | hook |
| `test_ia_ol_fallback_evidence.py` | B | yok | 0.1s | `check-fallback-evidence` hook'u | hook |
| `test_lake_evidence_smoke.py` | B+C | Lean (varsa koşar) | 1.0s | `check-lake-evidence` hook'u | hook |
| `test_plist_gate_exit.py` | B+C | launchctl + fake HOME | 12.7s | `check-plist-drift` hook'u | hook |
| `test_verify_manifest_overrides.py` | B | yok | 0.1s | `verify-delivery-repro-manifest` hook'u | hook |
| `test_verify_manifest_sidecar.py` | B | yok | 1.6s | `verify-delivery-repro-manifest` hook'u | hook |
| `test_dashboard_playwright_smoke.py` | C | Chromium (Playwright) | 10.0s | tarayıcı kurulumu commit ortamında garanti değil | `dashboard-smoke` |
| `test_preview_interaction_cdp.py` | C | Chromium + kendi sunucusu | 10.3s | aynı: CDP katmanı | `dashboard-smoke` |
| `test_fresh_clone_setup.py` | C | fake HOME + kurulum betiği | 60.6s / 74s / 120s+ | süre 2-3x değişken (ölçüldü) — commit bütçesini belirsizleştirir | `fresh-clone-http` |
| `test_verify_refs.py` | C | ağ (refs-online) | 3.7s | kaynak doğrulama ağa bağlı | `verify` (refs-online adımı) |
| `test_check_history.py` | C | sidecar | 0.1s | hafif; K15 sidecar zinciri CI'da | `verify` |
| `test_cleanup.py` | C | launchctl kayıtları | 0.1s | ortam-etkili (gerçek launchd durumuna bakar) | `verify` |
| `test_k18_daemon.py` | C | yok (mock) | 0.1s | hafif; daemon zincirinin parçası | `verify` |
| `test_preview_prestart.py` | C | yok (mock) | 0.9s | hafif; preview daemon zinciri | `verify` |
| `test_preview_reload_smoke.py` | C | canlı preview | 0.1s | unittest olarak 0 test topluyor (script-style) | `preview-reload-smoke` |
| `test_all_hooks_smoke.py` | C | tüm hook'lar | 0.0s | unittest olarak 0 test topluyor; tüm hook'ları çağırır (özyineleme) | script |

2026-10-28 triyajında değişenler:

- `test_daemon_http.py` **manifest'e alındı**: kendi daemon sürecini geçici
  portta başlatır (9-10s, `discover -p` ile üç koşumda da aynı). CI'da `CI`
  env'i yüzünden SKIP'e düşüyordu; yani bildirilen `daemon-http` job'ı onu
  hiç koşmuyordu — gerçekten koşabildiği tek yer pre-commit.
- `test_repro_manifest_topology.py` hem `EXCLUDE`'dan hem bağlamasından
  düşürüldü: dosya diskte yoktu ama `verify` bağıyla "bağlı" görünüyordu
  (bağlama denetimi dosya varlığını sormuyor). Regresyon testi eklendi:
  EXCLUDE'daki her girdi diskte olmalı.
- `test_fresh_clone_setup.py` dışarıda bırakıldı; gerekçe artık yorum değil
  ölçüm (60.6s → 74s → 120s+ timeout).
- Hook süresi: 184 dosya 139.6s → **185 dosya 148.0s** (daemon_http dahil).
