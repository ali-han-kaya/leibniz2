# M0 TOOLKIT DENETİM RAPORU — Stoic-Hume V5 Teslimi

**Araç:** `ALI_KOMUT_TOOLKIT_v3` → `M0_ANA_KOMUT.md` (12 fazlı çok-ajanlı orkestratör)
**Hedef:** `TESLIM_KLASOR_V5_2026-08-17.zip` (dış/klasör zip) → `Stoic-Hume-Final-V5_2026-08-17/` → `TESLIM_V5_FINAL_2026-08-17.zip` (iç/ana teslim)
**Tarih:** 2026-08-17 · **Denetçi:** M0 orkestratörü (Structure + Consistency + Evidence lensleri + Verifier betiği)
**Durum kodu ilkesi:** Bu rapordaki her sayı, çalıştırılmış bir komutun çıktısına dayanır. Tahmin yoktur; tahmin gerektiren her şey `ESTIMATE` / `UNKNOWN` olarak etiketlenmiştir.

---

## 1. KARAR (final)

- **İlk lens denetimi:** `CONDITIONAL` — 5 tutarlılık kalıntısı (C1–C5) + 1 iyileştirme fırsatı (C6) bulundu. Hiçbiri P0 (bloker) değil; tümü doğrulanabilir ve düzeltilebilir metadata sapması.
- **Revizyon sonrası (FIX-001…FIX-006 uygulandı):** `PASS` — bloker 0, majör 0, tüm kritik iddialar traceable.
- **Fail-closed gate (mekanik):** `v3_verify.py` yeniden hesaplanmış P0/P1 = 0 → `PASS` (bkz. §6).

Bu raporda beyan edilen hiçbir `PASS`, ham bulgulardan bağımsız bir "verdict" alanına güvenmez; her sonuç §6'daki komut çıktılarından yeniden türetilmiştir.

---

## 2. KONTROL EDİLENLER (M0 fazları)

| Faz | Eylem | Sonuç |
|---|---|---|
| 0 | Girdi envanteri (path, size, SHA-256) | 29 dosya (iç zip), 11 öğe (klasör) |
| 1 | Hedefi ölçülebilir gereksinime çevirme | Gereksinimler §7'de |
| 2 | Baseline hash'le sabitleme | orijinal iç zip `54386cb4…`, orijinal klasör zip `363a06e3…` |
| 3 | İddia-kanıt haritası | 64 referans, P-01…P-19 provenance satırı eşleşti |
| 4 | Kanıt denetimi | Schnieder 2011 DOI CrossRef ile doğrulandı (§5) |
| 5 | 3 lens paralel | C1–C5 + C6 bulguları (§3) |
| 6 | Yöntem denetimi | deterministik script + frozen output + manifest + sidecar = yeniden üretilebilir |
| 7 | Revizyon | FIX-001…FIX-006 (§4) |
| 8 | Geriye dönük kontrol | eski issue yeniden açılmadı; regression yok |
| 9 | Kör gate 2A | final adayı FIX kayıtları olmadan yeniden denetlendi (ham kanıt) |
| 10 | Manifest gate 2B | MANIFEST 18/18 yeniden doğrulandı (§6) |
| 11 | Serbest bırakma kapısı | 2-of-2: lens PASS + mekanik PASS |
| 12 | Paket bütünlüğü | zip yeniden aç → manifest karşılaştır → hash yeniden hesapla (§6) |

---

## 3. BULGULAR (başarısız olanlar — ID + şiddet + konum + kanıt)

| ID | Şiddet | Konum | Sorun | Kanıt |
|---|---|---|---|---|
| C1 | P1 | `stoic_hume_package/…/README.md:18` | "872 lines" yazıyor | `wc -l core_section.tex` = **877** |
| C2 | P1 | `README.md:32` | "31 pp." yazıyor (176. satırda "33 pp." ile çelişiyor) | `pdfinfo ingiliz_empirizmi_v3.pdf` → **Pages: 33** |
| C3 | P2 | `MANIFEST.txt:5` ve `:25` | başlık yorumunda "30 pp" yazıyor | aynı `pdfinfo` = 33 (satır 16 "33 pp." ile çelişki) |
| C4 | P1 | `TESLIM_V5_FINAL_2026-08-17/TEMIZLIK_KONTROL_LISTESI.md:18` | "23 dosya" yazıyor | `find` ile **29 dosya** sayıldı |
| C5 | P2 | `TEMIZLIK_KONTROL_LISTESI.md:118` | "212.731 B, MD5 b7ee84a7…" yazıyor | gerçek PDF **213335 B**, MD5 **1e5161e2…** (MANIFEST 18/18 OK) |
| C6 | P2 | README/REPRODUCIBILITY sürüm matrisi | yalnızca 3.10/3.11/3.12 listelenmiş | bu denetimde **Python 3.9.6** üç scripti byte-for-byte yeniden üretti |

**Kanıt komutu (C1, C4, C5):** `wc -l core_section.tex`; `find . -type f | wc -l`; `python3 -c "import hashlib;print(hashlib.md5(open('ingiliz_empirizmi_v3.pdf','rb').read()).hexdigest())"`.

**Not (bilinçli bırakılan):** `MANIFEST.txt:13` "Manuscript recompiled (31 pp)." değiştirilmedi — bu satır V5c ara sürümünün *tarihsel* kaydıdır (V5c gerçekten 31 sayfaydı; V5d'de 33'e çıktı). Yanlış olan yalnızca *final* durumu "30 pp" olarak gösteren satırlardı.

---

## 4. DEĞİŞTİRİLENLER (FIX-XXX + kanıt)

| FIX | Değişiklik | Önce → Sonra | Kanıt |
|---|---|---|---|
| FIX-001 | `README.md:18` | "872 lines" → "877 lines" | `wc -l` = 877 |
| FIX-002 | `README.md:32` | "31 pp." → "33 pp." | `pdfinfo` = 33 |
| FIX-003 | `MANIFEST.txt:5,25` | "30 pp" → "33 pp" | `pdfinfo` = 33 |
| FIX-004 | `TEMIZLIK:18` | "23 dosya" → "29 dosya" | `find` = 29 |
| FIX-005 | `TEMIZLIK:118` | "212.731 B / b7ee84a7…" → "213.335 B / 1e5161e2…" | MD5 + boyut yeniden hesaplandı |
| FIX-006 | `README.md` + `REPRODUCIBILITY.md` | sürüm matrisine **3.9.6** eklendi | 3.9.6'da 3 script byte-for-byte PASS |

**Kapsam kuralına uygunluk:** Yalnızca doğrulanabilir metadata düzeltildi. Makalenin tezi, teoremleri, formalizasyonu, script mantığı ve PDF içeriği **değiştirilmedi** (`core_section.tex`, `*.py`, `*.pdf`, `*.tex` hash'leri FIX öncesiyle aynıdır).

---

## 5. BELİRSİZ KALANLAR (`UNKNOWN` / `UNVERIFIED_SOURCE`)

- "Python 3.10/3.11/3.12'de test edildi" beyanı bu makinede (yalnızca 3.9.6 mevcut) **bağımsız olarak yeniden doğrulanamadı** — `UNVERIFIED_SOURCE` olarak işaretlendi; paketin kendi tarihsel iddiası olarak korundu, yanına 3.9.6 kanıtı eklendi.
- 64 referansın tamamının bibliyografik varlığı tek tek taranmadı (yalnızca açık DOI'li tek girdi CrossRef'ten doğrulandı: Schnieder 2011 → "A Logic for 'Because'", *Review of Symbolic Logic* 4(3): 445–465, CUP — **birebir eşleşti**). Kalan 63 girdi `UNVERIFIED_SOURCE` statüsünde paketin kendi provenance kaydına dayanır.

---

## 6. DOĞRULAMA KANITLARI (çalıştırılmış çıktılar)

```text
MANIFEST.txt MD5 denetimi        → 19/19 OK, 0 eksik, 0 uyumsuz
core_formal_model_check.py       → PASS + test_output.txt ile byte-for-byte
encoding_sensitivity_check.py    → PASS + frozen output ile byte-for-byte
gate15_check.py                  → PASS + frozen output ile byte-for-byte
pdfinfo ingiliz_empirizmi_v3.pdf → Pages: 33
core_section.tex yapısı          → 877 satır · 11 subsection · 9 subsubsection
                                   5 proposition · 1 lemma · 2 definition · 26 label (0 duplike)
References (LaTeX)               → 64 \item
KLASOR_CHECKSUMLARI.sha256       → 10/10 OK (orijinal klasör)
v3_verify.py (fail-closed gate)  → P0=0, P1=0 → PASS  [bkz. §6.1]
verify_delivery.py --verify-manifest (K10) → PASS (mock 3/3); tamper→exit 1, silme→exit 1  [bkz. §6.2]
```

### 6.1 Toolkit betiği çıktısı (`v3_verify.py` — mekanik, modelden bağımsız)

`python3 ALI_KOMUT_TOOLKIT_v3/scripts/v3_verify.py <paket_klasoru>` çalıştırıldı; fail-closed gate **ham bulgulardan yeniden hesaplanan** P0/P1 sayısına göre `PASS` üretti. Çıktının özeti (dosya sayısı, toplam boyut, secret/hijyen/bütçe bulguları) §9'daki doğrulama raporuna eşlik eder.

### 6.2 Katman tablosu — `verify_delivery.py` (K0–K13)

M0 raporunun yazıldığı tarihteki `v3_verify.py` kapısı, sonradan tek giriş
noktasına genişletildi: `verify_delivery.py` (K0–K13). Bu tablo güncel
fail-closed zincirini katman katman listeler; her satır çalıştırılmış bir
komutun çıktısına dayanır (tahmin yok). `--full` = K1-K7 + K6-referans +
K8 + K9 + soy hattı + K11 + K13; K10 ve K12 ayrıca çağrılır.

| Katman | Kontrol | Durum (son doğrulama) |
|---|---|---|
| K0 | Bayat zip taraması (CIKTI dışı, recursive) | PASS |
| K1 | Dış zip SHA-256 sidecar (kurcalanma) | PASS |
| K2 | KLASOR_CHECKSUMLARI.sha256 (klasör) | PASS |
| K3 | İç zip SHA-256 sidecar (kurcalanma) | PASS |
| K4 | MANIFEST.txt 19/19 (boyut + MD5) | PASS |
| K5 | 3 script byte-for-byte (donmuş çıktı) | PASS |
| K6 | PDF 33 sayfa + References 64/64 (+ `--check-references` çevrimiçi) | PASS |
| K7 | Hijyen + secret/anahtar taraması | PASS |
| K8 | Z3 sembolik ispat (12/12) | PASS |
| K9 | Lean 4 reduct-invariance (tümevarımsal) | PASS |
| K10 | reproducibility manifest digest (`--verify-manifest`) | PASS (aşağıda) |
| K11 | config drift (`gen_config.py --dry-run`; `--check-config-drift`) | PASS |
| K12 | LaunchAgent plist şablonu (`--check-plist`) | PASS (yerel macOS; Linux CI'da koşmaz) |
| K13 | gen_repro_manifest.py self-testi (`--check-repro-manifest`) | PASS |

**K10 bulguları (yeni katman — commit `7e28f2c`):** `verify_delivery.py
--verify-manifest reproducibility/manifest.json`, `gen_repro_manifest.py`
çıktısındaki her SHA-256'yı gerçek dosyayla karşılaştırır; eksik/uyuşmazlık
→ P1 → exit 1 (fail-closed, sessiz geçiş yok). Mock-3-dosya simülasyonu:

| Yol | Sonuç |
|---|---|
| PASS | `[K10] PASS — 3 OK / 0 uyuşmazlık / 0 eksik` → exit 0 |
| Tamper (`verify-report.md`'ye ekleme) | `2 OK / 1 uyuşmazlık` → exit 1 |
| Silme (`run-history/history.jsonl`) | `…(EKSİK)` → exit 1 |

K10, CI `reproducibility` job'ında manifest üretiminin hemen ardından koşar.
Bilinçli sınır: `manifest.sha256` sidecar'ı üretilir ama K10 henüz denetlemez;
`--verify-manifest` çevrimdışı K1-K7 taban kapısını da koşar (K6 çevrimiçi
denetim, Z3, Lean yok).

**Özet sayımı düzeltmesi:** §2 faz 10 ve §3 C5'teki "18/18", M0 denetim
tarihinin (2026-08-17) tarihsel kaydıdır; V5i'de `ingiliz_empirizmi_v3.pdf.metadata.sha256`
sidecar'ı eklenince MANIFEST 19 girdiye çıktı. §6/§7/§9 güncel sayıyı (19/19) taşır.

---

## 7. GEÇERLİLİK KANITLARI (kapsam)

- **Gereksinim kapsamı:** V5 mimari anayasasındaki maddelerin gerçekleşmesi — paketin kendi 12/12 zinciri yeniden doğrulandı (manifest, 3 script, PDF, checksum, zip bütünlüğü, preview↔PDF, 64/64 referans).
- **Kanıt kapsamı:** Açık DOI'li 1 kaynak CrossRef'ten doğrulandı (1/1); 3 script deterministik olarak yeniden üretildi (3/3); MANIFEST 19/19; klasör checksum'ı 10/10; K10 reproducibility manifest digest (mock 3/3, tamper/silme → exit 1).
- **Sınır (paketin kendi belirttiği):** finite-check scriptleri genel ispatın (yapısal indüksiyon, Lemma) yerine geçmez — bu sınır pakette zaten dürüstçe yazılıdır.

---

## 8. BÜTÇE RAPORU

- `v3_verify.py --budget 30` eşiğiyle çalıştırıldı: tahmini maliyet limitin altında (`ESTIMATE`; token ≈ dosya boyutu / 4). Blok yok.

---

## 9. FİNAL DOSYA LİSTESİ + HASH

İç paketin **MANIFEST.txt** dosyası, 19 dosyanın güncel boyut + MD5 kaydını içerir (FIX-006 sonrası README/REPRODUCIBILITY hash'leri güncellendi; V5i'de eklenen `ingiliz_empirizmi_v3.pdf.metadata.sha256` dahil 19/19 doğrulandı).

Orijinal (denetim öncesi) ve yeni (denetim sonrası, optimize) zip hash'leri — kurcalanabilirlik zinciri için burada sabitlenmiştir:

```text
TESLIM_V5_FINAL_2026-08-17.zip      (orijinal) = 54386cb4e9564661a66b9a08aa911f681f80e76a09663e9043f4dc0d0d4afd37
TESLIM_KLASOR_V5_2026-08-17.zip     (orijinal) = 363a06e36d71666e70fead77bf44d4c82da2edb57c1be1a30095da1a179a08aa
TESLIM_V5_FINAL_2026-08-17.zip      (yeni)     = 728763ce544ff501e47a2a3e0b7a659fdd6cd3440ca3952d28df9c73dbcf7f1a
TESLIM_KLASOR_V5_2026-08-17.zip     (yeni)     = 3ef74caeb6d1afa8ad7967dd5bd71b97c2eb597651456dcbd8e39c4db94481bc
```

Not: Bu rapor zip'lerin dışında verildiği için yeni hash'leri sabitleyebilir; zip'lerin *içindeki* belgeler self-reference kuralını korur (güncel değer her zaman yanındaki `.sha256` sidecar'dadır).

---

## 10. CLEANUP LOG (silme kaydı)

Bayat (superseded) zip'lerin silinme kaydı. Kanonik teslim yalnızca
`_calisma/CIKTI/` altındaki tek kopyadır; önceki nesiller yeniden üretimle
(repack) üzerine yazılarak bayat kalır. Aşağıdaki hash'ler silinme anında
dondurulmuş kanıttır ve yeniden türetilebilir: §9 tablosu + `git log` +
yanındaki `.sha256` sidecar.

### 10.1 Bayat zip — dondurulmuş orijinal hash

```text
TESLIM_KLASOR_V5_2026-08-17.zip  (bayat / orijinal) = 363a06e36d71666e70fead77bf44d4c82da2edb57c1be1a30095da1a179a08aa
```

### 10.2 Silme kaydı

| Tarih | Silinen (bayat) | Hash (dondurulmuş) | Neden |
|---|---|---|---|
| 2026-08-17 | `TESLIM_KLASOR_V5_2026-08-17.zip` (orijinal) | `363a06e3…` | M0 optimizasyonu (FIX-001…FIX-006) sonrası bayat kaldı; kanonik konumda üzerine yazıldı (bkz. §9) |
| 2026-08-17 | sonraki nesiller (`3ef74cae…`, `af8067ca…`, `d7f63d72…`, `fe731022…`) | yukarıdaki kısaltmalar | deterministik repack (commit `2e7c425`) ile bayat kaldı |

Dış zip'in tam soy hattı (kanıtlanabilir zincir) — **tek kaynak:**
`_calisma/CIKTI/zip_lineage.json` (11 nesil: 2 pre-git dondurulmuş + 9
git'ten yeniden türetilebilir). `verify_delivery.py --check-lineage`
her commit'li nesli `git show <commit>:<path> | sha256` ile yeniden
hesaplayıp kayıtlı hash'le karşılaştırır; `current` nesli ayrıca canlı
dosyayla doğrular (P0). Bu bölüm artık yalnızca o kaynağın özetidir:

```text
363a06e3…  (orijinal, §9)                          [pre-git, dondurulmuş]
3ef74cae…  (yeni, §9)                              [pre-git, dondurulmuş]
af8067ca…  (git init, 9f72b0e)                     [git show ile doğrulanır]
295aae0c…  (V5h: Beth 1953 + Fosl 1998, c65e84b)  [git show ile doğrulanır]
d7f63d72…  (K6-DETERM, c962bbf)                   [git show ile doğrulanır]
fe731022…  (V5i: K6-DETERM known limitation, e232ab2) [git show ile doğrulanır]
bec0bb0a…  (deterministik repack, 2492e98)         [git show ile doğrulanır]
8b390996…  (Popkin 1952 + Priest 2018, fad15f0)   [git show ile doğrulanır]
34e81dff…  (V5k: tectonic non-determinism, 07793f6) [git show ile doğrulanır]
58f7d1c6…  (V5l: repack determinizm kanıtı, 6bb9cb6) [git show ile doğrulanır]
918e0545…  (V5m: qpdf deneyi script + donmuş çıktı, d02cda8) ← GÜNCEL KANONİK (canlı dosya ile doğrulanır)
```

### 10.3 Güncel kanonik hash'ler (yanındaki sidecar ile birebir)

```text
TESLIM_KLASOR_V5_2026-08-17.zip = 918e054595f798d48843ece59f48582b2b22147edb0cdb06188f0c543b2e13aa
TESLIM_V5_FINAL_2026-08-17.zip  = 81a0244855cc574562bc18a611c94bf3ffbb0086c3ea32775de9d5f32473c28a
```

Not: `363a06e3…` değeri §9'da zaten "orijinal" olarak sabitlenmişti; §10 bu
değeri "bayat zip" olarak adlandırıp silme/supersede olayını kaydeder. K0
katmanı (`verify_delivery.py`) CIKTI dışındaki zip'leri P1 işaretleyerek yeni
bayat kopyaların sessizce birikmesini engeller. Soy hattı artık `zip_lineage.json`
tek kaynağından denetlenir (`--check-lineage`; CI'da `--full` içinde koşar,
`fetch-depth: 0` ile tam geçmiş kullanılır).

### 10.4 Toolkit zip — kökten `_calisma/TOOLKIT/` altına taşındı (K0 yeşil)

`_calisma/ALI_KOMUT_TOOLKIT_v3.zip` (45941 B, iCloud kanonik kopyasıyla
byte-identical `aff84c80…`) `_calisma/` kökünde başıboş duruyordu; K0
(`verify_delivery.py`) bunu P1 ile işaretliyordu. Kanonik kopya iCloud'da
(`ai önemli çıktılar/ALI_KOMUT_TOOLKIT_v3.zip`, aynı hash) olduğundan kök
kopyası yalnızca yerel çalışma kopyasıydı → `_calisma/TOOLKIT/` (gitignore'da,
extracted kopya zaten orada) altına taşındı. K0 artık PASS (P0=0, P1=0).

```text
ALI_KOMUT_TOOLKIT_v3.zip (kök → TOOLKIT/) = aff84c80b9c13253fb2bd1541400a0dfb4f51cac7492dcf143b40fe66663f991
```

| Tarih | Taşınan | Hash (dondurulmuş) | Neden |
|---|---|---|---|
| 2026-08-18 | `ALI_KOMUT_TOOLKIT_v3.zip` (`_calisma/` kökü → `_calisma/TOOLKIT/`) | `aff84c80…` | K0 P1'i (başıboş kök kopyası); kanonik iCloud'da, gitignore'da → TOOLKIT/ altına taşındı |

### 10.5 Kök-seviye başıboş `TESLIM_KLASOR_V5_2026-08-17.zip` — rm kaydı

`_calisma/` kökünde, CIKTI/ dışında duran başıboş `TESLIM_KLASOR_V5_2026-08-17.zip`
kopyası silindi (rm). Kanonik kopya yalnızca `_calisma/CIKTI/` altındadır;
kök kopyası `.gitignore`'da olduğundan hiç commit edilmedi (bkz. commit
`3d114e5`), yani **kendi hash'i silinme sonrası yeniden türetilemez**
(post-hoc dondurulamaz — şeffaflık notu). İçeriği kanonik dış zip'in
kopyasıydı; iCloud'daki kaynak orijinal (`363a06e3…`, §9 ile aynı)
508447 B olarak doğrulandı ve hâlâ mevcuttur.

| Tarih | Silinen | Hash | Neden |
|---|---|---|---|
| 2026-08-18 | `TESLIM_KLASOR_V5_2026-08-17.zip` (`_calisma/` kökü) | türetilemez (gitignore, rm sonrası); iCloud kaynak `363a06e3…` | başıboş kök kopyası; kanonik CIKTI/'da, kaynak iCloud'da — kök kopyası gereksizdi |

---

*Bu rapor `ALI_KOMUT_TOOLKIT_v3`'ün `M0_ANA_KOMUT.md` §8 rapor sırasına birebir uyar: karar → kontrol edilenler → başarısızlar → değişiklikler → belirsizler → doğrulama kanıtları → geçerlilik → bütçe → final dosya listesi. §10 (Cleanup log) bu sıraya eklenmiş bir teslim-sonrası uzantıdır.*
