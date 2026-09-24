# PDF Determinizmi: SDE, `/ID` Kalıntısı ve Kanonik Hash — Neden Böyle?

> **Diátaxis: Explanation** — Anlayış-yönelimli. Bu belge kararların *nedenini*
> ve ölçümlerin nasıl bu tasarıma zorladığını anlatır; komut listesi değildir
> (o: [`Makefile.texlive`](Makefile.texlive) / [`Makefile.tectonic`](Makefile.tectonic)),
> alan-alan sözleşme de değildir (o: [`TEX_RENDER_PIPELINE.md`](TEX_RENDER_PIPELINE.md),
> [`ID_RESIDUAL_ACCEPTANCE.md`](ID_RESIDUAL_ACCEPTANCE.md)).
> Göç kararlarının tarihi: [`TEXLIVE_MIGRATION_PLAN.md`](TEXLIVE_MIGRATION_PLAN.md).

## 1. Sorun: "bu PDF bu kaynaklardan çıktı" iddiası neye dayanır?

Teslim paketine giren bir PDF'in işe yarar bir özelliği vardır: doğrulanabilir
olması. Doğrulamanın en güçlü biçimi, kaynağı yeniden derleyip **aynı baytları**
bulmaktır. Ama bu depoda ilk denemede bu iş çalışmadı — ve çalışmaması öğretici
oldu. Çünkü ortaya çıkan şey bir "derleme hatası" değil, **determinizmin kime
ait bir özellik olduğu** sorusuydu.

Bu depodaki cevap tek cümlede şudur:

> Determinizm, motorun tek başına bir özelliği değil, **(motor, kaynak, SDE,
> platform)** dörtlüsünün bir özelliğidir. Karşılaştırma bu yüzden *bağlam
> içinde* yapılır ve bağlam değişimi kanıt olarak **kaydedilir**, gizlenmez.

Aşağısı bu cümlenin nasıl ölçülerek kazanıldığının hikâyesidir.

## 2. Ham bayt eşitliği neden referans olamadı

İlk varsayım doğaldı: aynı `.tex` → aynı PDF baytları. Ölçüm bu varsayımı üç ayrı
noktadan kırdı (hepsi `docs/ID_RESIDUAL_ACCEPTANCE.md` §2 ve
`skills/reproducible-pdf-build/SKILL.md` içinde kayıtlı):

| Kaynak | Ölçüm | Sonuç |
|---|---|---|
| pdfTeX, 2 bağımsız koşum (SDE=0) | ham hash `da868c13…` ↔ `014bed9a…` | Tek fark trailer'daki `/ID [<32-hex> <32-hex>]` satırı |
| tectonic (SDE'siz, oturumlar arası) | `4ad65b9b…` → `6cfc6c0a…` | SDE verilmezse motor güncel zamanı gömer |
| qpdf `--remove-metadata` (aynı girdi, 3 koşum) | `b090ac01…` / `429984da…` / `509a47a6…` | "Metadata'yı soyup hash'le" katmanının kendisi kararsız |

Üçüncü satır tasarımı en çok etkileyenidir: eğer kararlı bir dolaylı gösterge
aranırken kullanılan araç kendisi kararsızsa, o araç **referans** olamaz. Bu
yüzden qpdf bu depoda yalnızca *sidecar kararı* için kullanılır ve şu kurala
bağlanır: sidecar yalnız ham hash değiştiğinde yenilenir; ham hash aynıysa
mevcut sidecar birebir kopyalanır. Kural, "kararsız aracı her repack'te yeniden
koşturma" hatasını yapısal olarak engeller.

## 3. `SOURCE_DATE_EPOCH` neyi çözer, neyi çözmez

`SOURCE_DATE_EPOCH` (SDE), reproducible-builds sözleşmesinin zamandan bağımsız
derleme anahtarıdır: derleme duvar-saati yerine sabit bir epoch kullanır, böylece
`/CreationDate` ve `/ModDate` gibi alanlar koşumdan koşuma değişmez.

Ama ölçüm şunu gösterdi: **SDE, pdfTeX'in `/ID` alanını sabitlemez.**
`SDE=0` ile iki koşumun ham bayt akışı hâlâ farklıdır ve aradaki tek fark `/ID`
satırıdır (`ID_RESIDUAL_ACCEPTANCE.md` §1). Bu yüzden "SDE'yi ver, sorun biter"
kestirmesi bu depoda yanlış çıktı; SDE gerekli ama yeterli değil.

Tarihsel not olarak: `skills/reproducible-pdf-build/SKILL.md` ilk yazıldığında
"SOURCE_DATE_EPOCH … `/ID`'yi de sabitler" diyordu. Bu, V5l döneminde SDE'siz
koşumların gözleminden türetilmiş bir **hipotezdi**; sonraki ölçüm hipotezi
çürüttü ve metin bu belgeyle birlikte düzeltildi. Bir "saha dersi" belgesinin
ölçümle güncellenmesi, deponun kendi kuralının (ölçmeden varsayma) doğal
sonucudur.

İkinci SDE ayrıntısı da tasarımı belirledi: SDE **açıkça** alt sürece iletilir
(`export`), çünkü aksi halde motor güncel zamanı gömer ve hash oturumdan oturuma
kayar. Makefile'larda varsayılan değer `git log -1 --format=%ct`'tir: derleme
duvar-saatine bağlı olmaz ve `SOURCE_DATE_EPOCH=...` verilerek **tarihsel bir
commit yeniden üretilebilir**.

## 4. Neden kanonik (`/ID`-nötr) hash referans oldu

`/ID` PDF trailer'ında bir **dosya kimliğidir**: şifreleme ve çapraz-referans
için vardır, *içeriğin* parçası değildir. İki PDF'in `/ID`'sinin farklı olması
metnin, sayfaların veya iddianın farklı olduğu anlamına gelmez. Bu yüzden:

- **Referans** `/ID`-nötr kanonik hash'tir: `/ID [<32-hex> <32-hex>]` deseni sabit
  bir değere (`<0…0>` çifti) indirgenir, sonra SHA-256 alınır. Böylece ölçülen
  şey içerik olur. Ölçüm bunu doğruladı: ham hash'leri farklı iki koşum, kanonik
  normalizasyondan sonra birebir aynı (`a75c3409…`) çıktı.
- **Ham hash bilgi düzeyindedir**: karar onun üzerine kurulmaz, ama raporda kalır
  — çünkü ham hash'in *değişip değişmemesi* başlı başına bir bulgudur.
- **Fail-safe** tasarımın kalbidir: `/ID` deseni eşleşmezse fonksiyon *ham hash*
  döner. Yani "nötrleyemedim" durumu asla "fark yok" gibi görünmez; hiçbir fark
  gizlenemez.

Aynı mantık iki alternatifi de eler: `qpdf --static-id` girdi `/ID`'sini korur
(rastgele girdiyi düzeltmez) ve `--remove-metadata` zaten kararsızdır (§2). Yani
bu depoda `/ID` nötrlemesi *kendi* kodunda, açık ve desen-çıpalı yapılır.

## 5. Kanonik hash neden hâlâ SDE'ye bağlı

Kanoniklik yalnız `/ID`'yi nötrler. `/Info` içindeki tarihler kanonik görünümde
**kalır**. Dolayısıyla kanonik hash SDE'ye bağlıdır ve bu bir kusur değil, kasıtlı
bir şeffaflıktır: iki koşum ancak *aynı SDE* ile karşılaştırılabilir. Bu yüzden
kabul defterinin her satırı **SDE bağlamını taşır** ve şu kural geçerlidir:

> Yeni bağlam (CI, font paketi, motor sürümü, farklı SDE) → **yeni satır**.
> Eskisinin üzerine asla yazılmaz.

Üzerine yazmak, determinizmin "hâlâ geçerli mi" sorusunu bir kanıt kaydından bir
iddiaya dönüştürürdü; defter tam olarak bunu engellemek için var.

## 6. Neden çapraz-motor ve çapraz-platform eşitlik *beklenmez*

Ölçüm: tectonic 0.17.0 ile pdfTeX'in kanonik hash'leri **hiçbir zaman** eşit
değildir — font/ligatür/hinting farkları (§3, `ID_RESIDUAL_ACCEPTANCE.md`).
Dahası trend verisi platform farkını da gösteriyor:

| Kayıt | tectonic kanonik | pdfTeX kanonik |
|---|---|---|
| darwin, 2026-09-17 | `ad8fca69…` | `a75c3409…` |
| linux (CI), 2026-09-20 | `ad8fca69…` | `092154a0…` |
| linux (CI), 2026-09-21 | `ad8fca69…` | `092154a0…` |

(3. satır 2. satırın birebir tekrarıdır — platform-kapsamlı uzlaşma
 değişmezinin *çalıştığının* kanıtı: aynı platform + aynı kaynak → aynı hash.)

tectonic iki platformda **birebir aynı** — motorun kendi iç-determinizminin güçlü
kanıtı. pdfTeX ise farklı: paket seti farklı (Homebrew TeX Live 2026 ↔ Debian
`texlive` + `cm-super`), dolayısıyla *aynı motor sürümü* bile *aynı bağlam*
değildir. Bu yüzden:

- **Uzlaşma (concordance) platform-kapsamlıdır**: aynı kaynak + **aynı platform**
  → kanonik hash'ler değişmemeli. Kıyas bu dar bağlamda yapılır.
- **Çapraz-platform eşitliği ihlal sayılmaz**: farklı paket setleri farklı hash
  üretebilir; bunu "kanıt" saymak ölçmeden varsaymak olurdu (deponun R3 kuralı).
  Kapı bunun yerine bilgilendirici bir not yazar; tectonic iki platformda
  eşitse bunu "güçlü kanıt" olarak raporlar.

Bu ayrım, kapının neden *platform kapsamını* (cutoff'tan sonra en az bir darwin
+ bir linux kaydı) zorunlu tuttuğunu da açıklar: amaç hash'lerin eşitliğini
dayatmak değil, **karşılaştırılabilir bir bağlamın varlığını** garanti etmektir.

> Uygulama-kod tutarlılığı notu: `record_determinism_trend.py` docstring'inin 3.
> maddesi bir dönem çapraz-platform eşitliğini zorunlu gibi anlatıyordu; kod
> (§4 yorumu) bunu açıkça ihlal saymıyordu. Docstring koda göre düzeltildi —
> bu doküman kodun gerçekte yaptığını anlatır.

## 7. `make accept` neden bir defter aramasıyla bitiyor

Motor geçişi kaçınılmazdır (tectonic → TeXLive). Kaçınılmaz olan bir şeyi
yasaklamak yerine **bilinçli** hale getirildi:

1. `check` önce taze bir 2× koşum kanıtı üretir (kanonik hash + `rerun_left=0`).
2. `accept` çıkan kanonik hash'i kabul raporunun hash geçiş defterinde arar.
3. Defterde yoksa **fail-closed** düşer: "yeni bağlam → deftere bilinçli satır
   ekle" der, sessizce kabul üretmez.

Tasarımın amacı bir yasak değil, bir **farkındalık kapısı**dır: hash değişimi
istenen bir olay olabilir (motor yükseltmesi) ya da istenmeyen bir olay
(font paketi kaydı, ortam sapması). Defter bu iki durumu birbirinden ayırır —
çünkü ikisi de "hash değişti" olarak görünür, ama yalnız biri hata.

## 8. Haftalık trend neden var, hangi değişmezi neye karşı korur

Tek seferlik kanıt bir ana iyi gelir; tehlikeli olan sessiz kaymadır. Bu yüzden
ölçüm append-only bir JSONL'e (`docs/determinism_trend/determinism_trend.jsonl`)
haftalık cron + `workflow_dispatch` ile yazılır ve üç değişmez fail-closed
tutulur:

| Değişmez | Neyi korur |
|---|---|
| **Gençlik** — son kayıt < 7 gün | Kanıt bayatlamasın: koşum atlanırsa "yeşil" görüntü kanıtsız kalır |
| **Uzlaşma** — aynı kaynak + aynı platform → aynı hash'ler | Sessiz motor/ortam sapması: kaynak değişmediyse hash de değişmemeli |
| **Platform kapsamı** — iki platformdan kayıt | Karşılaştırılabilir bağlam var olsun; tek platformda kıyaslanamaz |

Kayıtlar asla yeniden yazılmaz (append-only); güncellik `source_mtime` +
`source_sha256` ile izlenir. Böylece sapma, sürüm çıkışında değil **ilk
haftada** görünür.

## 9. Neden iki motor paralel yaşar, neden iki betik

- **Geri dönüş yolu**: `Makefile.tectonic` silinmedi; motor geçişi geri
  alınabilir olmalı (plan Faz 7). İki motorlu dönem boyunca hash defteri de iki
  motorun kanıt kaydı olarak durur.
- **İki deney betiği, tek sözleşme**: `texlive_determinism_test.sh` (pdfTeX) ve
  `canvas_determinism_test.sh` (canvas/Incidental Proof) ayrıdır, çünkü canvas
  kaynağı `fontspec` + yerel font kullanır ve **pdfTeX zinciri onu derleyemez**
  (engine-stratification bulgusu). Ama kanonik-`/ID` fallback'i, SDE semantiği ve
  `verdict=PASS|FAIL` dili iki betikte **aynı sözleşmedir** — pinned testler
  (`test_canvas_determinism.py`, `test_determinism_trend_canvas.py`) bunu
  tek-sözleşme olarak tutar.
- **Motor sürümü tek kaynaktır**: CI'daki tectonic pini (sürüm + sha256 digest)
  iki job'da birebir aynıdır ve test bunu pinler; sürüm yükseltmesi iki job'ı
  **birlikte** değiştirmek zorundadır.

## 10. Reddedilen alternatifler (ve neden)

| Alternatif | Neden reddedildi |
|---|---|
| Ham bayt eşitliğini referans yapmak | pdfTeX `/ID`'si yüzünden her repack'te kırmızı olur; sinyal gürültüye boğulur |
| Karşılaştırmayı qpdf'e devretmek (`--static-id`, `--remove-metadata`) | Biri kalıntıyı gidermiyor, diğeri kendisi kararsız (§2) |
| Strict determinizm kapısını varsayılan açmak | Bilinen-kararsız zincirde her repack'te yanlış-pozitif; bu yüzden opt-in (`--strict-determinism`) |
| Çapraz-platform/çapraz-motor eşitliği zorunlu tutmak | Ölçüm bunu desteklemiyor; "ölçmeden varsayma" ihlali olurdu |
| Motor değişiminde defter satırını güncellemek | Kanıt kaydını iddiaya çevirir; geçmiş bağlam kaybolur |
| Engine'i değiştirip kanonik hash'i "yeni baseline" ilan etmek | Tam da fark edilmesi gereken sessiz kaymayı meşrulaştırır |

## 11. Bunun bedeli (dürüst trade-off'lar)

- Kanonik hash **bağlama bağımlıdır**: SDE'yi değiştirirseniz hash değişir. Bu,
  "tek bir doğru hash" beklentisini kırar; karşılığında her hash'in *hangi
  bağlamda* üretildiği bilinir.
- Motor geçişleri **elle** (bilinçli) yürütülür: otomatik yeşil yok, bir satır
  ekleme kararı var.
- `/ID` nötrlemesi kriptografik olarak "gerçek bayt eşitliği" değildir; kanıtın
  gücü, kabul edilen kalıntının **tanımlı ve denetlenebilir** olmasından gelir
  (tek satır, desenle eşlenir, eşleşmezse fail-safe).
- Bu tasarım okuyucudan bağlam disiplini ister: iki hash'i karşılaştırmadan önce
  SDE, motor sürümü ve platform aynı mı diye bakmak gerekir.

## 12. Nerede ne var

| Parça | Yer |
|---|---|
| Kanonik `/ID`-nötr hash (pdfTeX) | `_calisma/CIKTI/texlive_determinism_test.sh` (`canonical_sha`) |
| Kanonik `/ID`-nötr hash (canvas) | `_calisma/CIKTI/canvas_determinism_test.sh` |
| SDE varsayılanı (`git log -1 --format=%ct`) | `docs/Makefile.texlive`, `docs/Makefile.tectonic` |
| Kırılım ölçümleri + hash geçiş defteri | `docs/ID_RESIDUAL_ACCEPTANCE.md` |
| Trend kaydı + üç değişmez | `record_determinism_trend.py`, `docs/determinism_trend/` |
| Haftalık CI kanıtı | `.github/workflows/determinism-trend.yml` (`canvas-determinism` job'ı) |
| Saha dersi (dışa dönük) | `skills/reproducible-pdf-build/SKILL.md` |
| Göç kararlarının tamamı | `docs/TEXLIVE_MIGRATION_PLAN.md` |

Nasıl yapılır sorusu için: [`TEX_RENDER_PIPELINE.md`](TEX_RENDER_PIPELINE.md) ve
`make -f docs/Makefile.texlive {pdf,check,accept,engineinfo}`.
