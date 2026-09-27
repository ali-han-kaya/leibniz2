# Oturum Özeti — 2026-09-27

**Dal:** `main` · **HEAD:** `827430d` · **Push yapılmadı** (tüm iş yerelde).
**Kapsam:** video kompozisyonu → önizleme güvenliği → izolasyon kapıları → hakem incelemesi.
**Hakem incelemesi:** `docs/HAKEM_INCELEME_RAPORU_2026-09-27.md` (son tur) —
depodaki gerçek hakem raporu şablonu kullanılarak yapıldı; **1 Critical,
4 Important, 3 Minor**, hepsi `dosya:satır` kanıtıyla.
**Doğrulama notu:** aşağıdaki açık kalemlerden bazıları bir önceki
turdan devralınmıştı ve **bayattı**; her biri bu oturumda yeniden
ölçüldü. "Doğrulandı" ibaresi ölçüldüğü anlamına gelir.

---

## 1. Commit'lenen iş (hepsi yerel)

| commit    | ne                                                       |
| --------- | -------------------------------------------------------- |
| `b0b7ae3` | video: verdict dağılım grafiği + kapı kırılma animasyonu |
| `5fb2f74` | VERIFY-001 kanıtı — CSP altında hover-tooltip            |
| `517e37a` | kaçırılı veriyi nitelik bağlamından da kaçır             |
| `d5eef5a` | changelog satırı                                         |
| `a2d681e` | kökteki Vercel paketleme kalıntısını gizle               |
| `827430d` | başlık matrisi + CSP sözleşmesi + izolasyon kapısı       |

Ayrıca önceki turlar: `b7b5199` (video yüzeyi), `06cde8d`
(@remotion/player), `24e5d4b` (changelog), `2fee44f` (delegasyon).

**Çalışma ağacı temiz.** Index boş, untracked yok.

---

## 2. Ölçülen bulgular

### 2.1 `escapeHTML` nitelik bağlamında yetersizdi

Yalnız `& < >` kaçırıyordu; `title=` / `class=` / `data-ts=` içinde
serbest dizgi niteliği kapatıp yeni nitelik enjekte edebilirdi. Üç yuva
ölçüldü ve `escapeHTML`'e bağlandı.

Tarama: **135 template literal havuzu / 237 interpolasyon** →
nitelik bağlamında **0** kaçışsız veri. Kalan 137'nin tamamı ya
kaçırılmış ya da aritmetik sayı üreten yardımcı.

### 2.2 Kapının kendisi körleşmişti

İlk statik kapı **satır tabanlıydı**; `title="x ${…}` açılışı ile kapanış
tırnağı ayrı satırlarda olduğunda ihlal görünmüyordu (ölçüldü: satır
taraması 0 buldu, havuz taraması 1). Havuz tabanlı tarama ile değiştirildi.

### 2.3 Yol üstünde bulunan ayrı hata

`connectStream()` içinde `el` yalnız `flushStream()`'in yerel `const`'uydu;
üç kardeş dinleyici de onu kullanıyordu → her run özetinde
`ReferenceError` (kanıt koşusunda 18 kez). Kapsam taşındı.

### 2.4 Güvenlik kapsamı iki yerde boştu

- Testler `_route()`'tan **türetilmiyordu** → yeni rota sessizce kapsam
  dışı kalıyordu. Artık kaynak koddan okunuyor; yeni rota matrise girmezse
  fail-closed.
- **SSE hiç ölçülmemişti** (`/api/run`, `/api/run-stream`), kendi
  `send_header` bloğunu taşıyor.
- `serve_slides` / `serve_landing_assets` dört koruma katmanı uyguluyor,
  **sıfır testi** vardı.

### 2.5 Dört koruma katmanından üçü ölçülemez

Mutasyonla ölçüldü: karakter / uzantı / gizli dosya filtreleri tek tek
kaldırıldığında sunucu **yine 404** dönüyor. Yalnız
`realpath`+`commonpath` yük taşıyor. Katmanlar silinmedi (savunma
derinliği meşru) ama artık **yapısal olarak sabitlendi** — davranış
testleri sessizce silinmelerine izin veriyordu.

### 2.6 Atlanan test yeşil gibi görünüyordu

Tarayıcı modülleri Chromium yoksa `skipIf` ile atlanıyor. Tek roster'de
kapı "PASS" derken kanıt hiç koşmamış olurdu. İki kademe + **skip de
başarısızlık**: statik 7 modül her yerde, tarayıcı 2 modül yalnız
Chromium kurulu yerde.

---

## 3. Güncel durum (ölçüldü)

|                         |                                                |
| ----------------------- | ---------------------------------------------- |
| pre-commit hook         | **57**                                         |
| CI işi                  | **31** (13 required + 15 advisory + 3 PR-only) |
| test dosyası (manifest) | **174** PASS                                   |
| diskteki `test_*.py`    | 204 (30'u manifest dışı, çevre-bağımlı)        |
| güvenlik kapsamı        | 7 statik + 2 tarayıcı modül                    |

---

## 4. Bekleyen kararlar

| kalem | durum |
| ------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- || Hakem raporundaki 2 Critical | **Kapatıldı (son tur).** "2 Critical" ifadesi repoda **doğrulanamıyor** — raporun metni yok. Bunun yerine hakem incelemesinin **kendisi** yapıldı: `docs/HAKEM_INCELEME_RAPORU_2026-09-27.md`. Şablon: paketteki `internal_review_report.md` (388 sat., P0/P1/P2 + L1–L4 lens) → P0=**Critical**, P1=**Important**, P2=**Minor**. 15 denetim ölçüldü (D1–D15). |
| `repack_delivery.py:75-76` ResourceWarning | **Doğrulandı: hâlâ açık** → hakem raporunda **M-1 (Minor)** olarak sınıflandırıldı. Yol `_calisma/repack_delivery.py` (CIKTI değil). İki `sum(1 for _ in open(...))` — `with` yok. |
| `docs/Makefile.texlive` SOURCE_DATE_EPOCH | Kapatılmış görünüyor (6 geçiş). |
| `/tmp/review_brief.md` | **Dosya yok.** Ne diskte, ne git geçmişinde, ne worktree'lerde. Taşınacak içerik yok. |
| Kota tarihi | "22 Eylül" 27 Eylül'ün **5 gün öncesi**. Not 22 Ekim mi, "gecikti" mi — karar gerekiyor. |
| `github-site-sample` worktree | 8 untracked dosya (Primer örneği + ADR). **Bu oturumun işi değil**, başka dalda. Sahipliği belirsiz → dokunulmadı. |
| `pyproject.toml` / `uv.lock` | Kök Vercel kalıntısı; `.gitignore`'a eklendi (`a2d681e`). Kapandı. |

---

## 5. Ortam tuzakları (hepsi ölçüldü)

- **Playwright önbelleği oturum ortasında silinmişti** (`~/Library/Caches/ms-playwright/`); `playwright install chromium` ile onarıldı. Öldürülen kurulum `__dirlock` **dizini** bırakıp sonrakini kilitliyor.
- **Ağ takılırken `curl --max-time` bile komutu kilitleyebiliyor** → `timeout` sarmalayıcı şart.
- **Shell `cd` aralıksız çalışmıyor**; paralel kabuk çağrıları cwd'de yarışıyor. Güvenilir desen: tek komutta sıralı, ya da `python3 - <<'PY'` içinde `os.chdir`.
- **Backtick tuzağı:** `git commit -m "$(cat <<'EOF' … \`…\` … EOF )"`içinde backtick'ler komut sanılıp çalıştırılıyor. Çözüm: mesajı dosyaya yaz,`git commit -F dosya`.
- **Önizleme sunucusu komutlar arasında reap ediliyor.** Sağlam ölçüm: aynı komutta `&` ile başlat, `sleep`, curl'le, `kill $SRV`.
- **`urllib` boşluk/kontrol karakterli isteği istemci tarafında reddeder.** Tarayıcının gönderdiği yüzde-kodlanmış hali sınanmalı.
- **Tek iş parçacıklı `HTTPServer` sonsuz akışta kilitlenir**; üretim `ThreadingHTTPServer` kullanıyor. Test koşumu üretimden sapıyorsa ölçtüğün şey üretim değildir.
- **Uzun commit zinciri** pre-commit'te ~5–10 dk sürüyor; 300 sn zaman aşımı yetmiyor.

---

## 6. Sırf derlenen değil, davranışı ölçülen kalıplar

**Tokio denemesi** (`/tmp/tokio-lab`, repodan bağımsız, 344 satır, 7 test).
Aranan `select!`/`JoinSet`/Semaphore skill'i **bu ortamda yok** — repodaki
7 skill, `~/.claude/skills`'taki 9 skill ve `ruflo` ağacının tamamı
tarandı. Tek "Semaphore" eşleşmesi bir TypeScript dosyasıydı. Kalıplar
kanonik idiom olarak yazıldı.

Mutasyonla kanıtlandı: izin **işin içinde** alınırsa 2 test düşüyor
(klasik hata); `abort_all` kaldırılırsa `JoinSet` testi düşüyor;
`select!` yerine sıralı bekleme `select` testini düşüyor. `close()`
kaldırılınca test **başarısız olmadan asılı kalıyordu** — CI'da asılı test
düşen testten kötüdür, bu yüzden zaman aşımı eklendi.

**Devreden alışkanlık:** her kapı için "boş olamaz" sorusu soruldu —
boş roster, eksik dosya, ölü yardımcı adı, skip, pozitif kontrol yokluğu.

---

## 7. Bu oturumda yapılmayanlar

- `/tmp/review_brief.md` taşınmadı — **dosya yok**, içerik uydurulmadı.
- `github-site-sample`'daki 8 dosya commit edilmedi — **bu oturumun işi değil**.
- `pyproject.toml` / `uv.lock` commit edilmedi, gizlendi — kalıntı olduğu
  ölçüldü.
- Changelog HEAD'in bir commit gerisinde kalıyor. **Tasarım gereği**
  (`verify.yml`: _"tasarım gereği HEAD'in bir commit gerisinde kalabilir"_),
  advisory; pre-commit hook'u bir sonraki commit'te kapatıyor.
