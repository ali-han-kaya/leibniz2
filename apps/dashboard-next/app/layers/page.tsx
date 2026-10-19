import { ViewTransition } from "react";

import LayerStatusGrid from "@/components/LayerStatusGrid";
import {
  PanelCard,
  PanelCardContent,
  PanelCardHeader,
  PanelCardTitle,
} from "@/components/PanelCard";
import {
  findingBadge,
  insetWell,
  microLabel,
  panelStack,
} from "@/components/panel-style";
import { Badge } from "@/components/ui/badge";
import { formatTimestamp } from "@/lib/format";
import { normalizeFindings, normalizeLayers } from "@/lib/layers";
import { getLayers } from "@/lib/preview";
import { cn } from "@/lib/utils";

export const metadata = { title: "Katmanlar" };

// Katman durumu her koşumda tazelenir; build anında dondurulamaz
// (`/trend` ile aynı gerekçe — kaynakta no-store sinyali yok).
export const dynamic = "force-dynamic";

// K0-K21 katman durumu + P0/P1 bulgu ayrıntısı.
//
// Kaynak seçimi `getLayers()`tadır ve `/trend` ile AYNIdır: `TREND_SOURCE`
// (veya DATABASE_URL) `db` ise `trend_runs.layers` / `trend_runs.findings`
// okunur — yani sayfa kalıcı Postgres arşivinden beslenir; `preview` ise
// canlı `/api/latest`. Hangi kaynağın ve hangi koşumun gösterildiği başlıkta
// YAZILIR: DB satırı bayat olabilir, "son koşum" demek bunu gizlememeli.
//
// Veri yoksa/erişilemezse sayfa SESSİZ boş kalmaz: sebep basılır (fail-closed
// görünürlük, sıfır katman uydurulmaz). Şema öncesi DB satırlarında `layers`
// kolonu boştur; o durum ayrı bir mesajla ayrılır.
export default async function LayersPage() {
  const result = await getLayers();
  const rows = result.ok ? normalizeLayers(result.layers) : [];
  const findings = result.ok ? normalizeFindings(result.findings) : [];
  const p0 = findings.filter((finding) => finding.priority === "P0").length;
  const p1 = findings.filter((finding) => finding.priority === "P1").length;
  const stamp =
    result.ok && result.ts ? ` · ${formatTimestamp(result.ts)}` : "";
  const source = result.source === "db" ? "Postgres arşivi" : "canlı preview";

  return (
    <ViewTransition>
      <div className={panelStack()}>
        <PanelCard>
          <PanelCardHeader>
            <PanelCardTitle>K0–K21 Katman Durumu</PanelCardTitle>
            <span className={microLabel()}>
              {source}
              {stamp}
            </span>
          </PanelCardHeader>
          <PanelCardContent>
            {!result.ok ? (
              <p className="text-sm text-warn">{result.reason}</p>
            ) : rows.length === 0 ? (
              <p className="text-sm text-muted">katman verisi yok</p>
            ) : (
              <LayerStatusGrid rows={rows} verdict={result.verdict} />
            )}
          </PanelCardContent>
        </PanelCard>

        {result.ok ? (
          <PanelCard>
            <PanelCardHeader>
              <PanelCardTitle>P0/P1 Bulgu Ayrıntıları</PanelCardTitle>
              <span className={microLabel()}>
                {findings.length} bulgu · P0 {p0} · P1 {p1}
              </span>
            </PanelCardHeader>
            <PanelCardContent>
              {findings.length === 0 ? (
                <p className="text-sm text-muted">
                  bu koşumda P0/P1 bulgusu yok
                </p>
              ) : (
                <ul className="grid gap-(--panel-block-gap)">
                  {findings.map((finding, index) => (
                    <li
                      key={`${finding.id}-${index}`}
                      className={cn(insetWell(), "border border-border")}
                    >
                      <div className="flex flex-wrap items-baseline gap-(--panel-block-gap)">
                        <Badge
                          className={findingBadge({
                            priority: finding.priority,
                          })}
                        >
                          {finding.priority}
                        </Badge>
                        <span className="font-mono text-xs tracking-data text-muted">
                          {finding.id}
                        </span>
                      </div>
                      <p className="mt-(--panel-tight-gap) text-sm text-fg">
                        {finding.check}
                      </p>
                      <p className="mt-(--panel-tight-gap) break-words text-sm">
                        {finding.issue}
                      </p>
                      {finding.evidence ? (
                        <p className="mt-(--panel-tight-gap) break-words font-mono text-xs text-muted">
                          {finding.evidence}
                        </p>
                      ) : null}
                    </li>
                  ))}
                </ul>
              )}
            </PanelCardContent>
          </PanelCard>
        ) : null}
      </div>
    </ViewTransition>
  );
}
