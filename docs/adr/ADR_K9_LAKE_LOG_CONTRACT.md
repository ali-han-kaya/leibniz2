# ADR: K9 lake build logu — artifact + run summary fail-closed verdict

**Durum:** Kabul edildi (2026-10-15 — `.github/workflows/verify.yml`,
`run_summary_k9.py`, `consolidate_summary.py`, `gen_repro_manifest.py`'de
uygulandı; bu ADR yazıldığı an worktree'dedir, commit edilmemiştir).

**Bağlam:**

- Verify işinin "Run Lean lake build (K5-K11 separate step)" adımı betiği zaten
  `sh verify_lean_lake.sh 2>&1 | tee lean_lake_build.log` ile yazıyordu; log
  hiçbir artifact'a yüklenmiyordu — lake kapısı FAIL olursa kanıt run sonunda
  kayboluyordu.
- Run summary'de K9 görünürlüğü yalnız `klayers.json`'daki `verify_delivery`
  K9'una bağlıydı; ayrı fail-closed lake adımının kendi çıktısına dair özet yoktu
  (repo yorumu: "lake-proof job ayrıca bağımsız kapıdır").

**Karar:**

1. **Artifact:** `lean-lake-build-log` (verify işi, `if: always()` — kapı FAIL
   olsa bile kanıt saklanır; `if-no-files-found: error`; retention 30 gün).
2. **Run summary:** `run_summary_k9.py` aynı logu (tek kaynak) okur; durum
   sözleşmesi fail-closed:
   - `[K9-LAKE] PASS` → PASS (✅ + marker satırları)
   - `[K9-LAKE] FAIL` → FAIL (🔴 + ilk hata satırları)
   - **Log var ama verdict işareti yok (timeout/kesilme) → FAIL** — PASS asla
     türetilmez (yarım `tee` çıktısı yeşil sayılamaz)
   - Log yok → MISSING (⚠️ advisory not; consolidate exit'i etkilemez)
3. **Dört sözleşmenin birlikte değişmesi zorunlu:** verify.yml upload +
   merge pattern girişi, `ARTIFACT_JOBS["lean-lake-build-log"] = "verify"`,
   `PUBLISH_SCENARIO.md` artifact listesi (40→41), `consolidate_summary`
   SECTIONS + durum panosu (`K9 lake build` etiketi, K katmanları ile K12
   arasında).
4. **Ayrım:** Bu bölüm `verify_delivery` K9'unu (klayers `lean_proof`) DEĞİL,
   ayrı lake adımının kendi çıktısını gösterir — iki kapı birbirinin yerine geçmez.

**Sonuçlar:**

- Lake kapısının kanıtı her run'da (yeşil ya da kırmızı) indirilebilir.
- Durum panosu eksik/koşulmamış lake adımını ⚠️ ile görünür kılar.
- `summary_pattern_drift`/`check_workflow_artifact_docs` bu artifact'ı
  fail-closed denetler (doküman-senkron ailesi).

**Reddedilen alternatifler:**

- *Logu `precommit-logs`/`logs/` içine taşımak:* lake adımı logs/ yazmaz;
  ayrı artifact adı indirilebilirliği ve manifest takibini netleştirir.
- *Verdict'süz logu advisory saymak:* yarım kalmış derleme yeşil raporlanır —
  fail-closed ilkesiyle bağdaşmaz.

**Kapı bağı:** `test_run_summary_k9.py`, `test_consolidate_summary.py`,
`test_summary_pattern_drift.py`, `test_doc_artifact_sync.py`,
`test_workflow_contract.py`, `test_gen_repro_manifest.py`.

**Doğrulama (uygulama anı):** Gerçek lake 5.0.0 / Lean 4.14.0 (CI sürümü) ile
gerçek `verify_lean_lake.sh` koşumu → `[K9-LAKE] PASS` → summary bölümü + pano
`K9 lake build ✅`; odak batch 174/174.
