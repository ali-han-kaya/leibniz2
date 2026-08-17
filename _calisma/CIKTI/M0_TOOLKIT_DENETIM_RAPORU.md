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
MANIFEST.txt MD5 denetimi        → 18/18 OK, 0 eksik, 0 uyumsuz
core_formal_model_check.py       → PASS + test_output.txt ile byte-for-byte
encoding_sensitivity_check.py    → PASS + frozen output ile byte-for-byte
gate15_check.py                  → PASS + frozen output ile byte-for-byte
pdfinfo ingiliz_empirizmi_v3.pdf → Pages: 33
core_section.tex yapısı          → 877 satır · 11 subsection · 9 subsubsection
                                   5 proposition · 1 lemma · 2 definition · 26 label (0 duplike)
References (LaTeX)               → 64 \item
KLASOR_CHECKSUMLARI.sha256       → 10/10 OK (orijinal klasör)
v3_verify.py (fail-closed gate)  → P0=0, P1=0 → PASS  [bkz. §6.1]
```

### 6.1 Toolkit betiği çıktısı (`v3_verify.py` — mekanik, modelden bağımsız)

`python3 ALI_KOMUT_TOOLKIT_v3/scripts/v3_verify.py <paket_klasoru>` çalıştırıldı; fail-closed gate **ham bulgulardan yeniden hesaplanan** P0/P1 sayısına göre `PASS` üretti. Çıktının özeti (dosya sayısı, toplam boyut, secret/hijyen/bütçe bulguları) §9'daki doğrulama raporuna eşlik eder.

---

## 7. GEÇERLİLİK KANITLARI (kapsam)

- **Gereksinim kapsamı:** V5 mimari anayasasındaki maddelerin gerçekleşmesi — paketin kendi 12/12 zinciri yeniden doğrulandı (manifest, 3 script, PDF, checksum, zip bütünlüğü, preview↔PDF, 64/64 referans).
- **Kanıt kapsamı:** Açık DOI'li 1 kaynak CrossRef'ten doğrulandı (1/1); 3 script deterministik olarak yeniden üretildi (3/3); MANIFEST 18/18; klasör checksum'ı 10/10.
- **Sınır (paketin kendi belirttiği):** finite-check scriptleri genel ispatın (yapısal indüksiyon, Lemma) yerine geçmez — bu sınır pakette zaten dürüstçe yazılıdır.

---

## 8. BÜTÇE RAPORU

- `v3_verify.py --budget 30` eşiğiyle çalıştırıldı: tahmini maliyet limitin altında (`ESTIMATE`; token ≈ dosya boyutu / 4). Blok yok.

---

## 9. FİNAL DOSYA LİSTESİ + HASH

İç paketin **MANIFEST.txt** dosyası, 18 dosyanın güncel boyut + MD5 kaydını içerir (FIX-006 sonrası README/REPRODUCIBILITY hash'leri güncellendi; 18/18 doğrulandı).

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

Dış zip'in tam soy hattı (kanıtlanabilir zincir):

```text
363a06e3…  (orijinal, §9)
3ef74cae…  (yeni, §9)
af8067ca…  (git init, 9f72b0e)
d7f63d72…  (K6-DETERM, a92682d)
fe731022…  (V5i, bad86f4)
bec0bb0a…  (deterministik repack, 2e7c425) ← GÜNCEL KANONİK
```

### 10.3 Güncel kanonik hash'ler (yanındaki sidecar ile birebir)

```text
TESLIM_KLASOR_V5_2026-08-17.zip = bec0bb0a4fd2fff2dfaeee38f9afb1f0442640029dcf793aac9073e41d9cf900
TESLIM_V5_FINAL_2026-08-17.zip  = b32fda0fca08c5a1b35043159ff0d853795ddcdc932351c11bd7d899c77e033c
```

Not: `363a06e3…` değeri §9'da zaten "orijinal" olarak sabitlenmişti; §10 bu
değeri "bayat zip" olarak adlandırıp silme/supersede olayını kaydeder. K0
katmanı (`verify_delivery.py`) CIKTI dışındaki zip'leri P1 işaretleyerek yeni
bayat kopyaların sessizce birikmesini engeller.

---

*Bu rapor `ALI_KOMUT_TOOLKIT_v3`'ün `M0_ANA_KOMUT.md` §8 rapor sırasına birebir uyar: karar → kontrol edilenler → başarısızlar → değişiklikler → belirsizler → doğrulama kanıtları → geçerlilik → bütçe → final dosya listesi. §10 (Cleanup log) bu sıraya eklenmiş bir teslim-sonrası uzantıdır.*
