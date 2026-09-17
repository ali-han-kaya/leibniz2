---
name: revizyon-kapisi
description: "Sürümlü teslim revizyonlarında sessiz silme, iddia kimliği kayması, hata artığı, bayat ölçüm ve kaynak seviyesi drift’ini kapatır."
source: "Revizyon kapisi-v1.zip"
---

# Revizyon kapısı

Her revizyonda aşağıdaki yüklemler sayısal ölçülür ve sıfır olmalıdır:

- **P1 sayım-farkı:** gerekçesiz eksilen kayıt = 0.
- **P2 iddia-kimliği:** aynı ID + değişmiş metin + sınıflandırılmamış tip = 0.
- **P3 gövde-başlığı:** başlıkta düzeltilip gövdede yaşayan eski hata = 0.
- **P4 sınıf-taraması:** açık hata sınıfı = 0.
- **P5 artık-kova:** sınıflandırılmamış kalıntı eşleşmesi = 0.
- **P6 ölçüm-tazeliği:** son düzenlemeden önce alınmış teslim sayısı = 0.
- **P7 sürüm-işaretçisi:** manifest ile tutarsız sürüm ifadesi = 0.
- **P8 kaynak-seviyesi:** künyesiz `BIRINCIL` satırı = 0.

Metin değişimleri `IFADE`, `KAYNAK-ADI`, `DARALTMA`, `KAYMA` sınıflarından birine atanır. `KAYMA` yeni iddia kimliği alır; derece devralınmaz. `durum` ile `ihtilaf` ayrı alanlardır. Paket boyutu paketin içindeki rapora yazılmaz. Tavan baştan belirlenir; geçmeyen kapı açık borçla durur.

Kapı betiği değiştiğinde yeni kapı kendini onaylamaz; yanlış pozitif oranı ayrıca kaydedilir.
