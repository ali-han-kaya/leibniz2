#!/usr/bin/env node
// budgetOverDetailRows — 30 satır tavanı, en yeni üstte, taşma sayacı.
//
// Kapsam: TEK saf fonksiyon. Sandbox preview_vm_sandbox.js'te ortak — burada
// yalnızca incelediğimiz çıktıyı doğruluyoruz.
//
// NOT: bu dosya uzun süre preview.html'den inline <script> kazıyordu. Dashboard
// kodu preview.js'e taşınınca regex hiç eşleşmedi ve test, HİÇBİR YERDE
// koşulmadığı için sessizce ölü kaldı.
'use strict';

const assert = require('assert');
const { loadPreview } = require('./preview_vm_sandbox.js');

const { sandbox } = loadPreview();
assert.strictEqual(
  typeof sandbox.budgetOverDetailRows,
  'function',
  'budgetOverDetailRows preview.js içinde tanımlı değil'
);

const rows = Array.from({ length: 35 }, (_, i) => ({
  ts: `2026-08-01T00:${String(i).padStart(2, '0')}:00Z`,
  budget_usd: i + 1,
}));
const lines = sandbox.budgetOverDetailRows(rows).split('\n');

const CASES = [
  ['30 satır + taşma işareti', lines.length, 31],
  ['en yeni üstte', lines[0].includes('$35.00'), true],
  ['30. en yeni son satır', lines[29].includes('$6.00'), true],
  ['taşma sayacı doğru', lines[30].includes('… +5 run daha'), true],
  ['31. satır düşer', lines.some((l) => l.includes('$5.00')), false],
];
for (const [name, got, expected] of CASES) {
  assert.strictEqual(got, expected, name);
}
console.log(
  `budgetOverDetailRows: PASS — ${CASES.length} kural (30-row cap, newest-first, overflow count)`
);
