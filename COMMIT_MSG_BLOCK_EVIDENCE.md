# COMMIT_MSG_BLOCK_EVIDENCE.md

Üretim zamanı: 2026-08-20T22:11:28Z
Hook: `_calisma/CIKTI/commit_msg_hook.sh`
Test sayısı: 28

## Test Sonuçları

| # | Mesaj | Beklenen | Gerçek | Durum | Açıklama |
|---|-------|----------|--------|-------|----------|
| 1 | `fix: null pointer deerference` | İZİN | İZİN | ✅ | geçerli conventional commit |
| 2 | `docs: README güncelleme` | İZİN | İZİN | ✅ | geçerli kapsam + eylem |
| 3 | `feat(auth): OAuth desteği ekle` | İZİN | İZİN | ✅ | geçerli kapsam alt kapsam |
| 4 | `Merge branch 'main' into feature` | İZİN | İZİN | ✅ | git merge başlığı (izinli) |
| 5 | `Revert "feat: X ekle"` | İZİN | İZİN | ✅ | git revert başlığı (izinli) |
| 6 | `refactor: modül yeniden düzenle` | İZİN | İZİN | ✅ | geçerli refactor |
| 7 | `chore: bağımlılık güncelle` | İZİN | İZİN | ✅ | geçerli chore |
| 8 | `WIP` | BLOKE | BLOKE | ✅ | WIP başlık yasak |
| 9 | `wip: bir şey` | BLOKE | BLOKE | ✅ | wip: önekli yasak |
| 10 | `fix: WIP bir şey` | BLOKE | BLOKE | ✅ | WIP kelimesi içeren yasak |
| 11 | `test marker: deneme` | BLOKE | BLOKE | ✅ | test marker yasak |
| 12 | `test: deneme` | BLOKE | BLOKE | ✅ | test: noise yasak |
| 13 | `test` | BLOKE | BLOKE | ✅ | tek Kelime test yasak |
| 14 | `smoke test` | BLOKE | BLOKE | ✅ | smoke başlık yasak |
| 15 | `fix typo` | BLOKE | BLOKE | ✅ | fix typo noise |
| 16 | `minor fix` | BLOKE | BLOKE | ✅ | minor fix noise |
| 17 | `temp` | BLOKE | BLOKE | ✅ | temp noise yasak |
| 18 | `tmp` | BLOKE | BLOKE | ✅ | tmp noise yasak |
| 19 | `foo` | BLOKE | BLOKE | ✅ | foo noise yasak |
| 20 | `bar` | BLOKE | BLOKE | ✅ | bar noise yasak |
| 21 | `lorem ipsum dolor sit amet` | BLOKE | BLOKE | ✅ | lorem ipsum noise yasak |
| 22 | `asdf` | BLOKE | BLOKE | ✅ | asdf noise yasak |
| 23 | `duzgun baslik yok` | BLOKE | BLOKE | ✅ | iki nokta + boşluk formatı yok |
| 24 | `fix:single_space_yok` | BLOKE | BLOKE | ✅ | iki nokta sonrası boşluk yok |
| 25 | `<type>: placeholder düzenlenmemiş` | BLOKE | BLOKE | ✅ | şablon placeholder'ı var |
| 26 | `fix: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa...` | İZİN | İZİN | ✅ | 72 karakter (sınırda, izin) |
| 27 | `fix: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa...` | BLOKE | BLOKE | ✅ | 73 karakter (aşım, bloke) |
| 28 | `_(boş)_` | BLOKE | BLOKE | ✅ | boş mesaj bloke |

## Özet

- **Toplam test:** 28
- **Başarılı:** 28
- **Başarısız:** 0

**SONUÇ: PASS** — tüm testler beklenen davranışı üretiyor.

---
Otomatik üretilmiştir. Hook kuralları değişirse bu dosya da değişir.
Son yenileme: 2026-08-20T22:11:28Z
