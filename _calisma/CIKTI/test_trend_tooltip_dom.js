#!/usr/bin/env node
// showTrendTip / showRefsTrendTip — bütçe aşımı/altı renkleri (tt-over / tt-under).
//
// Kapsam: tooltip'in bütçe satırı rengi. Sandbox preview_vm_sandbox.js'te ortak;
// burada incelediğimiz tek somut düğüm #tip'tir.
//
// NOT: bu dosya uzun süre preview.html'den inline <script> kazıyordu. Dashboard
// kodu preview.js'e taşınınca regex hiç eşleşmedi ve test, HİÇBİR YERDE
// koşulmadığı için sessizce ölü kaldı. Ayrıca `sandbox.trendCache = …` yazımı
// script'in `let trendCache` binding'ine ULAŞMIYORDU — showTrendTip boş veri
// görüp sessizce dönüyordu. Artık setInScript ile atanıyor.
'use strict';

const assert = require('assert');
const { loadPreview } = require('./preview_vm_sandbox.js');

const tip = {
  innerHTML: '',
  style: { display: 'none', left: '', top: '' },
  offsetWidth: 100,
  offsetHeight: 50,
};
const { sandbox, setInScript } = loadPreview({ elements: { tip } });
const run = {
  ts: '2026-08-28T12:00:00Z',
  budget_usd: 31,
  budget_limit: 30,
  duration_s: 2,
  p0: 0,
  p1: 0,
  z3_passed: 12,
  z3_total: 12,
};

setInScript('BUDGET_LIMIT', 30);
setInScript('trendCache', [run]);
sandbox.showTrendTip(0, { clientX: 10, clientY: 10 });
assert(
  tip.innerHTML.includes('tt-over'),
  'showTrendTip must mark over-budget row'
);
assert(
  tip.innerHTML.includes('limit $30'),
  'showTrendTip must show the run limit'
);
setInScript('refsTrendCache', [run]);
sandbox.showRefsTrendTip(0, { clientX: 10, clientY: 10 });
assert(
  tip.innerHTML.includes('tt-over'),
  'showRefsTrendTip must mark over-budget row'
);
assert(
  tip.innerHTML.includes('limit $30'),
  'showRefsTrendTip must show the run limit'
);
const safe = Object.assign({}, run, { budget_usd: 29 });
setInScript('trendCache', [safe]);
sandbox.showTrendTip(0, { clientX: 10, clientY: 10 });
assert(
  tip.innerHTML.includes('tt-under'),
  'showTrendTip must mark under-budget row'
);
setInScript('refsTrendCache', [safe]);
sandbox.showRefsTrendTip(0, { clientX: 10, clientY: 10 });
assert(
  tip.innerHTML.includes('tt-under'),
  'showRefsTrendTip must mark under-budget row'
);
console.log(
  'trend tooltip DOM: PASS — showTrendTip/showRefsTrendTip over/under colors verified'
);
