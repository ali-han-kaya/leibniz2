---
name: birincil-kayit-dogrulama
description: "Bir olguyu model uzlaşmasıyla değil, izlenebilir birincil kayıtla doğrular."
source: "verify-chain.skill"
---

# Birincil kayıt doğrulaması

İki modelin aynı cevabı vermesi doğruluk değildir. Kabul edilen her olgu için:

1. İddiayı tek, sınanabilir cümle olarak yaz.
2. Yayıncı kaydı, DOI/Crossref kaydı, kurumsal katalog, dijital nüsha veya basılı nüsha gibi birincil kaydı belirle.
3. Kayda git; erişilemiyorsa tahmin etme, `OLCULMEDI` yaz.
4. Aynı olgu için dolaşımdaki bütün rakamları ve her birinin kaynağını listele.
5. Seçilen değeri ve elenen değerlerin nedenlerini tek satırla gerekçelendir.
6. Olgu, değer, seviye, kaynak ve doğrulama tarihini kaydet.

Seviyeler:

- `BIRINCIL`: yayıncı/orijinal kayıt veya tam tıpkıbasım + künye.
- `DIJITAL`: dijital nüsha; birincil iddia için ayrıca baskı/künye gerekir.
- `BEYAN`: kaynak beyanı var, bağımsız doğrulama yok.
- `OLCULMEDI`: kayıt erişilemedi veya ölçüm yapılmadı.

“İki model de böyle söyledi” kanıt değildir. Her kabul edilen değerin kaynak satırı, her elenen değerin gerekçesi, doğrulanamayan her kaydın açık etiketi bulunmalıdır.
