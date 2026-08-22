// test_budget_scan.js — Budget bar compute (parseBudgetLine / computeBudgetStatus
// / budgetLimitNote) Node unit test suite.
//
// Kapsam: normal, aşım, sıfır/geçersiz, parse edge case'leri.
// Çalıştır: node _calisma/CIKTI/test_budget_scan.js
'use strict';

const { parseBudgetLine, computeBudgetStatus, budgetLimitNote, fmtLimit } = require('./budget_scan.js');

let passed = 0, failed = 0;
function assert(cond, msg) {
  if (cond) { passed++; }
  else { failed++; console.error('  FAIL: ' + msg); }
}

function assertEq(actual, expected, msg) {
  const ok = actual === expected;
  if (ok) { passed++; }
  else { failed++; console.error('  FAIL: ' + msg + ' → expected=' + JSON.stringify(expected) + ', got=' + JSON.stringify(actual)); }
}

function assertDeep(actual, expected, msg) {
  const ok = JSON.stringify(actual) === JSON.stringify(expected);
  if (ok) { passed++; }
  else { failed++; console.error('  FAIL: ' + msg + ' → expected=' + JSON.stringify(expected) + ', got=' + JSON.stringify(actual)); }
}

// ── fmtLimit ─────────────────────────────────────────────────────────────────
console.log('── fmtLimit ──');
// ≥10 → tam sayı
assertEq(fmtLimit(30), '30', 'fmtLimit 30 → "30"');
assertEq(fmtLimit(100), '100', 'fmtLimit 100 → "100"');
// ≥1 → 1 ondalık
assertEq(fmtLimit(5), '5.0', 'fmtLimit 5 → "5.0"');
assertEq(fmtLimit(1), '1.0', 'fmtLimit 1 → "1.0"');
// <1 → 2 ondalık
assertEq(fmtLimit(0.08), '0.08', 'fmtLimit 0.08 → "0.08"');
assertEq(fmtLimit(0.1), '0.10', 'fmtLimit 0.1 → "0.10"');

// ── parseBudgetLine ──────────────────────────────────────────────────────────
console.log('── parseBudgetLine ──');
// Normal
const r1 = parseBudgetLine('[BÜTÇE] ~175990 token → $1.08 (limit $30.0, içerik 703961 B, yöntem=both)');
assertEq(r1.est, 1.08, 'parse normal: est=1.08');
assertEq(r1.limit, 30.0, 'parse normal: limit=30');

// Aşım
const r2 = parseBudgetLine('[BÜTÇE] ~1000000 token → $35.50 (limit $25.0, içerik 999999 B, yöntem=weighted)');
assertEq(r2.est, 35.50, 'parse overflow: est=35.50');
assertEq(r2.limit, 25.0, 'parse overflow: limit=25');

// Tam sınırda
const r3 = parseBudgetLine('[BÜTÇE] ~990000 token → $30.00 (limit $30.0, içerik 999999 B, yöntem=both)');
assertEq(r3.est, 30.00, 'parse exact: est=30.00');
assertEq(r3.limit, 30.0, 'parse exact: limit=30.0');

// Çok küçük değer
const r4 = parseBudgetLine('[BÜTÇE] ~1000 token → $0.03 (limit $30.0, içerik 500 B)');
assertEq(r4.est, 0.03, 'parse tiny: est=0.03');
assertEq(r4.limit, 30, 'parse tiny: limit=30');

// Limit ondalıklı (100.0)
const r5 = parseBudgetLine('[BÜTÇE] ~5000 token → $0.15 (limit $100.0, içerik 3000 B)');
assertEq(r5.est, 0.15, 'parse limit100: est=0.15');
assertEq(r5.limit, 100, 'parse limit100: limit=100');

// Eşleşmeyen satır → null
assertEq(parseBudgetLine('semBOLİK İSPAT — core_section.tex (Z3)'), null, 'parse no-match: null');
assertEq(parseBudgetLine('SONUÇ: PASS  (P0=0, P1=0)'), null, 'parse verdict line: null');
assertEq(parseBudgetLine(''), null, 'parse empty: null');
assertEq(parseBudgetLine('[BÜTÇE] incomplete'), null, 'parse incomplete: null');

// Bozuk sayı → null (NaN koruması)
assertEq(parseBudgetLine('[BÜTÇE] ~abc token → $xyz (limit $30.0)'), null, 'parse NaN est: null');
assertEq(parseBudgetLine('[BÜTÇE] ~100 token → $1.00 (limit $xyz)'), null, 'parse NaN limit: null');

// ── computeBudgetStatus ──────────────────────────────────────────────────────
console.log('── computeBudgetStatus ──');
// Normal
const s1 = computeBudgetStatus(1.08, 30.0);
assertEq(s1.pct, 4, 'status normal: pct=4%');
assertEq(s1.over, false, 'status normal: over=false');
assertEq(s1.barClass, 'z3fill budget', 'status normal: barClass');
assertEq(s1.cntClass, 'z3count ok', 'status normal: cntClass ok');
assertEq(s1.text, '$1.08 / $30.00', 'status normal: text');

// Aşım
const s2 = computeBudgetStatus(35.50, 25.0);
assertEq(s2.pct, 100, 'status overflow: pct capped 100');
assertEq(s2.over, true, 'status overflow: over=true');
assertEq(s2.barClass, 'z3fill err', 'status overflow: barClass err');
assertEq(s2.cntClass, 'z3count', 'status overflow: cntClass');
assert(s2.text.includes('AŞIM'), 'status overflow: text contains AŞIM');
assert(s2.text.includes('$35.50'), 'status overflow: text has est');

// Tam sınır (est === limit)
const s3 = computeBudgetStatus(30.00, 30.0);
assertEq(s3.pct, 100, 'status exact: pct=100');
assertEq(s3.over, false, 'status exact: over=false (est=limit → NOT overflow)');
assertEq(s3.barClass, 'z3fill budget', 'status exact: barClass');
assert(s3.text.indexOf('AŞIM') === -1, 'status exact: no AŞIM text');

// Çok küçük (pct=0 ama barClass/cntClass geçerli)
const s4 = computeBudgetStatus(0.01, 30.0);
assertEq(s4.pct, 0, 'status tiny: pct=0 (rounded)');
assertEq(s4.over, false, 'status tiny: over=false');
assertEq(s4.barClass, 'z3fill budget', 'status tiny: barClass');
assertEq(s4.cntClass, 'z3count ok', 'status tiny: cntClass ok');

// Yüzde ≈50
const s5 = computeBudgetStatus(15.0, 30.0);
assertEq(s5.pct, 50, 'status half: pct=50');
assertEq(s5.over, false, 'status half: over=false');

// Sıfır/geçersiz — est/limit yok
const s6 = computeBudgetStatus(null, 30.0);
assertEq(s6.pct, 0, 'status null est: pct=0');
assertEq(s6.text, '—', 'status null est: text="—"');

const s7 = computeBudgetStatus(5.0, null);
assertEq(s7.pct, 0, 'status null limit: pct=0');
assertEq(s7.text, '—', 'status null limit: text="—"');

const s8 = computeBudgetStatus(NaN, 30.0);
assertEq(s8.pct, 0, 'status NaN est: pct=0');

const s9 = computeBudgetStatus(5.0, 0);
assertEq(s9.pct, 0, 'status zero limit: pct=0 (guard)');

const s10 = computeBudgetStatus(5.0, -5);
assertEq(s10.pct, 0, 'status negative limit: pct=0 (guard)');

// İkisi de geçerli ama limit inanılmaz küçük (yine de hesapla)
const s11 = computeBudgetStatus(100.0, 0.01);
assertEq(s11.pct, 100, 'status tiny limit: pct capped 100');
assertEq(s11.over, true, 'status tiny limit: over=true');

// ── budgetLimitNote ──────────────────────────────────────────────────────────
console.log('── budgetLimitNote ──');
// Normal (altında)
assertEq(budgetLimitNote(5.0, 30.0), ' (limit $30 altında)', 'note under limit');
assertEq(budgetLimitNote(29.99, 30.0), ' (limit $30 altında)', 'note just under');

// Aşım (üstünde)
assertEq(budgetLimitNote(35.0, 30.0), ' (limit $30 üstünde — AŞIM)', 'note overflow');
assertEq(budgetLimitNote(30.01, 30.0), ' (limit $30 üstünde — AŞIM)', 'note just over');

// Nil/NaN guard
assertEq(budgetLimitNote(null, 30.0), '', 'note null value → empty');
assertEq(budgetLimitNote(5.0, null), '', 'note null limit → empty');
assertEq(budgetLimitNote(NaN, 30.0), '', 'note NaN value → empty');
assertEq(budgetLimitNote(5.0, NaN), '', 'note NaN limit → empty');

// limit >=10 → fmtLimit tamsayı
assertEq(budgetLimitNote(25.0, 100.0), ' (limit $100 altında)', 'note limit100');
assertEq(budgetLimitNote(150.0, 100.0), ' (limit $100 üstünde — AŞIM)', 'note limit100 overflow');

// ── Entegrasyon: parse + status zinciri ─────────────────────────────────────
console.log('── zincir: parse → status ──');
const chain = parseBudgetLine('[BÜTÇE] ~175990 token → $1.08 (limit $30.0, içerik 703961 B, yöntem=both)');
assert(chain !== null, 'chain parse');
if (chain) {
  const cs = computeBudgetStatus(chain.est, chain.limit);
  assertEq(cs.pct, 4, 'chain: pct=4');
  assertEq(cs.over, false, 'chain: over=false');
  assert(cs.text.indexOf('AŞIM') === -1, 'chain: no AŞIM');

  const note = budgetLimitNote(chain.est, chain.limit);  // 25.0 < 30.0
  assertEq(budgetLimitNote(25.0, chain.limit), ' (limit $30 altında)', 'chain: note under');
}

// ── Özet ─────────────────────────────────────────────────────────────────────
console.log('');
console.log(passed + ' PASS, ' + failed + ' FAIL');
if (failed > 0) process.exit(1);