# Bilinen CI Olayları (Known Incidents)

Bu belge, CI pipeline'ında yaşanan ve düzeltilen bilinen olayların kaydıdır.
Amaç: aynı sınıf olaylar tekrarlandığında kök neden ve çözüm tek bakışta görünür.

---

## INC-1: Azure mirror takılmasında apt_install.sh düzeltmesi

**Tarih:** 2026-08-19
**Etkilenen run'lar:** push `3bbf142` sonrası (düzeltme öncesi birden fazla run)
**Düzeltme commitleri:** `3bbf142` (ilk deneme — mirror dosyasını silme), `4e27908`
(kesin çözüm — URI çevirme)
**Durum:** ✅ Çözüldü, 2026-08-19'dan beri tekrarlanmadı

### Belirti

GitHub Actions `ubuntu-latest` runner'larında `apt-get update` / `apt-get install`
komutları zaman zaman **300 sn timeout** ile düşüyordu (exit 124). Aynı run'da
bir job geçirirken diğeri takılıyordu — tutarsız, tekrarlanabilir olmayan davranış.

### Kök neden

Runner'lar varsayılan olarak `azure.archive.ubuntu.com` mirror'ını kullanıyor.
Bu mirror bazen **erişilemez** hale geliyor (Azure altyapı sorunu). Runner'ın
sources dosyası (`/etc/apt/sources.list.d/ubuntu.sources` veya `sources.list`)
`mirror+file:/etc/apt/apt-mirrors.txt` URI'si kullanıyor — mirror dosyasını
**silmek** kaynağı tamamen kırıyor ("Downloading mirror file failed").

### İlk deneme (yanlış çözüm — `3bbf142`)

```bash
# YANLIŞ: mirror dosyasını silmek tüm kaynakları kırar
sudo rm /etc/apt/apt-mirrors.txt
```

Bu, `Downloading mirror file failed` hatasına yol açtı çünkü sources'taki
`mirror+file:` URI'si artık çözülemez oldu.

### Kesin çözüm (`4e27908` → `apt_install.sh`)

```bash
# DOĞRU: sources'taki mirror URI'lerini archive.ubuntu.com'a çevir
sudo sed -i \
    -e 's|mirror+file:/etc/apt/apt-mirrors\.txt|http://archive.ubuntu.com/ubuntu/|g' \
    -e 's|https\?://azure\.archive\.ubuntu\.com|http://archive.ubuntu.com|g' \
    -e 's|https\?://ports\.ubuntu\.com|http://archive.ubuntu.com|g' \
    "$f"
```

Ardından:
1. `apt-get update` — retry ile (Acquire::Retries=5)
2. Başarısızsa cache temizle + ikinci deneme
3. `apt-get install` — retry + timeout ile

### Workflow entegrasyonu

`verify.yml`'deki tüm `apt-get install` adımları artık `apt_install.sh`'i
çağırıyor:

```yaml
- name: Install deps
  run: bash _calisma/CIKTI/apt_install.sh poppler-utils qpdf
```

### Önlem

- `apt_install.sh` herhangi bir mirror sorununda otomatik olarak
  `archive.ubuntu.com`'a fallback yapıyor
- Mirror dosyasını silmiyor (URI çeviriyor)
- 300 sn timeout + retry ile dayanıklı

### Benzer olayların belirtileri

- `apt-get update` 300 sn timeout (exit 124)
- "Could not resolve host: azure.archive.ubuntu.com"
- "Downloading mirror file failed"
- Aynı run'da bir job yeşil, diğeri kırmızı (tutarsız)

---

## INC-2: GITHUB_STEP_SUMMARY env-snapshot hatası

**Tarih:** 2026-08-19
**Düzeltme:** `env-snapshot` adımında `GITHUB_STEP_SUMMARY` değişkeni
`set -euo pipefail` altında tanımsızken kullanılıyordu → stderr'e düşünce
exit 1 veriyordu
**Durum:** ✅ Çözüldü

### Belirti

Run `32241821709` — unit test'ler PASS ama verify job failure (exit 1).

### Kök neden

`env-snapshot` adımında `GITHUB_STEP_SUMMARY` dosya yolu `set -euo pipefail`
altında tanımsızken `echo "..." >> $GITHUB_STEP_SUMMARY` komutu boş
değerle çağrılıyordu → stderr'e hata, exit 1.

### Çözüm

Env değişkeninin varlığını kontrol edip tanımsızsa fallback dosyaya yazma.

---

## INC-3: dash/bash uyumsuzluğu (shellcheck)

**Tarih:** 2026-08-19
**Düzeltme:** pre-commit hook'ları POSIX dash uyumlu hale getirildi
(`[[ ]]` → `[ ]`, `$(( ))` → `expr` vb.)
**Durum:** ✅ Çözüldü

### Belirti

`pre-commit run --all-files` bazı hook'larda dash altında "syntax error"
veriyordu.

### Kök neden

GitHub Actions runner'ları `/bin/sh` olarak dash kullanıyor; bazı hook
betikleri bash-specific syntax (`[[ ]]`, process substitution vb.)
kullanıyordu.

### Çözüm

Tüm shell hook'ları POSIX dash uyumlu yeniden yazıldı; `actionlint` +
`shellcheck` ile CI'da sürekli denetleniyor.

---

## INC-4: main push GH006 — "Repack determinism + verify" zorunlu kontrolü kırmızı

**Tarih:** 2026-10-05
**Etkilenen run'lar:** verify-delivery [`37257949738`](https://github.com/ali-han-kaya/leibniz2/actions/runs/37257949738) (pre-fix zincir, HEAD `b79b66e`) — `Repack determinism + verify (sidecar sync)` = failure
**Push reddi:** `git push origin main:main` → `remote: error: GH006: Protected branch update failed`
**Düzeltme commit'i:** `3f7f88f` (repack + registry resync, TEK commit)
**Durum:** ✅ Çözüldü — `77d05e3`, `b1f5f1e`, `d566be2` main'e girdi; push artık geçiyor
**Kök neden analizi:** `docs/RCA_REPACK_SIDECAR_DRIFT.md`

### Belirti

Yerel main (`b79b66e`, origin/main'in 14 commit ilerisi) doğrudan push
edildiğinde GitHub reddetti:

```
remote: error: GH006: Protected branch update failed for refs/heads/main.
remote: Required status check "Repack determinism + verify (sidecar sync)" is failing.
```

CI tarafındaki job log'u tek bir dosyada sapma gösteriyordu: teslim zip'inin
içindeki `ingiliz_empirizmi_v3.tex` kopyası **76478 B**, depodaki kaynak ise
**76846 B** — zip kendi kaynağından eskiydi. `Delivery verification — K1-K19`
aynı koşumda yeşildi: yani sorun teslim mantığında değil, **artifact'ın
kaynakla senkron olmamasında**ydi ve yalnız bu zorunlu kontrol onu yakalıyordu.

### İlk deneme (yetersiz — tek katman onarım)

Önce yalnız repack çalıştırılıp 6 artifact dosyası commit'lendi (`8b01dd3`,
yerelde denendi). Bu, zincirin ikinci katmanını kırmızıya düşürdü: K14
`check_zip_lineage_drift.py` "zip + `zip_lineage.json` + `cleanup_log.json`
**aynı commit'te**" diye reddediyor — zip'i tazelemek kayıt defterlerini
tazelemeyi gerektirir, ikisi ayrı commit'te kaybolur.

### Kesin çözüm (`3f7f88f`)

1. Kanonik repack yeniden üretildi → 6 dosya değişti
   (`TESLIM_V5_FINAL…zip` 473464 → **473658 B**,
   `TESLIM_KLASOR_V5…zip` 511887 → **512086 B**, iki `.sha256`, `MANIFEST.txt`,
   `KLASOR_CHECKSUMLARI.sha256`)
2. Aynı commit içinde registry resync: `zip_lineage.json` (yeni V5q nesli,
   kanonik hash'ler) + `cleanup_log.json`
3. Determinizm kanıtlandı: yerel repack'in ürettiği iç zip SHA-256'sı
   `b37f45cf0860d3a9770cbf41994de4ca71e468e5701a678cb1aae9d65b677cc8`, CI'ın
   beklediği hash ile **birebir aynı**; yerel `ci_replay` 2/2 zip
   byte-identical, P0=0 / P1=0

### Önlem

- Push reddi artık "hangi zorunlu kontrol?" diye ayrı ayrı okunmuyor: GitHub
  reddinde tek satır (`Required status check "…" is failing`) veriyor; o kontrol
  doğrudan açılıp job log'una bakmak ~1 dakika.
- `3f7f88f`'ten sonra main push üç turda da geçti (`77d05e3`, `b1f5f1e`,
  `d566be2`) — required-check zinciri yeşil.

### Benzer olayların belirtileri

- `GH006: Protected branch update failed` + tek bir required check adı
- Repack job'ında yalnız **bir** dosyada bayt içerik (kaynak ≠ zip kopyası)
- Zip'i düzeltince `check_zip_lineage_drift.py` (K14) kırmızıya dönüyor
- "Son repack ne zaman?" sorusunun cevabı, ilgili son TeX değişikliğinden eski

---

## INC-5: PyYAML yokken türetilen önem listesi süreci SystemExit ile öldürüyor

**Tarih:** 2026-10-05
**Etkilenen run'lar:** land `03a72ce` verify-delivery [`37361885622`](https://github.com/ali-han-kaya/leibniz2/actions/runs/37361885622) = failure (`FAILED (errors=2, skipped=109)`) — iki hata da `test_rca_report.TestRequiredSource` içinde `SystemExit: 2`
**Düzeltme commit'i:** `9f0c9cb`
**Durum:** ✅ Çözüldü — `e2db1f4`/`1008538` main'de; `Delivery verification — K1-K19` hem `e2db1f4` hem `1008538`'de yeşil
**Kanıt zinciri:** yerel `python3 -m unittest test_rca_report` 23/23 · land [`37374017355`](https://github.com/ali-han-kaya/leibniz2/actions/runs/37374017355) DV=success · main [`37377743878`](https://github.com/ali-han-kaya/leibniz2/actions/runs/37377743878) DV=success · defter satırı `e2db1f4`

### Belirti

RCA tablosu `verdict: indeterminate | zorunlu 0 / advisory 0` yazıyordu —
fallback devreye girdiğinde süreç ölüyor, tablo boş kalıyordu. Yerelde
tekrarlanamıyordu; yalnız CI'da (PyYAML kurulu değil) çöküyordu.

### Kök neden

`GITHUB_TOKEN` branch protection okuyamaz: `administration` scope
**grant edilemez**. Bu yüzden required listesi `verify.yml` job adlarından
türetilir. Ama fallback `status_checks.gate_jobs()` çağırıyordu ve o fonksiyon
PyYAML yoksa `_require_yaml()` üzerinden **`sys.exit(2)`** çağırır — tam da
CI'da, yani fallback'in çalışmak zorunda olduğu tek yerde.

Kritik ayrıntı: `SystemExit`, `Exception`'ın **altında değildir**. Dolayısıyla
`except Exception` sarmalayıcısı onu yutmaz; süreç doğrudan ölür. Sarmalayıcı
"hatayı yutuyor" izlenimi verirken gerçek davranış sürecin sonlanmasıydı.

### İlk deneme (yetersiz — yalnız sarmalayıcı)

`except Exception` eklemek hatayı görünmez yapar ama `SystemExit`'i
yakalamaz; CI'da aynı ölüme düşülür.

### Kesin çözüm (`9f0c9cb`)

1. `gate_jobs()` yerine **`_derived_required(data=None)`**: aynı tek kaynağı
   kullanır (`sc.WORKFLOW` yolu + `sc.GATE_EXCLUDE` listesi), ama YAML
   okumayı kontrollü noktada yapar. `data` verilirse dosya hiç okunmaz.
2. Çağrı **`except BaseException`** ile korunur — hem `SystemExit` hem
   `ImportError` yutulur, `derived = []` ile `([], "bilinmiyor")` döner.
3. Test: `sys.modules["yaml"] = None` ile gerçek alt süreçte `required_contexts`
   patlamıyor, `([], "bilinmiyor")` dönüyor.

### Önlem

- `status_checks._require_yaml()` gibi **kitaplık katmanında `sys.exit`
  çağıran** kod, bir üst katmandaki `except Exception` ile güvenli sanılır.
  Sözleşmesi "listeyi döndür ya da öl" olan bir fonksiyon, opsiyonel
  bağımlılıkla çağrılmamalı.
- Degrade davranış **etiketli** dönmeli: `("…", "verify.yml job adları
  (canlı koruma okunamadı)")` → tablo okura doğruluğu da söyler.

### Benzer olayların belirtileri

- Yalnız CI'da, yerelde asla görülmeyen `SystemExit: 2` / exit code 2
- `HATA: PyYAML gerekli` stderr satırı + tablo satırının boş kalması
- `verdict: indeterminate | zorunlu 0 | advisory 0` (çelişki: koşum kırmızı,
  tablo temiz)
- `import yaml` içeren herhangi bir opsiyonel yedek yol
