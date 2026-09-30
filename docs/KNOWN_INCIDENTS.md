# Bilinen Olaylar (Known Incidents)

Bu belge, CI pipeline'ında ve Freebuff Preview tooling'inde yaşanan bilinen
olayların kaydıdır. Amaç: aynı sınıf olaylar tekrarlandığında en küçük
yeniden-üretim, gözlem, kök neden veya geçici çalışma yolu tek bakışta görünür.

---

## PREVIEW-1: Ekran-görüntüleyici kompozitörü frame üretmiyor

- **Tarih:** 2026-09-25
- **Durum:** 🔴 Açık — kök neden doğrulanmadı
- **Etkilenen yüzey:** Freebuff Preview ekran-görüntüleyicisi
- **Kapsam gözlemi:** Default ve incognito profillerdeki birden fazla localhost
  sekmesi

### Belirti

Preview sekmesi DOM'a bağlıdır ve `preview_snapshot` içerik üretir; buna
karşın `preview_screenshot` PNG üretmez ve şu hatayı döndürür:

```text
Could not capture the preview page: it produced no frames, which means the preview webview is not being composited. Reload the preview (preview_navigate "reload") or reopen the Preview tab, then try again.
```

Bu, uygulama sayfasının hata vermesi anlamına gelmez: aynı sekmede erişilebilirlik
ağacı okunabilir. Sorun snapshot ile compositor/capture hattı arasındadır.

### Üç adımlı minimum yeniden-üretim

1. `preview_open` ile herhangi bir `http://127.0.0.1:<port>/` sayfasını yeni bir
   Preview sekmesinde aç.
2. `preview_snapshot` çağır; DOM'un `RootWebArea` ve sayfa metniyle geldiğini
   doğrula.
3. Aynı sekmede `preview_screenshot` çağır; kompozitörün frame üretmediği hata
   döner.

### Gözlenen kontroller

- Yeni açılan default-profile sekmesi aynı hatayı verdi.
- Var olan localhost dashboard, `_preview_jobs_map.html` ve Pinokio sekmeleri
  aynı hatayı verdi.
- Incognito profil de aynı davranışı gösterdi.
- `preview_navigate "reload"` sonrasında ikinci screenshot denemesi de başarısız
  oldu; reload yanıtında ayrıca 15 saniyede load event gözlenmedi.
- DOM snapshot çalıştığı için “webview tamamen detach oldu” veya “sayfa kodu
  çalışmıyor” sonucu çıkarılamaz.

### Minimum kabul ölçütü

Aşağıdaki üç durumun aynı sekmede birlikte doğrulanması yeterlidir:

1. `preview_status` sekmede `loading: false` gösterir.
2. `preview_snapshot` DOM ağacını döndürür.
3. `preview_screenshot` geçerli bir PNG döndürmek yerine “no frames” hatası
   verir.

### Geçici çalışma yolu ve sonraki adımlar

- Metin/DOM doğrulaması `preview_snapshot` ile sürdürülebilir; ekran-görüntüsü
  için doğrulanmış bir workaround yoktur.
- Reload önerisi bu oturumda işe yaramadı; “Preview sekmesini yeniden aç” adımı
  ayrıca kullanıcı tarafından doğrulanmalı.
- İzleme hedefi compositor/surface lifecycle ve screenshot isteğinin frame
  beklerken aldığı hata olmalıdır.
- Düzeltme kapısı: snapshot veren herhangi bir localhost sekmesinde geçerli PNG
  alınması, reload sonrasında tekrar alınabilmesi ve console/loglarda en az bir
  frame üretildiğinin görülmesi.

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
