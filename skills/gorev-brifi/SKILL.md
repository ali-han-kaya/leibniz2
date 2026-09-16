---
name: gorev-brifi
description: "Her işi çıktı, kabul testi, güven, tavan, yasak, rapor ve takılma davranışıyla tarif eder."
source: "Gorev brifi-v1.zip"
---

# Görev brifi — yedi satır

```text
Kurallar: calisma-ahlaki · lab-denetim · verify-chain · ogrenim-dongusu · (sürümlü paketse) revizyon-kapisi geçerli. Tekrar anlatma, uygula.
1 ÇIKTI       nesne + tam yol + biçim
2 KABUL TESTİ çalıştırılabilir komut veya gözle görülebilir evet/hayır çıktısı
3 GÜVEN       TASLAK / ÖLÇÜM / BİRİNCİL
4 BİTTİ+TAVAN durdurucu koşul + sayısal tur/süre tavanı
5 YASAK       dokunulmayacak dosya, konu veya iş tipi
6 RAPOR       biçim ve sayısal uzunluk sınırı
7 TAKILIRSA   SOR / VARSAY+İŞARETLE / DUR
```

- Çıktı teslim edilebilir nesne olmalıdır; “incele” veya “araştır” tek başına çıktı değildir.
- Kabul testi yoksa üretime geçilmez; önce test tanımlanır.
- Varsayılan güven `ÖLÇÜM`dür; birincil kaynak gerektiren iddia `BİRİNCİL` olarak ayrıca doğrulanır.
- Tavan yazılmadan döngü başlamaz. Tavanda kalan iş açık borçtur.
- Geri alınamaz işlerde `SOR` zorunludur.
- Bağımsız dal yoksa alt ajan sayısı 1’dir.
