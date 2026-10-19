// K-katman durumu — SAF normalizasyon (React/Next importu yok).
//
// Tel şekli `/api/latest.layers`tır: verify_delivery.py'nin
// `build_layers_summary()` çıktısı, JSON'da anahtar→kayıt haritası:
//
//   {"K0": {"label": "...", "status": "PASS|FAIL|SKIP", "ran": true,
//           "findings": [{"id": "K8-Z3", "priority": "P0", "issue": "..."}]},
//    "UNREGISTERED": {...}}
//
// Sıra telde GARANTİ DEĞİL (JSON nesnesi); pano K0→K21 sırasını burada
// sabitler. Tanınmayan durum `UNKNOWN`a düşer ve nötr basılır — bilinmeyen
// bir durumu yeşile boyamak panoyu "her şey yolunda" diye okuturdu.

/** Tele beklenen katman sırası. Yeni bir K katmanı eklendiğinde buraya girer. */
export const LAYER_ORDER = [
  "K0",
  "K1",
  "K2",
  "K3",
  "K4",
  "K5",
  "K6",
  "K7",
  "K8",
  "K9",
  "K10",
  "K11",
  "K12",
  "K13",
  "K14",
  "K15",
  "K16",
  "K17",
  "K18",
  "K19",
  "K20",
  "K21",
] as const;

export type LayerKey = (typeof LAYER_ORDER)[number];

/** KAPALI durum kümesi: PASS yeşil, FAIL kırmızı, SKIP nötr, UNKNOWN nötr. */
export type LayerState = "PASS" | "FAIL" | "SKIP" | "UNKNOWN";

export type LayerView = {
  key: string;
  label: string;
  state: LayerState;
  ran: boolean;
  /** P0/P1 bulgu sayısı (INFO sayılmaz — katmanı FAIL yapmaz). */
  findings: number;
  /** İlk bulguların insan-okur metni (en fazla 3). */
  issues: string[];
};

const ISSUE_LIMIT = 3;

function stateOf(status: unknown): LayerState {
  const value = typeof status === "string" ? status.trim().toUpperCase() : "";
  if (value === "PASS" || value === "FAIL" || value === "SKIP") return value;
  return "UNKNOWN";
}

function issuesOf(findings: unknown): string[] {
  if (!Array.isArray(findings)) return [];
  const issues: string[] = [];
  for (const finding of findings) {
    if (!finding || typeof finding !== "object") continue;
    const record = finding as Record<string, unknown>;
    const issue = record.issue;
    if (typeof issue !== "string" || !issue.trim()) continue;
    const priority =
      typeof record.priority === "string" ? `${record.priority} ` : "";
    issues.push(`${priority}${issue}`.trim());
    if (issues.length >= ISSUE_LIMIT) break;
  }
  return issues;
}

/**
 * Ham `layers` haritasını sıralı, daraltılmış satırlara çevirir.
 *
 * K0-K21 önce sabit sırada; tanınan sıranın dışındaki anahtarlar (ör.
 * `UNREGISTERED`) alfabetik olarak sona eklenir — hiçbiri düşmez.
 */
export function normalizeLayers(
  raw: Record<string, unknown> | null | undefined
): LayerView[] {
  if (!raw || typeof raw !== "object") return [];
  const known = LAYER_ORDER.filter((key) => key in raw);
  const extra = Object.keys(raw)
    .filter((key) => !(LAYER_ORDER as readonly string[]).includes(key))
    .sort();
  const rows: LayerView[] = [];
  for (const key of [...known, ...extra]) {
    const entry = raw[key];
    if (!entry || typeof entry !== "object" || Array.isArray(entry)) continue;
    const record = entry as Record<string, unknown>;
    const state = stateOf(record.status);
    rows.push({
      key,
      label:
        typeof record.label === "string" && record.label.trim()
          ? record.label
          : key,
      state,
      // Durum SKIP ise koşmadı; alan yoksa durumdan türet (PASS/FAIL koştu).
      ran: typeof record.ran === "boolean" ? record.ran : state !== "SKIP",
      findings: Array.isArray(record.findings) ? record.findings.length : 0,
      issues: issuesOf(record.findings),
    });
  }
  return rows;
}

// P0/P1 bulgu ayrıntısı — `/layers` sayfasının alt kartı.
//
// Tel şekli (verify --json → preview_server findings[] → trend_runs.findings):
//   {"id":"K8-Z3","priority":"P0","check":"K8 sembolik ispat",
//    "issue":"z3-solver kurulu değil","evidence":"..."}
//
// `priority` KAPALI kümedir (P0/P1) — preview_server zaten yalnız bu ikisini
// yazar; yine de tanınmayan değer nötr kalır (sessizce P0'a terfi etmez).
export type FindingView = {
  id: string;
  priority: "P0" | "P1" | "UNKNOWN";
  /** İnsan-okur kontrol adı; yoksa id. */
  check: string;
  issue: string;
  evidence: string;
};

function findingPriority(value: unknown): FindingView["priority"] {
  const raw = typeof value === "string" ? value.trim().toUpperCase() : "";
  return raw === "P0" || raw === "P1" ? raw : "UNKNOWN";
}

/**
 * Ham bulgu dizisini sıralı, daraltılmış görünüme çevirir.
 *
 * `priority` sabittir: P0 önce, P1 sonra, tanınmayan en sonda. Girdi JSON
 * `null`/nesne-dışı öğeler içerebilir (Prisma Json kolonu) — bunlar düşer,
 * uydurma satır üretilmez.
 */
export function normalizeFindings(raw: unknown): FindingView[] {
  if (!Array.isArray(raw)) return [];
  const rows: FindingView[] = [];
  for (const item of raw) {
    if (!item || typeof item !== "object" || Array.isArray(item)) continue;
    const record = item as Record<string, unknown>;
    const id = typeof record.id === "string" ? record.id.trim() : "";
    const issue = typeof record.issue === "string" ? record.issue.trim() : "";
    const check =
      typeof record.check === "string" && record.check.trim()
        ? record.check.trim()
        : id;
    const evidence =
      typeof record.evidence === "string" ? record.evidence.trim() : "";
    if (!id && !issue) continue;
    rows.push({
      id: id || "—",
      priority: findingPriority(record.priority),
      check: check || id || "—",
      issue: issue || "—",
      evidence,
    });
  }
  const rank = { P0: 0, P1: 1, UNKNOWN: 2 } as const;
  return rows.sort((a, b) => rank[a.priority] - rank[b.priority]);
}

/** Özet sayaçlar — her durum için satır sayısı (eksik durum 0). */
export function layerCounts(rows: LayerView[]): Record<LayerState, number> {
  const counts: Record<LayerState, number> = {
    PASS: 0,
    FAIL: 0,
    SKIP: 0,
    UNKNOWN: 0,
  };
  for (const row of rows) counts[row.state] += 1;
  return counts;
}
