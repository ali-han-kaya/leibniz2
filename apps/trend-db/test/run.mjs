/**
 * run.mjs — test giriş noktası: `npm test` (node test/run.mjs).
 *
 * Test modülleri DİNAMİK import edilir: kayıt sırasında oluşan bir hata
 * (tsx kurulmamış, geçici dizin yazılamadı) `runAll`'ın içine karışmaz —
 * kurulum hatası olarak tek satır basılır. Yeni test modülü eklemek =
 * MODULES listesine bir satır.
 *
 * Her test modülü kendi geçici dizinini `TMP` olarak dışa verirse koşu
 * sonunda silinir: testler `os.tmpdir()` altına, repo içine değil.
 */
import fs from "node:fs";
import process from "node:process";
import { runAll } from "./mini.mjs";

const MODULES = ["./dry-run.test.mjs"];
const tempDirs = [];

try {
  for (const name of MODULES) {
    const mod = await import(name);
    if (mod.TMP) tempDirs.push(mod.TMP);
  }
  process.exitCode = (await runAll()) ? 0 : 1;
} catch (e) {
  process.exitCode = 1;
  console.error(`test koşucusu çöktü: ${(e && e.message) || e}`);
} finally {
  for (const dir of tempDirs) {
    fs.rmSync(dir, { recursive: true, force: true });
  }
}
