# TEMİZLİK KONTROL LİSTESİ — Silmeden Önce Doğrulama

**Tarih:** 2026-08-17
**Amaç:** Bilgisayarda biriken eski belgelerin, içerik kaybı olmadan silinebileceğini
**kanıtlayan** kontrol listesi. Her madde, silme izni vermeden önce çalıştırılmış bir
doğrulamaya dayanır.

**Altın kural:** Silme ancak bu listedeki her "✅ GÜVENLİ" maddesi için aşağıdaki
koşullar kanıtlandıktan sonra yapılır. Şüphede kalınan tek bir madde bile varsa o
dosya/dizin **silinmez**.

---

## 0. Önce sakla — KORUNAK (asla silme)

| # | Konum | Neden |
|---|-------|-------|
| K1 | `Downloads/port/TESLIM_V5_FINAL_2026-08-17.zip` + **`TESLIM_V5_FINAL_2026-08-17.zip.sha256`** (sidecar) | **Tek teslim paketi** — 29 dosya, zip içinden 18/18 manifest + 3 script byte-for-byte doğrulandı. SHA-256: zip'in yanındaki `.sha256` sidecar dosyasındadır (bu belge zip'in içinde olduğu için sabit hash yazılamaz — self-reference; sidecar her yeniden üretimde güncellenir). Doğrulama: `shasum -a 256 -c TESLIM_V5_FINAL_2026-08-17.zip.sha256` → OK. Sidecar'ı zip ile birlikte taşıyın |
| K2 | `Downloads/port/stoic_hume_package/Stoic_Hume_Formal_Section_2026-08-17/` | Paketin çalışma kaynağı (zip'in birebir üreteci) |
| K3 | `Downloads/port/FINAL-REVIZYON-MIMARISI-V5-KESIN-KILITLI.md` | V5 mimari anayasası (4 revizyon belgesinin sentezi) |
| K4 | `Downloads/port/preview.html` | Görsel özet |

**K1–K4 dışında hiçbir şey silinmeden önce bu liste okunmalıdır.**

---

## 1. Arşiv.zip ve içeriği

### 1.1 `Downloads/Arşiv.zip` — ✅ GÜVENLİ (silinebilir)

**Doğrulama:** Arşiv içinde 6 gerçek dosya var (6'sı da aşağıda ayrı ayrı denetlendi):

| Dosya | İçerik | Karar |
|-------|--------|-------|
| `en_..._master_plani.md` | Revizyon master planı | ✅ → V5 belgesine tam aktarıldı (bkz. §1.2) |
| `nihai_..._v2.md` | Revizyon mimarisi V2 | ✅ → V5 belgesine tam aktarıldı |
| `nihai_..._v3.md` | Revizyon mimarisi V3 | ✅ → V5 belgesine tam aktarıldı |
| `nihai_..._v4.md` | Revizyon mimarisi V4 | ✅ → V5 belgesine tam aktarıldı |
| `Atlas_..._Package.zip.html` | **Boş indirme kısayolu** | ✅ → silinebilir (bkz. §1.3) |
| `Leibniz .html` | **Boş indirme kısayolu** | ✅ → silinebilir (bkz. §1.3) |

### 1.2 Dört revizyon belgesinin içeriği V5'e aktarıldı mı? — ✅ KANITLANDI

**Yöntem:** Her belgenin tüm bölüm başlıkları çıkarıldı ve V5 belgesinin
(`FINAL-REVIZYON-MIMARISI-V5-KESIN-KILITLI.md`) başlık yapısıyla eşleştirildi.
**Sonuç: 4 belgenin bölümlerinin tamamı V5'te karşılık buluyor.**

| Master Plan bölümü | V5 karşılığı |
|---|---|
| §1 Teşhis (desk-reject) | §0 Verdict, §XXIII denetim |
| §2 Formal çekirdek (hyperint., imza, JL) | §II–VI, §XII, §XIV |
| §3 Filolojik revizyon (katalepsis, matbu iletim) | §XVII Filolojik kilit listesi |
| §4 Karşılaştırmalı (catuskoti, Xunzi) | §X Karşılaştırmalı — Kilitli |
| §5.1 Provenance 2.0 | §XVIII + **`provenance2_supplement.md`** (pakette, 7 kolon) |
| §5.2 Yayın stratejisi | §XIX |
| §6 30 günlük plan | §XXV Bundan Sonra |

| V2 bölümü | V5 karşılığı |
|---|---|
| I Panel audit (10 uzman) | §0 Verdict + §XXIII |
| II Daraltılmış tez | §I Kilitli merkez tez |
| III–IV Formal mimari + teorem adları | §II Final theorem hierarchy |
| V Expressive benchmark | §III E0/E1/E2 benchmark |
| VI Tarihsel düzeltmeler | §XVII |
| VII Hume PSR→Causal maxim | §VIII Hume |
| VIII Karşılaştırmalı budama | §X |
| IX Yasaklı dil listesi | §XIV (V5'te geri alındı) |
| XI Gate-based workflow | §XVI Gate sistemi |
| XII Kill Shot (10 soru) | §XXII Kill-Shot Q&A |

| V3 bölümü | V5 karşılığı |
|---|---|
| I Beth indirgemesi | §XII Beth'in konumu |
| II Kill Shot triviality | §XVI + Gate 1.5 |
| III E0/E1/E2 | §III |
| IV H1/H2/H3/H4 | §IV (makalede **HI1–HI4**, §2.15) |
| V Stoacı modal decomposition | §VII Encoding sensitivity |
| VI Typed fact sort | §V |
| VII Hume demotion dili | §VIII |
| VIII E0-E4 hiyerarşisi | §IX (makalede **Ev0–Ev4**, §4.6) |
| XII Objections and Replies | §XI (makalede §6, 7 itiraz) |
| XVI Gate 1.5 | §XVI + Gate 1.5 (makalede §2.14, 10/10) |

| V4 bölümü | V5 karşılığı |
|---|---|
| II Theorem 1 T_G-relative | §II + §0 (K-relative form; makale Prop 2.6) |
| III E0/E1/E2 Γ sınırlı | §III |
| VI Hyperint. dört katmanı | §IV (makalede §2.15) |
| VII Stoic encoding sensitivity | §VII (makalede §2.12, **test çalıştırıldı**) |
| IX E0-E4 ladder | §IX (makalede §4.6) |
| XI Objections & Replies | §XI (makalede §6) |
| XV Negative Result Matrix | §XIII (makalede §6.1) |
| XVII Gate 1.5 (tam formel) | §XVI + Gate 1.5 (makalede §2.14 + Tablo 1) |
| XIX Final cümle | §XXIV |

**Kilit nokta:** V5, V2–V4'ün **kaybettiği** içerikleri de geri getirdi (yasaklı dil
listesi, 7 itirazlı Objections & Replies, benchmark, filolojik kilit listesi,
Provenance 2.0, yayın stratejisi, zero-tolerance, AI disclosure, kill-shot Q&A) —
hepsi V5 başlıklarında görülüyor. Üstelik V4'ten sonraki tüm içerik, gerçek
makaleye de işlendi (V5 §XXIII denetimi: 6 eksik + 3 boşluk + Provenance 2.0 → **hepsi kapalı**).

### 1.3 İki HTML gerçekten boş mu? — ✅ KANITLANDI

**Yöntem:** Her iki dosyanın kaynağı okundu (13.5 KB). İkisi de Optimistic AI
arayüzünün "Preview is not available for this format. Please download the file to
view its contents." mesajını içeren **indirme kısayol sayfası** — içerik yok,
yalnızca `Atlas_x5f_V7_x5f_1_x5f_Final_x5f_Package.zip` için bir Download
bağlantısı var. Zip dosyasının kendisi indirilmemiş (yerel diskte yok).
**Sonuç: bilgi içermiyorlar; silmek kayıp yaratmaz.**

---

## 2. Downloads'taki eski/duplike dosyalar

| # | Dosya | Doğrulama | Karar |
|---|-------|-----------|-------|
| D1 | `Downloads/Stoic_Hume_Formal_Section_2026-08-17.zip` (163 KB, 01:28) | İçerik: V5 **öncesi** paket (INTEGRATION_NOTE 11431 B, README 5482 B = V5 öncesi boyutlar). Tüm bu içerik güncel pakette var ve **daha ileride** (V5). | ✅ GÜVENLİ — silinebilir |
| D2 | `Downloads/ingiliz_empirizmi_v3.pdf` (179.516 B, 02:08) | MD5 `fd09d7…` = V5 öncesi PDF (paketteki V5 PDF: 214.520 B, MD5 `3a9d8b1c…`, 33 sayfa). Eski sürüm; Hervet/Estienne hatası düzeltilmemiş hali. | ✅ GÜVENLİ — silinebilir |
| D3 | `Downloads/Arşiv.zip` | Bkz. §1.1 — 6 dosyanın 6'sı da denetlendi. | ✅ GÜVENLİ — silinebilir |
| D4 | `Downloads/2201 toplu rev/` | ⚠️ **DOKUNMA — bu çalışmanın parçası DEĞİL** (mpf_article, Deepseek revizyon dosyaları = ayrı bir makale/çalışma). Bu temizlik kapsamında değildir. | ⚠️ Ayrı değerlendir |
| D5 | `Downloads/port/` içindeki geçici `preview.html` / V5 / paket | K1–K4 = **KORUNAK**. | 🔒 Koru |

---

## 3. Silme sonrası doğrulama (opsiyonel ama önerilir)

Zip'i silinen içerikten bağımsız olarak açıp şunları çalıştırın:

```sh
# (0) zip bütünlüğü — sidecar ile:
shasum -a 256 -c TESLIM_V5_FINAL_2026-08-17.zip.sha256   # → OK vermeli

cd TESLIM_V5_FINAL_2026-08-17/stoic_hume_package/Stoic_Hume_Formal_Section_2026-08-17
python3 core_formal_model_check.py > /tmp/c1.txt && diff -q /tmp/c1.txt test_output.txt
python3 encoding_sensitivity_check.py > /tmp/c2.txt && diff -q /tmp/c2.txt encoding_sensitivity_output.txt
python3 gate15_check.py > /tmp/c3.txt && diff -q /tmp/c3.txt gate15_output.txt
# üçü de "byte-for-byte OK" vermeli; manifest denetimi 18/18 OK olmalı
```

Eğer bu üç komut + manifest denetimi geçerse, **silinen hiçbir şey paketten eksik değildir** —
çünkü paketin kendisi zip içinde, bağımsız olarak doğrulanabilir durumdadır.

---

## 4. Özet karar tablosu — UYGULANDI (2026-08-17)

| Madde | Karar | Durum |
|-------|-------|-------|
| K1–K4 (teslim paketi + V5 + preview) | 🔒 **KORU** | ✅ yerinde |
| Arşiv.zip + içindeki 6 dosya | ✅ **SİL** | ✅ **silindi** |
| Downloads/Stoic_Hume_Formal_Section_2026-08-17.zip (eski, V5 öncesi) | ✅ **SİL** | ✅ **silindi** |
| Downloads/ingiliz_empirizmi_v3.pdf (eski, V5 öncesi) | ✅ **SİL** | ✅ **silindi** |
| /tmp/arsiv_extract, /tmp/teslim_staging, /tmp/zip_verify* | ✅ **SİL** (geçici denetim dizinleri) | ✅ **silindi** |
| Downloads/2201 toplu rev/ | ⚠️ **KARAR YOK** — farklı çalışma | ⚠️ dokunulmadı |

**Silme sonrası doğrulama (2026-08-17, hepsi geçti):**
- Zip SHA-256 sidecar ile eşleşti (`shasum -a 256 -c` → OK)
- Zip bütünlüğü: `unzip -t` → no errors
- Zip içinden: manifest 18/18 OK · 3 script byte-for-byte OK
- Korunacakların tamamı yerinde (`TESLIM_V5_FINAL_2026-08-17.zip` + `.sha256` + V5 belgesi + preview + `stoic_hume_package/`)

**Sonuç:** Silinen hiçbir şey teslim paketinden eksik değil — paket bağımsız olarak doğrulanabilir durumda.
