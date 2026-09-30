# HAKEM İNCELEME RAPORU — 2026-09-27

**İncelenen nesne:** `_calisma/V5_ICERIK/TESLIM_V5_FINAL_2026-08-17/stoic_hume_package/Stoic_Hume_Formal_Section_2026-08-17/`
(22 dosyalık teslim paketi) + paketi doğrulayan repo içi kapı zinciri.

**İnceleme tarihi:** 2026-09-27
**Yöntem:** Depoda zaten bulunan hakem raporu şablonu birebir kullanıldı:
`.../Stoic_Hume_Formal_Section_2026-08-17/internal_review_report.md` (388 satır).
Şablonun bölüm mimarisi, önceliklendirme haritası ve kontrol listesi değiştirilmedi:

- Şablon §0 yöntemi → burada §0
- Şablon §1 "güçlü yanlar" → burada §1
- Şablon **P0 = yayınlanabilirlik için zorunlu** → burada **Critical**
- Şablon **P1 = güçlü iyileştirme** → burada **Important**
- Şablon **P2 = sunum ve editör düzeyi** → burada **Minor**
- Şablon §5 bağımsız doğrulama çıktıları → burada §5
- Şablon §6 kontrol listesi → burada §6

**Tutumluluk ilkesi:** Her madde ya ölçülmüş kanıta (`dosya:satır` + bu oturumda
yeniden üretilmiş çıktı) ya da "doğrulanamadı" etiketine bağlıdır. Tahmin yazılmamıştır.
Bu rapor, `findings.md`/`progress.md` içinde geçen **"2 Critical"** ifadesine dayanmaz —
o ifade repoda doğrulanamamıştır; aşağıdaki sınıflandırma yalnız bu oturumda ölçülen
kanıta dayanır.

---

## 0. Çalışma planı ve yöntem

1. **Envanter:** Paketteki 22 dosyanın tamamı listelendi; `MANIFEST.txt` ile disk
   karşılaştırıldı.
2. **Bağımsız yeniden üretim:** Paket içindeki **4 betiğin 4'ü de** çalıştırıldı ve
   donmuş çıktılarıyla bayt bayt karşılaştırıldı. Paket dışındaki 3 doğrulama
   betiği de çalıştırıldı.
3. **Çapraz kontrol:** `qpdf` non-determinizm hükmü, `z3` UNSAT iddiası, 61/61
   referans denetimi ve "yalnız stdlib" beyanı bağımsız olarak sınandı.
4. **Uzman lensleri** (şablonun dört lensi, mühendislik teslimine uyarlandı):
   - **L1 — Mimar/layer hakemi:** teslim paketinin iç bütünlüğü, kanıt zinciri;
   - **L2 — Güvenlik ve bütünlük hakemi:** hash/sidecar sözleşmesi, fail-closed
     kapılar, mutlak yol yasağı;
   - **L3 — Metodoloji ve yeniden üretilebilirlik denetçisi:** donmuş çıktı →
     canlı çıktı eşleşmesi, çalıştırma tarifinin var olup olmaması;
   - **L4 — Editör:** rapor ↔ metin ↔ manifest arası ad/etiket tutarlılığı.

---

## 1. Genel değerlendirme — ölçülmüş güçlü yanlar

Bunlar bu oturumda yeniden ölçüldü; hepsi **doğrulandı**.

| #   | Güçlü yan                                               | Ölçüm                                                                                                                                                                                              |
| --- | ------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | Üç donmuş kanıt çıktısı bayt-aynı yeniden üretiliyor    | `core_formal_model_check.py` → `test_output.txt` **IDENTIK**; `gate15_check.py` → `gate15_output.txt` **IDENTIK**; `encoding_sensitivity_check.py` → `encoding_sensitivity_output.txt` **IDENTIK** |
| 2   | Dördüncü donmuş kayıt da bayt-stabil                    | `qpdf_determinism_experiment.py` (varsayılan mod) → `qpdf_determinism_output.txt` **IDENTIK**                                                                                                      |
| 3   | MANIFEST bütünlüğü                                      | 21/21 dosyanın **MD5 + bayt sayısı** tutuyor; manifest dışı **hiçbir dosya yok** (kapsam tam, fazlalık yok)                                                                                        |
| 4   | Non-determinizm hükmü doğru ve araç sürümünden bağımsız | qpdf 12.4.0, aynı girdi (raw `74b2cdbd…` doğrulandı) → `--rerun 5` = **5/5 farklı stripped hash**                                                                                                  |
| 5   | Sembolik kanıt iddiası doğru                            | `symbolic_proof_z3.py` (pinned venv, z3 5.1.0) → **P4-d UNSAT, P4-e UNSAT, P5 SAT** — "TÜMÜ PASS"                                                                                                  |
| 6   | "Yalnız Python stdlib" beyanı doğru                     | Paket betiklerinin import kümesi: `argparse, hashlib, os, shutil, subprocess, sys, tempfile, itertools.product` — üçüncü taraf **yok**                                                             |
| 7   | Referans kanıtı bugün de canlı                          | `verify_delivery.py --check-references` → **61/61 PASS**, UNVERIFIED=0, MISMATCH=0, exit 0                                                                                                         |
| 8   | Fail-closed kapılar ayakta                              | `check_security_posture.sh` → 7/7 PASS; `check_review_freshness.py` → `review=7f56ac189204 sidecar=OK`; `check_absolute_paths.sh` → 588 dosya taranmış, **PASS**                                   |
| 9   | Dürüstlük disiplini                                     | Doğrulanamayan stripped hash _silinmemiş, gizlenmemiş_ — V5l "KNOWN LIMITATION" notu ve `qpdf_determinism_output.txt` içindeki sürüm izleme bloğu olayı açıkça, sürüm sürüm izliyor                |

Bu dokuz madde, tek başına, teslimin "yeniden üretilebilirlik" vaadini
kanıtlanmış kılar. Aşağıdaki bulgular bu tabanı çürütmez; **vaadin kapsam
tanımını** düzeltir.

---

## 2. Critical

### C-1 — Yeniden üretilebilirlik sözleşmesi, iddiaları doğrulamak için gereken üç aracı kapsam dışı bırakıyor

**Tespit.** `requirements.txt:6-8` şunu beyan ediyor:

> "This package depends ONLY on the Python 3 standard library. No third-party
> package is required."

Bu beyan **Python bağlamında doğru** (§1 madde 6). Ama paketin gerçekten
yeniden üretilmesi için gereken üç şey beyanın dışında kalıyor:

| Gereken araç                        | Nerede geçiyor                                                                                                                               | Beyanda var mı?                                                           |
| ----------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------- |
| `qpdf` (harici ikili)               | `qpdf_determinism_experiment.py:36` — _"Requires: qpdf only for --rerun mode"_; yoksa `exit 1` + "HATA: qpdf bulunamadı"                     | **Hayır** — `requirements.txt` bir Python paketi olmayan ikiliyi kapsamaz |
| `z3-solver` (pinned venv)           | `MANIFEST.txt:22-24` — _"Z3-verified (symbolic_proof_z3.py P4-d/P4-e UNSAT)"_; betik depoda `_calisma/CIKTI/`, z3 `_calisma/.venv_z3` içinde | **Hayır** — betik pakette yok, venv yolu hiç yazılmamış                   |
| Canlı ağ (CrossRef/SEP/OpenLibrary) | `verify_delivery.py`; bugün 61/61 PASS                                                                                                       | **Hayır** — çevrimdışı tekrarlanamaz, zaman-bağımlı                       |

**Ölçülen kanıt (bu oturumda).**

```
$ python3 _calisma/CIKTI/symbolic_proof_z3.py
ModuleNotFoundError: No module named 'z3'          exit=1     ← sistem python
$ ./_calisma/.venv_z3/bin/python _calisma/CIKTI/symbolic_proof_z3.py
[PASS] P4-d ... alınan=UNSAT   [PASS] P4-e ... alınan=UNSAT   TÜMÜ PASS   exit=0
$ python3 _calisma/CIKTI/verify_delivery.py --check-references
Çevrimiçi referans: 61/61 doğrulandı (PASS=61, UNVERIFIED=0, MISMATCH=0)   exit=0
```

**Etki.** Hakem paketi açıp `MANIFEST.txt`'in en güçlü iki iddiasını
(sembolik UNSAT kanıtı, 61/61 referans denetimi) yeniden üretmek istediğinde
**ikisini de üretemez**: biri için `z3` yok, diğeri için ağ yok. Üçüncüsü
(`qpdf`) kuruluysa çalışır ama bu, beyanın kendisinden çıkarılmaz. "No
third-party package is required" ibaresi, hakem için "bağımlılık yok, hemen
çalışır" okunur — oysa gerçekte üç katmanlı bir bağımlılık vardır ve
**hiçbiri pakette yazılı değildir**. Bu, teslimin tek değer önerisi olan
denetlenebilirliğin kendisini zedeleyen tek bulgudur.

**Önerilen düzeltme (tek dosya, üç satır).** `requirements.txt`'in "No third-party
package is required" cümlesi şu hâle getirilsin:

```
# Python bağımlılığı: yok (aşağıdaki import listesi doğrulandı).
# HARİCİ ARAÇLAR (pip ile gelmez, requirements.txt kapsamaz):
#   qpdf  >= 11   — yalnız qpdf_determinism_experiment.py --rerun modu.
#                    --rerun olmadan paket stdlib-only'dir ve donmuş kayıt
#                    byte-stabil çıkar.
#   z3-solver 5.1 — PAKET DIŞI doğrulama katmanı (_calisma/.venv_z3).
#                    symbolic_proof_z3.py pakete dahil DEĞİLDİR.
# ZAMAN-BAĞIMLI: verify_delivery.py --check-references canlı ağ kullanır
#   (CrossRef/SEP/OpenLibrary); çevrimdışı tekrarlanamaz, sonuç tarihe bağlıdır.
```

Ayrıca `MANIFEST.txt:22-24` ve `qpdf_determinism_output.txt`'ın "okuma"
satırına, bu iki iddianın **paket dışı doğrulandığı** notu düşülmeli.

---

## 3. Important

### I-1 — Hakem raporunun kapsam satırı pakette var olmayan üç dosyayı gösteriyor

`internal_review_report.md:5`:

> **Kapsam:** `core_section.tex`, `CORE_L0_FORMAL_SPEC.md`,
> `CORE_FORMAL_MODEL_CHECK_REPORT.md`, `core_formal_model_check.py`,
> `ingiliz_empirizmi_v2.pdf` (ana makale) — beş parça bütün olarak ele alındı.

| Raporda adı geçen                   | Paketteki karşılığı        | Durum                                                                                                                                                                        |
| ----------------------------------- | -------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `CORE_L0_FORMAL_SPEC.md`            | `L0_Lplus_spec.md`         | **Yok** — üstelik repo genelinde de yok (`find` → 0 sonuç). Adı değiştiğinin kanıtı dosyanın kendi içinde: `L0_Lplus_spec.md:56` _"The original `CORE_L0_FORMAL_SPEC.md` …"_ |
| `CORE_FORMAL_MODEL_CHECK_REPORT.md` | `model_check_report.md`    | **Yok** — repo genelinde de yok                                                                                                                                              |
| `ingiliz_empirizmi_v2.pdf`          | `ingiliz_empirizmi_v3.pdf` | **Yok** — v2'nin v3'le değiştirildiği `ingiliz_empirizmi_v3.tex:8`'de yazılı                                                                                                 |

**Etki.** Hakem, incelemenin kapsamını doğrulamak için raporun `:5` satırını
takip eder ve **beş parçadan üçünü bulamaz**. Raporda iki kez geçen
`CORE_L0_FORMAL_SPEC.md` atfı (`:246` "Spec dosyasında `Bel` tanımı düzeltildi")
da aynı ölü atıftır; yani P1-2 maddesinin _uygulandığı dosya_ belirsizdir.

**Düzeltme.** `:5`'teki kapsam satırı güncel adlarla değiştirilsin; `:246`'daki
`CORE_L0_FORMAL_SPEC.md` atfı `L0_Lplus_spec.md` olsun. (Raporda ayrıca bir
"ad değişikliği notu" tek paragraf olarak eklenebilir.)

### I-2 — Kontrol listesi ile teslim metni arasında çift yönlü kayma

`internal_review_report.md` §6, P0/P1/P2 maddelerini onay kutusuyla listeler.
Teslim metniyle karşılaştırıldığında iki kayma var:

| Rapor maddesi                                                                                               | Rapordaki durum                      | Teslimde ölçülen durum                                                                                                                                                                                                                                                                          |
| ----------------------------------------------------------------------------------------------------------- | ------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **P0-3** — "Definition (determination)" kutusu eklensin; _"(G) atomunun serbest değişken statüsü netleşti"_ | Kontrol listesinde **zorunlu, açık** | `core_section.tex` içinde `Definition (determination)` **yok** (0 eşleşme). `determines` `:494`, `direction of determination` `:663` — **tanımsız kullanılıyor**. Muadil tanım başka bir yolla konmuş: `:560` _Definition (Explicit definability)_, `:566` _Definition (Implicit definability)_ |
| **P2-6** — "hyperintensiyalite ile reifikasyonun barıştırılması bu cümle metinde açıkça yazılmalıdır"       | Kontrol listesinde **açık**          | **Kapanmış**: `core_section.tex:664-666` — _"grounding is hyperintensional, so the failure of $L_0$ to fix the extension of $G$ is not specific to FOL's extensionality; it persists for modal extensions as well"_                                                                             |

**Değerlendirme.** P0-3'ün _maddesi_ (çekirdek kavramın tanımsız bırakılması)
uygulamada **çözülmüş** — hatta raporun kendi §7.2-1'i (harici inceleme)
tarafından daha kesin bir çerçeve önerildiği için. Ancak bu **bilinçli bir
seçim olarak kaydedilmemiş**: rapor okuyan bir hakem, §6'ya bakıp P0-3'ü açık
sanır ve metinde de gerçekten `determine` tanımı bulamayınca **P0-3'ün hâlâ
açık olduğu** sonucuna varır. Ters yönde, P2-6 kapanmış olmasına rağmen rapor
onu hâlâ açık sayar.

**Düzeltme.** Rapor §6'ya iki durum satırı eklensin:

```
- [~] P0-3: "determination" kutusu YERINE §2.x Def (Explicit/Implicit
    definability) kondu — harici inceleme önerisi (§7.2-1) kabul edildi.
    Metinde "determine" kelimesi bu iki tanımın kapsamıyla okunur.
- [x] P2-6: KAPANDI — core_section.tex:664-666 hyperintensiyalite/reifikasyon
    mutabakatı metinde.
```

Ayrıca `:494` ve `:663`'teki "determines/determination" kullanımlarına
tek satırlık bir atf (`cf. Def. 2.7--2.8`) eklenmesi, P0-3'ün özünü
(kavramın adı değil, bağlantısının kurulması) kapatır.

### I-3 — Sidecar'ın ilk satırı yapısal olarak doğrulanamaz bir hash olarak görünüyor

`ingiliz_empirizmi_v3.pdf.metadata.sha256` iki satır taşıyor:

```
50263bcf…  ingiliz_empirizmi_v3.pdf.metadata     ← metadata-stripped
# raw: 74b2cdbd…  ingiliz_empirizmi_v3.pdf        ← ham dosya
```

Bu oturumdaki ölçüm:

- **raw satırı doğru:** `shasum -a 256` → `74b2cdbdb18fafbf…` **birebir** ✓
- **stripped satırı doğrulanamaz:** `qpdf --remove-metadata` **5/5 farklı** hash
  üretiyor (bugün: `e572e011, 9ecbc8c8, 3f432d75, 492b074d, f6e01b48`);
  kayıttaki `50263bcf…` bunların hiçbiri değil ve **hiçbir zaman** olamaz.

**Kapı ayakta (güçlü yan).** `check_review_freshness.py:141-143` dokümanı
kendisi "sidecar'daki `# raw:` satırı raw hash'i taşır — o tercih edilir" diyor
ve `:169` sırasıyla aday sidecar'ları en spesifikten genele tarayıp raw satırını
arıyor. Yani kapı yanlış satıra bakmıyor ve fail-closed.

**Etki.** Kapı sağlam olsa da sidecar dosyasının ilk satırı, bir hakem
gözünde "doğrulanabilir bütünlük kanıtı" gibi görünür. Hakem `qpdf` kurup
karşılaştırdığında **uyumsuzluk** bulur ve bunu zehirlenme/elle müdahale
sanabilir. Olay tasarım gereği non-deterministik ve `qpdf_determinism_output.txt`
bunu açıkça belgeliyor — ama **belge sidecar'ın değil, ayrı bir dosyanın
içinde**; sidecar'ın kendisi bu uyarıyı taşımıyor.

**Düzeltme.** Sidecar'a üçüncüncü bir satır eklensin (repack'in
`write_sidecar` yolunda, `_calisma/repack_delivery.py:185`):

```
# NOT: yukarıdaki stripped hash qpdf sürümünden ve koşudan koşuya DEĞİŞİR
# (non-deterministic; kanıt: qpdf_determinism_output.txt). Yalnızca
# "# raw:" satırı yeniden üretilebilir — bütünlük kapıları onu okur.
```

### I-4 — MANIFEST'in "Generated" başlığı yeniden üretimde güncellenmiyor

`MANIFEST.txt:2` → `# Generated: 2026-08-17 (added revised manuscript …)`.
Ama dosya 2026-09-26'da yeniden üretilmiş: içindeki `VERSION_TRACKING`
bloğu 2026-09-26 ölçümünü taşıyor (`qpdf 12.4.0 → 5/5 farklı`), dosyanın
mtime'ı da 2026-09-26 20:06. `repack_delivery.py:112-114` başlığı sabit
`2026-08-17` olarak üretiyor.

**Etki.** Hakem "bu nesne ne zaman üretildi, ne zaman bayatladı" sorusunu
başlıktan yanıtlar ve **yanlış** yanıtlar. Klasör adı da `2026-08-17` olduğu
için bu, "dokunulmamış teslim" izlenimini güçlendiriyor — oysa içerik
2026-09-26'da güncellenmiş.

**Düzeltme.** Başlık ya `SOURCE_DATE_EPOCH`'a ya da içeriğin en yeni
VERSION_TRACKING satırına bağlansın. `qpdf_determinism_output.txt` bunu
zaten doğru çözüyor: _"Yeni sürüm eklerken … VERSION_TRACKING satırına yaz."_
Aynı disiplin MANIFEST başlığına da uygulanmalı.

---

## 4. Minor

### M-1 — `repack_delivery.py:75-76` kapatılmamış `open()`

```python
core_lines = sum(1 for _ in open(os.path.join(PKG, "core_section.tex"), encoding="utf-8", errors="ignore"))
spec_lines = sum(1 for _ in open(os.path.join(PKG, "L0_Lplus_spec.md"), encoding="utf-8", errors="ignore"))
```

`with` yok. CPython'da refcount sayesinde üretici ifadesi tüketilir tüketilmez
dosya kapanır, dolayısıyla üretimde sorun yok; ancak `-W error::ResourceWarning`
altında kırılır ve PyPy gibi refcount'siz uygulamalarda kapanma GC'ye kalır.
İki satır `with open(...) as f: … ` hâline getirilmeli.

### M-2 — Donmuş kayıttaki sürüm-izleme hash'leri "bugünkü" izlenimi veriyor

`qpdf_determinism_output.txt` "2026-09-26 qpdf 12.4.0 → `c086cdab 4fe4275b
22898321 4efa9262 77a95c44`" yazıyor. Bugün aynı komut beş **başka** hash
veriyor. Betik bunu bilinçli olarak yapıyor (`qpdf_determinism_experiment.py:60-66`:
hash'ler "BAKED-IN CONSTANTS", varsayılan mod byte-stabil olmalı) ve
`--rerun` çıktısının "run'dan run'a DEĞİŞİR — bu deneyin kendisi" olduğunu
yazıyor. Yani bu bir **kusur değil, bir tasarım**; Minor'e düşürülüyor çünkü
kaydı okuyan bir hakem o satırları bugünkü ölçüm sanabilir. Tek satırlık
uyarı ("bu satırlar 2026-09-26 koşusunun snapshot'ıdır, yeniden ölçüm
`--rerun` ile alınır") yeter.

### M-3 — "K5" atfı paket içinde çözümlenemiyor

`qpdf_determinism_output.txt` son paragrafı: _"Bu dosya donmuş kayıttır (K5
byte-for-byte)."_ Paket içinde K5'i çalıştıracak hiçbir betik yok
(`core_formal_model_check.py`, `encoding_sensitivity_check.py`,
`gate15_check.py`, `qpdf_determinism_experiment.py` dışında script yok).
K5 depodadır. Atfın çözümü "paket dışı" olarak işaretlenmeli.

---

## 5. Bağımsız doğrulama çıktıları (bu inceleme için hesaplandı)

| #   | Denetim               | Komut                                                                       | Sonuç                                                                |
| --- | --------------------- | --------------------------------------------------------------------------- | -------------------------------------------------------------------- |
| D1  | Donmuş kanıt 1        | `python3 core_formal_model_check.py` ⇔ `test_output.txt`                    | **IDENTIK** (exit 0)                                                 |
| D2  | Donmuş kanıt 2        | `python3 gate15_check.py` ⇔ `gate15_output.txt`                             | **IDENTIK** (exit 0)                                                 |
| D3  | Donmuş kanıt 3        | `python3 encoding_sensitivity_check.py` ⇔ `encoding_sensitivity_output.txt` | **IDENTIK** (exit 0)                                                 |
| D4  | Donmuş kayıt 4        | `python3 qpdf_determinism_experiment.py` ⇔ `qpdf_determinism_output.txt`    | **IDENTIK** (exit 0)                                                 |
| D5  | MANIFEST bütünlüğü    | 21 satırın MD5 + boyut doğrulaması                                          | **21/21 tutuyor**, manifest dışı dosya **0**                         |
| D6  | Ham PDF hash          | `shasum -a 256 ingiliz_empirizmi_v3.pdf`                                    | `74b2cdbd…` = kayıttaki raw hash **birebir**                         |
| D7  | Non-determinizm hükmü | `qpdf_determinism_experiment.py --rerun 5`                                  | **5/5 farklı** → NON-DETERMINISTIC **doğrulandı**                    |
| D8  | Sembolik kanıt        | `.venv_z3/bin/python symbolic_proof_z3.py`                                  | **TÜMÜ PASS** (P4-d/P4-e UNSAT)                                      |
| D9  | Referans kanıtı       | `verify_delivery.py --check-references`                                     | **61/61 PASS**, UNVERIFIED=0 (çevrimiçi)                             |
| D10 | stdlib beyanı         | 4 betiğin import kümesi                                                     | üçüncü taraf import **yok**                                          |
| D11 | Güvenlik duruşu       | `bash check_security_posture.sh`                                            | **7/7 PASS** (exit 0)                                                |
| D12 | Review tazeliği       | `python3 check_review_freshness.py`                                         | **PASS** — `review=7f56ac189204 sidecar=OK` (exit 0)                 |
| D13 | Mutlak yol yasağı     | `bash check_absolute_paths.sh`                                              | **PASS** — 588 dosya taranmış                                        |
| D14 | Repo ölçekleri        | `.pre-commit-config.yaml` / `verify.yml`                                    | **57** hook · **31** CI işi (3 required + 13 advisory + 15 koşulsuz) |
| D15 | Ölü atıf taraması     | `CORE_L0_FORMAL_SPEC.md`, `CORE_FORMAL_MODEL_CHECK_REPORT.md`               | paket **ve** repo genelinde **0** eşleşme                            |

**Doğrulanamayan / kapsam dışı bırakılanlar.** (a) Makalenin felsefi içeriği
ve teoremlerinin doğruluğu — bu inceleme bir _teslim mühendisliği_ incelemesidir,
içerik hakemliği değildir; `internal_review_report.md` zaten içerik hakemliğini
ayrıca yürütmüştür. (b) `z3` UNSAT kanıtının _matematiksel_ doğruluğu — kanıt
doğru üretiliyor, kanıtın kendisi denetlenmedi. (c) 61/61 referans denetiminin
_doğruluğu_ — bugün PASS ölçüldü, ancak ağ bağımlı ve zaman-bağımlı olduğu için
sürdürülebilir değil. Bu üçü "başarılı" olarak değil, **kapsam dışı** olarak
işaretlenir.

---

## 6. Kontrol listesi

- [ ] **C-1** `requirements.txt`'e üç harici bağımlılık satırı (qpdf / z3-solver / canlı ağ) + `MANIFEST.txt:22-24`'e "paket dışı doğrulandı" notu
- [ ] **I-1** `internal_review_report.md:5` kapsam satırı güncel adlarla (3 atıf)
- [ ] **I-1b** `internal_review_report.md:246` spec atfı → `L0_Lplus_spec.md`
- [ ] **I-2** Rapor §6'ya P0-3 "yerine kondu" + P2-6 "kapandı" durum satırları; `core_section.tex:494,663`'e `cf. Def. 2.7--2.8` atfı
- [ ] **I-3** Sidecar'a "stripped hash doğrulanamaz" notu (`repack_delivery.py:185` `write_sidecar`)
- [ ] **I-4** `MANIFEST.txt:2` "Generated" başlığını içerik tarihine bağla (`repack_delivery.py:112-114`)
- [ ] **M-1** `repack_delivery.py:75-76` → `with open(...)`
- [ ] **M-2** `qpdf_determinism_output.txt` VERSION_TRACKING satırına snapshot uyarısı
- [ ] **M-3** "K5 byte-for-byte" atfına "paket dışı" etiketi

---

## 7. Hüküm

Teslim, bu incelemenin dokuz ölçülmüş maddesinde (**§1**) kendini kanıtladı:
dört donmuş kanıt bayt-aynı yeniden üretiliyor, MANIFEST 21/21 temiz,
non-determinizm hükmü ve Z3 UNSAT kanıtı bağımsız doğrulandı, kapılar ayakta,
"yalnız stdlib" beyanı doğru. Bu, sıradan bir teslimin çok üstündedir ve
**yayınlanabilirlik açısından engel yoktur**.

Kritik sayılan **tek** bulgu (C-1) bir _yalan_ değil, bir **eksik beyan**dır:
üç doğrulama aracının hiçbiri yanlış çalışmıyor — üçü de bu oturumda çalıştı
ve iddia ettiklerini yaptı. Ancak "no third-party package is required" ibaresi
okunduğunda hakem üç kanıttan ikisini üretemeyeceğini bilmiyor. Düzeltme
tek dosyada üç satır ve birkaç dakikadır; **yayın öncesi zorunlu, sonrası değil.**

Important maddelerin dördü de aynı ailedendir: **teslim edilen metin ile
teslim edilen metni anlatan belgeler arasındaki kayma.** Hiçbiri doğruyu
yanlışlaştırmıyor; hepsi hakemin "hangi sürümü inceliyorum" sorusunu
bir dakika daha uzatıyor. I-1 ve I-2 birlikte, raporun kendi kontrol
listesinin güvenilirlik sınırını belirlemek için tek bir §6 notuyla kapatılır.

Minor'ler düzeltilmezse de teslim ayakta kalır; M-1 tek bir iki satırlık
`with` değişikliğidir ve ayrıca ele alınmaya değer.

**Tek cümlelik özet:** Bu teslim, iddialarını kanıtlamış bir teslimdir —
eksik olan kanıtlar değil, **kanıtların koşulunun yazılı sözleşmesidir.**
