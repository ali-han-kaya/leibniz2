/**
 * mini.mjs — bağımlılıksız minimal test koşucusu.
 *
 * Neden kendi koşucusu: `apps/trend-db` sözleşmesi TEK bir seam'e bağlı —
 * `load.ts` CLI çıktısı. Bu seam'i test etmek için 200 satırlık bir test
 * framework'ü (jest/vitest) eklemek, denenecek yüzeyden büyük olurdu.
 * Burada gerekenler yalnız: kayıt, sırayla koş, hata mesajıyla raporla,
 * özet döndür, çıkış kodu ver. Bağımlılık: sıfır (node built-in).
 *
 * Çıktı TAP-benzeri: `ok 1 - ad`, `not ok 1 - ad` + mesaj, sonra özet.
 * Kullanım:
 *   import { test, eq, ok, match } from "./mini.mjs";
 *   test("ad", () => { eq(1, 1, "şu eşit olmalı"); });
 *   // ... test modülleri import edildikten sonra:
 *   import { runAll } from "./run.mjs" (giriş noktası)
 */
import process from "node:process";

const cases = [];

/** Test kaydeder. `fn` senkron veya async olabilir. */
export function test(name, fn) {
  cases.push({ name, fn });
}

export function eq(actual, expected, msg = "") {
  const a = JSON.stringify(actual);
  const b = JSON.stringify(expected);
  if (a !== b) {
    throw new Error(`${msg ? msg + " — " : ""}beklenen ${b}, gelen ${a}`);
  }
}

export function ok(cond, msg = "koşul sağlanmalı") {
  if (!cond) {
    throw new Error(msg);
  }
}

export function match(text, re, msg = "") {
  if (!re.test(text)) {
    throw new Error(`${msg ? msg + " — " : ""}desen eşleşmedi: ${re}`);
  }
}

export function notMatch(text, re, msg = "") {
  if (re.test(text)) {
    throw new Error(`${msg ? msg + " — " : ""}desen eşMEMELİYDİ: ${re}`);
  }
}

/**
 * Ortam yokluğundan atlama — BAŞARISIZLIK DEĞİL, ama görünür olmalı.
 *
 * Neden ayrı bir sinyal: kimlik bilgisi (DATABASE_URL) gerektiren sözleşme
 * testleri kimlik yokken "geçti" sayılırsa yeşil yalan söyler (hiçbir şey
 * doğrulanmadı), "kaldı" sayılırsa ortam-eksikliği kod kırığı gibi görünür.
 * Bu yüzden atlananlar ayrı sayılır ve özet satırında AYRI yazılır.
 */
export class Skip extends Error {}

export function skip(reason) {
  throw new Skip(reason);
}

/** Kayıtlı testleri sırayla koşar; süre ölçer, TAP-benzeri çıktı verir. */
export async function runAll() {
  let passed = 0;
  let skipped = 0;
  const failures = [];
  for (let i = 0; i < cases.length; i += 1) {
    const { name, fn } = cases[i];
    const started = process.hrtime.bigint();
    try {
      await fn();
      const ms = Number(process.hrtime.bigint() - started) / 1e6;
      console.log(`ok ${i + 1} - ${name} (${ms.toFixed(0)}ms)`);
      passed += 1;
    } catch (err) {
      if (err instanceof Skip) {
        console.log(`skip ${i + 1} - ${name} — ${err.message}`);
        skipped += 1;
        continue;
      }
      console.log(`not ok ${i + 1} - ${name}`);
      console.log(`  ---\n  ${(err && err.message) || err}\n  ...`);
      failures.push(name);
    }
  }
  // `total` = GERÇEKTEN koşulan vaka: atlananlar paydaya girmez, çünkü
  // "passed === total" sözleşmesi "hiçbir vaka kırmızı değil" demektir.
  // Atlanan sayısı ayrıca yazılır ki ortam yokluğu sessizleşmesin.
  const total = cases.length - skipped;
  console.log(
    `\n# ${passed}/${total} geçti` +
      (skipped ? ` · ${skipped} ortam yokluğundan atlandı` : "") +
      (failures.length ? ` · ${failures.length} kaldı` : "")
  );
  for (const name of failures) {
    console.log(`#   BAŞARISIZ: ${name}`);
  }
  return failures.length === 0;
}

/** Koşucudan çıkış kodu ister (0 = yeşil). */
export async function runAndExit() {
  const okAll = await runAll();
  process.exit(okAll ? 0 : 1);
}
