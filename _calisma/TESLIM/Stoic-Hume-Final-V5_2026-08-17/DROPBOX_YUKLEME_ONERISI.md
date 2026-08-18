# Dropbox Yükleme Önerisi — Stoic-Hume V5 Final Paket

**Tarih:** 2026-08-17 · **Ana taşıma birimi:** `TESLIM_KLASOR_V5_2026-08-17.zip` (tek dosya — Dropbox hazır klasörünün tamamı, 11 öğe içinde)

---

## 1. Önerilen Dropbox yapısı — tek dosya

```
Dropbox/
└── TESLIM_KLASOR_V5_2026-08-17.zip        ← ANA TAŞIMA BİRİMİ (her şey içinde)
└── TESLIM_KLASOR_V5_2026-08-17.zip.sha256 ← klasör zip checksum (zip ile AYNI klasörde, zorunlu)
```

**Neden tek dosya?** `TESLIM_KLASOR_V5_2026-08-17.zip`, Dropbox hazır klasörünün tamamını
taşır — içinde 11 öğe var:

```
Stoic-Hume-Final-V5_2026-08-17/            ← (zip içinde)
├── TESLIM_V5_FINAL_2026-08-17.zip         ← iç zip: ana teslim (29 dosya, her şey içinde)
├── TESLIM_V5_FINAL_2026-08-17.zip.sha256  ← iç zip checksum (sidecar)
├── KLASOR_CHECKSUMLARI.sha256             ← klasör checksum'ı (10 dosya; kendini listelemez)
├── TEK_SATIR_DOGRULAMA.txt                ← kurcalanma kontrolü talimatı
├── TEK_DOSYA_TASIMA.txt                   ← tek-dosya taşıma rehberi
├── DROPBOX_YUKLEME_KOMUTLARI.sh           ← hazır komut bloğu (4 katmanlı doğrulama)
├── TESLIM_OZETI.md                        ← tek sayfalık özet (doğrulama zinciri)
├── TESLIM_KRONOLOJISI.md                  ← teslim süreci kronolojisi (26 bölüm + NİHAİ DURUM)
├── DROPBOX_YUKLEME_ONERISI.md             ← bu dosya
├── FINAL-REVIZYON-MIMARISI-V5-KESIN-KILITLI.md  ← V5 mimari anayasası (XXVI)
└── preview.html                           ← 13 bölümlük görsel özet (Delivery Timeline, 18 madde)
```

Dropbox'a **yalnızca 2 dosya** (zip + sidecar) kopyalamak yeterli; açınca insan gözüyle
okunur klasör + tüm doğrulama araçları gelir. Üç katmanlı bütünlük zinciri:

```sh
# Katman 1 — klasör zip'i (taşınan dosyanın kendisi)
shasum -a 256 -c TESLIM_KLASOR_V5_2026-08-17.zip.sha256

# Katman 2 — açılan klasörün içi (10 dosya; kendini listelemez)
unzip TESLIM_KLASOR_V5_2026-08-17.zip
cd Stoic-Hume-Final-V5_2026-08-17
shasum -a 256 -c KLASOR_CHECKSUMLARI.sha256

# Katman 3 — iç zip + paket
shasum -a 256 -c TESLIM_V5_FINAL_2026-08-17.zip.sha256
# (iç zip açılırsa: manifest 18/18 + 3 script byte-for-byte + PDF 33 sayfa)
```

---

## 2. Adlandırma kuralları

| Öğe | Kural | Örnek |
|---|---|---|
| **Klasör zip'i (ana birim)** | `SURUM_KLASOR_YYYY-MM-DD.zip` | `TESLIM_KLASOR_V5_2026-08-17.zip` |
| **İç zip (ana teslim)** | `SURUM_FINAL_YYYY-MM-DD.zip` | `TESLIM_V5_FINAL_2026-08-17.zip` |
| **Sidecar** | zip adı + `.sha256` (birebir aynı kök) | `TESLIM_KLASOR_V5_2026-08-17.zip.sha256` |
| **İç klasör** | `Calisma-Surum_YYYY-MM-DD` | `Stoic-Hume-Final-V5_2026-08-17` |
| **Yardımcılar** | Büyük harf + alt çizgi (makine taraması kolay) | `TEK_SATIR_DOGRULAMA.txt`, `TESLIM_OZETI.md` |

Notlar:
- **Dosya adını DEĞİŞTİRME** — sidecar içindeki hash zip dosya adına bağlıdır; ad
  değişirse `shasum -a 256 -c` başarısız olur.
- **Tarih ekle** (`2026-08-17`): bulutta eski/yeni sürüm karışmasını önler. Yeni bir
  sürüm üretilirse zip adlarını güncel tarihle yenileyin.
- **Sidecar'ı zip ile aynı klasöre koyun** — ayrı klasöre taşınırsa doğrulama komutu çalışmaz.

---

## 3. Yükleme adımları (2 dosya)

1. Dropbox'a 2 dosyayı kopyala:
   ```sh
   cd ~/Downloads/port
   cp TESLIM_KLASOR_V5_2026-08-17.zip TESLIM_KLASOR_V5_2026-08-17.zip.sha256 ~/Dropbox/
   ```
2. **Yüklemeden önce** ve **senkron bittikten sonra** doğrula:
   ```sh
   cd ~/Dropbox
   shasum -a 256 -c TESLIM_KLASOR_V5_2026-08-17.zip.sha256   # → OK
   ```
3. (İsteğe bağlı) İç katmanları da doğrula — yukarıdaki Katman 2–3 komutları.

---

## 4. Checksum (referans)

Klasör zip'inin güncel SHA-256'sı sidecar dosyasındadır (`TESLIM_KLASOR_V5_2026-08-17.zip.sha256`).
Bu belge zip'in içinde yaşadığı için sabit hash gömülmemiştir — self-reference (zip
yeniden üretilince sabit değer eskir). Sidecar'ı görüntüle:

```sh
cat TESLIM_KLASOR_V5_2026-08-17.zip.sha256
```

İç zip'in checksum'ı da kendi sidecar'ında (`TESLIM_V5_FINAL_2026-08-17.zip.sha256`).
Sidecar'ların kaybolmasına karşı nihai değerleri `TEK_SATIR_DOGRULAMA.txt` talimatındaki
yöntemle bağımsız olarak yeniden hesaplayabilirsiniz:

```sh
shasum -a 256 TESLIM_KLASOR_V5_2026-08-17.zip
```

---

## 5. Neden bu düzen?

- **Tek dosya taşınır:** Dropbox'a yalnızca 2 dosya (zip + sidecar) kopyalanır; içeride
  her şey — makale, paket, scriptler, belgeler, preview, checksum'lar — birlikte gelir.
- **Kendini kanıtlar:** yeni makine simülasyonuyla doğrulandı — yalnızca zip + sidecar
  olan herhangi bir makinede tüm katmanlar bağımsız doğrulanabiliyor.
- **Klasör alternatifi:** 11 öğeli açık klasör düzeni de hâlâ geçerlidir (`Stoic-Hume-Final-V5_2026-08-17/`
  — `KLASOR_CHECKSUMLARI.sha256` ile tek komutla doğrulanır, 10/10); tek-dosya zip'i bu klasörün
  birebir paketlenmiş hâlidir.
