# HAKEM İNCELEME RAPORU — 2026-10-20 (ZİNCİR)

**İncelenen nesne:** teslim zincirinin geri kalanı — `verify_delivery.py` K katmanları
(K0-K21), `_calisma/CIKTI/check_unit_tests.list` test manifesti, `.github/workflows/verify.yml`
CI işleri + pre-commit kablolaması.

**İnceleme tarihi:** 2026-10-20
**Yöntem:** Depoda bulunan hakem raporu şablonu birebir kullanıldı:
`docs/HAKEM_INCELEME_RAPORU_2026-09-27.md` (§0 yöntem, §1 güçlü yanlar,
Critical/Important/Minor önceliklendirmesi, §5 bağımsız doğrulama, §6 kontrol
listesi, §7 hüküm). Şablonun P0/P1/P2 haritası korunur: P0 → Critical,
P1 → Important, P2 → Minor.

**Tutumluluk ilkesi:** Her madde ya ölçülmüş kanıta (`dosya:satır` + bu oturumda
yeniden üretilmiş çıktı) ya da "doğrulanamadı" etiketine bağlıdır. Tahmin
yazılmamıştır. Önceki raporun "31 CI işi / 174 test" sayıları bu oturumda
yeniden ölçülmüş ve bayat bulunmuştur (gerçek: **35 iş / 242 test**) — aşağıdaki
sınıflandırma yalnız bu oturumda ölçülen kanıta dayanır.

---

## 0. Çalışma planı ve yöntem

1. **Envanter:** K katman anahtarları (`verify_delivery.py:233-254` → K0-K21, 22
   katman) listelendi; test manifesti 242 girdi sayıldı; workflow'daki job
   id'leri çekildi (35).
2. **Bağımsız yeniden üretim:** Liste üyeliği disk+git'e karşı tarandı (242/242
   mevcut, tekrarsız); liste-dışı 33 test EXCLUDE kümesine karşı ölçüldü;
   `status_checks.py` bayraksız koşturuldu (15 required + 20 advisory);
   `parse_unit_test_failures.py` docstring'li/ docstring'siz iki sentetik logla
   koşturuldu (fail-open repro).
3. **Çapraz kontrol:** `--full` bayrak kümesi (`apply_full_flags`) ile K katman
   haritası karşılaştırıldı; CI verify job'unun gerçek komutu (`--full`,
   `verify.yml:376`) ve `set -o pipefail` (`:187`) okundu; `K1-K19` iş adı ile
   gerçek katman kümesi karşılaştırıldı; `CI_JOB_COVERAGE` anahtarları 35 job'a
   karşı ölçüldü.
4. **Uzman lensleri** (şablonun dört lensi, zincir denetime uyarlandı):
   - **L1 — Mimar/katman hakemi:** K0-K21 tanım → `--full` → CI job kapsama zinciri;
   - **L2 — Güvenlik ve bütünlük hakemi:** fail-closed/fail-open yönü (pipefail,
     vacuous-sınıflandırıcı, yorum-üretici regex'leri);
   - **L3 — Metodoloji ve yeniden üretilebilirlik denetçisi:** liste ↔ disk ↔ git
     üçlü tutarlılığı, EXCLUDE kural disiplini, sayaç tutarlılığı (19/21, 61/64);
   - **L4 — Editör:** katman adları, iş adları, doküman sayıları arası tutarlılık.

---

## 1. Genel değerlendirme — ölçülmüş güçlü yanlar

Bunlar bu oturumda yeniden ölçüldü; hepsi **doğrulandı**.

| #   | Güçlü yan                                              | Ölçüm                                                                                                                                                                                                                          |
| --- | ------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| 1   | Test manifesti disk+git ile birebir                    | 242/242 girdi diskte **ve** gitte mevcut; liste içi tekrar **0**                                                                                                                                                               |
| 2   | Liste-dışı 33 testin tamamı kural kapsamında           | `tracked − listed` 33 testin 33'ü `sync_check_unit_tests.py` EXCLUDE kümesinde; `EXCLUDE ∩ listed` = ∅ (çelişki yok)                                                                                                            |
| 3   | 35 job'un tamamı sınıflı, yetim yok                    | `status_checks.py` (bayraksız, çevrimdışı) → 15 required + 20 advisory = 35; `GATE_EXCLUDE` 20 id, tamamı workflow'da mevcut                                                                                                   |
| 4   | Kapsam kaydında hayalet yok                            | `CI_JOB_COVERAGE` 8 anahtarın 8'i mevcut job (`a11y-gate`, `ci-simulate`, `daemon-http`, `dashboard-smoke`, `plist-check`, `pptx-export`, `preview-reload-smoke`, `verify`)                                                    |
| 5   | `--full` → CI verify hattı kapalı                      | `apply_full_flags` K0-K9, K11, K13-K18, K21'i açıyor; CI `verify` job'u `--full` koşuyor (`verify.yml:376`); K10/K12 ayrı job'larda (`:1671`, `:2586`)                                                                            |
| 6   | K6 sayaçları tutarlı                                   | tex `References` `\item` = **64** = config `expected_refs`; MANIFEST 21 satır = config `expected_manifest` 21 (config auto-load, `verify_delivery.py:5553-5556`)                                                                 |
| 7   | Pre-commit hook'u vacuous-korumalı                     | `check_unit_tests_hook.sh:187-200` her dosyanın log'unu saklayıp `check_zero_check_fail_open.py` ile sınıflıyor; 0 gerçek test = FAIL (exit kodu korunuyor, yalnızca sınıflandırıcı stdout'u atılıyor)                            |
| 8   | klayers tek-kayıt yolu izlenebilir                     | `run_summary_klayers` workflow'da **0** kez geçiyor; tek kablolama `consolidate_summary.py:54` — `status()` değişikliğinin exit etkisini izlemek için tek yer yeterli                                                            |

Bu sekiz madde, zincirin "kapsam" vaadini kanıtlanmış kılar. Aşağıdaki bulgular
bu tabanı çürütmez; **kapsam beyanı ile icra arasındaki** boşlukları ölçer.

---

## 2. Critical

**Bu oturumda Critical bulgu YOKTUR.** En yakın aday (I-3'teki PR yorum
fail-open'ı) Critical'e yükseltilmedi: `verify.yml:187`'de `set -o pipefail`
ölçüldü — unittest FAIL'inde job'un kendisi kırmızı kalır, merge engeli çalışır.
Yalan söyleyen yalnızca insan-yüzü yorumdur, kapı değil. Benzer şekilde I-2'deki
K19/K20 icra boşluğu, iki katmanın da bloke edici olmaması (opt-in bayraklar)
nedeniyle Critical değildir.

---

## 3. Important

### I-1 — K4'ün "19/19" sayaçları üç yerde bayat; configsuz koşum yanlış-P0 üretir

**Tespit.** MANIFEST 21 satırdır (bu oturumda 21/21 ölçüldü), config
`expected_manifest: 21` (`verify_delivery.config.json`, commit'li) ile uyumludur.
Ama kodda üç bayat iz var:

- `verify_delivery.py:70` — modül dokümanı: `K4 Manifest MANIFEST.txt 19/19`;
- `verify_delivery.py:237` — katman adı: `"K4": "Manifest 19/19"`;
- `verify_delivery.py:173` — `EXPECTED_MANIFEST = 19` (varsayılan);
- ayrıca `verify_delivery.py:5221` yorumu `K4: manifest 18/18` diyor (üçüncü bir sayı).

**Ölçülen etki.** Config auto-load olduğu sürece (`:5553-5556`, kardeş dizindeki
`verify_delivery.config.json`) K4 geçer. Ama config dosyası yoksa (silinmiş /
kopyalanmış ağaçta koşum) `ok=21 != 19` → **P0** `"manifest 21/19"` yanlış-pozitifi.
Fail-closed tasarımda yanlış-pozitif, yanlış-negatif kadar olmasa da kapı
güvenini zedeler: hakem "kapı kendi sayacını bilmiyor" okur.

**Düzeltme.** Üç etiket de `MANIFEST_FILES` uzunluğundan türetilsin (tek kaynak;
`repack_delivery.py` zaten öyle üretiyor) veya en azından 21'e sabitlensin;
configsuz yolun P0'ı ancak `parse_manifest` sayacıyla `MANIFEST_FILES`
uzunluğu çelişirse üretilsin.

### I-2 — "K1-K19" iş adı bayat; K19 ve K20 hiçbir icra yolunda koşmuyor

**Tespit.** `verify.yml:58` ve `:354`: `Delivery verification — K1-K19`. Gerçek:

| Katman | `--full`'da | CI job'da | Pre-commit hook'ta |
| ------ | ----------- | --------- | ------------------ |
| K0     | ✓ (çekirdek) | ✓ (`--full` içinde) | ✓ |
| K1-K9, K11, K13-K18, K21 | ✓ | ✓ (`--full` içinde) | K21 ayrıca `:809`'da |
| K10    | — (PATH ister) | ✓ (`reproducibility:1671` `--verify-manifest`) | — |
| K12    | — (macOS) | ✓ (`plist-check:2586`) | — |
| **K19** (`--coq-proof`) | — | **yok** (repo genelinde `coq` 0 eşleşme) | **yok** |
| **K20** (`--check-launchd`) | — | **yok** | **yok** |

`_calisma/CIKTI/run_full_with_coq.sh` mevcut ama hiçbir dosyadan başvurulmuyor
(kablosuz). K19 birim testleri bataryada koşuyor (`test_check_coq_axioms.py` vb.
242 listede) — yani **mantık testli, katman icrasız**.

**Etki.** "Kayıt var, koşum yok" ailesi (önceki rapordaki phantom-kayıt
akrabası): katman haritası 22 katman vaat eder, CI 20'sini icra eder. K19/K20
opt-in olduğu için merge engeli yoktur, ama zincir raporu "K0-K21 doğrulandı"
okunur.

**Düzeltme.** Ya iş adı gerçek kümeyi yazsın (`K0-K18 + K21`, + K10/K12 ayrı
job notu), ya K19/K20 uygun job'a bağlansın (K20 macOS-advisory, K19 coq
kurulu job), ya da katman haritası ikisini "manuel/opt-in" diye etiketlesin.

### I-3 — PR başarısızlık yorumu docstring'li testte fail-open (repro'lu)

**Tespit.** `verify.yml:188` discover `-v` çıktısını `unit_tests.log`'a yazar;
yorum adımı (`:217`, `github-script`) `_calisma/CIKTI/github_scripts/unit_test_failure_comment.js:17`
ile ayrıştırır:

```js
/^(\S+) \(\S+\) \.\.\. (FAIL|ERROR)$/
```

Aynı desen `parse_unit_test_failures.py:28`'de de var. Python 3.9+'da
docstring'li testte `-v` işaretçisi iki satıra bölünür (`test_x (mod.Cls)` /
`docstring… ... FAIL`) ve tek-satır regex eşleşemez.

**Ölçülen kanıt (bu oturumda).**

```
$ printf 'test_x (mod.Cls)\ndocstring first line. ... FAIL\nFAIL: test_x ...' > /tmp/doctest.log
$ python3 _calisma/CIKTI/parse_unit_test_failures.py /tmp/doctest.log
✅ Tüm testler yeşil (4 satır log)    exit=0     ← FAIL varken yeşil
$ # kontrol (docstring'siz aynı FAIL):
"🧪 Unit Test Düşenler — 1 düşen test"   exit=1  ← doğru yakalar
```

JS aynı regex'i taşıdığından desen-özdeş davranış gösterir (py tarafı
çalıştırılarak, js tarafı desen-özdeşliğiyle kanıtlandı).

**Etki (sınırlı).** Job'un kendisi `set -o pipefail` (`:187`) sayesinde kırmızı
kalır — merge engeli çalışır (bu yüzden Critical değil). Ama PR'a düşen yorum
"düşen yok" der; hakem yorumu okuyup log'u açmazsa tabloyu yanlış okur.

**Düzeltme.** İki satırı birleştiren ön-işleme (önceki rapordaki öneri: `FAILED
(failures=N)` özetine dayan veya iki satırı reassemble et) her iki ayrıştırıcıya
da uygulansın; kırmızıya düşüren mutant test eklensin.

### I-4 — Durum panosu katman anahtarlarını hardcode'luyor; K15/K19/K21 başlığa ulaşmaz

**Tespit.** `preview_server.py:483`: `core = ["K1",...,"K7"]`;
`:505-506`: `ext = ["K8","K9","K10","K11","K12","K13","K14","K16","K17","K18","K20"]`
— **K15, K19, K21 yok**. Yorum satırları da bayat: `:264` "K0-K17 per-katman",
`:482` "Pre-commit: K1-K7". K0 yalnızca `p0/p1` sayaçları üzerinden başlığa
yansır (kısmi mitigasyon, ölçüldü `:492-496`).

**Etki.** Yeni katman anahtarı eklendiğinde başlık hükmü (beş ikon) onu görmez;
K21 SDE guard'ı FAIL verse bile rozet yeşil kalabilir. Rozet, PR yorumundaki
gibi insan-yüzü hükümdür.

**Düzeltme.** Anahtar listeleri katman haritasından (`verify_delivery.py:233-254`)
türetilsin veya yeni anahtar eklendiğinde kırmızıya düşen statik test eklensin
(`preview_test_env.py` desenindeki gibi).

### I-5 — Öncelik kovalamacası kapalı küme: `in ("P0", "P1")`

**Tespit.** `verify_delivery.py:303,315`: `f.get("priority") in ("P0", "P1")`.
Öncelik kümesi kapalıdır (P0/P1/INFO); gelecekte eklenecek bir engelleyici seviye
("P2" veya küçük harf yazımı) sessizce düşer: kovalanmaz, raporlanmaz, FAIL üretmez.

**Etki.** Bugün zararsız (üç değer de biliniyor), ama "bilinmeyeni düşür"
varsayılan yöndür: fail-closed zincirde bilinmeyen bulgu **görünür** olmalıydı.

**Düzeltme.** Bilinmeyen `priority` INFO'ya gömülmek yerine açık bir
"P-UNKNOWN" bulgusu üretsin (fail-closed) veya kapalılık bir testle pin'lensin.

---

## 4. Minor

### M-1 — EXCLUDE'da var olmayan dosya

`sync_check_unit_tests.py` EXCLUDE kümesi `test_repro_manifest_topology.py`
içeriyor; dosya gitte **yok** (ölçüldü: `exc − tracked = [test_repro_manifest_topology.py]`).
Zararsız (var olmayanı dışlamak etkisizdir) ama kural kümesinin ölü girdi
taşıdığını gösterir; silinmeli.

### M-2 — Doküman sayıları üç ayrı yerde üç ayrı değer

Ölçülen gerçek: **35 job / 71 hook-id** (`verify.yml` job regex sayımı;
`.pre-commit-config.yaml` `- id:` sayımı). Yazılanlar: önceki rapor §5 D14
"31 CI işi · 57 hook"; `status_checks.py:79` yorumu "31 job − 16 hariç";
`AGENTS.md` "63 hooks". Üçü de bayat. Sayılar metin içinde sabitlenmek yerine
üreten komutla (bu rapordaki regex'ler) pin'lenmeli.

### M-3 — `AGENTS.md`'de üç bayat zincir iddiası

Ölçüldü: (a) `check_lean_statements.check_twin()` — dosyada `twin` 0 eşleşme,
fonksiyon yok (davranış iddiası test edilemedi, ölü referans); (b)
`CI_JOB_COVERAGE["dashboard-smoke"]` hayaleti — job artık mevcut
(`verify.yml:2982`), kayıt tutarlı (§1 madde 4); (c) "test_launchd_minimal_path.py
hiçbir branch'te commit'li değil" — dosya commit'li (`e6572d1`). Üçü de
doküman-drift'tir, kod bulgusu değildir.

### M-4 — "Referans" adında iki farklı sayaç: 64 vs 61

K6 `References {refs}` = tex `\item` sayısı (**64**, ölçüldü); `--check-references`
çevrimiçi denetimi **61/61** (önceki rapor D9). İkisi de doğru, kümeleri farklı
(çevrimiçi alt küme). Aynı ad, hakemde "64 mü 61 mi?" sorusu üretir. K6
etiketine `(tex \item)` açıklaması tek satırla eklenmeli.

### M-5 — Modül dokümanında bayat `--full` tarifi

`verify_delivery.py:53`: `--full` = "K1-K14 + referans + Z3 + Lean". Gerçek
(`apply_full_flags`): K0-K9, K11, K13-K18, K21 + referans + Z3 + Lean (+lineage,
+history). Doküman iki katman neslini geriden takip ediyor.

---

## 5. Bağımsız doğrulama çıktıları (bu inceleme için hesaplandı)

| #   | Denetim                | Komut / kaynak                                                                 | Sonuç                                                                                        |
| --- | ---------------------- | ------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------- |
| V1  | Katman envanteri       | `grep` katman haritası `verify_delivery.py:233-254`                            | **K0-K21, 22 katman** (istekteki "K0-K17" bayat)                                              |
| V2  | Test manifesti         | 242 girdi ↔ disk + git taraması                                                | **242/242 mevcut**, tekrar 0                                                                 |
| V3  | Liste-dışı kapsamı     | `tracked − listed` ↔ EXCLUDE                                                   | 33 testin 33'ü kural kapsamında; çelişki 0                                                   |
| V4  | Job sınıflandırması    | `python3 status_checks.py` (bayraksız, çevrimdışı)                             | **15 required + 20 advisory = 35**, yetim 0                                                  |
| V5  | `--full` kapsamı       | `apply_full_flags` ↔ katman haritası                                           | K0-K9, K11, K13-K18, K21 ✓; K10/K12 ayrı job; **K19/K20 icrasız**                             |
| V6  | K6 sayaçları           | tex `\item` sayımı + config                                                    | **64 = 64**; MANIFEST 21 = 21                                                                |
| V7  | Yorum fail-open repro  | sentetik `-v` log'u → `parse_unit_test_failures.py`                            | docstring'li FAIL → **"yeşil", exit 0** (kontrol: docstring'siz yakalanıyor)                  |
| V8  | Job fail-closed'i      | `verify.yml:187`                                                               | `set -o pipefail` **mevcut** — job exit'i korunuyor                                          |
| V9  | Pano hardcode          | `preview_server.py:483,505-506`                                                | core K1-K7; ext'te **K15/K19/K21 yok**                                                       |
| V10 | Kovalama kapalılığı    | `verify_delivery.py:303,315`                                                   | `in ("P0","P1")` — tam eşleşme                                                               |
| V11 | Sayaç gerçekleri       | job-id regex + hook-id sayımı                                                  | **35 job / 71 hook** ("31/57/63" yazımları bayat)                                            |
| V12 | Ölü kural girdisi      | `exc − tracked`                                                                | `test_repro_manifest_topology.py` gitte **yok**                                              |

**Doğrulanamayan / kapsam dışı bırakılanlar.** (a) 242 testin _içerik_ doğruluğu
— üyelik ve kablolama ölçüldü, test mantığı denetlenmedi. (b) 35 job'un
_canlı_ koşum sonucu — tanım ve sınıflandırma ölçüldü, CI koşusu
çalıştırılmadı. (c) JS yorumlayıcının çalışır repro'su — desen py ile özdeş
olduğu için davranış aynılığı çıkarımsaldır, koşusal değildir. Bu üçü
"başarılı" değil, **kapsam dışı** olarak işaretlenir.

---

## 6. Kontrol listesi

- [ ] **I-1** `verify_delivery.py:70,237` "19/19" → tek-kaynak sayaç; `:173`
  varsayılanı 21; `:5221` "18/18" yorumu düzeltmesi
- [ ] **I-2** `verify.yml:58,354` iş adı gerçek küme; K19/K20 ya job'a bağlansın
  ya "manuel/opt-in" etiketlensin (`run_full_with_coq.sh` kablosu dahil)
- [ ] **I-3** İki satır-birleştirme düzeltmesi (`parse_unit_test_failures.py:28`,
  `github_scripts/unit_test_failure_comment.js:17`) + kırmızı-mutant test
- [ ] **I-4** `preview_server.py:483,505-506` anahtar listeleri katman
  haritasından türesin (`:264` yorumu dahil)
- [ ] **I-5** `verify_delivery.py:303,315` bilinmeyen öncelik → açık bulgu
- [ ] **M-1** EXCLUDE'dan `test_repro_manifest_topology.py` satırı silinsin
- [ ] **M-2** Sayı sabitleri üreten komutla pin'lensin (31/57/63 yazımları)
- [ ] **M-3** `AGENTS.md` üç bayat iddia (twin, phantom, launchd-testi) güncellensin
- [ ] **M-4** K6 etiketine `(tex \item)` açıklaması
- [ ] **M-5** `verify_delivery.py:53` `--full` tarifi güncellensin

---

## 7. Hüküm

Zincir, bu incelemenin sekiz ölçülmüş maddesinde (**§1**) kendini kanıtladı:
242 testin tamamı disk+git'te ve kural-dışı fire yok; 35 job'un tamamı
required/advisory olarak sınıflı; `--full` → CI hattı kapalı; sayaçlar (64/21)
config ile tutarlı; pre-commit hook'u vacuous-korumalı. Çekirdek (K0-K7 +
batarya + merge engeli) ayaktadır ve **yayınlanabilirlik açısından engel
yoktur.**

Critical bulgu yoktur. Important maddelerin beşi de aynı ailedendir:
**icra edilen zincir ile zinciri anlatan etiketler arasındaki kayma**
(sayaçlar, iş adları, pano anahtarları, yorum regex'i, öncelik kümesi).
Hiçbiri kapıyı açmıyor — `pipefail`, config auto-load ve EXCLUDE disiplini
bunu sağlıyor — ama beşi de hakemin "ne koştu, ne raporlandı" sorusunu
bulandırıyor. En somutu I-3'tür (çalışan repro'su var); en yapısal olanı
I-2'dir (iki katmanın icra yolu yok).

Minor'ler doküman hijyenidir; M-3 ayrıca `AGENTS.md`'nin zincir bölümünün
yeniden ölçülmesi gerektiğini gösterir.

**Tek cümlelik özet:** Zincir koşuyor ve kapalı — eksik olan koşum değil,
**koşumun adının ve sayacının güncel sözleşmesidir.**
