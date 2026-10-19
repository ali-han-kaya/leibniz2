# ADR: token_delivery exit-code kontratının CI'a bağlanması (air-gapped, fail-closed)

**Durum:** Kabul edildi (2026-10-15 — `_calisma/CIKTI/token_delivery.py`,
`_calisma/CIKTI/test_token_delivery_contract.py` ve
`.github/workflows/token-delivery.yml` olarak uygulandı; bu ADR yazıldığı an
worktree'dedir, üçü de commit edilmemiştir — untracked).

**Bağlam:**

- İki-fazlı lease delivery tasarımının token sızıntısı özniteliği
  (`test_lease_token_fuzz.py`: gorevli token log/exception/stdout/metric/
  status_api yüzeylerinde **hiç** görünmez) CI'da bir giriş noktası
  bekliyordu. "Green is not evidence" disiplini CI'a taşınmalıydı:
  kapının kendi kendini kör edebileceği (vakuum) senaryosu da
  denetlenmeliydi.
- `verify.yml` yoğun sahiplik taşıyor: doc job tablosu iki-envaryant
  sözleşmesi (`test_doc_job_sync`), required set'in verify.yml'den
  türetilmesi (`status_checks`), artifact/merge-pattern kontratları — ve
  worktree'de başka ajanların staged+unstaged verify.yml işleri var.

## Kararlar

1. **Ayrı workflow dosyası** (`.github/workflows/token-delivery.yml`),
   verify.yml'e adım değil. Gerekçe: sahiplik izolasyonu (başkalarının
   uncommitted verify.yml işine dokunmamak) + yukarıdaki kontrat
   zincirlerine hiç girmemek. Sonuç: doc job tablosu, required set ve
   artifact listesi **etkilenmez** (yeni job `name:`'i tabloya girmez —
   girerse `test_doc_job_sync` invariant 1 ihlal olurdu çünkü o tablo
   yalnız verify.yml job'larını belgeler).
2. **Exit-code kontratı** (CI adımı bu kodları bekler):
   `0 PASS / 1 LEAK / 2 VACUITY / 3 ENV`. Fail-closed varsayılan: hiçbir
   hata yolu 0 üretmez; `evaluate()` saf çekirdek rc haritasını
   `test_token_delivery_contract` pin'ler.
3. **Air-gap mekanizma olarak, runner ayarı olarak değil:** GitHub
   Actions'ta adım bazlı ağ kesimi yoktur; bu yüzden `token_delivery.py`
   başlarken socket katmanını kapatır (`socket.socket /
   create_connection / getaddrinfo → RuntimeError`). Ağ çağrısı sızarsa
   istisna rc=3 olur — "ağ kullanılmadı" iddiası kodla zorlanır. Adımlarda
   pip kurulumu yoktur (stdlib only).
4. **Mutasyon canary ikinci adım:** `--redact off` kampanyası **rc=1
   dönmek zorunda**; rc=0 dönerse fuzzer/probe vakuumdur (kapının gözü
   kopmuştur) ve adım kırmızıya döner. Canary'ye rc≠1 (ör. 3) dönerse
   kontratin kendisi kiriktir — yine kırmızı. Her iki yönde de fail-closed.
5. **Artifact yok:** rapor `GITHUB_STEP_SUMMARY`'ye gömülür (dosya
   çalışma anında yazılır). Gerekçe: upload-artifact ekleme zincirine
   dokunmak ci-hygiene K4 retention sınıfını, PUBLISH_SCENARIO artifact
   listesini ve merge-pattern kontratlarını tetiklerdi — bu işin
   kapsamıdır, bu ADR'ın değildir.
6. **Tetikleyiciler:** `pull_request` + `workflow_dispatch`; `schedule`
   YOK (gated-schedules K1-K7 bağışık kalır). **Kullanım kuralı:** elle
   dispatch ana dala yapılmamalı — advisory `audit-live-ci` en son main
   run'ını inceler; PR koşumları bu denetimi etkilemez.
7. **Required check DEĞİLDİR:** branch-protection required set'i
   verify.yml job'larından türer; eklenmedi (eklemek ayrı politika
   kararıdır). Job yine fail-closed: kontrat kırmızıysa workflow kırmızıdır.
8. **Kırmızı sınıflandırma:** `test_gated_schedules` →
   `vercel-deploy-check.yml` parity kırmızısı bu bağlama **önceden
   mevcuttur** (HEAD'de de `schedule:` var ve 0 kapı script'i çağırıyor;
   iki dosya da başkalarının `MM` işleri). Bu iş kapsamı dışında; bu ADR
   onarmaz, yalnızca sahiplik notunu taşır.

## Kapı envanteri (yeni workflow bu kapıların hepsinden geçti — 2026-10-15, yerel)

| Kapı | Kapsam | Sonuç |
|------|--------|-------|
| ci_hygiene_gate (K1-K3) | tüm `*.yml` | PASS (permissions/concurrency/timeout var; upload yok → K4 n/a) |
| check_action_pins | tüm `uses:` | PASS (checkout@v7, setup-python@v7 pindi eşit) |
| check_python3_shell | tüm workflows | PASS (`shell: python3` adımı yok) |
| check_action_runtimes | workflows | PASS |
| test_gated_schedules | schedule'lı dosyalar | bağışık (0 `schedule:`) |
| test_doc_job_sync / workflow_contract / status_checks | verify.yml | etkisiz (verify.yml'e dokunulmadı; doğrulandı: OK) |
| actionlint | CI kapısı | yerel KURULU DEĞİL (sınırlılık; YAML bilinen-temiz desenlerle yazıldı) |

## Sonuçlar (yerel kanıt)

CLI: rc=0 (120 tohum, `--json --out` birebir CI arayüzü), rc=1 canary,
rc=3 usage. Kontrat testi 11/11 OK. Fuzz suiti yeşil. 4 dosya hijyen
temiz (final-newline, CR/trailing yok).

## Bağlantılı dokümanlar

- Test envanteri ve geçiş kuralları: `TEST_INVENTORY_CONTRACT.md` (taslak).
- Öznitelik kaynağı: `_calisma/CIKTI/test_lease_token_fuzz.py` (docstring).
