# Docker Güvenlik Kapıları Birleşik Raporu (PR #65–#69)

Bu doküman, 2026-10-01'de main'e giren beş docker-güvenlik PR'ının teslimini
kalıcı kayda geçirir. PR'lar kapandığı için açıklamaları bir daha
yazılamıyordu; içerik burada yaşar.

Kapsam: 14 commit, beş PR, dört fail-closed test sınıfı (K7, K8 ve iki
kapsam guard'ı). Her PR tek bir ölçülen boşluğu kapattı — hiçbiri "iyileştirme"
gerekçesiyle açılmadı.

## Nasıl main'e girdi

| PR | Başlık | Merge commit | Tarih | Ölçek |
|---|---|---|---|---|
| #65 | `docs(docker):` kapı zinciri tablosu ve kapalı döngü | `71a6e09` | 2026-10-01 | 2 commit · 2 dosya · +50 / −3 |
| #66 | `fix(docker):` yama-desen kapısı tüm Dockerfile'ları kapsasın | `47e79ef` | 2026-10-01 | 4 commit · 4 dosya · +130 / −11 |
| #67 | `docs(cron):` ilk Pazartesi SKIP doğrulaması | `fc8b010` | 2026-10-01 | 3 commit · 3 dosya · +115 / −1 |
| #68 | `test(docker):` smoke hook kaydı sözleşmesi (K7) | `38c58ba` | 2026-10-01 | 3 commit · 3 dosya · +90 / −3 |
| #69 | `test(ci):` docker kapı bağımsızlığı sözleşmesi (K8) | `674de6f` | 2026-10-01 | 2 commit · 2 dosya · +75 / −0 |

Her biri merge-commit konvansiyonuyla (`-X PUT .../merge -f merge_method=merge`)
birleşti; squash/rebase yapılmadı.

## Beş mantıksal birim

### 1. Kapı zinciri tablosu (#65)

Doküman "üç katman"ı yalnız **paket** zinciri (apt/pip/npm) için
kullanıyordu; **zorlama** zinciri — smoke job, yama-desen hook'u, cron —
hiçbir tabloda görünmüyordu, dağınık bölümlerden çıkarılıyordu. Kapı
tablosu eklendi ve kapalı döngü diyagramı her adımın hangi kapıya
bağlandığını gösterecek şekilde güncellendi.

**Yan etki:** bu tablo, sonraki iki PR'nin boşluğunu da kayda geçirdi
(bkz. "Yanlış ölçülen adım").

### 2. Kapsam guard'ı (#66)

`check-dockerfile-security-patching` yalnız `^Dockerfile$` ile eşleşiyordu
ve süit tek dosyayı okuyordu (`ROOT / "Dockerfile"`). İkinci bir Dockerfile
eklenmesi onu tamamen kapsam dışı bırakıyordu: ne hook ateşlenir ne
sözleşme uygulanır.

Hook deseni `(^|/)Dockerfile$` yapıldı. Ancak sözleşmenin kendisi iki
stage'li bookworm pini beklediği için her Dockerfile'a körlemesine
uygulanamaz — meşru bir tek-stage yardımcı image'ı kırılırdı. Bu yüzden
çözüm genişletme değil **görünür kılma** oldu: `repo_dockerfiles()` keşfi
+ `test_no_uncovered_dockerfile` fail-closed guard'ı.

### 3. Cron SKIP doğrulaması (#67)

`schedule` satırının kabul ölçütü SKIP sayımını içermiyordu; `dispatch`
satırı `SKIP: trivy yok 0 kez` kaydederken asıl doğrulanması gereken
`schedule` satırı yalnız `verdict=PASS` diyordu. Ölçüt eklendi, sapma
tablosuna SKIP'a özel satır girdi, "İlk Pazartesi doğrulaması" bölümü
üç ölçümü bir araya getirdi.

### 4. Smoke hook kayıt sözleşmesi (K7, #68)

`check-dockerfile-security-patching`'in kayıt sözleşmesi vardı;
`check-docker-security-smoke`'unki yoktu — yalnız genel hook listesi
tutuyordu. Asıl sözleşme **parite**: hook'un `entry`'si, CI'ın smoke
job'ının çağırdığı script ile aynı olmalı.

Bu PR bir de ölçülmemiş bir hatayı düzeltti: `files: Dockerfile` deseni
`Dockerfile.md` ve `Dockerfile.bak` gibi Dockerfile olmayan dosyaları da
tetikliyordu; her tetikleme tam build + Trivy + health demek.

### 5. CI bağımsızlık sözleşmesi (K8, #69)

Kapı `verify.yml` içinde bir job **değil** — ayrı bir workflow
(`docker-security.yml`), `verify.yml` onu 0 kez referans alıyor, iki job
arasında `needs:` yok. Yani hook'tan bağımsız çalışıyor. Ama bu bir
kazaydı: kimse eklemedi, kimse kaldırmadı. Dört özellik sözleşmeye
bağlandı.

## Test sayısı ilerlemesi (ölçüldü)

Her merge commit'indeki gerçek `def test_` sayıları:

| Commit | `test_dockerfile_security_patching` | `test_gated_schedules` | Toplam |
|---|---|---|---|
| `fb38f8c` (oturum başı) | 13 | 18 | **31** |
| `71a6e09` (#65) | 13 | 18 | 31 |
| `47e79ef` (#66) | 17 | 18 | 35 |
| `fc8b010` (#67) | 17 | 21 | 38 |
| `38c58ba` (#68) | 17 | 24 | 41 |
| `674de6f` (#69) | 17 | 28 | **45** |

`test_gated_schedules.py` artık beş sınıf taşıyor:
`TestScheduleGateParity` · `TestSkipIsNotEvidenceInCI` ·
`TestSmokeHookRegistrationContract` (K7) · `TestDockerGateCiIndependence`
(K8) · `TestCronRunbookParity`.

## Zincir kanıtı

Beş PR'ın **her commit'i** 52 hook'luk zincirden geçti:

```
48 Passed / 4 Skipped / 0 Failed
```

Dört skip'in gerekçesi doğrulandı ve duruma göre değişir: prettier ve
dashboard typecheck JS/TS stage olmadığı için; iki docker hook'u
`Dockerfile` stage olmadığı için. **Dockerfile stage'li bir commit
ölçüldüğünde** skip sayısı 4 → 2'ye düştü ve iki gate gerçekten çalıştı:

```
Passed: 50  Skipped: 2
Docker security smoke (SKIP-aware, fail-closed)......Passed  (17.87s)
  docker_client=29.7.2  colima=running  trivy=0.74.0
  trivy_findings=0  health_http=200  container_health=healthy  verdict=PASS
Dockerfile security-patching contract (fail-closed)..Passed  (0.06s)
```

PR CI'si: her birinde **54 SUCCESS / 5 SKIPPED / 0 FAILURE** — temiz main
tabanıyla birebir. Merge sonrası main push'un üç workflow'u
(`verify-delivery`, `docker-security`, `test-smoke`) de yeşil.

## Mutation kanıtı — ve neyin zayıf olduğu

Her yeni guard için mutasyon denendi. Dördü de yakalandı, ama **ilk ölçümde
bazıları "yaşadı"** ve iki farklı sebep vardı — ikisi de kayda değer:

| PR | Mutasyon | Yakalayan |
|---|---|---|
| #66 | M1 hook daraldı + ikinci Dockerfile | 5 test FAIL |
| #66 | M2 hook aşırı-totadı | 2 test FAIL |
| #66 | M3 hijyen dizini keşfe sızdı | 1 test FAIL |
| #67 | M1 kayıt satırından SKIP sayımı kalktı | `first_monday_requires_skip_count_zero` |
| #67 | M2 SKIP sapma satırı silindi | `deviation_table_covers_skip_appearing` |
| #67 | M3 sapma satırından sha256 teşhisi kalktı | `deviation_table_covers_skip_appearing` |
| #67 | M4 komuttan `--event schedule` kalktı | `first_monday_pins_measurements` |
| #68 | M1 `entry` başka script'e yönlendi | `entry_runs_the_ci_parity_script` |
| #68 | M2 `files` aşırı-totadı | `matches_real_dockerfiles_only` |
| #68 | M3 `always_run` eklendi | `is_change_scoped_not_always_run` |
| #68 | M4 `language: script` | `is_change_scoped_not_always_run` |
| #69 | M1 `smoke`'a `needs:` eklendi | `gate_jobs_have_no_needs` |
| #69 | M2 `push`'a `paths:` daraltıldı | `push_trigger_is_not_narrowed_by_paths` |
| #69 | M3 `verify.yml` kapıyı yuttu | `gate_is_a_separate_workflow` |
| #69 | M4 sözleşme manifest'ten çıktı | `patching_contract_also_runs_in_ci` |

### Zayıf testler (gerçek kusurlar)

1. **#67, M3/M4:** sapma tablosu ve prosedür bölümü **genelinde** aranıyordu.
   `sha256sum` başka bir satırda da, `--event schedule` yalnız prose'de de
   geçtiği için testler **ilgisiz metin üzerinden** geçiyordu. Sapma testi
   satırın kendisine, komut testi filtrenin tamamına daraltıldı.
2. **#68, M1:** parite kontrolü **alt-dize**ydi. `...smoke.sh.bak` alt-dizde
   `...smoke.sh`'yi barındırdığı için yanlış yönlendirme kaçıyordu. Tam
   eşitliğe (liste üyeliği) çevrildi.

### Harness hataları (testler değil)

- **#66:** `replace(..., 1)` yorum satırındaki aynı metni değiştiriyordu,
  gerçek `files:` anahtarı duruyordu. Anahtar biçimine çıpalandı.
- **#67:** M2'de harness satırı silmiyordu, **yeniden adlandırıyordu** —
  jeton durduğu için test haklı olarak geçiyordu. Satır tabanlı silmeye
  çevrildi.
- **#68:** `stages:` / `language:` genel dizeler birden çok hook'ta geçtiği
  için mutasyon **ilk hook'a** yazılıyordu. Smoke bloğuna sabitlendi.

## Yanlış ölçülen adım

Bu rapor yazılırken `docker-security.yml` ölçülürken yerel masaüstü
çalışma ağacından (`~/Desktop/leibniz2`) okundu. O dizin `origin/main`'e değil, **ayrı soydaki yerel
`main`'e** (`cf838ed`) bağlıdır; orada smoke job'ının `timeout-minutes`'ı 20
görünüyor ve iş 111 satırdır. `origin/main`'de ise 30'dur (yorumuyla:
*"image-scan aynı build+scan'i 20 dk'de bitiriyor, smoke buna health zincirini
ekliyor → 30 dk"*).

Sonuç: #65'teki doküman **doğruymuş**, ölçüm hatalıydı. Ders: çalışma
ağacını adıyla değil `git rev-parse HEAD` ile doğrula. Bu oturumdaki tüm
PR işleri temiz `origin/main` worktree'sinde yapıldı; hatalı olan yalnız bu
tek ölçüm turuydu.

Ayrıca #66'nın ilk commit denemesi **başarısız oldu** (`COMMIT_RC=1`, 2 FAIL):
zincir çalışma ağacındaki test dosyasını okuyor, testler düzeltilmeden önce
launch edilmişti.

## Bu raporun kendi sözleşmesi (K9)

Özet dokümanlar zamanla ayrışır: test sayısı değişir, hash yanlış yazılır,
bir PR unutulur. `_calisma/CIKTI/test_gated_schedules.py` içindeki
`TestGateMergeReportContract` (K9) bu raporun iddialarını **canlı yüzeyden**
türetip karşılaştırır: PR satırları ve merge hash'leri kendi tablo
satırında, test toplamı AST ile sayılan canlı süitlerden, SKIP koşulu
sayısı script'ten.

Altı mutasyonla kanıtlandı, altısı da doğru testle kırıldı:

| Mutasyon | Yakalayan |
|---|---|
| M1 PR tablo satırı silindi | `report_lists_every_merged_gate_pr` |
| M2 merge hash'i bozuldu | `report_merge_hashes_match_real_merges` |
| M3 test toplamı değiştirildi | `report_test_counts_match_live_suites` |
| M4 taban değeri silindi | `report_test_counts_match_live_suites` |
| M5 SKIP koşul sayısı yalanlandı | `report_records_the_undocumented_skip_messages` |
| M6 belgelenmemiş SKIP adı silindi | `report_records_the_undocumented_skip_messages` |

İlk ölçümde **üçü yaşadı**, hepsi aynı sınıf hataydı — test, iddiayı
**ilgisiz metin üzerinden** geçiyordu:

1. `"#68"` araması dokuz yerde tutuyordu; mutasyon tablosunda da
   `| #68 | M1 …` satırları vardı. Satır + hex hash biçimine daraltıldı.
2. `47e79ef` düz araması tutuyordu — hash ilerleme tablosunda da geçiyor.
   Artık yalnız kendi PR satırında aranıyor.
3. SKIP sayısı için serbest `\b5\b` regex'i "5 PR" gibi ilgisiz sayılarla
   tutuyordu. `**5 SKIP koşulu**` biçimine bağlandı.

Ayrıca bu rapor yazılırken **iki gerçek hata** yakalandı ve düzeltildi:
"İki SKIP mesajı" denmişken script'te **5** koşul olduğu ve
`severityOf()` kusurunun main'de değil PR #54'te olduğu. İkisi de test
sayesinde değil, doğrudan ölçümle bulundu.

## Ölçüldü, kapatılmadı

Bu birimler sırasında bulunan ama kapsam dışı bırakılan borç — hepsi ölçüldü,
hiçbiri tahmin değil:

1. **27 test dosyası yerel hook'ta hiç koşmuyor.** Diskte 176 `test_*.py`,
   `check_unit_tests.list` 149 kayıt. Yerel geri bildirim eksikliği; CI'nın
   tam discover'ı onları koşuyor, yani güvenlik açığı değil.
2. **`ci_full_discover_drift_guard.py` yetim.** Tam olarak (1)'i kapatmak
   için yazılmış, docstring'i `verify.yml`'e bağlanmasını öneriyor — ama hiçbir
   yerde referansı yok. Çalıştırılınca `PASS` veriyor ama çıktısı bozuk:
   `kayıtlı batarya: GREEN (0/160 passed)` ve kesilmiş bir cümle; docstring'de
   de `α�ansı` mojibake'si var.
3. **5 SKIP koşulu var, runbook yalnız birini belgeliyor.** Önce "iki
   mesaj" sanıldı; bu raporun testi sayımı script'ten türetti ve **5**
   çıktı. SKIP sözleşmesi (exit 0 + kanıt dosyasının iki satırı) beş koşulda
   da geçerli:

   | Satır | Koşul |
   |---|---|
   | 52 | `docker CLI yok — smoke koşulamaz` |
   | 53 | `trivy yok — güvenlik gate'i eksik` |
   | 62 | `colima start başarısız — daemon sağlanamadı` |
   | 64 | `docker daemon erişilemiyor ve colima kurulu değil` |
   | 66 | `colima start sonrası daemon hâlâ erişilemiyor` |

   Runbook ve K-testleri yalnız 53'ü (`trivy yok`) türetiyor. 52 numaralı
   koşul **ilk** kontrol olduğu için, gerçek bir CI arızasında log'un ilk
   satırı dokümanda karşılığı olmayan bir mesaj olur. K9 testi artık koşul
   **sayısını** script'ten türetip raporla karşılaştırıyor.
4. ~~**`severityOf()` varsayılanı PR #54'te — main'de değil.**~~ **KAPANDI
   (2026-10-05, PR #82).** Önce main'de canlı bir borç sanıldı; ölçüm bunun
   tersini gösterdi. `trivy_sarif_pr_comment.js` **yalnız**
   `origin/land/migration-gates-2026-09-30` ve ayrı soydaki yerel `main`'de
   bulunuyor; `origin/main`'de hiç yok. PR #54'teki `severityOf()` satır
   21–27'de eksik severity'yi `sev || "HIGH"` ile HIGH sayıyor ve PR #54'te
   25 yanlış HIGH engeli üretti. Yani canlı bir kusur değil, **henüz düşmemiş
   kodun içinde** bir kusur: #54 merge edilmeden önce düzeltilmeli, yoksa
   hatayla birlikte main'e iner.

   **Canlı koşum öngörüyü doğruladı.** PR #82 (bu kodun gerçek PR koşumu,
   2026-10-05) `docker-security` işinde tam bu sınıfı üretti: annotate adımı
   `Trivy: 12 CRITICAL/HIGH bulgu` ile kırmızıya döndü — hepsi MEDIUM/LOW
   `pip` bulgusuydu. İki bağımsız kök neden ölçüldü:

   1. `trivy-action@v0.35.0` SARIF'te severity filtresini **kasten kaldırır**
      (`entrypoint.sh`: `format=sarif` → `unset TRIVY_SEVERITY`, "Building
      SARIF report with all severities"). Workflow `limit-severities-for-sarif:
      true` vermediği için SARIF 12 MEDIUM/LOW taşıdı.
   2. v0.69.3 SARIF şemasında `properties.severity` **yok**; seviye
      `message.text` gövdesinde `Severity: MEDIUM` satırı olarak yaşıyor.
      Script yalnız `properties.severity` baktığı için default-deny ile
      hepsini HIGH saydı.

   Düzeltme iki yüzeye birlikte indi: workflow'a `limit-severities-for-sarif:
   true`, script'e message-gövdesi fallback'i (properties önce). Regresyon iki
   battery senaryosuyla sabitlendi (v0.69.3 şeması: MEDIUM → temiz yorum,
   HIGH → setFailed) + `TestTrivySarifSeverityContract` (4 pin testi). Yerel
   kanıt: gerçek v0.69.3 SARIF'iyle script artık `✅ CRITICAL/HIGH bulgu yok`
   üretiyor, `setFailed` yok; battery 64/64 PASS.
5. **Yerel `main` ayrı soyda.** `cf838ed`, `origin/main`'den 157 commit ayrı ve
   hiçbiri remote'ta değil; PR #54 bu 153 commit'i land etmeye çalışıyor ve
   şu an `CONFLICTING`.