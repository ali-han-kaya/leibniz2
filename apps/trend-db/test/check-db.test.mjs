/**
 * check-db.test.mjs — GERÇEK çakışma ölçümünün sözleşme testleri.
 *
 * Neden ayrı tur: `--dry-run` "en çok eklenecek / en az atlanacak" diyordu,
 * çünkü mevcut satırlarla çakışma bağlantısız ÖLÇÜLEMEZ (loader'ın kendi
 * notu). `--check-db` bu boşluğu kapatır: mevcut satırlar SALT-OKUNUR
 * okunur ve sayaçlar KESİN olur. `--keys-file=<yol>` aynı ölçümü kimlik
 * bilgisi olmadan, bir JSONL anlık görüntüsü üzerinden yapar — bu yüzden bu
 * modülün çoğu vakası HERMETİKTİR (ağ yok, sır yok); canlı DB vakaları
 * kimlik yoksa `skip` ile atlanır, "geçti" sayılmaz.
 *
 * Seam: loader CLI çıktısı (stdout/stderr/çıkış kodu) — içeriğe dokunulmaz.
 */
import fs from "node:fs";
import path from "node:path";
import { eq, match, notMatch, skip, test } from "./mini.mjs";
import {
  TMP,
  fixture,
  liveCredentials,
  rowHashOf,
  runLoader,
  runLiveLoader,
} from "./helpers.mjs";

export { TMP };

/** 3 aday, 0 doğrulama-dışı, 0 dosya-içi çakışma. */
const C1 =
  '{"ts": "2026-10-01T10:00:00.000000+00:00", "verdict": "PASS", "p0": 0, "p1": 0}';
const C2 =
  '{"ts": "2026-10-01T11:00:00.000000+00:00", "verdict": "FAIL", "p0": 1, "p1": 2}';
const C3 =
  '{"ts": "2026-10-01T12:00:00.000000+00:00", "verdict": "PASS", "p0": 0, "p1": 0}';
const SOURCE = [C1, C2, C3];

const TS_OF = (line) => JSON.parse(line).ts;

/** `--dry-run --json` çıktısını koşar ve tek satırlık özeti ayrıştırır. */
function summary(...args) {
  const r = runLoader(...args);
  eq(r.code, 0, `çıkış 0 olmalı — stderr: ${r.stderr}`);
  const lines = r.stdout.trim().split("\n");
  eq(lines.length, 1, `tek satır JSON beklenir: ${r.stdout}`);
  return JSON.parse(lines[0]);
}

// ── bayrak sözleşmeleri (kimlik gerekmez) ───────────────────────────────────

test("bayrak: --check-db dry-run olmadan çıkış 2 (gerçek koşuda zaten ölçülür)", () => {
  const p = fixture("cdbnodry.jsonl", SOURCE);
  const r = runLoader(p, "--check-db");
  eq(r.code, 2, r.stdout);
  match(r.stderr, /--check-db yalnız --dry-run ile/, r.stderr);
  notMatch(r.stderr, /bilinmeyen bayrak/, "--check-db bilinen bayrak olmalı");
  notMatch(r.stdout, /\[DRY-RUN\]/, "rapor basılmamalı");
});

test("bayrak: --keys-file dry-run olmadan çıkış 2", () => {
  const p = fixture("keynodry-src.jsonl", SOURCE);
  const snap = fixture("keynodry-snap.jsonl", []);
  const r = runLoader(p, `--keys-file=${snap}`);
  eq(r.code, 2, r.stdout);
  match(r.stderr, /--keys-file yalnız --dry-run ile/, r.stderr);
  notMatch(r.stdout, /\[DRY-RUN\]/, "rapor basılmamalı");
});

test("bayrak: iki çakışma kaynağı birlikte verilemez (kaynak tektir)", () => {
  const p = fixture("bothsrc.jsonl", SOURCE);
  const snap = fixture("bothsnap.jsonl", []);
  const r = runLoader(p, "--dry-run", "--check-db", `--keys-file=${snap}`);
  eq(r.code, 2, r.stdout);
  match(r.stderr, /birlikte/, r.stderr);
  notMatch(r.stdout, /\[DRY-RUN\]/, "rapor basılmamalı");
});

test("bayrak: --keys-file değeri `=` ile verilmeli (yol konum sanılmasın)", () => {
  const p = fixture("eqform.jsonl", SOURCE);
  const snap = fixture("eqform-snap.jsonl", []);
  const spaced = runLoader(p, "--dry-run", "--keys-file", snap);
  eq(spaced.code, 2, spaced.stdout);
  match(spaced.stderr, /--keys-file=<yol>/, spaced.stderr);
  const empty = runLoader(p, "--dry-run", "--keys-file=");
  eq(empty.code, 2, empty.stdout);
  match(empty.stderr, /--keys-file/, empty.stderr);
});

test("kimlik: --check-db DATABASE_URL yoksa çıkış 1 ve rapor BASILMAZ", () => {
  const p = fixture("nodbcreds.jsonl", SOURCE);
  const r = runLoader(p, "--dry-run", "--check-db");
  eq(r.code, 1, `kimlik yokken ölçüm yapılamaz: ${r.stdout}`);
  match(r.stderr, /DATABASE_URL/, r.stderr);
  // Sessizce "en çok" raporuna düşmek yalan olurdu: kesin sayı isteyen
  // çağıran, kesin olmayan sayı görürse onu kesin sanar.
  notMatch(r.stdout, /\[DRY-RUN\]/, "belirsiz rapor basılmamalı");
  notMatch(r.stderr, /bilinmeyen bayrak/, "--check-db bilinen bayrak olmalı");
});

test("snapshot: dosya yoksa sade hata, çıkış 1", () => {
  const p = fixture("nosnap-src.jsonl", SOURCE);
  const missing = path.join(TMP, "yok-boyle-bir-snapshot.jsonl");
  const r = runLoader(p, "--dry-run", `--keys-file=${missing}`);
  eq(r.code, 1, r.stdout);
  match(r.stderr, /snapshot okunamadı/, r.stderr);
  match(r.stderr, /yok-boyle-bir-snapshot\.jsonl/, "hata yolu söylemeli");
  notMatch(r.stderr, /\n\s+at\s/, "Node yığını basılmamalı");
  notMatch(r.stdout, /\[DRY-RUN\]/, "rapor basılmamalı");
});

test("snapshot: bozuk JSON satır numarasıyla, çıkış 1", () => {
  const p = fixture("badsnap-src.jsonl", SOURCE);
  const snap = fixture("badsnap.jsonl", [`{"ts": "${TS_OF(C1)}"}`, "{bozuk"]);
  const r = runLoader(p, "--dry-run", `--keys-file=${snap}`);
  eq(r.code, 1, r.stdout);
  match(r.stderr, /snapshot satır 2: JSON ayrıştırılamadı/, r.stderr);
  notMatch(r.stdout, /\[DRY-RUN\]/, "rapor basılmamalı");
});

// ── kesin sayılar (snapshot kaynağıyla, kimlik gerekmez) ────────────────────

test("kesin: ts eşleşmesi mevcut satırı 'zaten var' sayar", () => {
  const p = fixture("tssrc.jsonl", SOURCE);
  const snap = fixture("tssnap.jsonl", [`{"ts": "${TS_OF(C1)}"}`]);
  const j = summary(p, "--dry-run", "--json", `--keys-file=${snap}`);
  eq(j.conflictSource, "snapshot");
  eq(j.conflictRows, 1);
  eq(j.candidates, 3);
  eq(j.alreadyPresent, 1);
  eq(j.insert, 2);
  eq(j.skip, 1, "atlanacak = doğrulama-dışı + dosya-içi + zaten var");
  eq(j.dbConnected, false);
  // Sınırlar korunur: kesin değer sınırı İHLAL ETMEZ.
  eq(j.insertAtMost, 3);
  eq(j.skipAtLeast, 0);
});

test("kesin: hash eşleşmesi (farklı ts) da mevcut satır sayılır", () => {
  const p = fixture("hashsrc.jsonl", SOURCE);
  const snap = fixture("hashsnap.jsonl", [
    `{"source_row_sha256": "${rowHashOf(C2)}"}`,
  ]);
  const j = summary(p, "--dry-run", "--json", `--keys-file=${snap}`);
  eq(
    j.alreadyPresent,
    1,
    "ts farklı ama satır-hash aynı → ON CONFLICT DO NOTHING"
  );
  eq(j.insert, 2);
  eq(j.conflictRows, 1);
});

test("kesin: iki eşleşme de sayılır, aynı aday iki kez sayılmaz", () => {
  const p = fixture("both-src.jsonl", SOURCE);
  const snap = fixture("both-snap.jsonl", [
    `{"ts": "${TS_OF(C1)}"}`,
    `{"source_row_sha256": "${rowHashOf(C2)}"}`,
    `{"ts": "${TS_OF(C1)}", "source_row_sha256": "${rowHashOf(C1)}"}`,
  ]);
  const j = summary(p, "--dry-run", "--json", `--keys-file=${snap}`);
  eq(j.conflictRows, 3);
  eq(j.alreadyPresent, 2, "C1 iki satırla eşleşse de TEK aday sayılır");
  eq(j.insert, 1);
  eq(j.skip, 2);
});

test("kesin: eşleşme yoksa hiçbiri düşmez", () => {
  const p = fixture("nomatch-src.jsonl", SOURCE);
  const snap = fixture("nomatch-snap.jsonl", [
    '{"ts": "2025-01-01T00:00:00.000000+00:00"}',
    '{"source_row_sha256": "deadbeef"}',
  ]);
  const j = summary(p, "--dry-run", "--json", `--keys-file=${snap}`);
  eq(j.alreadyPresent, 0);
  eq(j.insert, 3);
  eq(j.skip, 0);
  eq(j.conflictRows, 2, "kaynak satır sayısı kaynak-tarafsız raporlanır");
});

test("kesin: boş snapshot → sıfır çakışma, sınırlarla aynı sayı", () => {
  const p = fixture("emptysnap-src.jsonl", SOURCE);
  const snap = fixture("empty-snap.jsonl", []);
  eq(fs.readFileSync(snap).length, 0, "boş dosya 0 bayt olmalı");
  const j = summary(p, "--dry-run", "--json", `--keys-file=${snap}`);
  eq(j.conflictSource, "snapshot");
  eq(j.conflictRows, 0);
  eq(j.alreadyPresent, 0);
  eq(j.insert, j.insertAtMost, "kaynak boşsa kesin = sınır");
  eq(j.skip, j.skipAtLeast);
});

test("kesin: karışık dosyada kimlik doğrulaması bozulmaz", () => {
  const p = fixture("mixedsrc.jsonl", [
    '{"ts": "2026-10-01T10:00:00.000000+00:00", "verdict": "PASS"}',
    '{"ts": "2026-10-01T10:00:00.000000+00:00", "verdict": "FAIL"}',
    '{"verdict": "PASS"}',
    "null",
  ]);
  const snap = fixture("mixed-snap.jsonl", [
    '{"ts": "2026-10-01T10:00:00.000000+00:00"}',
  ]);
  const j = summary(p, "--dry-run", "--json", `--keys-file=${snap}`);
  eq(j.candidates, 1);
  eq(j.duplicatesInFile, 1);
  eq(j.invalidSkipped, 2);
  eq(j.alreadyPresent, 1);
  eq(j.insert, 0);
  eq(j.skip, 4, "1 dosya-içi + 2 doğrulama-dışı + 1 zaten var");
});

test("kesin: ölçüsüz mod aynı alanları sınır olarak taşır (geri uyumlu)", () => {
  const p = fixture("plain-src.jsonl", SOURCE);
  const j = summary(p, "--dry-run", "--json");
  eq(j.conflictSource, "none");
  eq(j.conflictRows, 0);
  eq(j.alreadyPresent, 0);
  eq(j.insert, j.insertAtMost);
  eq(j.skip, j.skipAtLeast);
  eq(j.dbConnected, false);
});

test("prose: ölçülen mod 'bu raporda YOK' demez, kesin sayıyı yazar", () => {
  const p = fixture("prosesrc.jsonl", SOURCE);
  const snap = fixture("prose-snap.jsonl", [`{"ts": "${TS_OF(C1)}"}`]);
  const r = runLoader(p, "--dry-run", `--keys-file=${snap}`);
  eq(r.code, 0, r.stderr);
  match(r.stdout, /çakışma kaynağı: snapshot \(1 satır\)/, r.stdout);
  match(r.stdout, /zaten var olan aday: 1/, r.stdout);
  match(r.stdout, /eklenecek \(kesin\): 2 · atlanacak \(kesin\): 1/, r.stdout);
  notMatch(r.stdout, /bu raporda YOK/, "ölçülmüş sayı varken 'yok' denemez");
  notMatch(r.stdout, /\(en çok\)|\(en az\)/, "sınır dili kullanılmamalı");
});

test("kesin: aynı girdide çıktı birebir aynı (deterministik)", () => {
  const p = fixture("det-src.jsonl", SOURCE);
  const snap = fixture("det-snap.jsonl", [`{"ts": "${TS_OF(C2)}"}`]);
  const a = runLoader(p, "--dry-run", `--keys-file=${snap}`);
  const b = runLoader(p, "--dry-run", `--keys-file=${snap}`);
  // Önce yeşil olmalı: iki koşu da AYNI HATAYI verse çıktılar eşit olurdu
  // ve determinizm testi sessizce hiçbir şeyi doğrulamazdı (ilk koşuda
  // tam olarak bu tuzağa düşüldü — vaka kırmızıyken "geçti").
  eq(a.code, 0, `koşu yeşil olmalı — stderr: ${a.stderr}`);
  eq(b.code, 0, `koşu yeşil olmalı — stderr: ${b.stderr}`);
  eq(a.stdout, b.stdout, "iki koşu birebir aynı çıktı vermeli");
});

// ── canlı DB (kimlik yoksa atlanır, "geçti" sayılmaz) ───────────────────────

function needLive() {
  if (!liveCredentials()) {
    skip("DATABASE_URL yok (apps/trend-db/.env) — canlı ölçüm atlandı");
  }
}

test("canlı: --check-db kesin sayı verir ve kimlikler tutar", () => {
  needLive();
  const p = fixture("live-src.jsonl", SOURCE);
  const r = runLiveLoader(p, "--dry-run", "--json", "--check-db");
  eq(r.code, 0, `çıkış 0 olmalı — stderr: ${r.stderr}`);
  const j = JSON.parse(r.stdout.trim());
  eq(j.conflictSource, "db");
  eq(j.dbConnected, true);
  eq(j.conflictRows >= 1, true, "ölçüm gerçekten tabloyu okumuş olmalı");
  // Kimlikler: kaynak-tarafsız ve her koşulda doğru olmalı.
  eq(j.insert + j.alreadyPresent, j.candidates, "insert + zaten var = aday");
  eq(
    j.skip,
    j.invalidSkipped + j.duplicatesInFile + j.alreadyPresent,
    "atlanacak = doğrulama-dışı + dosya-içi + zaten var"
  );
  eq(j.insert <= j.insertAtMost, true, "kesin değer üst sınırı aşamaz");
  eq(j.skip >= j.skipAtLeast, true, "kesin değer alt sınırın altına inemez");
});

test("canlı: iki koşu aynı tablo sayısını görür (dry-run YAZMAZ)", () => {
  needLive();
  const p = fixture("live-nowrite-src.jsonl", SOURCE);
  const first = JSON.parse(
    runLiveLoader(p, "--dry-run", "--json", "--check-db").stdout.trim()
  );
  const second = JSON.parse(
    runLiveLoader(p, "--dry-run", "--json", "--check-db").stdout.trim()
  );
  // Yazma olsaydı ikinci koşu daha fazla satır ve daha fazla "zaten var"
  // görürdü: sayılar kayardı. Aynı kalmaları salt-okunurluğun kanıtıdır.
  eq(second.conflictRows, first.conflictRows, "tablo satır sayısı değişmemeli");
  eq(second.alreadyPresent, first.alreadyPresent, "çakışma sayısı kaymamalı");
  eq(second.insert, first.insert);
});
