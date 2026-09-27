import { cva } from "class-variance-authority";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { panelCard, panelLabel, tableHead } from "@/components/panel-style";
import { getTrend } from "@/lib/preview";

// Koşum geçmişi tablosu — iki tüketici paylaşır:
//   app/@trend/page.tsx  → ana panonun kompakt slotu (küçük pencere)
//   app/trend/page.tsx   → tam sayfa görünümü (20 satır)
// İkisi de aynı sözleşmeyi okur; markup tek yerde kalır ki pencere/başlık
// dışındaki her şey sürüklenemesin.
//
// Markup shadcn ailesinden kurulur: `Card` (kabuk) + `Table`/`TableHeader`/
// `TableBody`/`TableRow`/`TableHead`/`TableCell`. Satır kenarı ve hücre
// dolgusu primitive'in varsayılanlarından gelir (`border-b` → --border,
// `p-2` + `px-4` → 6px/10px = preview.html'in `th, td` değerleri).
//
// patterns-explicit-variants: hucre-rengi kararlari (p0>0 kirmizi, p1>0 sari)
// cva-variant'ta — sira-bileseninde ternary-degil. Renkler repo-token'lari.
const cellVariants = cva("px-4", {
  variants: {
    tone: {
      neutral: "",
      error: "text-err",
      warn: "text-warn",
      muted: "text-muted",
    },
  },
  defaultVariants: { tone: "neutral" },
});

// Server Component — veri burada toplanır (VerdictCard ile aynı örüntü).
export default async function RunsTable({
  title,
  limit,
}: {
  title: string;
  limit: number;
}) {
  const { history } = await getTrend(limit);
  // Sıra sözleşmesi: `history` eskiden-yeniye gelir; pencereyi tüketici kısar
  // ve en-yeni üstte göstermek için çevirir (DB ve HTTP kaynağı aynı sözleşme).
  const rows = history.slice(-limit).reverse();

  return (
    <Card className={panelCard()}>
      <CardHeader>
        <h2 className={panelLabel()}>{title}</h2>
      </CardHeader>
      <CardContent>
        {history.length === 0 ? (
          <p className="text-sm text-muted">
            henüz veri yok — ilk run bekleniyor
          </p>
        ) : (
          <Table className="font-mono text-sm">
            <TableHeader>
              <TableRow>
                <TableHead className={tableHead}>ZAMAN</TableHead>
                <TableHead className={tableHead}>P0</TableHead>
                <TableHead className={tableHead}>P1</TableHead>
                <TableHead className={tableHead}>SÜRE</TableHead>
                <TableHead className={tableHead}>Z3</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((r, i) => (
                // Satır vurgusu `bg-surface-raised`: shadcn'ın `bg-muted/50`
                // gölgesi bu depoda yanlış çalışır — `--color-muted` pano
                // token'larında bir METİN rengi (globals.css notu).
                <TableRow key={i} className="hover:bg-surface-raised">
                  <TableCell className={cellVariants({ tone: "muted" })}>
                    {r.ts ?? "—"}
                  </TableCell>
                  <TableCell
                    className={cellVariants({
                      tone: (r.p0 ?? 0) > 0 ? "error" : "neutral",
                    })}
                  >
                    {r.p0 ?? "—"}
                  </TableCell>
                  <TableCell
                    className={cellVariants({
                      tone: (r.p1 ?? 0) > 0 ? "warn" : "neutral",
                    })}
                  >
                    {r.p1 ?? "—"}
                  </TableCell>
                  <TableCell className={cellVariants()}>
                    {r.duration_s != null ? `${r.duration_s}s` : "—"}
                  </TableCell>
                  <TableCell className={cellVariants()}>
                    {r.z3_total ?? "—"}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  );
}
