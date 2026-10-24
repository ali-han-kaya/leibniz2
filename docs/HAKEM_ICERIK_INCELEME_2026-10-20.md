# İÇERİK HAKEM İNCELEMESİ — 2026-10-20

**İncelenen nesne:** `Stoic_Hume_Formal_Section_2026-08-17/` paketinin felsefi
içeriği — `core_section.tex` (885 satır), `L0_Lplus_spec.md`, `model_check_report.md`,
`core_formal_model_check.py` + donmuş çıktıları.

**Sorular:** (a) iki büyük önermenin geçerliliği, (b) karşımodel tekliği iddiası,
(c) kavram merdiveninin yeterliliği.

**Yöntem:** Metin satır satır okundu; her ispat elle denetlendi; sayısal
iddialar paketteki scriptlerden **bağımsız** kaba-kuvvetle yeniden üretildi;
üç paket scripti donmuş çıktılarıyla bayt bayt karşılaştırıldı. Tarihsel-filolojik
doğruluk (alıntıların Hume/Stoa metinlerini gerçekten destekleyip desteklemediği)
bu incelemenin kapsamı dışındadır — aşağıda "filolojik kapsam dışı" diye işaretlenir.

**Hüküm (peşin):** İki önerme de geçerli, teklik iddiası doğru, merdiven içsel
tutarlı ve dürüst sınırlı. Critical bulgu **yok** — ret değil, küçük revizyon
önerilir: Beth çıpasındaki bir cümle yanlış, Hume merdiveninin 2-3. basamakları
literatürsüz.

---

## a) Önerme 1 (kuvvet ilişkisi) + köprü-çöküş — GEÇERLİ

`core_section.tex` Prop `prop:strength`: $T_2 \land M_0 \models T_1$ ve
$T_1 \land M_0 \not\models T_2$.

- ($\Rightarrow$) Kanıt doğru: $\mathcal M \models \mathrm{Causal}(b,c)$ varsayımıyla
  M$_{0a}$'dan $\mathrm{Custom}(b)$, M$_{0b}$'den $\mathrm{Bel}(b,c)$; $T_2$'den
  $\neg\mathrm{Just}(b,c)$; yani $T_1$. Niceleme keyfî çift üzerinden — geçerli.
- ($\not\Leftarrow$) $(0,1,1,1)$ karşımodeli doğru: M$_{0a}$, M$_{0b}$, $T_1$ boş
  doğrulukla sağlanır ($Causal=0$), $T_2$ öncülü doğru/sonucu yanlış olduğu için
  yanlıştır. Geçerli.

Prop `prop:bridge-collapse`: $T_1 \land B_0 \models T_2$ kanıtı doğru
($B_0$'dan $\mathrm{Causal}$, $T_1$'den $\neg\mathrm{Just}$). Çift-düzeyi
$(\star)$ iff'i doğru: çiftte $T_1$ geçerli + $T_2$ geçersiz ⟺
$\mathrm{Custom}\land\mathrm{Bel}\land\mathrm{Just}\land\neg\mathrm{Causal}$
($\mathrm{Causal}=1$ olsaydı $T_1$ $\neg\mathrm{Just}$ verip
$\mathrm{Just}=1$ ile çelişirdi). Global formülasyon
($T_1\land M_0\land\neg T_2 \iff T_1\land M_0\land\exists(\star)$) iki yönüyle de
doğru; "$(\star)$ tek başına $T_1$'i ima etmez" uyarısı yerinde (V5g skop
düzeltmesi metne işlemiş).

**Bağımsız kaba-kuvvet** (paket scriptinden ayrı yazıldı): 16 yorumlamanın
16'sında $T_2\land M_0\models T_1$ için karşı-örnek **0**; $T_1\land M_0\models T_2$
için tek karşı-örnek **$(0,1,1,1)$**; $T_1\land M_0\land B_0\models T_2$ için
karşı-örnek **0**. Paket scriptleri de donmuş çıktılarıyla bayt-aynı
(`core_formal_model_check.py`, `gate15_check.py`, `encoding_sensitivity_check.py`
→ üçü de IDENTIK, exit 0). Üç katmanlı mutabakat: el kanıtı + bağımsız sayım +
paket yeniden üretimi.

## b) Önerme 2 (örtük tanımlanamazlık) — GEÇERLİ

Lemma `lem:reduct-invariance` standart ve doğru (aynı $L_0$-redükt → tüm
$L_0$-cümlelerinde anlaşma; tümevarım düzgün).

Prop `prop:underdet` inşası doğru: $\mathrm{Custom}(b)\land\neg\mathrm{Just}(b,c)$
sağlayan $M_0$-modeli mevcut (M$_{0a}$/M$_{0b}$ bu atamayla çelişmez); O$_1$-O$_2$
hedef çiftin iki öğesini de elde-kılar; $G_1$ çifti içerir ($O_3$ sağlanır),
$G_2$ içermez ($O_3$ boş doğrulukla). İki genişleme de $\mathcal K$'da,
redüktleri aynı, (G)'de ayrışıyor. Örtük-tanımlanamazlık hükmü geçerli.

Prop `prop:definability` (açık indirgenemezlik) ve `prop:stability` (teori-stabilite)
lemmanın doğru corollari'leri. "Mekanizma geneldir, ilgi içeriktedir" paragrafı
triviality itirazını metin içinde sahipleniyor — doğru hamle.

## c) Karşımodel tekliği — DOĞRU (sayımın ötesinde ispatlı)

Tablo A'nın 16 satırının 16'sı da tanımdan doğrulandı (M$_{0a}$/M$_{0b}$ ihlal
notları dahil doğru). Teklik sayımla değil, analitik olarak da kapanıyor:
$T_2$ yanlış ⟺ $\mathrm{Custom}=\mathrm{Bel}=\mathrm{Just}=1$; bu atamada $M_0$
$Causal$'dan bağımsız doğru; $T_1$ doğru ⟺ $\mathrm{Causal}=0$. Yani tek aday
$(0,1,1,1)$. Metnin "unique countermodel" iddiası (Tablo A + §Verification madde 1)
ispatlıdır.

## d) Kavram merdiveni — İÇSEL TUTARLI, DÜRÜST SINIRLI, LİTERATÜRSÜZ

Dört basamak (psikolojik-genetik / epistemik / normatif-dışlama / grounding)
metnin kendi işlevini görüyor:-formedeki her çıkarımın hangi basamakta durduğu
işaretli; 4. basamak "Hume'a atfedilemez" diye etiketli; Kapanış (Scope §1-5)
beş olumsuzlamayla tezi daraltıyor. Aşırı-atıf tuzağına düşmüyor — bu, merdivenin
asıl işi ve yapılmış.

**I-1 — Hume basamakları 2-3 literatürsüz.** `Garrett`/`Owen`/`Strawson` tex'te
**0**, spec'te **0** eşleşme (ölçüldü). 3. basamak ("normatif dışlama") yalnızca
`Della Rocca 2010` + `Pruss 2006` adıyla geçiyor; 2. basamak ("epistemik")
"unpacking gerekli" deyip unpacking'i dipnota bırakıyor. Hume-uzmanı bir hakem
" sympathi/association okuması nerede?" diye sorar ve metin cevap veremez. Teoremler
buna bağlı değil — ama merdiven, tarihî çıpa iddiasını taşıyamıyor.
Düzeltme: 2-3. basamağa en az Garrett 1997 / Owen 1999 konumlandırması (iç hakem
raporu P0-5'in istediği üç kavram ayrımı: a priori destek / entitlement / delil).

**I-2 — Beth çıpasındaki kapanış cümlesi yanlış.** Metin (§Definability-qual):
"$\mathcal K$ … arbitrary ultrapowers or unions of chains … altında kapalı
değil". Oysa $\mathcal K$'yı kesen (1)-(3) koşulları birinci-mertebeden
(tipleme imza-düzeyinde), (4) madde üye-filtreleyici değil (teori hakkında
negatif betim) — yani $\mathcal K$ elementer sınıftır; ultraçarpım ve elementer
zincir birleşimi altında **kapalıdır** (Łoś, Tarski-Vaught). Hiçbir teorem bu
cümleye dayanmıyor (her şey doğrudan inşayla kanıtlı) — ama basılı yanlış bir
model-teori iddiasıdır. Düzeltme: cümle silinip "Beth'e başvurulmuyor; başarısızlık
doğrudan çiftle gösterildi" yazılsın (kontrapozitif yönü — açık-tanım yokluğu —
sonuçla zaten tutarlı).

**M-1 — "determines" tekil kullanımı.** `:494` ("no $L_0$-sentence determines
whether (G) holds") tanımlı terimlere (`Def Explicit/Implicit definability`) atıfsız
duruyor. Tek satırlık `cf.` atfı P0-3'ün özünü kapatır; teorem etkilenmez.

---

## Filolojik kapsam dışı (işaret, hüküm değil)

Alıntı doğrulukları (T 1.3.14.20, EHU 5.1, DL 7.46, Sextus AM 7.248, Della
Rocca/Pruss/Fine/Schnieder aktarımları) denetlenmedi — bu inceleme formel
geçerlilik incelemesidir. Stoacı (S) iskeletinin modal klozu dışarıda bırakması
metin içinde açıkça kaydedilmiş bir seçimdir (tutarlı, eksik değil).

## Kontrol listesi

- [ ] **I-1** Hume merdiveni 2-3. basamağa Garrett/Owen konumlandırması
- [ ] **I-2** Beth paragrafındaki kapanış cümlesi düzeltmesi (doğrudan-inşa vurgusu)
- [ ] **M-1** `:494` "determines" → tanımlara `cf.` atfı
