# Commit'lenmemiş iş envanteri (2026-09-27 → kapanış 2026-09-28)

> **Kapanış (2026-09-28):** envanterdeki üç kalem de karara bağlandı ve
> yürütüldü — P1 worktree'si kendi dalında commit'lendi, P2 stash'lerine
> dokunulmadı, P3 migration'ları canlıya uygulandı. Ayrıca commit'i bloklayan
> 23 yetim pre-commit patch'i arşivlenip karantinaya alındı. Kararlar ve
> kanıtlar: §C–§F.

Bu dosya **ölçüm kaydıdır**: "ne commit'li, ne commit'lenmemiş, kimin kararı"
sorusunun cevabı. Amaç, commit'lenmemiş iş riskini görünmez olmaktan
çıkarmak — risk silinmez, **görünür ve sahiplenilir hâle gelir**.

> Yöntem: `git status --porcelain -uall` (ana ağaç), `git worktree list` +
> her worktree'nin `status`, `git stash list` + her stash'in `^3` (gizli
> untracked) ağacı ve **blob geçmişi testi** (`git log --all
> --find-object=<blob>`: içerik depoda daha önce commit'lenmiş mi?).
> Tahmin yok, ölçüm var.

## A. Oturumda adı geçen üç iş — **üçü de commit'li**

| # | İş | Durum | Commit |
|---|---|---|---|
| 1 | Tip-güvenli loader (`InputJsonValue` tip-guard'ı, `load.ts` `json()`) | ✅ commit'li | `07e22aa` (2026-09-19) |
| 2 | 50 hook'lu pre-commit zinciri | ✅ commit'li, bugün **59** hook | `07e22aa` (47→50), son ekleme `9b4133b` |
| 3 | Parmak-izi (orphan patch) kapısı | ✅ commit'li, 3 tur | `07e22aa` → `a624cdb` (arşiv globu) → `11ea4c1` (çift parmak-izi + özel uyarı) |

Bu oturumun (2026-09-27) kendi commit'leri:

- `e3ef72d` — trend-db loader: `--dry-run --json` makine-okunur yüzey +
  JS tarafı minimal test koşucusu (11 vaka) + Python sarmalayıcı kapısı.
- `11ea4c1` — precommit-orphans: yetim patch'e sha256+md5 çift parmak-izi,
  çıktının en üstünde özel `BİLİNEN OLAY PARMAK-İZİ` uyarı bloğu.

**Ana çalışma ağacı tamamen temiz**: `git status --porcelain -uall` → boş.
Bu oturumdan commit'lenmemiş tek bir dosya yok.

## B. Gerçekten commit'lenmemiş iş — üç kalem, üç farklı sahip

### P1 — `feat/github-site-sample` worktree'sinde 8 untracked dosya
`git worktree list` → `.worktrees/github-site-sample` (`a24c4db`, main'e
**merge'li değil**). Bu dal **başka bir thread'in** işi; sahiplik belirsiz
olduğu için dokunulmadı.

| Dosya | main'deki durumu |
|---|---|
| `design-system/github/sample.html` (21 kB) | **yok** — yalnız burada |
| `design-system/github/scripts/check_github_primer_sample.py` (10 kB) | **yok** — yalnız burada |
| `docs/ADR-0001-pinokio-launcher-javascript.md` (2.6 kB) | **yok** — depoda hiç ADR yok |
| `design-system/github/README.md` | **farklı** (worktree 11 645 B, main 10 027 B) |
| `design-system/github/raw.json` | **farklı** (worktree 88 589 B, main 87 689 B) |
| `tokens.css` · `tokens.json` · `check_github_tokens.py` | main ile **ayni** (kopya) |

> Risk: bu worktree `git worktree remove`/disk temizliğiyle giderse 3 dosya
> **yalnız** orada olduğu için kalıcı olarak kaybolur. Doğru yer: kendi
> dalında commit (main'e karıştırmadan).

### P2 — 2 eski stash: uygulanırsa **iş kaybı değil, iş kaybı üretir**
`stash@{0}` "pre-reword-stash: dirty entries from other threads" (taban
`512be11`), `stash@{1}` "gen changelog + github_scripts defensive" (taban
`831b941`). Tabanlar HEAD'den **yüzlerce commit geride**; bu yüzden stash
ağacı, HEAD'e göre büyük ölçüde **eksik** bir anlık görüntüdür.

Kanıt — `git diff --numstat HEAD stash@{N}` (`+` = stash'ta yeni satır):

| Dosya | + | − | Yorum |
|---|---|---|---|
| `.github/workflows/verify.yml` | 62 | **892** | iş akışı kısaltılmış sürüm |
| `.pre-commit-config.yaml` | 11 | **276** | **50 hook'lu zincir silinirdi** |
| `README.md` | 21 | **244** | changelog silinirdi |
| `_calisma/CIKTI/check_unit_tests.list` | **0** | 51 | 51 test kaydı kaybolurdu |
| `_calisma/CIKTI/texlive_determinism_test.sh` | 14 | 126 | — |
| `_calisma/CIKTI/test_workflow_contract.py` | 16 | 42 | — |
| `docs/PUBLISH_SCENARIO.md` | 27 | 36 | — |

Hiçbir dosyada saf ekleme yok. Gizli untracked ağaç (`stash^3`) da yeni iş
değil: `.venv_z3/`, `__pycache__/`, `.build/`, `_calisma/TOOLKIT/` —
hepsi `.gitignore`'da (satır 18 / 68 / 140) ve yeniden üretilebilir; ayrıca
`docs/archive/rc-review-20260831/{run,review_dispatch}.md` **eski** sürümler
(`028d744` bu dosyaları taşınabilir yola normalize ederek commit'lemişti;
stash'teki kopya normalize edilmemiş hâli).

> Risk: **tehlike yanlış yönde.** "Commit'lenmemiş işi kaybetmeyelim" diye
> bu iki stash'i uygulamak/geri almak ~1 700 satırı **silmek** olurdu.
> Doğru işlem: dokunmamak (veya bilinçli olarak düşürmek).

### P3 — Migration'lar repoda, veritabanında **uygulanmamıştı** → uygulandı
`20260927193000_trend_runs_rls` + `20260927194500_trend_runs_query_indexes`
dosya olarak commit'liydi; `prisma migrate deploy` çalıştırılmamıştı. Bu commit
konusu değil, **çalışma zamanı eylemi**ydi: RLS + index'ler canlı DB'de yoktu,
yani "RLS hazır" iddiası o an gerçek değildi. **2026-09-28'de uygulandı** (§D).

## C. Kararlar — soruldu ve uygulandı (2026-09-28)

| Kalem | Soru | Karar | Sonuç |
|---|---|---|---|
| P1 worktree dosyaları | `feat/github-site-sample` dalında commit'lenir mi, silinir mi? | **kendi dalında commit'le** | `2ef1821` (9 dosya, 51 hook yeşil, worktree artık temiz) |
| P2 stash'ler | Uygulansın mı, düşürülsün mü, dursun mu? | **dokunma** | Değişiklik yok; kanıt §B tablosu |
| P3 migration | `migrate deploy` çalıştırılsın mı? | **canlıya uygula** | §D |

Kalemler farklı thread'lerde doğduğu için karar sahipliği kullanıcıya
soruldu; yukarıdaki sonuçlar o kararların uygulanmış hâlidir. Yeni bir
untracked dosya ya da stash belirdiğinde tabloyu güncelle — kayıt, kapının
kendisi kadar değerlidir.

## D. P3 sonucu — migration'lar canlıya uygulandı

`DATABASE_URL="$DATABASE_URL_UNPOOLED" npx prisma migrate deploy` ile
`20260927193000_trend_runs_rls` ve `20260927194500_trend_runs_query_indexes`
uygulandı; pooled bağlantıya dokunulmadı. Yazma yolu köprü (grant) üzerinden
**rollback'li bir prob** ile doğrulandı: sayaç 269 → 270 → 269, kalıcı iz yok.
`apps/trend-db/README.md`'deki artık yanlış olan "migration uygulama bekliyor"
iddiası kaldırıldı.

## E. Yetim pre-commit patch'leri — arşiv + karantina

Kapı (`check_precommit_orphans.py`) commit'i blokluyordu. Teşhis: `exit 1`
gizli bir eksik patch'ten değil, **kapının tasarımından** geliyordu — 24
saatten eski her patch fail-closed bloklar; KNOWN-INCIDENT etiketi *uyarıdır*,
muafiyet değildir (iki test bunu `returncode == 1` ile sabitler). Cache'teki
24 patch'in 23'ü arşivle sha256 birebir aynıydı; kalan 1'i
(`patch1790561449-4597`, 5.8 saatlik) taze ve eşleşmesiz → zaten bloklamıyordu.
Yani "kapsanmamış 24. patch" hipotezi **yanlış** çıktı.

| Ölçüm | Değer |
|---|---|
| Cache'teki patch | 24 |
| Arşivle birebir (sha256) aynı | 23 (11 benzersiz içerik) |
| Arşivle eşleşmeyen, dokunulmadı | 1 — taze, kurtarma penceresinde |
| Arşiv | `_calisma/CIKTI/recovery_patches_20260928/` — MANIFEST + 11 patch |
| Karantina | `~/.cache/pre-commit-orphans-quarantine-20260928/` — 23 patch + MANIFEST |

Karantina **silme değil taşımadır**: her dosyanın arşivde byte-eşdeğeri var,
yani bilgi kaybı yok. Taşıma sonrası kapı `exit 0`; 18 kapı testi `OK`. Geri
almak için karantinadaki dosyayı `~/.cache/pre-commit/` içine geri taşımak
yeterli.

## F. `klayers.json` — commit'lenmedi

`_calisma/CIKTI/klayers.json` (2.7 kB, `verdict: PASS`, 22 katman) bu oturumda
09:23'te üretilmiş bir **koşum sidecar'ı**. Üreticisi `verify_delivery.py
--klayers-out`; tüketicisi `_calisma/mcp/verify_mcp/server.py`, ama onu bir
*preview dir*'den okur — `CIKTI/`'den değil. İçinde zaman damgası yok,
provenance kaydı yok. Bu yüzden commit'lenmedi, untracked bırakıldı ve burada
belgelendi. (`CIKTI/` içinde 512 dosya izleniyor; ama izlenenler adlandırılmış
kanıt dosyaları, bu ise geçici bir sidecar.)
