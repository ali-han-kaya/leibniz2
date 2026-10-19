/**
 * helpers.mjs — JS sözleşme testlerinin PAYLAŞILAN koşum aracı.
 *
 * Neden ayrı dosya: `*.test.mjs` modülleri import edildiklerinde testlerini
 * KAYDEDER. Bir test modülünü diğerinden import etmek, kayıt sırasına bağlı
 * kırılgan bir bağımlılık kurardı (çift kayıt ya da hiç kayıt olmama).
 * Burası yalnız altyapıdır: test kaydı yapmaz, bu yüzden `run.mjs` MODULES
 * listesine girmez.
 *
 * Seam kuralı (dry-run.test.mjs ile aynı): loader CLI'sı siyah kutudur —
 * stdout/stderr/çıkış kodu. İçeriğe (Prisma, prepare()) dokunulmaz.
 */
import crypto from "node:crypto";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";
import { ok } from "./mini.mjs";

const HERE = path.dirname(fileURLToPath(import.meta.url));
export const APP = path.resolve(HERE, "..");
export const LOADER = path.join(APP, "scripts", "load.ts");
export const TSX = path.join(APP, "node_modules", ".bin", "tsx");

/** Testler için tek geçici çalışma alanı (giriş noktası sonunda silinir). */
export const TMP = fs.mkdtempSync(path.join(os.tmpdir(), "trend-dry-"));

ok(fs.existsSync(TSX), `tsx yok: ${TSX} (apps/trend-db: npm install)`);
ok(fs.existsSync(LOADER), `loader yok: ${LOADER}`);

/**
 * Loader'ı KİMLİK BİLGİSİ OLMADAN koşar.
 *
 * cwd geçici dizindir: dotenv repo kökündeki `.env`i bulamaz. Böylece
 * dry-run'ın gerçekten kimlik bilgisine ihtiyacı olmadığı kanıtlanır
 * (varsayılmaz) ve testler yerel sırlara bağlanmaz.
 */
export function runLoader(...args) {
  const env = { ...process.env };
  delete env.DATABASE_URL;
  delete env.DATABASE_URL_UNPOOLED;
  return spawnLoader(env, args);
}

/**
 * Yerel DATABASE_URL'i bulur: ortam değişkeni ya da `apps/trend-db/.env`.
 * Değer asla basılmaz/raporlanmaz — yalnız varlığı/yokluğu görünür olur.
 */
export function liveCredentials() {
  if (process.env.DATABASE_URL) return process.env.DATABASE_URL;
  const envFile = path.join(APP, ".env");
  if (!fs.existsSync(envFile)) return null;
  for (const raw of fs.readFileSync(envFile, "utf-8").split("\n")) {
    const m = /^DATABASE_URL=(.*)$/.exec(raw.trim());
    if (!m) continue;
    // dotenv sözleşmesi: değer `"..."` ya da `'...'` içine alınmış olabilir;
    // tırnaklar ayrıştırılır. Ham değeri (tırnaklı) ortam değişkeni olarak
    // geçirmek bağlantı dizesini bozar — host `base` gibi anlamsız bir
    // parçaya düşer. Bu yüzden dotenv ile AYNI sadeleştirme burada yapılır.
    const value = m[1].trim().replace(/^(['"])(.*)\1$/, "$2");
    if (value) return value;
  }
  return null;
}

/** Loader'ı kimlik bilgisiyle koşar (canlı DB'ye SALT-OKUNUR yollar için). */
export function runLiveLoader(...args) {
  const env = { ...process.env, DATABASE_URL: liveCredentials() };
  delete env.DATABASE_URL_UNPOOLED;
  return spawnLoader(env, args);
}

function spawnLoader(env, args) {
  const res = spawnSync(process.execPath, [TSX, LOADER, ...args], {
    cwd: TMP,
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
  fs.writeFileSync(p, lines.join("\n") + (lines.length ? "\n" : ""), "utf-8");
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

/**
 * Loader'ın satır-hash'i: kaynak satırın AYRIŞTIRILMIŞ hâlinin sha256'sı.
 * Test bunu kendi hesaplar ki ``--keys-file`` snapshot'ında gerçek bir
 * `source_row_sha256` uydurabilsin (loader'ın iç hesabı taklit edilmez).
 */
export function rowHashOf(line) {
  return crypto
    .createHash("sha256")
    .update(JSON.stringify(JSON.parse(line)))
    .digest("hex");
}
