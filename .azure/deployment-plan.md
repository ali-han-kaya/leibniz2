# Azure Deployment Plan — verify-dashboard

> Üretim-yüzeyi: `_calisma/CIKTI/preview_server.py` dashboard'u (Dockerfile + `/api/health`
> healthcheck + `dashboard-state` kalıcı volume — docker-compose.yml'deki birebir karşılığı).
> Bu plan **azure-prepare** artifaktıdır; `Validated` statüsünü ve Validation-Proof
> bölümünü yalnız **azure-validate** skill'i doldurur.

**Status: Draft**

## 1. Hedef özeti

| Parametre | Değer | Kaynak |
|---|---|---|
| Servis | verify-dashboard (Python 3.11-slim container) | `Dockerfile:39,62` |
| Hedef-servis | Azure Container Apps | kullanıcı kararı (2026-09-23) |
| Bölge | `westeurope` | kullanıcı kararı (2026-09-23) |
| Kalıcı state | Azure Files share `dashboard-state` → mount `/app/state` | kullanıcı kararı; compose `dashboard-state` volume karşılığı |
| Healthcheck | `GET /api/health` (timeout 4s) | docker-compose.yml healthcheck |
| Log hedefi | Log Analytics (PerGB2018, 30 gün) | ACA entegrasyon standardı |
| Kayıt | ACR Basic (admin-user; azd push için) | infra/main.bicep |

## 2. Recipe

```yaml
recipe:
  type: containerapp        # azd: infra/main.bicep + azure.yaml services.dashboard
  service: dashboard
  port: 8000
  healthPath: /api/health
  stateMount: /app/state    # Azure Files (share: dashboard-state, quota 5 GiB)
  scale: { minReplicas: 1, maxReplicas: 3 }
```

## 3. Mimari notlar

- **Ingress/SSL:** ACA, otomatik HTTPS + public endpoint verir (`ACA_ENDPOINT` output).
  Uçlar dışarıya açılınca `/api/stop` allowlist'i (yalnız localhost) stop-isteğini reddeder —
  güvenli-taraf; dashboard kontrol-akışı yerelde kalır.
- **State:** trend-jsonl, kanıt-defterleri (DEPLOY_EVIDENCE.md dahil) ve `server_events.jsonl`
  `/app/state`'te yaşar; yeniden-dağıtımda korunur.
- **Sır yokluk:** repo'da hiçbir secret container-image'e gömülü değil (K7 hijyen-kapısı
  kanıtı); Azure tarafında da sır gerektirmiyor.
- **Kayan-taban riski:** `python:3.11-slim-bookworm` — docker-security haftalık cron-Trivy
  akışı Azure-image'e de uygulanabilir (ayrı takip; bu planın kapsamı dışı).

## 4. Maliyet-tahmini (aylık, westeurope kaba)

| Kaynak | SKU | Tahmin |
|---|---|---|
| Container Apps | 1 vCPU / 2 GiB, min 1 replika | ~$35–55 |
| Log Analytics | PerGB2018, düşük hacim | ~$5–10 |
| ACR | Basic | ~$5 |
| Azure Files | 5 GiB LRS | ~$0.6 |
| **Toplam** | | **~$45–70/ay** |

## 5. Öncül-checklist (azure-deploy'da tam liste)

- [ ] `az login` + abonelik onayı (kullanıcıdan **asla varsayma**)
- [ ] `azure-validate` tamamlanmış, bu planın Status'u `Validated`
- [ ] `infra/main.bicep` derleme-dogrulaması (`az bicep build`)
- [ ] Pre-deploy checklist (azure-deploy references) tamamen işaretli

## 6. Geri-alma (rollback)

`azd deploy` önceki revision'ı değiştirmez — rollback: `az containerapp revision list`
üzerinden önceki revision'a geri dönüş; tam-tear-down: `azd down` (yıkıcı —
azure-deploy kuralı gereği ayrı onay ister).

## 7. Validation Proof

> **BU BÖLÜM azure-validate TARAFINDAN DOLDURULUR — elle doldurulması yasaktır.**

(boş — henüz doğrulanmadı)
