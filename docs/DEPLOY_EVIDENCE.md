## Kanıt-defteri

| Tarih | HEAD (origin/main) | verify-delivery | docker-security | test-smoke | determinism-trend |
|---|---|---|---|---|---|
| 2026-09-22 | da58b14 | [success #35593197353](https://github.com/ali-han-kaya/leibniz2/actions/runs/35593197353) | [success #35593197488](https://github.com/ali-han-kaya/leibniz2/actions/runs/35593197488) | [success #35593197727](https://github.com/ali-han-kaya/leibniz2/actions/runs/35593197727) | [failure #35580855610](https://github.com/ali-han-kaya/leibniz2/actions/runs/35580855610) |
| 2026-10-05 | 77d05e3 | [failure #37270510556](https://github.com/ali-han-kaya/leibniz2/actions/runs/37270510556) | [failure #37270510666](https://github.com/ali-han-kaya/leibniz2/actions/runs/37270510666) | [success #37270510649](https://github.com/ali-han-kaya/leibniz2/actions/runs/37270510649) | [success #37242819374](https://github.com/ali-han-kaya/leibniz2/actions/runs/37242819374) |
| 2026-10-05 | b1f5f1e | [failure #37272394821](https://github.com/ali-han-kaya/leibniz2/actions/runs/37272394821) | [failure #37272394862](https://github.com/ali-han-kaya/leibniz2/actions/runs/37272394862) | [success #37272394778](https://github.com/ali-han-kaya/leibniz2/actions/runs/37272394778) | [success #37297101317](https://github.com/ali-han-kaya/leibniz2/actions/runs/37297101317) |
| 2026-10-05 | f79992c | [failure #37309920285](https://github.com/ali-han-kaya/leibniz2/actions/runs/37309920285) | [failure #37309920425](https://github.com/ali-han-kaya/leibniz2/actions/runs/37309920425) | [success #37309920393](https://github.com/ali-han-kaya/leibniz2/actions/runs/37309920393) | [success #37297101317](https://github.com/ali-han-kaya/leibniz2/actions/runs/37297101317) |

> Not (2026-10-05): verify-delivery kırmızısı yalnızca **advisory** "Live CI doc↔GitHub sync audit" job'ından; diğer tüm job'lar yeşil. docker-security kırmızısı `libpcre2-8-0` **CVE-2026-103111** (düzeltme PR #82'de).

## Bayatlık kapısı (haftalık cron)

Bu defter **elle yazılır**; tazeliği `deploy-evidence` workflow'unda fail-closed
denetlenir. Cron `47 3 * * 1` — determinism-trend'in haftalık ölçümü
(`17 3 * * 1`) bittikten SONRA: önce ölçüm kaydı (PR → main), sonra bu defterin
o ölçümü değerlendirmesi. Sıralama `test_gated_schedules.py` içinde kıvidir.

```bash
python3 _calisma/CIKTI/deploy_evidence.py --check   # kapı (yerel)
python3 _calisma/CIKTI/deploy_evidence.py --print   # satırları TSV olarak gör
```

Dört denetim ekseni:

- **Yapı** — başlık beklenen sütunlarda, her satır 6 hücre, tarih ISO, HEAD kısa-hex, koşum hücresi `<conclusion> #<run_id>`.
- **HEAD kapsamı** — en yeni satır origin/main'in atası ve en fazla **3 anlamlı commit** geride. Kanıt satırı ve changelog commit'leri (`docs(deploy)`, `chore(changelog)`) sayılmaz: onlar kanıtı geriye götürmez, tam olarak geride olduğunun kaydıdır. Sayım `origin/main`'e karşı yapılır.
- **Yaş** — en yeni satır 21 günden eski değil (haftalık cron + iki haftalık tolerans), gelecek tarihli de olamaz.
- **Koşum gerçekliği** — en yeni 2 satırdaki run id'ler GitHub'da var ve hücrede yazan sonuçla **birebir** aynı. Eski satırlar canlıya sorulmaz (log saklama süresi geçmişte yanlış kırmızı üretirdi). Geçici API hatası 3 kez yeniden denenir; hâlâ erişilemiyorsa `DOGRULANAMADI` (altyapı) ile `sapmasi` (kanıt yanlış) ayrı raporlanır — ikisi de kırmızı, ama farklı eylem gerektirir.

**Kırmızı olduğunda:** en yeni HEAD'in dört koşumu bittikten sonra o HEAD için satır
ekle — yaş, HEAD açığı ve sonuç sapması aynı eylemle kapanır. Sadece `BAYAT:` satırı
yazan koşumları yeşile çevirmek kanıtı düzeltmez, yoksa eder.

Çıkış kodları: **0** taze · **1** bayat kanit (job kırmızı) · **2** ölçülemez
(defter yok, `gh` yok, owner/repo çözülemedi — kırmızı sayılır).
