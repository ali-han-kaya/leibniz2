---
name: ogrenim-dongusu
description: "Bir koşudan çıkan dersi, holdout kümesine bakmadan ölçülen ve kalıcı düzeltmeye dönüştürülen bir döngüye çevirir."
source: "ogrenim-dongusu.skill"
---

# Öğrenim döngüsü

## Kabul kuralı

```text
KABUL ⟺ Δ_içeride ≥ 0 VE Δ_dışarıda ≥ 0 VE max(Δ_içeride, Δ_dışarıda) > 0
```

- `içeride`: düzeltmenin üretildiği bilinen hata kümesi.
- `dışarıda`: düzeltme üretilirken okunmayan, önceden ayrılmış holdout kümesi.
- Holdout kümesi düzeltme üretiminde okunmaz; yalnız bağımsız değerlendirme aşamasında kullanılır.
- Her öneri tek mekanizmayı hedefler.
- Kapı değişikliği kendi aday sürümüyle kendini onaylamaz; önceki kapı ve önceden sabitlenmiş bağımsız kabul testleri kullanılır.
- Kabul edilen ve reddedilen her düzeltme tarih, örüntü, delta, karar ve gerekçeyle kaydedilir.

## Döngü

1. Koşu izlerini ve ölçülmeyenleri topla.
2. Tekrarlayan hata imzalarını kümele.
3. Tek mekanizmalı düzeltme öner.
4. İçeride/dışarıda bölmelerini ayır; holdout’u kapalı tut.
5. Önceden sabitlenmiş testlerle ölç.
6. İçeride kazanıp holdout’ta kaybettiren düzeltmeyi reddet ve kaydet.
