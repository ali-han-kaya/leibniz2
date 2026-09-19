/**
 * load.ts — history.jsonl → TrendRun tablosu (idempotent).
 *
 * Neon sözleşmesi: DATABASE_URL pooled (-pooler) bağlantıdır; Prisma Client
 * adapter ile kurulur (Prisma 7 SQL iş-akışı).
 *
 * Yükleme-semantiği (supabase-postgres-best-practices turu, 2026-09-19):
 * skill `data-batch-inserts` gereği satır-satır await yerine ~500'lük
 * `createMany` dilimleri (tek round-trip/dilim); `skipDuplicates: true`
 * → `ON CONFLICT DO NOTHING` (skill `data-upsert`'in insert-or-ignore
 * örüntüsü, atomik). Sayaçlar artık gerçek eklenen satırı verir.
 *
 * Kullanım: DATABASE_URL=... npm run load -- [history.jsonl yolu]
 * Varsayılan yol: TCC-mirror (~/Library/Caches/com.freebuff/preview/history.jsonl)
 */
import "dotenv/config";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import crypto from "node:crypto";
import { Prisma, PrismaClient } from "../generated/client";
import type * as runtime from "@prisma/client/runtime/client";
import type { TrendRunCreateManyInput } from "../generated/models";
import { PrismaPg } from "@prisma/adapter-pg";

const DEFAULT_SOURCE = path.join(
  os.homedir(),
  "Library",
  "Caches",
  "com.freebuff",
  "preview",
  "history.jsonl"
);

const sourcePath = process.argv[2] ?? DEFAULT_SOURCE;
if (!process.env.DATABASE_URL) {
  console.error(
    "DATABASE_URL yok — .env veya ortam değişkeni olarak pooled URL ver"
  );
  process.exit(1);
}

const adapter = new PrismaPg({ connectionString: process.env.DATABASE_URL });
const prisma = new PrismaClient({ adapter });

type Row = Record<string, unknown>;

function rowHash(row: Row): string {
  return crypto.createHash("sha256").update(JSON.stringify(row)).digest("hex");
}

function tsToDate(ts: unknown): Date {
  return new Date(String(ts));
}

function num(v: unknown): number | null {
  return typeof v === "number" ? v : null;
}

function str(v: unknown): string | null {
  return typeof v === "string" && v.length > 0 ? v : null;
}

function bool(v: unknown): boolean | null {
  return typeof v === "boolean" ? v : null;
}

function isJsonInput(v: unknown): boolean {
  if (
    typeof v === "string" ||
    typeof v === "number" ||
    typeof v === "boolean"
  ) {
    return true;
  }
  if (Array.isArray(v)) {
    return v.every((x) => x === null || isJsonInput(x));
  }
  if (typeof v === "object" && v !== null) {
    return Object.values(v).every((x) => x === null || isJsonInput(x));
  }
  return false;
}

/**
 * InputJsonValue tip-guardı (typescript-advanced-types turu, 2026-09-19):
 * skill'in "assertion yerine guard" ilkesi — `as never[]` escape-hatch'i
 * yerine derleyicinin kendi kontrolü. Prisma input-sözleşmesi: JSON alan
 * değerinde kök-`null` yalnız `NullableJsonNullValueInput` üzerinden
 * geçer (belirsizlik: DbNull vs JsonNull); üye-konumdaki `null` serbest.
 * Eksik kaynak-anahtarı → Prisma.DbNull (SQL NULL): eski loader'ın JS-null
 * davranışıyla birebir (JSON-null DEĞİL) — agregasyonlar ve
 * `equals: Prisma.DbNull` sorguları için tutarlı.
 */
function json(
  v: unknown
): Prisma.NullableJsonNullValueInput | runtime.InputJsonValue {
  if (v === null || v === undefined) {
    return Prisma.DbNull;
  }
  if (!isJsonInput(v)) {
    const kind = Array.isArray(v) ? "array" : typeof v;
    throw new Error(
      `JSON olmayan değer (kind=${kind}) — Prisma InputJsonValue sözleşmesi dışı`
    );
  }
  return v as runtime.InputJsonValue;
}

async function main() {
  const lines = fs
    .readFileSync(sourcePath, "utf-8")
    .split("\n")
    .filter((l) => l.trim().length > 0);
  console.log(`kaynak: ${sourcePath} (${lines.length} satır)`);

  let skipped = 0;
  const pending: TrendRunCreateManyInput[] = [];
  for (const line of lines) {
    const row: Row = JSON.parse(line);
    if (!row.ts || typeof row.verdict !== "string") {
      skipped += 1;
      continue;
    }
    const hash = rowHash(row);
    const data = {
      ts: tsToDate(row.ts),
      verdict: row.verdict,
      p0: num(row.p0) ?? 0,
      p1: num(row.p1) ?? 0,
      durationS: num(row.duration_s),
      durationPctWarn: bool(row.duration_pct_warn),
      budgetUsd: num(row.budget_usd),
      budgetLimit: num(row.budget_limit),
      budgetMethod: str(row.budget_method),
      refCount: num(row.ref_count),
      refsVerified: num(row.refs_verified),
      refsTotal: num(row.refs_total),
      refsMismatch: num(row.refs_mismatch),
      refsBySource: json(row.refs_by_source),
      z3Passed: num(row.z3_passed),
      z3Failed: num(row.z3_failed),
      z3Total: num(row.z3_total),
      leanOk: bool(row.lean_ok),
      leanSource: str(row.lean_source),
      leanOverride: bool(row.lean_override),
      leanDetail: json(row.lean_detail),
      lineageOk: bool(row.lineage_ok),
      lineageCount: num(row.lineage_count),
      lineageSummary: json(row.lineage_summary),
      patternDrift: json(row.pattern_drift),
      patternDriftDetail: json(row.pattern_drift_detail),
      cliOverrideCount: num(row.cli_override_count),
      cliOverrides: json(row.cli_overrides),
      hookEnv: json(row.hook_env),
      precommitHooks: json(row.precommit_hooks),
      statusBoard: json(row.status_board),
      findings: json(row.findings),
      auditRefsTrend: str(row.audit_refs_trend),
      flakyCount: num(row.flaky_count),
      deterministicCount: num(row.deterministic_count),
      exitCode: num(row.exit_code),
      rawSha256: str(row.raw_sha256),
      strippedSha256: str(row.stripped_sha256),
      historySidecarSha256: str(row.history_sidecar_sha256),
      pdfPages: num(row.pdf_pages),
      sourceRowSha256: hash,
    };
    pending.push(data);
  }
  // Tek createMany/dilim = tek round-trip (skill: data-batch-inserts,
  // 10-50x). skipDuplicates → ON CONFLICT DO NOTHING: aynı kaynak-tekrarı
  // (source_row_sha256) VE aynı ts çakışması sessizce atlanır.
  let insertedCount = 0;
  const CHUNK = 500;
  for (let i = 0; i < pending.length; i += CHUNK) {
    const res = await prisma.trendRun.createMany({
      data: pending.slice(i, i + CHUNK),
      skipDuplicates: true,
    });
    insertedCount += res.count;
  }
  console.log(
    `bitti: ${pending.length} kayıt işlendi (${insertedCount} eklendi), ${skipped} atlandı`
  );
  await prisma.$disconnect();
}

main().catch(async (e) => {
  console.error(e);
  await prisma.$disconnect();
  process.exit(1);
});
