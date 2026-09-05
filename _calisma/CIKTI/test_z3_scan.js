// test_z3_scan.js — Z3 progress bar compute (parseZ3Line / computeZ3Status)
// Node unit test suite.
//
// Kapsam: reset / summary (PASS+FAIL) / control / eşleşmeyen satır; bar
// durumu (ilerleme, FAIL, tümü PASS, total=0 koruması). budget_scan.js'in
// test deseniyle birebir — z3_scan.js DOM'suz saf modüldür.
// Çalıştır: node _calisma/CIKTI/test_z3_scan.js
'use strict';

const { Z3_TOTAL, parseZ3Line, computeZ3Status } = require('./z3_scan.js');

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

// ── Z3_TOTAL sabiti ─────────────────────────────────────────────────────────
console.log('── Z3_TOTAL ──');
assertEq(Z3_TOTAL, 12, 'Z3_TOTAL = 12 (K8: 12 sembolik ispat kontrolü)');

// ── parseZ3Line ─────────────────────────────────────────────────────────────
console.log('── parseZ3Line ──');
// reset: yeni koşu başlangıcı
assertDeep(parseZ3Line('SEMBOLİK İSPAT KONTROLÜ (K8) başlıyor'),
           { type: 'reset' }, 'SEMBOLİK İSPAT → reset');
assertDeep(parseZ3Line('  K8 SEMBOLİK İSPAT: 12 kontrol'),
           { type: 'reset' }, 'gömülü SEMBOLİK İSPAT → reset');

// summary: PASS satırı (özet tablo)
assertDeep(parseZ3Line('  [PASS] P1-a  reduct invariance'),
           { type: 'summary', status: 'PASS', id: 'P1-a' },
           'summary PASS → {summary, PASS, P1-a}');
// summary: FAIL satırı + boşluk toleransı
assertDeep(parseZ3Line('  [ FAIL ] P4-b  sat-cek'),
           { type: 'summary', status: 'FAIL', id: 'P4-b' },
           'summary FAIL (boşluklu) → P4-b');
// summary: alt kimlik (P2-note gibi — regex sözleşmesi)
assertDeep(parseZ3Line('  [PASS] P3-note  not satırı'),
           { type: 'summary', status: 'PASS', id: 'P3-note' },
           'summary P3-note → alt kimlik');
// summary: satır başındaki önekler (renklendirme işaretleri) toleransı
assertDeep(parseZ3Line('<span>  [PASS] P5-e</span>'),
           { type: 'summary', status: 'PASS', id: 'P5-e' },
           'summary HTML sarmalı → P5-e');

// control: bireysel canlı ilerleme satırı
assertDeep(parseZ3Line('[P1-a] lem_alt: UNSAT (0.004s)'),
           { type: 'control', id: 'P1-a' },
           'control P1-a → UNSAT satırı');
assertDeep(parseZ3Line('[P4-b] ... SAT'),
           { type: 'control', id: 'P4-b' },
           'control P4-b → SAT satırı');

// eşleşmeyen satırlar → null
assertEq(parseZ3Line(''), null, 'boş satır → null');
assertEq(parseZ3Line('  SONUÇ: PASS — 12/12'), null, 'SONUÇ satırı → null');
assertEq(parseZ3Line('  [OK] P1-a'), null, 'PASS/FAIL olmayan etiket → null');
assertEq(parseZ3Line('  [PASS] P9-x'), null, 'P9 (kapsam dışı) → null');
assertEq(parseZ3Line('  [PASS] not-a-control'), null, 'kimlik yok → null');
assertEq(parseZ3Line('const [P1-a] = 1;'), null,
         'satır başı DEĞİLSE control yakalanmaz (string içi yanlış pozitif yok)');

// ── computeZ3Status ─────────────────────────────────────────────────────────
console.log('── computeZ3Status ──');
// İlerleme: 3/12 görüldü, 2 PASS — nötr sınıflar, yüzde yuvarlanır.
let s = computeZ3Status(3, 2, 0, 12);
assertEq(s.pct, 25, '3/12 → %25');
assertEq(s.barClass, 'z3fill', 'ilerlemede nötr bar sınıfı');
assertEq(s.cntClass, 'z3count', 'ilerlemede nötr sayaç sınıfı');
assertEq(s.text, '2/12', 'ilerleme metni PASS sayısı/toplam');
assert(!s.text.includes('FAIL'), 'FAIL yokken FAIL eki olmaz');

// FAIL: err sınıfı + FAIL eki (sayaç ok DEĞİL)
s = computeZ3Status(5, 4, 1, 12);
assertEq(s.pct, 42, '5/12 → %42 (round)');
assertEq(s.barClass, 'z3fill err', 'FAIL → err bar');
assertEq(s.cntClass, 'z3count', 'FAIL → sayaç ok DEĞİL');
assertEq(s.text, '4/12 · 1 FAIL', 'FAIL eki "· N FAIL"');
assert(s.text.includes('FAIL'), 'FAIL metni içerir');

// Tümü PASS: ok sınıfları
s = computeZ3Status(12, 12, 0, 12);
assertEq(s.pct, 100, '12/12 → %100');
assertEq(s.barClass, 'z3fill ok', 'tümü PASS → ok bar');
assertEq(s.cntClass, 'z3count ok', 'tümü PASS → ok sayaç');
assertEq(s.text, '12/12', 'tümü PASS metni FAIL ekisiz');

// Sıfır-bölme koruması: total <= 0 → pct 0, text geçerli
s = computeZ3Status(0, 0, 0, 0);
assertEq(s.pct, 0, 'total=0 → pct 0 (sıfır-bölme yok)');
assertEq(s.text, '0/0', 'total=0 metni');
s = computeZ3Status(3, 3, 0, -1);
assertEq(s.pct, 0, 'total<0 → pct 0');

// Zincir: parse → durum (gerçek akış özeti)
console.log('── zincir: parse → durum ──');
let seen = new Set(), okSet = new Set(), failSet = new Set();
function feed(line) {
  const p = parseZ3Line(line);
  if (!p) return;
  if (p.type === 'reset') { seen.clear(); okSet.clear(); failSet.clear(); return; }
  if (p.type === 'summary') { (p.status === 'PASS' ? okSet : failSet).add(p.id); seen.add(p.id); }
  else if (p.type === 'control') { seen.add(p.id); }
}
feed('SEMBOLİK İSPAT KONTROLÜ');
feed('[P1-a] lem_alt: UNSAT');
feed('  [PASS] P1-a  reduct invariance');
feed('[P2-b] red: SAT');
feed('  [FAIL] P2-b  red');
feed('  [PASS] P3-c  transitivity');
feed('  SONUÇ: FAIL — 1 FAIL');
const st = computeZ3Status(seen.size, okSet.size, failSet.size, Z3_TOTAL);
assertEq(seen.size, 3, 'zincir: 3 kontrol görüldü');
assertEq(okSet.size, 2, 'zincir: 2 PASS');
assertEq(failSet.size, 1, 'zincir: 1 FAIL');
assertEq(st.text, '2/12 · 1 FAIL', 'zincir: bar metni');
assertEq(st.barClass, 'z3fill err', 'zincir: FAIL → err');

// Reset sonrası sayaçlar temizlenir (yeni koşu)
feed('SEMBOLİK İSPAT KONTROLÜ');
assertEq(seen.size, 0, 'reset sonrası görülenler temiz');
assertEq(okSet.size, 0, 'reset sonrası PASS temiz');

console.log('');
console.log(`${passed} PASS, ${failed} FAIL`);
process.exit(failed === 0 ? 0 : 1);
