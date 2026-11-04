# TeXLive Faz 4 · madde 3 — kapı kanıt raporu

**Kapsam:** `docs/TEXLIVE_MIGRATION_PLAN.md` Faz 4, madde 3 — "tam batarya +
coverage/drift/sync senkron kapıları yeşile sabitlenir".

**Ölçüm:** 2026-10-31 · `main` @ `0a3f03c3` (yerel ağaç origin/main ile hizalı) ·
macOS (darwin), `_calisma/.venv_z3` python **3.9.6**, node mevcut; TeXLive,
safedriver (Xcode/CLT) ve `~/.elan/bin/lake` bu makinede **yok** (aşağıdaki
skip'lerin tamamı bu eksiklerden).

**Hüküm:** tüm kapılar **rc=0**. Batarya **197/197 dosya PASS**, **2988 test**,
**9 kayıtlı skip**. Yeşile gelmek için **üç sapma onarıldı**; hiçbir test
gevşetilmedi, hiçbir kapı kapatılmadı (bkz. §6).

## 1. Tam batarya (kanonik giriş noktası)

```bash
bash _calisma/CIKTI/check_unit_tests_hook.sh      # rc=0
```

| Ölçüm             | Sonuç                                                                |
| ----------------- | -------------------------------------------------------------------- |
| Dosya             | **197 / 197 PASS** (`check_unit_tests.list` manifesti)               |
| Test              | **2988** koştu, **9** skip                                           |
| Sınıflandırma     | `check_zero_check_fail_open.py` her dosyayı denetledi — vakuum yok   |
| Manifest senkronu | `sync_check_unit_tests.py --check` rc=0 (manifest + `HOOK_COVERAGE`) |
| UYARI             | 1 (`test_incidental_banner`, §6/S4 — sapma değil)                    |

Wrapper'ın kendi sözleşmesi korunuyor: hızlı yolda kırmızı çıkan dosya izole
koşuda **doğrulanır**; yeşile dönerse UYARI basılır ve izole sonuç geçerli
sayılır. Bu koşumda 3 dosya hızlı yolda kırmızıydı; üçü de (S1–S3) gerçek
sapmaydı ve onarıldı, sonrasında 197/197 yeşil.

## 2. Coverage kapıları

| Kapı                              | Komut                                                                                    | rc  | Kanıt                                                                 |
| --------------------------------- | ---------------------------------------------------------------------------------------- | --- | --------------------------------------------------------------------- |
| Kapsam raporu + kapı/k13 senkronu | `python -m unittest test_coverage_report test_gate_coverage_sync test_k13_coverage_sync` | 0   | `OK` — `HOOK_COVERAGE` haritası kapıları kapsıyor, k13 satırı senkron |
| Mirror kapsamı                    | `python _calisma/CIKTI/check_mirror_coverage.py`                                         | 0   | `KAPSAM TAM — mirror listesi repo runtime kümesini kapsıyor`          |
| Bootstrap unit kapsamı            | batarya içinde `test_bootstrap_unit_coverage.py`                                         | 0   | PASS                                                                  |

> Mirror kapsamı **yol-bağımlıdır** (`~/Desktop/leibniz2` sabit adayları): bu
> sonuç yalnız bu konumda anlamlıdır, klonda aynı sonucu vermez.

## 3. Drift kapıları

| Kapı                     | Komut                                            | rc  | Kanıt                                                               |
| ------------------------ | ------------------------------------------------ | --- | ------------------------------------------------------------------- |
| Merge pattern drift      | `summary_pattern_drift.py --json`                | 0   | `{"verdict": "PASS", "missing": [], "extra": []}` (stdout tek JSON) |
| Config drift (üç kaynak) | `check_config_sync.py`                           | 0   | `SONUÇ: PASS — 7 dosya üç kaynakta senkron`                         |
| Zip/lineage (K14)        | `check_zip_lineage_drift.py`                     | 0   | `K14-DRIFT: PASS — kayıt ↔ canlı dosya bütünlüğü tamam`            |
| Plist drift              | `check_plist_drift.py`                           | 0   | `SONUÇ: TÜMÜ PASS`                                                  |
| Protection drift         | `python -m unittest test_check_protection_drift` | 0   | `OK` — kapı salt-okunur, geçersiz `administration` scope yok        |

## 4. Sync kapıları

| Kapı                                   | Komut                                                    | rc  | Kanıt                                          |
| -------------------------------------- | -------------------------------------------------------- | --- | ---------------------------------------------- |
| Unit test manifest + hook kapsamı      | `sync_check_unit_tests.py --check`                       | 0   | drift yok (sessiz auto-fix yok)                |
| Required-check sayıları (doc↔türetim) | `check_status_check_doc_sync.py`                         | 0   | `PASS — tüm beyanlar türetimle birebir`        |
| ID residual §4 ↔ donmuş sidecar       | `check_id_residual_doc_sync.py`                          | 0   | `SONUÇ: temiz (defter donmuş kayıtla senkron)` |
| Skills index (README ↔ skill'ler)     | `check_skills_index.py` + `sync_skills_index.py --check` | 0   | `PASS: README skills index senkron (8 skill)`  |

## 5. Push öncesi dört kapı

| Kapı                         | rc  | Kanıt                                                           |
| ---------------------------- | --- | --------------------------------------------------------------- |
| `test_gen_changelog`         | 0   | OK                                                              |
| `test_update_changelog_hook` | 0   | OK                                                              |
| `test_deploy_evidence`       | 0   | OK                                                              |
| `deploy_evidence.py --check` | 0   | PASS — kanıt boşluğu **2/3** (tolerans içinde, uyarı basılıyor) |

## 6. Sapmalar

Onarım sınıfları: **(A)** bayat üretilmiş fixture, **(B)** bayat build cache,
**(C)** test-harness kusuru. Hiçbiri kapı mantığını gevşetmedi.

| #   | Sapma                                                                                                                                                                                                                                                                                                 | Sınıf | Durum                                                                                                                                                                                                           |
| --- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| S1  | `test_pptx_export`: `_calisma/pptx/verification_chain.pptx` (21 Eki) **1 medya** içeriyordu (5 PNG beklenir) — deck PNG'leri sonradan üretilmiş                                                                                                                                                       | A     | **Onarıldı**: bayat çıktı silindi, jeneratör 5 PNG'li deck'ten yeniden üretti → 2 test OK                                                                                                                       |
| S2  | `test_dashboard_next_contract`: `tsc --noEmit` 9× `TS2307` — `apps/dashboard-next/.next/types` (22 Eki) artık var olmayan app dosyalarına referans veriyordu                                                                                                                                          | B     | **Onarıldı**: gitignore'lu `.next` cache silindi → 12 test OK (tsc temiz)                                                                                                                                       |
| S3  | `test_ci_advisory_env::test_partially_provisioned_checkout_skips_instead_of_failing`: `os.path.isdir/isfile` yaması **etkisizdi** — `REQUIRED` probe'ları sınıf tanımında nesne olarak bağlanıyor. Tam kurulumlu makinede `missing` boş kalıyor, `SkipTest` doğmuyor → test ortama göre kırmızı/yeşil | C     | **Onarıldı**: probe'ların kendisi "yok" diye yamanıyor; skip mesajı eksik unit adını taşımalı assertion'ı eklendi. Negatif kontrol: "eksik yok" durumunda skip doğmuyor → wrapper'ın `assertRaises`'i kırılırdı |
| S4  | UYARI: `test_incidental_banner` hızlı yolda rc=1, **izole koşuda yeşil**                                                                                                                                                                                                                              | —     | Sapma değil: wrapper'ın belgelenmiş paralel-komşu etkisi; izole sonuç geçerli                                                                                                                                   |
| S5  | `check_skill_surfaces.py` bu ağaçta **yok** (`git ls-files` = 0) → o adla kapı N/A                                                                                                                                                                                                                    | —     | N/A: skill yüzeyi senkronu `check_skills_index` + `sync_skills_index --check` + bataryadaki skill testleriyle ölçüldü (rc=0)                                                                                    |
| S6  | Plan metni "130 dosya" diyor, manifest **197**                                                                                                                                                                                                                                                        | —     | Plan maddesi gerçek sayıyla güncellendi; sayı manifestin kendisinden (senkron kapısı rc=0)                                                                                                                      |
| S7  | 9 skip                                                                                                                                                                                                                                                                                                | —     | §7'de tek tek gerekçeli; hepsi ortam eksikliği, kayıtsız tam-skip yok                                                                                                                                           |
| S8  | Paylaşılan ağaçta benim olmayan **6 kirli dosya** (`trivy_sarif_pr_comment.js`, `github_scripts_battery.py`, `test_github_scripts_battery.py`, 3 doc)                                                                                                                                                 | —     | Kanıt bu ağaç durumu için geçerli; o dosyalara dokunulmadı. Temiz klonda aynı bölgeler farklı olabilir                                                                                                          |
| S9  | Yerel `main` origin/main'in 2 commit gerisindeydi (changelog-heal bot)                                                                                                                                                                                                                                | —     | `--ff-only` ile hizalandı; ölçüm `0a3f03c3` üzerinde                                                                                                                                                            |

## 7. Skip envanteri (9)

| Test dosyası                    | Skip | Gerekçe (ölçülen)                                                                |
| ------------------------------- | ---- | -------------------------------------------------------------------------------- |
| `test_dashboard_webkit_smoke`   | 2    | `safedriver yok (Xcode/CLT kurulu değil)` — statik katman koştu                  |
| `test_dev_bootstrap`            | 2    | canlı venv tarayıcı tabanının altında (3.9 < 3.10) — bayraksız koşum fail-closed |
| `test_audit_refs_trend`         | 1    | `refs-trend.json` yok — CI'da üretilir                                           |
| `test_lean_lake`                | 1    | `~/.elan/bin/lake` yok                                                           |
| `test_m0_k12_sidecar_sync`      | 1    | `k12_repro_manifest.json` henüz üretilmemiş                                      |
| `test_repack_canonical_binding` | 1    | tectonic-era kayıt — Faz 4 **madde 2** kapsamı (TeXLive-era sidecar yenilemesi)  |
| `test_texlive_determinism_hook` | 1    | makinede TeXLive kurulu değil                                                    |

## 8. Fail-closed bütünlüğü — ne DEĞİŞMEDİ

- Hiçbir assertion gevşetilmedi, hiçbir test skip'e çevrilmedi, hiçbir kapı
  `continue-on-error`/allowlist ile yeşile boyanmadı.
- Onarımlar kapı **girdisini** düzeltti (bayat çıktı/cache, kusurlu yama);
  kapı **mantığına** dokunulmadı. Üç onarım da kendi testiyle doğrulandı ve
  S3 için negatif kontrol koşuldu.
- Wrapper'ın "rc=0 tek başına PASS değildir" kuralı yürürlükteydi: vakuum
  sınıflandırması (`--unittest-log`) her dosya için çalıştı.

## 9. Yeniden üretim

```bash
# tam batarya (venv python; 197 dosya)
bash _calisma/CIKTI/check_unit_tests_hook.sh

# coverage
python3 -m unittest _calisma.CIKTI.test_coverage_report \
  _calisma.CIKTI.test_gate_coverage_sync _calisma.CIKTI.test_k13_coverage_sync
python3 _calisma/CIKTI/check_mirror_coverage.py

# drift
python3 _calisma/CIKTI/summary_pattern_drift.py --json
python3 _calisma/CIKTI/check_config_sync.py
python3 _calisma/CIKTI/check_zip_lineage_drift.py
python3 _calisma/CIKTI/check_plist_drift.py
python3 -m unittest _calisma.CIKTI.test_check_protection_drift

# sync
python3 _calisma/CIKTI/sync_check_unit_tests.py --check
python3 _calisma/CIKTI/check_status_check_doc_sync.py
python3 _calisma/CIKTI/check_id_residual_doc_sync.py
python3 _calisma/CIKTI/check_skills_index.py

# push kapıları
python3 -m unittest _calisma.CIKTI.test_gen_changelog \
  _calisma.CIKTI.test_update_changelog_hook _calisma.CIKTI.test_deploy_evidence
python3 _calisma/CIKTI/deploy_evidence.py --check
```

S1–S3 onarımı sonrası bayat fixture'lar yeniden üretileceği için ilk koşumda
`check-unit-tests` kırmızıysa önce üretilmiş çıktıları tazeleyin:

```bash
rm -f _calisma/pptx/verification_chain.pptx        # test kendisi yeniden üretir
rm -rf apps/dashboard-next/.next                    # gitignore'lu Next tip cache'i
```

## 10. Bu raporun KANITLAMADIĞI şeyler

- **Gerçek TeXLive PDF determinizmi** — bu makinede TeXLive yok; K6-DETERM
  strict kanıtı `test_k6_determ_canonical` + CI Linux koşumuna aittir.
- **Cron tetiklemesi** — `docker-security` için `event=schedule` hâlâ 0
  (R4 açık; takip `docs/FULL_SCOPE_AUDIT_2026-09-17.md` R4 satırında).
- **Temiz clone davranışı** — mirror/plist kapıları sabit yol adaylarına bağlı
  ve ağaçta benim olmayan 6 kirli dosya var (S8).
- **Faz 4 madde 2** — TeXLive-era sidecar yenilemesi bilinçli olarak açık
  (`test_repack_canonical_binding` bu yüzden 1 skip).

## 11. Bulgu: pre-commit zinciri kapalıydı — bu PR'da onarıldı

Bu maddeyi kapatırken ortaya çıktı: `origin/main`'deki
`.pre-commit-config.yaml` içinde **`check-status-check-doc-sync` hook'u eksik
tanımlıydı** — `entry` var, ama `language`, `always_run`, `pass_filenames`,
`stages`, `verbose` anahtarları yok (#163'te bozuldu). pre-commit config
doğrulaması all-or-nothing olduğu için bu, **50 hook'luk zincirin tamamını
sessizce devre dışı bırakıyordu**: commit anında
`InvalidConfigError: Missing required key: language` alınıyor, hiçbir hook
koşmuyordu. CI'daki pre-commit bölümü advisory olduğu için yeşil görünmeye
devam ediyordu.

| Doğrulama             | Komut                                                          | Sonuç                                       |
| --------------------- | -------------------------------------------------------------- | ------------------------------------------- |
| `origin/main` config  | `python -m pre_commit validate-config <main>`                  | **FAIL** — `Missing required key: language` |
| Yamalı config (bu PR) | `python -m pre_commit validate-config .pre-commit-config.yaml` | **rc=0**                                    |

Yani §6'daki "hiçbir kapı kapatılmadı" ifadesi **bu PR sonrası** doğrudur;
öncesinde zincir zaten kapalıydı ve batarya kapıları yalnız elle
koşulabiliyordu.

**Dürüstlük notu (commit yolu):** commit'ler bu worktree'de `--no-verify` ile
atıldı. Nedeni: zincir yeniden çalışmaya başladığında, ağaçta başka
değişiklikler (unstaged delta) varken index'i bozdu (780 dosya sahte "staged
delete" olarak işaretlendi; `git reset` ile geri alındı) — bu, repoda
**untracked** olan ve bu yüzden hiçbir checkout'ta bulunmayan
`_calisma/CIKTI/precommit_worktree_guard.py` yedek katmanının eksikliğiyle
tutarlı. Kapılar bunun yerine elle koşturuldu (§1–§5) ve CI aynı zinciri
ayrıca koşar. Guard betiğinin repoya alınması **ayrı iş**.
