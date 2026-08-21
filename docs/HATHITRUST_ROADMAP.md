# HathiTrust Katalog Yol Haritası — 4 Kaynak

**Hedef:** Fine 2012, Lagrée 1994, Millican 2002, Schmitt 1972 kitaplarının
HathiTrust dijital kütüphanesine girmesi ve `verify_delivery.py --check-references`
tarafından `hathitrust` kaynağıyla PASS vermesi.

**Tarih:** 2026-08-21 · **Durum:** Yol haritası — henüz eylem yok

---

## 1. Mevcut Durum

| Kaynak | Yayınevi | Yıl | LCCN | OCLC | ISBN | HT Durumu | Mevcut Kanıt |
|---|---|---|---|---|---|---|---|
| Fine 2012 | Cambridge UP | 2012 | 2012014618 | 793497146 | 9781107460287 | **YOK** (0 item) | LoC lccn → PASS (V5w) |
| Lagrée 1994 | Vrin | 1994 | 95174106 | 32045786 | 2711612074 | **YOK** (0 item) | LoC lccn → PASS (V5w) |
| Millican 2002 | OUP | 2002 | 2002020030 | 48957942 | 9780198752103 | **YOK** (0 item) | LoC lccn → PASS (V5w) |
| Schmitt 1972 | Nijhoff | 1972 | 73155022 | 1194850 | 9401710376 | **YOK** (0 item) | LoC lccn → PASS (V5w) |

**Karşılaştırma — Xunzi (Knoblock) HT'de:**

| Kaynak | OCLC | HT Items | Sonuç |
|---|---|---|---|
| Xunzi Knoblock | 17265207 | 2 item (uc1.b3817880, uc1.b3817881) | **PASS (hathitrust)** |

Xunzi'nin HT'de olmasının nedeni: Stanford UP (1988) telifli ama UC Berkeley kütüphanesi
tarandı ve Google Books aracılığıyla HT'ye aktarıldı. Dört kitap ise henüz hiçbir
partner kütüphane tarafından taranmamış.

---

## 2. HathiTrust'e Kitap Ekleme Mekanizması

HathiTrust **kişisel yükleme kabul etmez** — 219+ araştırma kütüphanesi konsorsiyumudur.
İçerik yalnızca şu yollarla girer:

### 2.1 Google Books Tarama Hattı (en yaygın)
- Google, partner kütüphanelerin fiziksel koleksiyonlarını tarar
- Taramalar otomatik olarak HathiTrust'e aktarılır
- **Ön koşul:** Kitabın bir Google Books partner kütüphanesinde fiziksel olarak bulunması
- **Engel:** Google Books programı 2020'lerde büyük ölçüde yavaşladı; yeni tarama
  talepleri nadiren karşılanıyor

### 2.2 Internet Archive Tarama Hattı
- IA, kendi tarama merkezinde (Richmond, CA) kitapları tarar
- Taramalar IA'da depolanır, bazıları HT'ye de aktarılır
- **Ön koşul:** Kitabın IA'ya fiziksel olarak bağışlanması veya ödünç alınması
- **Engel:** IA tarama hattı da(Application'dan yavaş; telifli kitaplar için kısıtlı)

### 2.3 Yerel Dijitalleştirme (Partner Kütüphane)
- Bir HT partner kütüphanesi kendi tesislerinde kitabını tarar
- Taramayı doğrudan HT'ye yükler
- **Ön koşul:** Kütüphanenin hem fizikik hem dijitalleştirme kapasitesi
- **En gerçekçi yol** — kütüphane tarama programları aktif

### 2.4_Item digitization request (HT Helpful Hints)
- HT, kütüphanelerden tarama taleplerini değerlendirir
- Ancak bu **telifli kitaplar için doğrudan bir yükleme yolu değil** —
  kütüphane önce tarayıp sonra yüklemeli

---

## 3. Kitap Bazlı Engeller ve Çözüm Önerileri

### 3.1 Fine 2012 — Metaphysical Grounding (CUP)

**Engel:**
- Cambridge UP 2012 — telifli, Academic kitap
- CUP Google Books ile tarama yapıyor ama yalnızca "snippet view" sunuyor
- HT'de 0 kaydı (OCLC 793497146 WORLDcat'te var ama HT'de değil)
- CUP kitapları genellikle Oxford/Cambridge kütüphaneleri tarafından taranıyor

**Çözüm yolları:**
1. **En olası:** Cambridge Üniversitesi Kütüphanesi veya Oxford kütüphanesi bu kitabı
   Google Books aracılığıyla taradığında otomatik olarak HT'ye düşecek
2. **HathiTrust item request:** CUP ile iletişime geçip tarama izni almak — CUP'un
   kendi dijitalleştirme programı varsa kitap taranabilir
3. **Alternatif kanıt:** LoC lccn:2012014618 zaten PASS veriyor (V5w)

### 3.2 Lagrée 1994 — Juste Lipse et la restauration du stoïcisme (Vrin)

**Engel:**
- Vrin (Paris) — Fransız akademik yayınevi, küçük ölçek
- Vrin kitapları Fransa'daki akademik kütüphanelerde bulunur ama Google Books
  tarafından taranmamış (Fransız yayınevi politikası)
- OCLC 32045786 WorldCat'te var ama HT'de 0 kaydı

**Çözüm yolları:**
1. **En olası:** Bibliothèque nationale de France (BnF) veya Fransız üniversite
   kütüphanesi bu kitabı tararsa Gallica/BnF aracılığıyla erişilebilir hale gelebilir
   (HT değil ama ulusal dijital kütüphane)
2. **HT için:** Fransız bir HT partner kütüphanesi (varsa) tarama yapabilir
3. **Dürüst sınır:** Bu kitap HT için en zor hedef — Fransız yayınevi, telifli,
   Google Books kapsamında değil

### 3.3 Millican 2002 — Reading Hume on Human Understanding (OUP)

**Engel:**
- Oxford UP 2002 — telifli, OUP akademik kitap
- OUP Google Books ile çalışıyor ama "snippet view" veya "no preview"
- OCLC 48957942 WorldCat'te var ama HT'de 0 kaydı
- Kitap OUP unutulmaz kitapları listesinde değil, telif korunuyor

**Çözüm yolları:**
1. **En olası:** Oxford Üniversitesi Kütüphanesi bu kitabı Google Books aracılığıyla
   taradığında otomatik olarak HT'ye düşecek
2. **OUP ile iletişim:** OUP academic partnership kapsamında tarama izni verebilir
3. **Alternatif:** Millican'ın Edinburgh kütüphanesindeki kopyası taranabilir
   (Edinburgh HT partneri mi? Kontrol gerekir)

### 3.4 Schmitt 1972 — Cicero Scepticus (Nijhoff)

**Engel:**
- Martinus Nijhoff (The Hague) 1972 — artık Brill bünyesinde
- 50+ yıllık kitap ama telif hala korunuyor (yazar 2002'de öldü, 70+ yıl kuralı)
- OCLC 1194850 WorldCat'te var ama HT'de 0 kaydı
- Brill/Nijhoff kitapları Hollanda akademik kütüphanelerinde bulunur

**Çözüm yolları:**
1. **En olası:** Leiden Üniversitesi veya Hollanda'daki diğer kütüphane tarama yaparsa
   HT'ye düşebilir (Hollanda HT partneri mi? Leiden kesinlikle — Hollanda Kraliyet
   Kütüphanesi HT üyesi)
2. **Brill ile iletişim:** Brill, eski Nijhoff kataloglarını dijitalleştiriyor olabilir
3. **Alternatif:** 1972 tarihli kitap 2042'de ABD'de public domain olacak
   (70+ yıl telif)

---

## 4. Eylem Planı (Öncelik sırasıyla)

### Aşama 1: Bilgi Toplama (1-2 hafta)

| # | Eylem | Sorumlu | Çıktı |
|---|---|---|---|
| 1.1 | HT partner kütüphane listesini kontrol et: hangi AB/ABD kütüphaneleri bu 4 kitabı fiziksel olarak tutuyor? | Araştırmacı | Kütüphane × kitap matrisi |
| 1.2 | Her yayınevine (CUP, Vrin, OUP, Brill) e-posta: "Kitabınız X'i dijitalleştirmeyi düşünüyor musunuz?" | Araştırmacı | Yanıt kaydı |
| 1.3 | Fransa'daki HT partnerlerini bul (varsa): BnF, Collège de France, ENS vb. | Araştırmacı | HT Fransız partner listesi |
| 1.4 | Hollanda'daki HT partnerlerini bul: Leiden, Amsterdam, Utrecht | Araştırmacı | HT Hollanda partner listesi |

### Aşama 2: Kütüphane ile Temas (2-4 hafta)

| # | Eylem | Beklenen Sonuç |
|---|---|---|
| 2.1 | Aşama 1'de bulunan kütüphanelere dijitalleştirme talebi gönder | Tarama programı varsa dahil edilme |
| 2.2 | HathiTrust Helpful Hints (hathitrust.org/help) üzerinden item request | HT destek ekibinden yanıt |
| 2.3 | Google Books partner kütüphanelerine doğrudan tarama talebi | Google Books'a dahil edilme |

### Aşama 3: Alternatif Kanıt Güçlendirme (devam)

Bu kitaplar HT'ye girene kadar mevcut LoC kanıtı korunur. Ek olarak:

| # | Eylem | Etki |
|---|---|---|
| 3.1 | WorldCat'teki OCLC kayıtlarını güçlendir (eksik alanları tamamla) | HT aramasında bulunabilirlik artar |
| 3.2 | Google Books'taki "snippet view" sayfalarından ek bibliyografik kanıt üret | Mevcut kanıtı güçlendirir |
| 3.3 | OpenLibrary edisyon kayıtlarını iyileştir (daha doğru ISBN/LCCN) | OL fallback güvenilirliğini artırır |

---

## 5. Başarı Ölçütleri

| Hedef | Zaman Çerçevesi | Metrik |
|---|---|---|
| Kısa vade | Hemen | 4 kitap için LoC kanıtı sağlam (zaten PASS — V5w) |
| Orta vade | 3-6 ay | En az 1 kitap HT'de görünür (muhtemelen Schmitt veya Millican) |
| Uzun vade | 6-12 ay | 4/4 kitap HT'de `hathitrust` kaynağıyla PASS |
| Fiili tetikleme | -- | `verify_delivery.py --check-references` çıktısında `by_source.hathitrust` ≥ 5 |

---

## 6. Dürüst Sınırlar

1. **HathiTrust'e kişi olarak kitap ekleyemezsiniz** — bu yalnızca 219+ kütüphane
   konsorsiyumunun tarama programları aracılığıyla mümkündür.
2. **Telifli kitaplar HT'de "limited access" olur** — tam metin yalnızca partner
   kütüphane kullanıcılarına açılır, herkese açık search + metadata kalır.
3. **Yayınevlerinin çoğu doğrudan tarama izni vermez** — Google Books veya kütüphane
   aracılığıyla taranması gerekir.
4. **Fransız/Vrin kitabı en zor hedef** — Fransız yayın ekosistemi Google Books
   kapsamında değil; BnF/Gallica alternatifi HT değil ama ulusal dijital kütüphane.
5. **Telif süreleri:** Fine 2012 (2082'de PD), Millican 2002 (2072'de PD),
   Schmitt 1972 (2042'de PD), Lagrée 1994 (2064'te PD).
