# pre-commit patch kalıntısı — 2026-09-28

`~/.cache/pre-commit/patch*` içinde 24s+ yaşlı **9 yetim** vardı ve
her worktree'deki commit'i blokluyordu (`check-precommit-orphans`
fail-closed). Bu dizin, kapının kendi önerdiği
`_calisma/CIKTI/recovery_patches_<tarih>/` deseniyle aynı yöntemle
kurtarıldı: **önce kopyalandı, doğrulandı, sonra silindi**.

Aynı içerikli tekrarlar (ölü pre-commit koşumlarının art arda
snapshot'ları) tek kopyayla temsil edilir; `tekrar` sütunu kaç
cache adının o içerikle eşleştiğini gösterir.

| dosya | bayt | yaş | sha256 (kısa) | md5 (kısa) | tekrar | bloklayan |
|---|---|---|---|---|---|---|
| `patch1790473294-15456` | 47985 | 24.5h | `51ff1e021eb0…` | `7a1ed9fb9519…` | 3 | 4 |
| `patch1790474169-42397` | 47538 | 24.2h | `794951263a20…` | `ad5946dc8434…` | 1 | 2 |
| `patch1790474548-62535` | 37782 | 24.1h | `a065e57ea550…` | `b22207171288…` | 2 | 3 |
| `patch1790475353-8775` | 64325 | 23.9h | `6ee498e7a4e7…` | `247811b726bb…` | 0 | 0 |
| `patch1790484557-55606` | 17192 | 21.4h | `6250f613b48d…` | `7bf9e0dad382…` | 0 | 0 |
| `patch1790484861-62494` | 15489 | 21.3h | `622f21e2083c…` | `dbc066e078e2…` | 0 | 0 |
| `patch1790485592-83937` | 40229 | 21.1h | `d98695428a19…` | `c2193a6a4352…` | 0 | 0 |
| `patch1790487215-5164` | 13936 | 20.6h | `0a715ade9b08…` | `2d04d36d88be…` | 3 | 0 |
| `patch1790527577-24105` | 5741 | 9.4h | `13329c954db8…` | `040794834ee9…` | 1 | 0 |
| `patch1790527912-44775` | 5715 | 9.3h | `71c7147d77f0…` | `cb555d935b0d…` | 1 | 0 |
| `patch1790530135-13343` | 11170 | 8.7h | `761fc4330d8e…` | `5dfe3e47171f…` | 1 | 0 |

## Dokunulan dosyalar (patch başına)

**`patch1790473294-15456`** (14 dosya)
- `_calisma/CIKTI/audit_live_ci_sync.py`
- `_calisma/CIKTI/check_unit_tests.list`
- `_calisma/CIKTI/status_checks.py`
- `_calisma/CIKTI/test_atomic_write_guard.py`
- `_calisma/CIKTI/test_audit_live_ci_sync.py`
- `_calisma/CIKTI/test_sidecar_guarantee.py`
- `_calisma/CIKTI/test_texlive_repro_documented.py`
- `_calisma/CIKTI/texlive_determinism_hook.sh`
- `_calisma/CIKTI/texlive_determinism_test.sh`
- `_calisma/CIKTI/workflow_contract.py`
- `docs/HISTORY_CLEANUP.md`
- `docs/PUBLISH_SCENARIO.md`
- `docs/publish_precheck.sh`
- `skills/verify-chain/SKILL.md`

**`patch1790474169-42397`** (13 dosya)
- `_calisma/CIKTI/audit_live_ci_sync.py`
- `_calisma/CIKTI/status_checks.py`
- `_calisma/CIKTI/test_atomic_write_guard.py`
- `_calisma/CIKTI/test_audit_live_ci_sync.py`
- `_calisma/CIKTI/test_sidecar_guarantee.py`
- `_calisma/CIKTI/test_texlive_repro_documented.py`
- `_calisma/CIKTI/texlive_determinism_hook.sh`
- `_calisma/CIKTI/texlive_determinism_test.sh`
- `_calisma/CIKTI/workflow_contract.py`
- `docs/HISTORY_CLEANUP.md`
- `docs/PUBLISH_SCENARIO.md`
- `docs/publish_precheck.sh`
- `skills/verify-chain/SKILL.md`

**`patch1790474548-62535`** (10 dosya)
- `_calisma/CIKTI/audit_live_ci_sync.py`
- `_calisma/CIKTI/status_checks.py`
- `_calisma/CIKTI/test_atomic_write_guard.py`
- `_calisma/CIKTI/test_audit_live_ci_sync.py`
- `_calisma/CIKTI/test_sidecar_guarantee.py`
- `_calisma/CIKTI/workflow_contract.py`
- `docs/HISTORY_CLEANUP.md`
- `docs/PUBLISH_SCENARIO.md`
- `docs/publish_precheck.sh`
- `skills/verify-chain/SKILL.md`

**`patch1790475353-8775`** (16 dosya)
- `.github/workflows/verify.yml`
- `README.md`
- `_calisma/CIKTI/audit_live_ci_sync.py`
- `_calisma/CIKTI/status_checks.py`
- `_calisma/CIKTI/test_advisory_coe_surfacing.py`
- `_calisma/CIKTI/test_atomic_write_guard.py`
- `_calisma/CIKTI/test_audit_live_ci_sync.py`
- `_calisma/CIKTI/test_sidecar_guarantee.py`
- `_calisma/CIKTI/test_texlive_repro_documented.py`
- `_calisma/CIKTI/texlive_determinism_hook.sh`
- `_calisma/CIKTI/texlive_determinism_test.sh`
- `_calisma/CIKTI/workflow_contract.py`
- `docs/HISTORY_CLEANUP.md`
- `docs/PUBLISH_SCENARIO.md`
- `docs/publish_precheck.sh`
- `skills/verify-chain/SKILL.md`

**`patch1790484557-55606`** (5 dosya)
- `_calisma/CIKTI/check_unit_tests.list`
- `_calisma/CIKTI/test_check_design_tokens.py`
- `_calisma/CIKTI/test_coverage_report.py`
- `_calisma/CIKTI/test_surface_cwv_report.py`
- `design-system/scripts/check_tokens.py`

**`patch1790484861-62494`** (3 dosya)
- `_calisma/CIKTI/test_check_design_tokens.py`
- `_calisma/CIKTI/test_surface_cwv_report.py`
- `design-system/scripts/check_tokens.py`

**`patch1790485592-83937`** (10 dosya)
- `_calisma/CIKTI/test_check_design_tokens.py`
- `_calisma/CIKTI/test_surface_cwv_report.py`
- `apps/dashboard-next/app/(panel)/@trend/loading.tsx`
- `apps/dashboard-next/app/(panel)/@verdict/loading.tsx`
- `apps/dashboard-next/app/VerdictCard.tsx`
- `apps/dashboard-next/app/error.tsx`
- `apps/dashboard-next/app/globals.css`
- `apps/dashboard-next/app/layout.tsx`
- `apps/dashboard-next/components/RunsTable.tsx`
- `design-system/scripts/check_tokens.py`

**`patch1790487215-5164`** (2 dosya)
- `_calisma/CIKTI/test_check_design_tokens.py`
- `design-system/scripts/check_tokens.py`

**`patch1790527577-24105`** (4 dosya)
- `_calisma/CIKTI/check_unit_tests.list`
- `_calisma/CIKTI/test_coverage_report.py`
- `apps/trend-db/prisma/schema.prisma`
- `docs/TREND_CHART_READ_PATH.md`

**`patch1790527912-44775`** (4 dosya)
- `_calisma/CIKTI/check_unit_tests.list`
- `_calisma/CIKTI/test_coverage_report.py`
- `apps/trend-db/prisma/schema.prisma`
- `docs/TREND_CHART_READ_PATH.md`

**`patch1790530135-13343`** (3 dosya)
- `.github/workflows/verify.yml`
- `_calisma/CIKTI/check_security_browser.list`
- `_calisma/CIKTI/test_dashboard_keyboard_nav.py`

