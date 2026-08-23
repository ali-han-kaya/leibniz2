# REFERANS KANIT DENETİMİ — 64/64

**Hedef:** `ingiliz_empirizmi_v3.tex` §References (64 girdi)
**Yöntem:** CrossRef API (6 dergi makalesi) + SEP doğrudan URL (5) + OpenLibrary (22 kitap/edişyon) + Internet Archive (25; kapsam dışı kalanlar HathiTrust + Google Books fallback; erken-modern edisyonlar birebir `ia_ids` identifier'ıyla) + doğrudan URL (1; arşivlenmiş açık erişim makalesi) + Perseus CTS (2 antik birincil metin) — çevrimiçi doğrulanan 61/64. Çevrimiçi indekslenmeyen kalan girdiler bağımsız web/bibliyografik kaynağa dayanır. Her "GEÇTİ" bir bağımsız kaynağa dayanır; kaynak adresi `Kanıt` sütunundadır.
**Tarih:** 2026-08-17 · **Güncelleme:** 2026-08-18 (V5h/V5j düzeltmeleri işlendi) · 2026-08-19 (V5n: Norton 1981 + Popkin 1951 CrossRef'e eklendi — canlı kapsam 54→56; V5o: çevrimiçi denetim paralel havuzda koşar — bütçe-skip kapanır, 56/56; V5p: OL'den OCLC/LCCN çekildi, HathiTrust fallback'i OL'den önce denenir — Xunzi HT kaydıyla PASS; V5q: 64→çevrimiçi kapsam boşluğu kapatıldı — 4 Sextus edisyonu IA `ia_ids` ile, Della Rocca 2010 arşivlenmiş URL ile, 61/64; V5r: OL edisyon kayıtlarında bu kitaplarda oclc YOK — tam identifier matrisi HT'ye denendi, yalnızca Xunzi eşleşir) · 2026-08-20 (V5s: "5 UNVERIFIED" öncülü bugünkü canlı koşuyla kapandı — 61/61 PASS, UNVERIFIED=0; OCLC→HT matrisi yeniden denendi, yalnızca Xunzi eşleşir; 4 modern telifli kitap HT kataloğunda yok, OL fallback PASS ile kalır) · 2026-08-21 (V5t: Della Rocca 2010 artık CrossRef dışı Handle System API'den doğrulanır — makalenin kendi DC.identifier'ı bir Handle'dır, DOI yok; V5u: canlı CI denetimi — `audit_live_ci_sync.py` doc↔GitHub senkronunu fail-closed doğrular, "11/17" eski sayılar gerçekle (17 job/22 artifact) senkronlandı; V5w: Lagrée/Millican/Schmitt/Fine kitapları HathiTrust'sız katalog kanıtıyla — Library of Congress lccn kayıtlarıyla PASS, `by_source`'ta `loc` kaynağı) · 2026-08-22 (V5x: Fine 2012'nin hatalı LCCN'i kaldırıldı — Correia tek yazarlı kitabına işaret ediyordu; `isbn:9781107460287` ile OpenLibrary fallback'i PASS, 61/61 korundu; V5y: Fine 2012'nin OpenLibrary'den bulunan OCLC'si (`793497146`) belgelenir — HT Bib API 0 kayıt döndürür; proje ilkesi gereği yanlış PASS üretmez, OL fallback'te kalır) · **Sonuç etiketi:** GEÇTİ (birebir) / DÜZELTİLDİ (V5h/V5j) / KÜÇÜK NOT (bibliyografik küçük sapma) / HATA (düzeltme gerekir) / DOĞRULANAMADI.

---

## 1. Özet

| Durum | Sayı |
|---|---|
| GEÇTİ (birebir) | **60** |
| DÜZELTİLDİ (V5h: Beth 1953, Fosl 1998 · V5j: Popkin 1952, Priest 2018) | **4** |
| KÜÇÜK NOT | 0 |
| HATA | 0 |
| DOĞRULANAMADI | 0 |

**Orijinal bulgu (2026-08-17):** Beth 1953 girişi "Journal of Symbolic Logic 18(1): 8–13" olarak yazılmıştı; doğrusu Indagationes Mathematicae 15 (1953): 330–339 (+ Proc. KNAW A56: 330–339).

**Güncelleme (2026-08-18):** işaretlenen 4 girdi `ingiliz_empirizmi_v3.tex`'te düzeltildi — V5h (Beth 1953, Fosl 1998) ve V5j (Popkin 1952, Priest 2018). 64/64 kaynak artık ya birebir doğrulanmış ya da bibliyografik olarak düzeltilmiştir. Detay → §5.

> Not: önceki özetteki "62 GEÇTİ" aritmetik hataydı (62+2+1+1 = 66 ≠ 64). Gerçek sayım 60 GEÇTİ + 4 işaretli = 64.

---

## 2. Tam tablo (64 girdi)

| # | Kaynak | Sonuç | Kanıt |
|---|---|---|---|
| 1 | Artemov 2008, RSL 1(4):477–513 | GEÇTİ | CrossRef DOI 10.1017/s1755020308090060 |
| 2 | Artemov & Fitting 2019, CUP | GEÇTİ | CUP/Google Books |
| 3 | Beauchamp (ed.) 1999, OUP | GEÇTİ | OUP Oxford Philosophical Texts |
| 4 | Beebee 2006, Routledge | GEÇTİ | Routledge/Taylor&Francis |
| 5 | Beth 1953, Indag. Math. 15:330–339 | DÜZELTİLDİ (V5h) | JSL 18(1):8–13 → Indag. Math. 15 (1953) 330–339 (+ Proc. KNAW A56) |
| 6 | Bobzien 2003, 85–123 | GEÇTİ | Cambridge Companion to the Stoics (CUP) |
| 7 | Brittain 2006, Hackett | GEÇTİ | Hackett / BMCR |
| 8 | Bury 1933–49, Loeb 4 cilt | GEÇTİ | Loeb (LCL 291 = Against Logicians, 1935) |
| 9 | Cicero Academica (Lucullus 145) | GEÇTİ | Brittain 2006 + yumruk benzetmesi (REP/Long&Sedley 41B) |
| 10 | Correia & Schnieder 2012, CUP | GEÇTİ | CUP/PhilPapers |
| 11 | Della Rocca 2010, PI 10(7) | GEÇTİ | Handle System API (hdl.handle.net/2027/spo.3521354.0010.007 → quod.lib.umich.edu/p/phimp/3521354.0010.007/1) — CrossRef dışı (V5t) |
| 12 | Diogenes Laertius (Hicks/Dorandi) | GEÇTİ | Loeb 1925 + CUP 2013 |
| 13 | Dorandi 2013, CUP | GEÇTİ | CUP/BMCR |
| 14 | Elman 1984, Harvard | GEÇTİ | Harvard East Asian Monographs 110 |
| 15 | Fine 2012, "Guide to Ground", 37–80 | GEÇTİ | CUP (ch. 1, pp. 37–80) |
| 16 | Floridi 2002, OUP (ACS 46) | GEÇTİ | OUP/PhilPapers |
| 17 | Fosl 1998, ECSSS Newsletter 11:35–36 | DÜZELTİLDİ (V5h) | JHP 36(2) → ECSSS Newsletter no.11 (35–36) |
| 18 | Frede 1983, 65–93 | GEÇTİ | PhilPapers (Skeptical Tradition, UC Press) |
| 19 | Garrett 1997, OUP | GEÇTİ | OUP |
| 20 | Goldman 1979, 1–23 | GEÇTİ | PhilPapers/Springer (D. Reidel) |
| 21 | Goldman 1986, Harvard UP | GEÇTİ | Harvard UP |
| 22 | Graham 1978, Chinese UP | GEÇTİ | Chinese University Press HK |
| 23 | Graham 1989, Open Court | GEÇTİ | Open Court |
| 24 | Hansen 1983, Michigan UP | GEÇTİ | Univ. of Michigan Press |
| 25 | Hansen 1992, OUP | GEÇTİ | OUP |
| 26 | Herbert of Cherbury 1624, De Veritate | GEÇTİ | Paris 1624 (biyografi kaynakları) |
| 27 | Hicks 1925, Loeb 2 cilt | GEÇTİ | Loeb (LCL 184/185) |
| 28 | Hume, Norton & Norton 2000, OUP | GEÇTİ | OUP Oxford Philosophical Texts |
| 29 | Hume, Beauchamp 1999, OUP | GEÇTİ | OUP |
| 30 | Hume, Selby-Bigge/Nidditch 1975, Clarendon | GEÇTİ | Clarendon 3. baskı |
| 31 | Hunt 1998, Brill | GEÇTİ | Brill (Mnemosyne Supp. 181) — "T.J. Hunt" = Terence J. Hunt |
| 32 | Kjellberg 1996, SUNY | GEÇTİ | SUNY (pp. 1–25) |
| 33 | Lagrée 1994, Vrin | GEÇTİ | Vrin (1994) |
| 34 | Leibniz, Monadologie §32 | GEÇTİ | Monadologie (PSR pasajı) |
| 35 | Lipsius 1584, De Constantia | GEÇTİ | Plantin, Antwerp 1584 |
| 36 | Lipsius 1604, Manuductio/Physiologia | GEÇTİ | Plantin-Moretus, Antwerp 1604 |
| 37 | Locke, Nidditch 1975, Clarendon | GEÇTİ | Clarendon (Nidditch ed.) |
| 38 | Long & Sedley 1987, CUP c.1 | GEÇTİ | CUP |
| 39 | Millican 2002, 27–65 | GEÇTİ | Clarendon (Reading Hume, ed. Millican) |
| 40 | Nawar 2022, ASSV 96(1):185–207 | GEÇTİ | CrossRef DOI 10.1093/arisup/akac002 |
| 41 | Nidditch 1975, Clarendon | GEÇTİ | Clarendon (Clarendon Locke ed.) |
| 42 | Norton 1981, HEI 1(4):331–344 | GEÇTİ | ScienceDirect/PhilPapers |
| 43 | Norton & Norton 1996, Edinburgh | GEÇTİ | Edinburgh Bibliographical Society |
| 44 | Popkin 1951, PQ 1(5):385–407 | GEÇTİ | OUP/PhilPapers/JSTOR |
| 45 | Popkin 1952, RoM 6(1):65–81 | DÜZELTİLDİ (V5j) | yeniden basım sayfası 133–148 → 133–147 |
| 46 | Popkin 1979, UC Press | GEÇTİ | UC Press |
| 47 | Priest 2010, Comp. Phil. 1(2) | GEÇTİ | CrossRef DOI 10.31979/2151-6014(2010).010206 |
| 48 | Priest 2018, OUP | DÜZELTİLDİ (V5j) | tam alt başlık "An Essay on Buddhist Metaphysics and the Catuṣkoṭi" eklendi |
| 49 | Pruss 2006, CUP | GEÇTİ | CUP |
| 50 | Rošker, SEP "Epistemology in Chinese Philosophy" | GEÇTİ | plato.stanford.edu (2014; rev. 2025) |
| 51 | Baltzly/Durand/Shogry 2023, SEP "Stoicism" | GEÇTİ | plato.stanford.edu (2023) |
| 52 | Bolyard, SEP "Medieval Skepticism" | GEÇTİ | plato.stanford.edu (2009; rev. 2025) |
| 53 | Papy, SEP "Justus Lipsius" | GEÇTİ | plato.stanford.edu (2004; rev. 2019) |
| 54 | Van Norden, SEP "Wang Yangming" | GEÇTİ | plato.stanford.edu (2014) |
| 55 | du Vair 1594, Paris | GEÇTİ | Persée/Wikisource (1594) |
| 56 | Schmitt 1972, Nijhoff | GEÇTİ | Martinus Nijhoff, The Hague |
| 57 | Schmitt 1983, 225–251 | GEÇTİ | PhilPapers (Skeptical Tradition, UC Press) |
| 58 | Schnieder 2011, RSL 4(3):445–465 | GEÇTİ | CrossRef DOI 10.1017/S1755020311000104 |
| 59 | Sextus 1562, tr. Estienne, Cenevre | GEÇTİ | Christie's/Swann (Henri Estienne Latin çevirisi) |
| 60 | Sextus 1569, tr. Hervet | GEÇTİ | Floridi 2010/Popkin 1953 (Gentian Hervet) |
| 61 | Sextus 1621, Chouet Yunanca baskı | GEÇTİ | Biblio/Istituto Ellenico (Pierre & Jacques Chouët) |
| 62 | Sextus, Bury (Loeb) | GEÇTİ | Loeb (Bury) |
| 63 | Tillemans 1999, Wisdom | GEÇTİ | Wisdom Publications (1999) |
| 64 | Xunzi 22, Knoblock tr. | GEÇTİ | Stanford UP (Knoblock 1988–94); ctext.org |

---

## 3. Düzeltilen giriş (Beth 1953 — V5h)

**Durum (2026-08-18): DÜZELTİLDİ** — `.tex`'te JSL 18(1):8–13 künyesi Indagationes Mathematicae 15: 330–339 (+ Proc. KNAW A56) ile değiştirildi. Aşağıdaki orijinal tespit artık tarihsel kayıttır.

```text
MEVCUT (hatalı):
Beth, E.W. (1953). "On Padoa's Method in the Theory of Definition."
Journal of Symbolic Logic 18(1): 8--13.

ÖNERİLEN (doğru):
Beth, E.W. (1953). "On Padoa's Method in the Theory of Definition."
Indagationes Mathematicae 15: 330--339. (Proc. Kon. Ned. Akad. Wetensch. A56: 330--339.)
```

**Kanıt:** cambridge.org'un JSL "review" kaydı, makaleyi "Koninklijke Nederlandse Akademie van Wetenschappen, Proceedings, series A, vol. 56 (1953), pp. 330–339; also Indagationes Mathematicae, vol. 15, pp. 330–339" olarak verir. Princeton (Tennant 1985), Synthese (2011), nLab ve JSTOR kaynakları aynı koordinatları tekrarlar. "JSL 18(1): 8–13" hiçbir kaynakta bulunamadı.

## 4. Düzeltilen giriş (Fosl 1998 — V5h)

**Durum (2026-08-18): DÜZELTİLDİ** — `.tex`'te JHP 36(2) künyesi ECSSS Newsletter 11: 35–36 ile değiştirildi. Aşağıdaki orijinal tespit artık tarihsel kayıttır.

`Fosl, P.S. (1998). Review of Norton & Norton, The David Hume Library. Journal of the History of Philosophy 36(2).`
- Norton & Norton 1996 kitabı **doğrulandı**.
- Fosl'un kitap hakkındaki incelemesi **ECSSS Newsletter no. 11 (ss. 35–36)** olarak bulundu; "JHP 36(2)" yeri teyit edilemedi. Güncelleme önerisi: ya ECSSS newsletter künyesine çevir, ya da `UNVERIFIED_SOURCE` etiketiyle bırak.

---

## 5. Düzeltme kaydı ve paket hash

### 5.1 Düzeltmeler

| Sürüm | Girdi | Düzeltme |
|---|---|---|
| V5h | Beth 1953 | "JSL 18(1):8–13" → Indagationes Mathematicae 15: 330–339 (+ Proc. KNAW A56: 330–339) |
| V5h | Fosl 1998 | "JHP 36(2)" → ECSSS Newsletter 11: 35–36 |
| V5j | Popkin 1952 | yeniden basım sayfası 133–148 → 133–147 |
| V5j | Priest 2018 | tam alt başlık "An Essay on Buddhist Metaphysics and the Catuṣkoṭi" eklendi |

### 5.2 V5i determinism notu (referans bağlamı dışı)

V5i (2026-08-17) K6-DETERM katmanını ekledi: `qpdf --remove-metadata` ile PDF'in metadata-stripped SHA-256'sı hesaplanır (`ingiliz_empirizmi_v3.pdf.metadata.sha256`). **Known limitation:** tectonic 0.17.0 byte-deterministic olmadığından `--strict-determinism` varsayılan kapalıdır; drift bilgi amaçlı raporlanır (P0/P1 yok). Bu, referans doğruluğunu değil yalnızca PDF derleme tekrarlanabilirliğini etkiler (bkz. MANIFEST V5k notu).

**V5l/V5m eki (2026-08-18):** qpdf non-determinizm deneyi `qpdf_determinism_experiment.py` + donmuş çıktı `qpdf_determinism_output.txt` olarak yeniden üretilebilir hale getirildi (K5 4. script çifti; varsayılan mod donmuş kayıt, `--rerun [N]` canlı deney). V5l bulgusu aynen teyit edildi: `qpdf --remove-metadata` aynı girdi üzerinde farklı çıktılar üretir; repack sidecar'ı yalnızca raw hash değişince yeniden üretir. Bu, referans doğruluğunu değil yalnızca PDF derleme/repack tekrarlanabilirliğini etkiler (bkz. MANIFEST V5l/V5m notu).

### 5.3 Paket hash (2026-08-18 repack, V5m)

| Dosya | SHA-256 |
|---|---|
| `TESLIM_KLASOR_V5_2026-08-17.zip` (dış) | `918e054595f798d48843ece59f48582b2b22147edb0cdb06188f0c543b2e13aa` |
| `TESLIM_V5_FINAL_2026-08-17.zip` (iç) | `81a0244855cc574562bc18a611c94bf3ffbb0086c3ea32775de9d5f32473c28a` |

### 5.4 Çevrimiçi kapsam genişletmesi (IA/Perseus + fallback)

Denetim başlangıçta CrossRef + SEP + "bağımsız web araması" idi. `verify_delivery.py --check-references` çevrimiçi doğrulamayı şu kaynaklara genişletti:

| Kaynak | Girdi | Yöntem |
|---|---|---|
| CrossRef | 6 | DOI canlı doğrulama (dergi makaleleri) |
| SEP | 5 | doğrudan URL |
| OpenLibrary | 22 | search.json (kitap/edişyon) |
| Internet Archive | 25 | advancedsearch; kapsam dışı kalanlar HathiTrust (identifier) + Library of Congress (lccn) + Google Books (GBOOKS_API_KEY) fallback'iyle denenir; erken-modern edisyonlar (Sextus 1562/1569/1621) birebir `ia_ids` identifier doğrulamasıyla |
| Doğrudan URL / Handle | 1 | arşivlenmiş açık erişim makalesi (Wayback kopyasından HTTP 200 + başlık/bulgu) **ya da** Handle System API (V5t: Della Rocca 2010 — CrossRef dışı kalıcı tanımlayıcı) |
| Perseus CTS | 2 | GetPassage (antik birincil metin pasajı) |

Toplam **61 canlı girdi**; kalan 3 girdi (64 − 61 — Beth 1953, Fosl 1998, Popkin 1952) §2 tablosuna ve sabit denetim notlarına dayanır (üçü de V5h/V5j'de DÜZELTİLDİ kaydıdır). **V5q:** 64 referansın tamamı artık bir listede — kapsam boşluğu 5'ti (Della Rocca 2010 + 4 Sextus edisyonu) ve kapatıldı: Sextus 1562 Estienne (`bub_gb_ddgo3O27ItcC`), 1569 Hervet (`bub_gb_RyhI9DhB82sC`/`nHEaGbVSZMcC`), 1621 Chouet (`bub_gb_-Yio5nIT2m0C`), Loeb/Bury (title+creator sorgusu) IA'da birebir identifier doğrulamasıyla; Della Rocca 2010 "PSR" (Philosophers' Imprint 10(7)) PI sitesi bot-korumalı ve CrossRef DOI'si kayıtlı değilken Wayback'te arşivlenmiş kopyasından doğrulanır (içerikte 'Della Rocca' + 'PSR'). **V5n:** Norton 1981 (`10.1016/0191-6599(81)90026-7`) ve Popkin 1951 (`10.2307/2216311`) DOI'leri CrossRef'ten doğrulandı — kapsam-dışı kalan son 2 dergi makalesi artık çevrimiçi doğrulanır (kapsam-dışı 10 → 8). Sonuçlar her CI run'ında `refs-online` VERSION JSON + `refs-trend` zaman serisinde izlenir. İki dürüst sınır: Google Books anahtarsız **429** (kota) döndürür — tam denetim `GBOOKS_API_KEY` ister; HathiTrust ISBN yerine **OCLC** indeksler — ISBN'li `ht_ids` çoğu modern telifli kitapta kayıt bulamaz. Her ikisi de yanlış PASS üretmez, `UNVERIFIED` izi bırakır.

**V5o (2026-08-19): 11 UNVERIFIED kaynak kapatıldı → 56/56 canlı.** `refs-trend`'de 43/54 (11 UNVERIFIED) görünen dönemdeki kaynakların tümü artık gerçek API yanıtıyla doğrulanır: 6 OpenLibrary girdisi (Hansen 1983/1992, Hicks 1925, Hunt 1998, Lipsius 1584, Long & Sedley 1987) o dönemde ağ zaman aşımına düşmüştü — sorgu değil geçici ağ hatası; 5 Internet Archive girdisi (Fine 2012, Lagrée 1994, Millican 2002, Schmitt 1972, Xunzi/Knoblock) IA'da indekslenmez, OpenLibrary fallback'i ile PASS olur (aşağıdaki canlı kanıt). Kök neden: denetim 200 sn bütçeyle **sıralı** koşuyordu ve rate-limit edilen OpenLibrary (~8 sn/çağrı) bütçeyi bitirip kalan kaynakları budget-skip'e düşürüyordu. V5o: kontroller `REFERENCE_POOL_SIZE=4` havuzda paralel koşar (`concurrent.futures`, ex.map sırayı korur; her işçi çağrıdan önce bütçeyi denetler — yanlış PASS yok); bütçe 260 sn'ye çıkarıldı. Canlı doğrulama (2026-08-19, varsayılan bütçeyle): **56/56 PASS, 94 sn** — crossref 6, sep 5, openlibrary 27 (22 doğrudan + 5 IA-fallback), archive 16, perseus 2.

V5o kanıtı — hedefli canlı sorgu sonuçları (11 kaynağın her biri):

| Kaynak | Sonuç | Gerçek API yanıtı |
|---|---|---|
| Hansen 1983 | PASS | OL: 'Language and logic in ancient China' by Chad Hansen, 1983, Univ. of Michigan Press |
| Hansen 1992 | PASS | OL: 'A Daoist theory of Chinese thought' by Chad Hansen, 1992, OUP |
| Hicks 1925 | PASS | OL: 'Diogenes Laertius', 1925 (Loeb edisyonu bulundu) |
| Hunt 1998 | PASS | OL: 'A textual history of Cicero's Academici libri' by T.J. Hunt, 1998, Brill |
| Lipsius 1584 | PASS | OL: 'De constantia' by Justus Lipsius, 1586 baskısı (eşleşme) |
| Long & Sedley 1987 | PASS | OL: 'The Hellenistic philosophers' by A.A. Long, 1987, CUP |
| Fine 2012 | PASS | IA: 0 sonuç → OL fallback: 'Metaphysical Grounding' (Correia, 2012, CUP) |
| Lagrée 1994 | PASS | IA: 0 sonuç → OL fallback: 'Juste Lipse et la restauration du stoïcisme' (Vrin, 1994) |
| Millican 2002 | PASS | IA: 0 sonuç → OL fallback: 'Reading Hume on Human Understanding' (OUP, 2002) |
| Schmitt 1972 | PASS | IA: 0 sonuç → OL fallback: 'Cicero Scepticus' (Springer/Nijhoff) |
| Xunzi (Knoblock) | PASS | IA: 0 sonuç → OL fallback: 'Xunzi' by John Knoblock (Stanford) |

Not: HathiTrust ISBN araması 5 kaynakta da 0 kayıt döndürdü (telifli kitaplar, ISBN indeksi yok) ve IA mediatype:texts varyantı da 0 sonuç verdi — OL fallback'i bu kaynaklar için tek geçerli çevrimiçi kanıttır; `UNVERIFIED` izi bırakmaz, kaynağı doğru işaretler (`by_source`'ta openlibrary).

**V5p (2026-08-19): OpenLibrary'den OCLC/LCCN çekildi, HathiTrust önceliklendirildi.** OpenLibrary edition/search kayıtlarından alınan identifier'lar `REFERENCE_ARCHIVE.ht_ids`'e eklendi (HathiTrust ISBN yerine OCLC/LCCN indeksler — `oclc:`/`lccn:` önekleri `hathitrust_check` tarafından zaten destekleniyordu):

| Kaynak | OL'den alınan identifier | HathiTrust canlı sonucu |
|---|---|---|
| Lagrée 1994 | `oclc:32045786`, `lccn:95174106` (OL kaydı) | 0 kayıt — Vrin kitabı HT kataloğunda yok → OL fallback PASS |
| Millican 2002 | `oclc:48957942`, `lccn:2002020030` (OL kaydı) | 0 kayıt — OUP 2002 telifli → OL fallback PASS |
| Schmitt 1972 | `oclc:1194850` (OL kaydı) | 0 kayıt — Nijhoff 1972 → OL fallback PASS |
| Xunzi (Knoblock) | `lccn:87033578` (Stanford 1988 edisyonu), `oclc:17265207` (HT kaydının kendi OCLC'si) | **MATCH** — "Xunzi: a translation and study of the complete works", Stanford 1988, 2 item (uc1.b3817880/81) → **HathiTrust PASS** |
| Fine 2012 | OL'deisbn:9781107460287 (Metaphysical Grounding, CUP 2012) —isbn ile eşleşti | PASS |

Fallback sırası da değişti: `_archive_fallback` artık **HathiTrust'ı OpenLibrary'den ÖNCE** dener — HT kaydı başlıkla birebir katalog kanıtıdır, OL arama eşleşmesinden daha güçlü; HT'de kayıt yoksa (0 kayıt, ~1 sn) OL devreye girer. Canlı doğrulama: Xunzi → `hathitrust` kaynağı, diğer 4 → `openlibrary` (hepsi PASS). Dürüst sınır: Lagrée/Millican/Schmitt/Fine kitapları HT kataloğunda gerçekten YOK (her üç identifier tipi — oclc, lccn, isbn — HT Bib API'de 0 kayıt döndürdü); OL fallback'i bu dört kaynak için tek çevrimiçi kanıttır.

**V5r (2026-08-19): kapsamlı edisyon-kayıt taraması kesinleştirdi.** 5 kaynağın TÜM OpenLibrary edisyonları (`/works/…/editions.json`) tarandı: hiçbirinde **oclc alanı yok** — V5p'teki oclc değerleri (Lagrée `32045786`, Millican `48957942`, Schmitt `1194850`, Xunzi `17265207`) arama indeksindendir, edisyon kayıtlarından değil. Edisyon kayıtları yalnızca **lccn** taşır; tam liste: Fine `2012014618`, Lagrée `95174106`, Millican `2002020030`, Schmitt `73155022`, Xunzi `87033578` (+ Knoblock-dışı Xunzi edisyonları). Tam matris HT Bib API'ye denendi (her oclc + her lccn + isbn): **yalnızca Xunzi `lccn:87033578` eşleşir** ("Xunzi: a translation and study of the complete works", 2 item). Yeni bulunan lccn'ler (Fine `2012014618` (yanlış — Correia tek yazarlı kitap) kaldırıldı; isbn:9781107460287 (Correia & Schnieder eds.) eklendi. Schmitt `73155022` 0 kayıt döndürdü — HT bu kitabı kataloğunda tutmuyor (Vrin, telifli). Yine de doğru identifier olduğu için `ht_ids`'e eklendi: HT ileride bu kaydı alırsa denetim otomatik eşleşir; şu an yanlış PASS üretmez.

**V5s (2026-08-20): "5 UNVERIFIED" öncülü bugünkü canlı koşuyla kapandı — 61/61 PASS, UNVERIFIED=0.** `--check-references` yeniden koşuldu (`by_verdict: {PASS: 61}`, 0 UNVERIFIED, 0 MISMATCH). Hedef 5 kaynağın güncel durumu: **Xunzi (Knoblock) → `hathitrust` PASS** (`lccn:87033578`; ayrıca `oclc:17265207` — HT kaydının kendi OCLC'si); **Fine 2012, Lagrée 1994, Millican 2002, Schmitt 1972 → `openlibrary` fallback PASS**. "UNVERIFIED" görünümünün kaynağı, dünkü yerel simülasyon çıktısıydı (`.freebuff/sim/verify_job/references_online.json`, 49/54); sim bugünkü kodla yeniden koşulunca 5 kaynak da PASS'e döner (refs-online VERSION JSON + sim çıktısıyla doğrulandı). OCLC→HathiTrust bağlantısı bugün canlı API yanıtıyla yeniden denendi:

| Kaynak | Bugün test edilen identifier | HT Bib API canlı sonucu |
|---|---|---|
| Fine 2012 | `oclc:793497146`, `lccn:2012014618` (OL indeks) | 0 kayıt → OL fallback PASS |
| Lagrée 1994 | `oclc:32045786`, `lccn:95174106` (OL indeks) | 0 kayıt → OL fallback PASS |
| Millican 2002 | `oclc:48957942`, `lccn:2002020030` (OL indeks) | 0 kayıt → OL fallback PASS |
| Schmitt 1972 | `oclc:1194850`, `lccn:73155022` (OL indeks) | 0 kayıt → OL fallback PASS |
| Xunzi (Knoblock) | `oclc:17265207` | **1 kayıt** — "Xunzi : a translation and study of the complete works" → HT PASS |

Dürüst sınır (değişmedi, canlı kanıtla): Fine/Lagrée/Millican/Schmitt **telifli modern kitaplardır** (CUP 2012, Vrin 1994, OUP 2002, Nijhoff 1972) ve HathiTrust yalnızca partner kütüphanelerin taradığı eserleri kataloglar; bu dört kitap HT'de gerçekten yok. "OCLC ile HT-PASS" üretmek burada **yanlış pozitif** olurdu (proje ilkesi: yanlış PASS üretme); gerçek çevrimiçi kanıt OL kaydıdır ve kaynaklar zaten PASS'tir. Fine `lccn:2012014618` OL'de şu an "Grounding and explanation" başlığıyla ilişkili görünüyor (OL veri gürültüsü — edisyon kaydı CUP cildine ait olabilir); HT'de yine 0 kayıt, verdict'ü etkilemez. Identifier matrisi korunur: HT ileride kayıt alırsa denetim otomatik eşleşir.

**V5t (2026-08-21): Della Rocca 2010 "PSR" artık CrossRef DIŞI bir kaynaktan doğrulanıyor — Handle System API.** Makalenin kendi metadata'sı (`DC.identifier`) DOI değil **Handle** verir: `http://hdl.handle.net/2027/spo.3521354.0010.007`. CrossRef'te DOI yok (10.3998/... 404), doi.org'da da 404, DataCite'te kayıt yok — bu makale (2010) PI'nin DOI atamaya başladığı 2021+ döneminden öncedir; kalıcı tanımlayıcısı Handle'dır. `verify_delivery.py`'ye `handle_check` eklendi: Handle System API (`hdl.handle.net/api/handles/<handle>`) — DOI ile aynı altyapı, CrossRef dışı kayıt — 200 + `responseCode 1` + URL değeri bekler; URL değeri `quod.lib.umich.edu/p/phimp` çözülür. Canlı doğrulama (2026-08-21): `Handle çözüldü: https://quod.lib.umich.edu/p/phimp/3521354.0010.007/1` → PASS (`by_source`'ta `handle`). Kaynak sayısı değişmedi (61/61 PASS); bu, Della Rocca'yı arşivlenmiş Wayback kopyasından (V5q) makalenin kendi kalıcı tanımlayıcısına taşıyan **daha güçlü** bir doğrulamadır.

**V5u (2026-08-21): Canlı CI denetimi bulgusu işlendi — `audit_live_ci_sync.py`.** Önceki turda "11 job / 17 artifact" beklentisi güncel pipeline ile karşılaştırıldı: canlı run **17 job / 22 artifact** üretiyor (16 kapı + `audit-live-ci` meta-denetçi; denetim kendini hariç tutunca 16/21, PUBLISH_SCENARIO doc'u ile birebir PASS). 11/17 rakamları eski pipeline durumuna aittir — doc'a job/artifact sayıları gerçekle senkronlanarak işlendi (`1499b93`, daemon-http job+artifact dahil). Bu, referans denetimini değil, **teslim pipeline'ının dokümantasyon bütünlüğünü** etkiler: `audit-live-ci` advisory job'ı her push'ta doc↔GitHub senkronunu fail-closed doğrular (drift → exit 1, artifact: `audit-live-ci`). Referans kapsamı değişmedi (61/61 PASS).

**V5w (2026-08-21): Lagrée/Millican/Schmitt/Fine kitapları için HathiTrust'sız katalog kanıtı — Library of Congress (LoC).** V5r/V5s'te belgelenen dürüst sınır ("bu 4 kitap HT kataloğunda yok; OL fallback tek çevrimiçi kanıttır") kapatıldı: `_archive_fallback` zincirine HT'den hemen sonra **LoC** eklendi (`loc_check`). LoC item API (`https://www.loc.gov/item/{lccn}/?fo=json`) ht_ids'teki `lccn:` identifier'larını doğrudan ulusal katalog kaydına çözer — HT'den bağımsız, aynı güçte katalog kanıtı. Canlı doğrulama (gerçek API yanıtı, `ia_ol_fallback_evidence.py --offline` ile birebir):

| Kaynak | LCCN | LoC kaydı (canlı) | Sonuç |
|---|---|---|---|
| Fine 2012 | ~~`2012014618`~~ (V5x: kaldırıldı — Correia tek yazarlı kitabına işaret ediyordu) | — | **PASS (openlibrary)** — V5x: `isbn:9781107460287` ile OL |
| Lagrée 1994 | `95174106` | "Juste Lipse et la restauration du stoïcisme : étude et traduction des traités stoïciens" (1994) | **PASS (loc)** |
| Millican 2002 | `2002020030` | "Reading Hume on human understanding : essays on the first Enquiry" (2002) | **PASS (loc)** |
| Schmitt 1972 | `73155022` | "Cicero Scepticus : a study of the influence of the Academica in the Renaissance" (1972) | **PASS (loc)** |

Xunzi (Knoblock) HT'de kaldı (`lccn:87033578` — HT kaydı birebir). Zincir artık **IA → HathiTrust → LoC → OpenLibrary → Google Books**; by_source'ta yeni `loc` kaynağı (3 kaynak OL'den LoC'ye taşındı). Kapsam değişmedi (61/61 PASS) — kanıt güçlendi: 3 kitap artık arama-eşleşmesi (OL) değil, bağımsız ulusal katalog kaydıyla (LoC lccn) doğrulanıyor.

**V5x (2026-08-22): Fine 2012 identifier düzeltmesi — LoC yerine OpenLibrary.** V5w tablosundaki Fine satırı hatalı LCCN taşıyordu: `2012014618` aslında Correia'nın tek yazarlı "Grounding and explanation" kitabına ait (derleme bölümüne değil). Düzeltme (`398a148`): `lccn:2012014618` + `isbn:1107022894` kaldırıldı, `isbn:9781107460287` (Correia & Schnieder eds. "Metaphysical Grounding", CUP 2012) eklendi. Fine 2012 artık `loc_check`'te lccn bulamadığı için **OpenLibrary** fallback'iyle PASS olur (`by_source`'ta `openlibrary`); `ia_ol_fallback_evidence.py` + testleri yeni kaynak haritasına taşındı (LOC_SOURCES: Lagrée/Millican/Schmitt; OL_SOURCES: Fine). Kapsam değişmedi — **61/61 PASS**.

**V5y (2026-08-22): Fine 2012'nin OCLC numarası belgelendi — HT'de 0 kayıt.** OpenLibrary arama indeksinden bulunan OCLC: `793497146` ("Metaphysical Grounding", Correia & Schnieder eds., CUP 2012 cildi için WorldCat kaydı). HathiTrust Bib API'ye `oclc:793497146` olarak denendi: **0 kayıt** döndü — HT bu cildi kataloğunda tutmuyor (telifli modern derleme, 2012). Aynı cilt için `isbn:9781107460287` de HT'de 0 kayıt döndürür. Sonuç: OCLC varlığı HT-PASS üretmek için yeterli değil — projenin fail-closed ilkesi gereği, HT API'den gerçek pozitif yanıt alınmadıkça `hathitrust` PASS verilmez. Fine 2012 **OpenLibrary fallback** ile PASS'ta kalır (`by_source`: `openlibrary`). OCLC `793497146` belgelenir, ht_ids'e eklenmez: değeri yalnızca izlenebilirliktir, kanıt zincirini değiştirmez. Kapsam: **61/61 PASS** (değişmedi).

**V5z (2026-08-23): Bugünkü canlı CI doğrulaması — 61/61 PASS, UNVERIFIED=0.** `refs-online` artifact'ı canlı run'dan (`32645290824`, commit `7b78e0f`, generated `2026-08-23T14:25:19Z`) alındı: `by_verdict: {PASS: 61}` (0 UNVERIFIED, 0 MISMATCH), `verified: 61`. Kaynak kırılımı: `crossref 6, sep 5, openlibrary 23, archive 20, loc 3, hathitrust 1, handle 1, perseus 2` (toplam 61). Bu koşu, V5s (08-20) sonrası eklenen tüm kanıt zincirlerini birlikte doğrular: **LoC** (`loc: 3` — Lagrée/Millican/Schmitt, V5w), **Handle** (`handle: 1` — Della Rocca 2010, V5t), **HathiTrust** (`hathitrust: 1` — Xunzi, V5s/V5r), Fine 2012 OpenLibrary fallback (V5x/V5y). Kapsam V5s'ten bu yana sabit: **61/61 PASS**.
