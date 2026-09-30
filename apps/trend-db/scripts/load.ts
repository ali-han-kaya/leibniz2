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
 * `--dry-run` (2026-09-27): DB'ye dokunmadan ön-uçuş raporu. Eşleme TEK
 * kaynaktan (`prepare()`) geçtiği için rapor gerçek koşudan ayrışamaz;
 * kaynak dosyanın SHA-256'sı + kaç satırın ekleneceği/atlanacağı basılır.
 * Bu modda Prisma Client kurulmaz ve DATABASE_URL GEREKMEZ (kimlik bilgisi
 * olmayan makinede/CI'da koşabilir). Çıkış kodu gerçek koşunun kaderini
 * yansıtır: 0 = yüklenebilir, 1 = kaynak bozuk/okunamaz, 2 = kullanım hatası.
 * Mevcut satırlarla çakışma bağlantısız ÖLÇÜLEMEZ — rapor bunu "en çok
 * eklenecek / en az atlanacak" olarak işaretler.
 *
 * `--check-db` / `--keys-file=<yol>` (2026-09-28, 3. TDD turu): dry-run'ın
 * "en çok/en az" sınırını KESİN sayıya çeviren çakışma kaynakları. Yalnız
 * `--dry-run` ile verilir; ikisi BİRLİKTE verilemez (tek kaynak).
 *   - `--check-db`: mevcut satırlar SALT-OKUNUR okunur (findMany SELECT ts,
 *     source_row_sha256) → `insert`/`skip` gerçek olur. DATABASE_URL yoksa
 *     belirsiz rapor basmak yerine çıkış 1 (kesin sayı isteyen çağıran,
 *     sınır dilini kesin sanmasın).
 *   - `--keys-file=<yol>`: aynı ölçüm kimlik bilgisi olmadan, JSONL anlık
 *     görüntüsünden (`{"ts": ...}` ve/veya `{"source_row_sha256": ...}`).
 *     `=` biçimi şarttır: `--keys-file yol` yazımı yolu konum argümanı
 *     sanardı (sessiz yanlış kaynak) → çıkış 2.
 * Ölçülen modda prose "(kesin)" der ve "bu raporda YOK" iddiasını düşürür.
 *
 * `--json` (2026-09-27, 2. TDD turu): `--dry-run` raporunun MAKİNE-okunur
 * karşılığı — prose'in yerine tek satır JSON (aynı `prepare()` sayıları).
 * İnsan-okunur Türkçe prose bu modda insan içindir; bir betiğin/başka bir
 * dilin tükettiği sözleşme JSON'dır. `--json` TEK BAŞINA anlamsızdır
 * (gerçek koşuda "eklenecek" sayısı ancak DB'ye yazdıktan sonra bilinir)
 * → kullanım hatası, çıkış 2 (fail-closed: sessizce prose'e düşmez).
 *
 * Kullanım: DATABASE_URL=... npm run load -- [history.jsonl yolu] [--dry-run]
 *   [--json] [--check-db | --keys-file=<yol>]
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

const USAGE =
  "kullanım: DATABASE_URL=... npm run load -- [history.jsonl yolu] [--dry-run]" +
  " [--json] [--check-db | --keys-file=<yol>]";
const KEYS_FILE_PREFIX = "--keys-file=";
const KNOWN_FLAGS = new Set(["--dry-run", "--json", "--check-db"]);

// Bayraklar konumdan bağımsızdır; bilinmeyen bayrak sessizce yutulmaz
// (fail-closed): `--dri-run` yazım hatası gerçek yükleme başlatmasın.
const argv = process.argv.slice(2);

// `--keys-file` YALNIZ `=` biçiminde kabul edilir. Boşluklu yazımda yol
// konum argümanı sanılır ve "fazla argüman"a düşerdi; hangi hatanın
// olduğunu söylemek için bunu bilinmeyen-bayrak denetiminden ÖNCE ele al.
if (argv.some((a) => a === "--keys-file")) {
  console.error(`--keys-file=<yol> biçiminde verilmeli — ${USAGE}`);
  process.exit(2);
}
const keysFileArg = argv.find((a) => a.startsWith(KEYS_FILE_PREFIX));
const keysFile =
  keysFileArg === undefined
    ? undefined
    : keysFileArg.slice(KEYS_FILE_PREFIX.length);
if (keysFile !== undefined && keysFile.length === 0) {
  console.error(`--keys-file=<yol> boş olamaz — ${USAGE}`);
  process.exit(2);
}

const unknownFlags = argv.filter(
  (a) =>
    a.startsWith("--") && !KNOWN_FLAGS.has(a) && !a.startsWith(KEYS_FILE_PREFIX)
);
if (unknownFlags.length > 0) {
  console.error(`bilinmeyen bayrak: ${unknownFlags.join(", ")} — ${USAGE}`);
  process.exit(2);
}
const dryRun = argv.includes("--dry-run");
const jsonMode = argv.includes("--json");
const checkDb = argv.includes("--check-db");
if (jsonMode && !dryRun) {
  console.error(
    `--json yalnız --dry-run ile birlikte kullanılabilir — ${USAGE}`
  );
  process.exit(2);
}
// Çakışma ölçümü yalnız dry-run'ın anlamıdır: gerçek koşuda "eklenecek"
// sayısı ancak yazdıktan sonra bilinir (ölçüm yazımdan önce yalan olur).
if (checkDb && !dryRun) {
  console.error(
    `--check-db yalnız --dry-run ile birlikte kullanılabilir — ${USAGE}`
  );
  process.exit(2);
}
if (keysFile !== undefined && !dryRun) {
  console.error(
    `--keys-file yalnız --dry-run ile birlikte kullanılabilir — ${USAGE}`
  );
  process.exit(2);
}
if (checkDb && keysFile !== undefined) {
  console.error(
    `--check-db ve --keys-file birlikte verilemez (tek çakışma kaynağı) — ${USAGE}`
  );
  process.exit(2);
}
const positional = argv.filter((a) => !a.startsWith("--"));
if (positional.length > 1) {
  console.error(`fazla argüman: ${positional.slice(1).join(", ")} — ${USAGE}`);
  process.exit(2);
}
const sourcePath = positional[0] ?? DEFAULT_SOURCE;

/**
 * GİRDİ/KULLANIM hatası — beklenen, düzeltilebilir durum. Üst düzey
 * yakalayıcı yalnız `message` basar: kullanıcıya Node yığını değil, ne
 * yapması gerektiğini söyleyen tek satır gider. Beklenmeyen hatalar
 * (program hatası) `Error` kalır ve YIĞINIyla basılır — sessizce
 * yutulmaz, ayıklanır.
 */
class CliError extends Error {}

/** `errno` kodunu okunabilir tek cümleye çevirir (yol zaten ayrı yazılır). */
const READ_ERRORS: Record<string, string> = {
  ENOENT: "dosya bulunamadı",
  EACCES: "erişilemedi",
  EPERM: "izin yok",
  EISDIR: "dizin, dosya değil",
  ENOTDIR: "yolun bir bileşeni dosya değil",
};

function readSource(p: string): Buffer {
  try {
    return fs.readFileSync(p);
  } catch (e) {
    const code = (e as NodeJS.ErrnoException).code ?? "Bilinmeyen hata";
    throw new CliError(`kaynak okunamadı: ${p} (${READ_ERRORS[code] ?? code})`);
  }
}

/**
 * Çakışma ölçümünün NORMALİZE anahtar kümesi: bir aday bu kümelerden
 * herhangi biriyle eşleşirse `ON CONFLICT DO NOTHING` onu zaten düşürürdü.
 * `rows` = kaynağın satır sayısı (kaynak-tarafsız): "kaç satırla
 * karşılaştırıldı" sorusunun cevabı, kaçının eşleştiğinden ayrı raporlanır.
 */
type ConflictKeys = {
  ts: Set<string>;
  hashes: Set<string>;
  rows: number;
};

/**
 * `--keys-file` anlık görüntüsünü okur (JSONL). Satırlar `{"ts": ...}`
 * ve/veya `{"source_row_sha256": ...}` taşır; boş satırlar atlanır.
 * Bozuk JSON satır numarasıyla raporlanır (kaynak dosyayla aynı disiplin) —
 * sessizce "eşleşme yok" saymak çakışmayı gizlerdi.
 */
function readSnapshot(p: string): ConflictKeys {
  let buf: Buffer;
  try {
    buf = fs.readFileSync(p);
  } catch (e) {
    const code = (e as NodeJS.ErrnoException).code ?? "Bilinmeyen hata";
    throw new CliError(
      `snapshot okunamadı: ${p} (${READ_ERRORS[code] ?? code})`
    );
  }
  const physical = buf.toString("utf-8").split("\n");
  const ts = new Set<string>();
  const hashes = new Set<string>();
  let rows = 0;
  for (let i = 0; i < physical.length; i += 1) {
    const line = physical[i].trim();
    if (line.length === 0) continue;
    rows += 1;
    let parsed: unknown;
    try {
      parsed = JSON.parse(line);
    } catch (e) {
      throw new CliError(
        `snapshot satır ${i + 1}: JSON ayrıştırılamadı — ${(e as Error).message}`
      );
    }
    if (
      typeof parsed !== "object" ||
      parsed === null ||
      Array.isArray(parsed)
    ) {
      continue;
    }
    const row = parsed as Row;
    if (typeof row.ts === "string" && row.ts.length > 0) {
      ts.add(tsToDate(row.ts).toISOString());
    }
    if (
      typeof row.source_row_sha256 === "string" &&
      row.source_row_sha256.length > 0
    ) {
      hashes.add(row.source_row_sha256);
    }
  }
  return { ts, hashes, rows };
}

/**
 * Adaylardan kaçının mevcut olduğunu sayar. `pending` dosya-içi çakışmaları
 * ŞİMDİDEN elemiş olduğundan her aday en fazla BİR kez sayılır — bir adayın
 * birden çok snapshot satırıyla eşleşmesi sayıyı şişirmez.
 */
function countPresent(pending: PreparedRow[], keys: ConflictKeys): number {
  let n = 0;
  for (const p of pending) {
    if (keys.ts.has(p.tsKey) || keys.hashes.has(p.hash)) n += 1;
  }
  return n;
}

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

/**
 * `--json` sözleşmesi (makine-okunur dry-run özeti). Alan adları ve
 * tipleri KAPI: betikler bunları okur, prose yalnız insan içindir.
 * `insertAtMost`/`skipAtLeast` "en çok/en az"tur — DB'ye bağlanmadan
 * mevcut satırlarla çakışma ölçülemez (bkz. `skipDuplicates`).
 */
type DryRunSummary = {
  mode: "dry-run";
  source: string;
  sourceSha256: string;
  bytes: number;
  linesFull: number;
  linesPhysical: number;
  blankSkipped: number;
  candidates: number;
  invalidSkipped: number;
  duplicatesInFile: number;
  insertAtMost: number;
  skipAtLeast: number;
  /** Çakışmanın kaynağı: ölçülmediyse "none", snapshot/DB ise ilgili kaynak. */
  conflictSource: "none" | "snapshot" | "db";
  /** Karşılaştırılan mevcut satır sayısı (kaynak-tarafsız). */
  conflictRows: number;
  /** Adaylardan kaçı zaten mevcut (ölçüldüyse KESİN, değilse 0). */
  alreadyPresent: number;
  /** KESİN eklenecek = candidates − alreadyPresent. */
  insert: number;
  /** KESİN atlanacak = doğrulama-dışı + dosya-içi + zaten var. */
  skip: number;
  dbConnected: boolean;
};

type PreparedRow = {
  data: TrendRunCreateManyInput;
  hash: string;
  /** `ts` (@unique) için normalize anahtar: aynı an → aynı anahtar. */
  tsKey: string;
};

/**
 * Tek satırı Prisma girdisine çevirir — TEK kaynak: gerçek yükleme de
 * --dry-run raporu da buradan geçer (rapor ile yükleme ayrışamaz).
 *
 * `null` = doğrulama-dışı satır (ts yok ya da verdict string değil) → atlanır.
 * JSON nesnesi olmayan değer (`null`, `5`, `"x"`, `[...]`) da doğrulama-dışı
 * sayılır: eskiden `null` satırı TypeError ile tüm yüklemeyi düşürürdü;
 * artık atlanan satır olarak SAYILIR (sayaç yalan söylemez).
 * Bozuk JSON fail-closed kalır ve satır numarasıyla raporlanır.
 */
function prepare(line: string, lineNo: number): PreparedRow | null {
  let parsed: unknown;
  try {
    parsed = JSON.parse(line);
  } catch (e) {
    throw new CliError(
      `satır ${lineNo}: JSON ayrıştırılamadı — ${(e as Error).message}`
    );
  }
  if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
    return null;
  }
  const row = parsed as Row;
  if (!row.ts || typeof row.verdict !== "string") {
    return null;
  }
  const hash = rowHash(row);
  const ts = tsToDate(row.ts);
  const data: TrendRunCreateManyInput = {
    ts,
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
  return { data, hash, tsKey: ts.toISOString() };
}

async function main() {
  // Kaynak dosya bir kez Buffer olarak okunur: SHA-256 ve ayrıştırma aynı
  // baytlardan gelir (ikinci okuma = TOCTOU penceresi yok).
  const buf = readSource(sourcePath);
  const sourceSha256 = crypto.createHash("sha256").update(buf).digest("hex");
  const physicalLines = buf.toString("utf-8").split("\n");
  const lines = physicalLines.filter((l) => l.trim().length > 0);

  const pending: PreparedRow[] = [];
  let invalid = 0;
  let duplicates = 0;
  const seenTs = new Set<string>();
  const seenHashes = new Set<string>();
  for (let i = 0; i < lines.length; i += 1) {
    const prepared = prepare(lines[i], i + 1);
    if (!prepared) {
      invalid += 1;
      continue;
    }
    // Dosya-içi çakışma: ts (@unique) veya satır-hash (@unique) tekrarı.
    // Postgres `ON CONFLICT DO NOTHING` bu satırı zaten düşürürdü; JS'te
    // elemek sayıyı KESİN yapar (ilk görülüm kazanır — SQL sırasıyla aynı).
    const tsKey = prepared.tsKey;
    if (seenTs.has(tsKey) || seenHashes.has(prepared.hash)) {
      duplicates += 1;
      continue;
    }
    seenTs.add(tsKey);
    seenHashes.add(prepared.hash);
    pending.push(prepared);
  }

  if (dryRun) {
    // Çakışma ölçümü: TEK kaynak (snapshot VEYA canlı DB) ya da hiçbiri.
    // Ölçülmezse sınır dili ("en çok/en az") korunur; kesin sayı yalnız
    // buradan doğar. Sayılar tek yerden hesaplanır — prose ve JSON ayrışamaz.
    let conflictSource: "none" | "snapshot" | "db" = "none";
    let conflictRows = 0;
    let alreadyPresent = 0;
    let dbConnected = false;
    if (keysFile !== undefined) {
      const keys = readSnapshot(keysFile);
      conflictSource = "snapshot";
      conflictRows = keys.rows;
      alreadyPresent = countPresent(pending, keys);
    } else if (checkDb) {
      // Kesin sayı isteyen çağıran, kesin OLMAYAN sayı görürse onu kesin
      // sanar: kimlik yokken sınır raporuna düşmek sessiz bir yalan olurdu.
      if (!process.env.DATABASE_URL) {
        console.error(
          "DATABASE_URL yok — --check-db mevcut satırları okumak için pooled URL gerektirir"
        );
        process.exit(1);
      }
      // SALT-OKUNUR: yalnız iki kolon çekilir, hiçbir yazma yapılmaz.
      const adapter = new PrismaPg({
        connectionString: process.env.DATABASE_URL,
      });
      const prisma = new PrismaClient({ adapter });
      try {
        const rows = await prisma.trendRun.findMany({
          select: { ts: true, sourceRowSha256: true },
        });
        const keys: ConflictKeys = {
          ts: new Set(rows.map((r) => r.ts.toISOString())),
          hashes: new Set(
            rows
              .map((r) => r.sourceRowSha256)
              .filter((h): h is string => typeof h === "string" && h.length > 0)
          ),
          rows: rows.length,
        };
        conflictSource = "db";
        conflictRows = keys.rows;
        alreadyPresent = countPresent(pending, keys);
        dbConnected = true;
      } finally {
        await prisma.$disconnect();
      }
    }

    // Değişmezler: insert + alreadyPresent = aday; skip = doğrulama-dışı +
    // dosya-içi + zaten var. Ölçülmemiş modda alreadyPresent = 0 olduğundan
    // insert/skip sırasıyla insertAtMost/skipAtLeast'ye EŞİT olur (uyumlu).
    const summary: DryRunSummary = {
      mode: "dry-run",
      source: sourcePath,
      sourceSha256,
      bytes: buf.length,
      linesFull: lines.length,
      linesPhysical: physicalLines.length,
      blankSkipped: physicalLines.length - lines.length,
      candidates: pending.length,
      invalidSkipped: invalid,
      duplicatesInFile: duplicates,
      insertAtMost: pending.length,
      skipAtLeast: invalid + duplicates,
      conflictSource,
      conflictRows,
      alreadyPresent,
      insert: pending.length - alreadyPresent,
      skip: invalid + duplicates + alreadyPresent,
      dbConnected,
    };
    const measured = conflictSource !== "none";
    if (jsonMode) {
      // Tek satır, satır sonu olmadan: `| jq` ve satır-bazlı okuyucular
      // için güvenli. Alan adları sözleşmedir (docs: README "dry-run").
      console.log(JSON.stringify(summary));
      return;
    }
    console.log(`[DRY-RUN] kaynak: ${summary.source} (${summary.bytes} bayt)`);
    console.log(`[DRY-RUN] sha256: ${summary.sourceSha256}`);
    console.log(
      `[DRY-RUN] satır: ${summary.linesFull} dolu / ${summary.linesPhysical} fiziksel` +
        ` (boş atlanan: ${summary.blankSkipped})`
    );
    console.log(
      `[DRY-RUN] aday: ${summary.candidates} · doğrulama-dışı atlanan: ${summary.invalidSkipped}`
    );
    console.log(
      `[DRY-RUN] dosya-içi çakışma: ${summary.duplicatesInFile}` +
        " (aynı ts veya aynı satır-hash → ON CONFLICT DO NOTHING)"
    );
    if (measured) {
      // Ölçülmüş mod: kesin sayı varken sınır dili yanıltıcı olurdu
      // ("en çok 3" ile "3" karıştırılırdı) — bu yüzden dil ayrışır.
      console.log(
        `[DRY-RUN] çakışma kaynağı: ${conflictSource} (${conflictRows} satır)`
      );
      console.log(`[DRY-RUN] zaten var olan aday: ${summary.alreadyPresent}`);
      console.log(
        `[DRY-RUN] eklenecek (kesin): ${summary.insert} ·` +
          ` atlanacak (kesin): ${summary.skip}`
      );
    } else {
      console.log(
        `[DRY-RUN] eklenecek (en çok): ${summary.insertAtMost} ·` +
          ` atlanacak (en az): ${summary.skipAtLeast}`
      );
      console.log(
        "[DRY-RUN] DB bağlantısı kurulmadı (DATABASE_URL gerekmez);" +
          " mevcut satırlarla çakışma bu raporda YOK — kesin sayı için normal koşu"
      );
    }
    return;
  }

  if (!process.env.DATABASE_URL) {
    console.error(
      "DATABASE_URL yok — .env veya ortam değişkeni olarak pooled URL ver"
    );
    process.exit(1);
  }

  const adapter = new PrismaPg({ connectionString: process.env.DATABASE_URL });
  const prisma = new PrismaClient({ adapter });
  try {
    console.log(
      `kaynak: ${sourcePath} (${lines.length} satır, sha256 ${sourceSha256})`
    );
    // Tek createMany/dilim = tek round-trip (skill: data-batch-inserts,
    // 10-50x). skipDuplicates → ON CONFLICT DO NOTHING: aynı kaynak-tekrarı
    // (source_row_sha256) VE aynı ts çakışması sessizce atlanır.
    let insertedCount = 0;
    const CHUNK = 500;
    for (let i = 0; i < pending.length; i += CHUNK) {
      const res = await prisma.trendRun.createMany({
        data: pending.slice(i, i + CHUNK).map((p) => p.data),
        skipDuplicates: true,
      });
      insertedCount += res.count;
    }
    console.log(
      `bitti: ${pending.length} kayıt işlendi (${insertedCount} eklendi),` +
        ` ${invalid + duplicates} atlandı`
    );
  } finally {
    await prisma.$disconnect();
  }
}

main().catch((e) => {
  // CliError = kullanıcının düzeltebileceği hata → tek satır mesaj.
  // Diğer hatalar program hatasıdır → yığın basılır (ayıklanabilsin).
  console.error(e instanceof CliError ? e.message : e);
  process.exit(1);
});
