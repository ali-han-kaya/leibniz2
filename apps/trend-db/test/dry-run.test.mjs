/**
 * dry-run.test.mjs — `load.ts` CLI çıktısının sözleşme testleri.
 *
 * SEAM: loader'ın stdout/stderr'i ve çıkış kodu. İçeriğe (Prisma, DB,
 * `prepare()`) dokunulmaz — siyah kutu. Bu, `--dry-run` raporunun
 * gerçekten "yüklemekle aynı sayıları" söylediğini dışarıdan doğrulamanın
 * tek yoludur: aynı `prepare()` yolundan geçse bile, çıktı yüzeyi
 * sözleşmeden ayrılabilir (sayaç unutulabilir, etiket değişebilir).
 *
 * Her koşu KİMLİK BİLGİSİ OLMADAN yapılır: DATABASE_URL/DATABASE_URL_UNPOOLED
 * ortamdan silinir ve cwd geçici dizindir (dotenv `.env` bulamaz) — yani
 * dry-run'ın gerçekten DB'ye ihtiyacı olmadığı da kanıtlanır, varsayılmaz.
 */
import crypto from "node:crypto";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";
import { eq, match, notMatch, ok, test } from "./mini.mjs";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const APP = path.resolve(HERE, "..");
const LOADER = path.join(APP, "scripts", "load.ts");
const TSX = path.join(APP, "node_modules", ".bin", "tsx");

/** Testler için tek geçici çalışma alanı (giriş noktası sonunda silinir). */
export const TMP = fs.mkdtempSync(path.join(os.tmpdir(), "trend-dry-"));

ok(fs.existsSync(TSX), `tsx yok: ${TSX} (apps/trend-db: npm install)`);
ok(fs.existsSync(LOADER), `loader yok: ${LOADER}`);

/** Loader'ı kimlik bilgisi olmadan koşar; sonucu {code, stdout, stderr} verir. */
export function runLoader(...args) {
  const env = { ...process.env };
  delete env.DATABASE_URL;
  delete env.DATABASE_URL_UNPOOLED;
  const res = spawnSync(process.execPath, [TSX, LOADER, ...args], {
    cwd: TMP, // dotenv'in .env bulamaması için repo kökü DEĞİL
    env,
    encoding: "utf-8",
    timeout: 120000,
  });
  return {
    code: res.status,
    stdout: res.stdout ?? "",
    stderr: res.stderr ?? "",
  };
}

/** Fixture yazar: satır listesinden JSONL üretir, yolunu döner. */
export function fixture(name, lines) {
  const p = path.join(TMP, name);
  fs.writeFileSync(p, lines.join("\n") + "\n", "utf-8");
  return p;
}

/**
 * Ana fixture — 5 dolu satır:
 *   1) geçerli (aday)
 *   2) geçerli (aday)
 *   3) 2 ile aynı ts → dosya-içi çakışma
 *   4) ts yok → doğrulama-dışı
 *   5) "null" → JSON nesnesi değil → doğrulama-dışı
 */
export const MIXED = [
  '{"ts": "2026-09-27T10:00:00.000000+00:00", "verdict": "PASS", "p0": 0, "p1": 0}',
  '{"ts": "2026-09-27T10:05:00.000000+00:00", "verdict": "FAIL", "p0": 1, "p1": 2}',
  '{"ts": "2026-09-27T10:05:00.000000+00:00", "verdict": "PASS", "p0": 0, "p1": 0}',
  '{"verdict": "PASS"}',
  "null",
];

/** Prose raporundaki `etiket: değer` çiftlerini {etiket: değer} sözlüğüne çevirir. */
function parseProse(stdout) {
  const out = {};
  for (const line of stdout.split("\n")) {
    if (!line.startsWith("[DRY-RUN] ")) continue;
    const body = line.slice("[DRY-RUN] ".length);
    // "kaynak: <yol> (N bayt)" → iki ayrı alan
    const src = /^kaynak: (.*) \((\d+) bayt\)$/.exec(body);
    if (src) {
      out.source = src[1];
      out.bytes = Number(src[2]);
      continue;
    }
    const sha = /^sha256: ([0-9a-f]{64})$/.exec(body);
    if (sha) {
      out.sourceSha256 = sha[1];
      continue;
    }
    const m = /^([a-zçğıöşü-]+): (.*)$/.exec(body);
    if (m) out[m[1]] = m[2];
  }
  return out;
}

test("dry-run: kaynak SHA-256 ve bayt sayısı dosyanın gerçek baytlarından", () => {
  const p = fixture("sha.jsonl", MIXED);
  const raw = fs.readFileSync(p);
  const r = runLoader(p, "--dry-run");
  eq(r.code, 0, `çıkış kodu 0 olmalı — stderr: ${r.stderr}`);
  const prose = parseProse(r.stdout);
  eq(prose.sourceSha256, crypto.createHash("sha256").update(raw).digest("hex"));
  eq(prose.bytes, raw.length);
  eq(prose.source, p, "rapor kaynak yolunu aynen yazmalı");
});

test("dry-run: sayaçlar 5 dolu / 2 aday / 2 doğrulama-dışı / 1 çakışma", () => {
  const p = fixture("mixed.jsonl", MIXED);
  const r = runLoader(p, "--dry-run");
  eq(r.code, 0, r.stderr);
  const prose = parseProse(r.stdout);
  match(r.stdout, /satır: 5 dolu \/ 6 fiziksel \(boş atlanan: 1\)/, r.stdout);
  match(r.stdout, /aday: 2 · doğrulama-dışı atlanan: 2/, r.stdout);
  match(r.stdout, /dosya-içi çakışma: 1/, r.stdout);
  match(r.stdout, /eklenecek \(en çok\): 2 · atlanacak \(en az\): 3/, r.stdout);
  eq(prose.sha256 !== undefined, false, "sha256 ayrı satırda");
});

test("dry-run: DATABASE_URL gerekmez ve hiçbir yükleme kanıtı basılmaz", () => {
  const p = fixture("nodb.jsonl", MIXED);
  const r = runLoader(p, "--dry-run");
  eq(r.code, 0, r.stderr);
  match(r.stdout, /DB bağlantısı kurulmadı/);
  notMatch(r.stdout, /bitti:/, "dry-run yükleme yapmamalı");
  notMatch(r.stdout + r.stderr, /DATABASE_URL yok/);
});

test("dry-run: aynı satırın hash tekrarı da dosya-içi çakışma sayılır", () => {
  const row = '{"ts": "2026-09-27T11:00:00.000000+00:00", "verdict": "PASS"}';
  const other = '{"ts": "2026-09-27T12:00:00.000000+00:00", "verdict": "FAIL"}';
  const p = fixture("hashdup.jsonl", [row, other, row]);
  const r = runLoader(p, "--dry-run");
  eq(r.code, 0, r.stderr);
  match(r.stdout, /dosya-içi çakışma: 1/, r.stdout);
  match(r.stdout, /eklenecek \(en çok\): 2 · atlanacak \(en az\): 1/, r.stdout);
});

test("gerçek koşu: DATABASE_URL yoksa açık hata + çıkış 1", () => {
  const p = fixture("real.jsonl", MIXED);
  const r = runLoader(p);
  eq(r.code, 1, `çıkış 1 olmalı — stdout: ${r.stdout}`);
  match(r.stderr, /DATABASE_URL yok/);
});

test("bayrak: bilinmeyen bayrak çıkış 2 (fail-closed, yükleme başlamaz)", () => {
  const r = runLoader("--dri-run");
  eq(r.code, 2, r.stdout);
  match(r.stderr, /bilinmeyen bayrak: --dri-run/);
});

test("kaynak: bozuk JSON satır numarasıyla, çıkış 1", () => {
  const p = fixture("bad.jsonl", [
    '{"ts": "2026-09-27T10:00:00Z", "verdict": "PASS"}',
    "{bozuk",
  ]);
  const r = runLoader(p, "--dry-run");
  eq(r.code, 1, r.stdout);
  match(r.stderr, /satır 2: JSON ayrıştırılamadı/);
});

test("kaynak: dosya yoksa sade hata (Node yığını değil), çıkış 1", () => {
  const missing = path.join(TMP, "yok-boyle-bir-dosya.jsonl");
  const r = runLoader(missing, "--dry-run");
  eq(r.code, 1, `çıkış 1 olmalı — stdout: ${r.stdout}`);
  match(r.stderr, /kaynak okunamadı/, r.stderr);
  match(r.stderr, /yok-boyle-bir-dosya\.jsonl/, "hata yolu söylemeli");
  notMatch(r.stderr, /\n\s+at\s/, "Node yığın çerçevesi basılmamalı");
  notMatch(r.stderr, /Error: ENOENT/, "ham Node hatası sızmamalı");
});

test("--json: makine-okunur özet, prose ile aynı sayılar", () => {
  const p = fixture("json.jsonl", MIXED);
  const r = runLoader(p, "--dry-run", "--json");
  eq(r.code, 0, r.stderr);
  const lines = r.stdout.trim().split("\n");
  eq(lines.length, 1, `tek satır JSON beklenir: ${r.stdout}`);
  const j = JSON.parse(lines[0]);
  const proseOut = runLoader(p, "--dry-run").stdout;
  const raw = fs.readFileSync(p);
  eq(j.mode, "dry-run");
  eq(j.source, p);
  eq(j.sourceSha256, crypto.createHash("sha256").update(raw).digest("hex"));
  eq(j.bytes, raw.length);
  eq(j.linesFull, 5);
  eq(j.linesPhysical, 6);
  eq(j.blankSkipped, 1);
  eq(j.candidates, 2);
  eq(j.invalidSkipped, 2);
  eq(j.duplicatesInFile, 1);
  eq(j.insertAtMost, 2);
  eq(j.skipAtLeast, 3);
  eq(j.dbConnected, false);
  // İki yüzey AYNI sayıları söylemeli: prose "en çok/en az" birleşik
  // etikette yazdığı için çapraz-kontrol ham stdout üzerinden yapılır.
  eq(j.insertAtMost, Number(/eklenecek \(en çok\): (\d+)/.exec(proseOut)[1]));
  eq(j.skipAtLeast, Number(/atlanacak \(en az\): (\d+)/.exec(proseOut)[1]));
});

test("--json: dry-run olmadan kullanılırsa çıkış 2 (fail-closed)", () => {
  const p = fixture("jsonflag.jsonl", MIXED);
  const r = runLoader(p, "--json");
  eq(r.code, 2, r.stdout);
  match(r.stderr, /--json/);
  // Yanlış-sahte yeşil: --json BİLİNEN bayrak olduğu için reddi
  // "yalnız --dry-run ile birlikte" demeli, "bilinmeyen bayrak" değil.
  notMatch(r.stderr, /bilinmeyen bayrak/, "--json artık bilinen bayrak olmalı");
  match(r.stderr, /--dry-run/, "hata --dry-run gereksinimini söylemeli");
  notMatch(r.stdout, /\[DRY-RUN\]/, "rapor basılmamalı");
});

test("dry-run: aynı girdide çıktı birebir aynı (deterministik sıralama)", () => {
  const p = fixture("det.jsonl", MIXED);
  const a = runLoader(p, "--dry-run");
  const b = runLoader(p, "--dry-run");
  eq(a.stdout, b.stdout, "iki koşu birebir aynı çıktı vermeli");
});
