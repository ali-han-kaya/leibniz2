# TESLİM — V5 FINAL PAKET (2026-08-17)

Bu zip, İngiliz Empirizmi çalışmasının kilitli final teslim paketidir.

## İçerik

```
TESLIM_V5_FINAL_2026-08-17/
├── TESLIM_NOTU.md                        ← bu dosya
├── FINAL-REVIZYON-MIMARISI-V5-KESIN-KILITLI.md   ← V5 mimari anayasası (sentez belgesi)
├── preview.html                          ← görsel özet (tarayıcıda açılır)
└── stoic_hume_package/
    └── Stoic_Hume_Formal_Section_2026-08-17/    ← reproducibility paketi (18 dosya + MANIFEST)
```

## Paket özeti

- **Makale:** `ingiliz_empirizmi_v3.tex/.pdf` — V5, **33 sayfa** (tectonic ile derlendi).
  Eklenen V5 bölümleri: §2.12 encoding sensitivity (çalıştırılmış test), §2.13 E0/E1/E2,
  §2.14 Gate 1.5 (10/10 Tablo 1), §2.15 HI1–HI4, §4.6 Ev0–Ev4, §6 Objections & Replies
  + §6.1 Negative-Result Matrix, Open Science Statement, M 7.151–152 atıfı,
  Estienne 1562 düzeltmesi.
- **Formal çekirdek:** `core_section.tex` (877 satır) + `L0_Lplus_spec.md` — V5'te değişmedi.
- **3 doğrulama scripti (stdlib-only, deterministik):**
  `core_formal_model_check.py`, `encoding_sensitivity_check.py`, `gate15_check.py`
  — her biri donmuş çıktısıyla byte-for-byte eşleşmeli.
- **Provenance 2.0:** `provenance2_supplement.md` — 7 kolonlu kanıt kaydı (25 satır, P-01…P-19).
- **MANIFEST.txt:** 18 dosyanın boyut + MD5 kaydı.

## Bütünlük doğrulaması (SHA-256)

Zip'in SHA-256 özeti, zip'in yanındaki sidecar dosyasındadır:

```sh
# zip'in bulunduğu dizinde:
shasum -a 256 -c TESLIM_V5_FINAL_2026-08-17.zip.sha256
# → TESLIM_V5_FINAL_2026-08-17.zip: OK
```

Not: Hash, zip'in *kendisinin* bir fonksiyonudur ve zip içindeki bu notu değiştirirse
zip'i de değiştirir — bu yüzden özet, zip'in içine değil yanındaki `.sha256` dosyasına
kayıtlıdır (standart bütünlük pratiği). Zip'i kopyaladığınızda `.sha256` dosyasını da
birlikte taşıyın.

## Doğrulama (paket içinden)

```sh
cd stoic_hume_package/Stoic_Hume_Formal_Section_2026-08-17
python3 core_formal_model_check.py > /tmp/c1.txt && diff /tmp/c1.txt test_output.txt
python3 encoding_sensitivity_check.py > /tmp/c2.txt && diff /tmp/c2.txt encoding_sensitivity_output.txt
python3 gate15_check.py > /tmp/c3.txt && diff /tmp/c3.txt gate15_output.txt
```

## V5 mimarisinin durumu

**Kalan boşluk: YOK.** V5 mimarisindeki tüm maddeler gerçekleşti:
6 eksik (encoding sensitivity, E0/E1/E2, Objections & Replies, Negative-Result Matrix,
Gate 1.5 T1–T10, Open Science) + 3 kalan boşluk (HI1–HI4, Ev0–Ev4, M 7.151–152)
+ Provenance 2.0 supplement — hepsi kapalı.

## Silmeden önce sakla

Bu zip + `stoic_hume_package/` dizini yeterli. Arşiv'deki boş indirme kısayolları
(`Atlas_V7_1_Final_Package.zip.html`, `Leibniz .html`) ve eski revizyon belgeleri
silinebilir.
