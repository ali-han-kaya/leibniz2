# Commit-msg hook — BLOKE kanıtı (gerçek kötü başlık denemesi)

Bu belge, `commit-msg` hook'unun `.pre-commit-config.yaml`'deki **diğer dört
kapıyla birlikte** çalıştığını ve kötü başlığı gerçekten **BLOKE ettiğini**
kayıt altına alır. Deneme `git commit --allow-empty` ile yapıldı — commit
oluşmadığı için çalışma ağacına ve history'ye hiçbir etkisi yoktur.

- **Tarih:** 2026-08-19
- **Ortam:** macOS, repo kökü `/Users/alikaya/Desktop/leibniz2`
- **Başlangıç HEAD:** `e6cbdca7fcd86669f043f7a44e4306056dbd4791`
- **Bitiş HEAD:** `e6cbdca7fcd86669f043f7a44e4306056dbd4791` (değişmedi → commit oluşmadı)
- **Çalışma ağacı:** temiz (`git status --short` boş)

---

## TEST 1 — noise/marker başlık (`wip: yarım iş`)

```bash
git commit --allow-empty -m "wip: yarım iş"
# → exit 1 (commit BLOKE edildi)
```

### Kapı sırası (tüm zincir koştu; commit-msg EN SONDA bloke etti)

| # | Hook | Sonuç |
|---|---|---|
| 1 | `update-config` (config senkronu) | ✅ Passed |
| 2 | `verify-delivery` (K1-K7) | ✅ Passed |
| 3 | `verify-delivery-symbolic` (K8/Z3, 12/12) | ✅ Passed |
| 4 | `verify-delivery-lean` (K9/Lean reduct-invariance) | ✅ Passed |
| 5 | `commit-msg-style` (başlık denetimi) | 🔴 **Failed** (exit 1) |

### commit-msg çıktısı (birebir)

```
Commit message style (noise prevention)..................................Failed
- hook id: commit-msg-style
- duration: 0.02s
- exit code: 1

commit-msg: HATA — noise/marker başlık yasak
commit-msg:   başlık: wip: yarım iş
commit-msg:   kural: bkz. .gitmessage (git config commit.template .gitmessage)
```

---

## TEST 2 — format ihlali (iki nokta + boşluk yok)

```bash
git commit --allow-empty -m "format-ihlali-başlık"
# → exit 1 (commit BLOKE edildi)
```

```
commit-msg: HATA — başlık '<kapsam>: <eylem>' formatında olmalı (iki nokta + boşluk)
commit-msg:   başlık: format-ihlali-başlık
commit-msg:   kural: bkz. .gitmessage (git config commit.template .gitmessage)
```

---

## Sonuç

- Her iki kötü başlık da `commit-msg-style` hook'u tarafından **fail-closed**
  reddedildi; hiçbir commit oluşmadı (`git log` başlangıçla aynı).
- `commit-msg` hook'u, pre-commit stage'inin **dört kapısı başarıyla geçtikten
  sonra** devreye girer — yani kapı izole değil, tam zincirin parçasıdır.
- Geçerli başlıkla commit zaten sürekli doğrulanıyor: bu repodaki her commit
  `update-config, verify-delivery, Z3, Lean, commit-msg` **5/5 Passed** çıktısı
  verir (ör. `e6cbdca` kurulum commit'i).

> Kurulum tek komutla: `bash _calisma/CIKTI/setup_commit_hooks.sh` — bu,
> `git config commit.template .gitmessage` + `pre-commit install` +
> `pre-commit install --hook-type commit-msg` üçünü kurar.
