#!/usr/bin/env node
const fs = require('fs');
const vm = require('vm');
const assert = require('assert');
const html = fs.readFileSync(__dirname + '/preview.html', 'utf8');
const match = html.match(/<script>\n"use strict";([\s\S]*?)<\/script>/);
assert(match, 'inline dashboard script not found');
const tip = { innerHTML: '', style: { display: 'none', left: '', top: '' }, offsetWidth: 100, offsetHeight: 50 };
const sandbox = { console, Date, isFinite, encodeURIComponent, decodeURIComponent, setTimeout, setInterval: () => {},
  fetch: () => Promise.resolve({ json: () => Promise.resolve([]) }),
  EventSource: function() { this.addEventListener = () => {}; this.close = () => {}; }, navigator: {},
  window: { innerWidth: 1200, innerHeight: 800 }, document: {
    getElementById: id => id === 'tip' ? tip : { addEventListener: () => {}, classList: { toggle(){}, add(){}, remove(){} } },
    querySelectorAll: () => [], addEventListener: () => {},
  },
};
vm.createContext(sandbox);
vm.runInContext('"use strict";\n' + match[1], sandbox);
const run = { ts: '2026-08-28T12:00:00Z', budget_usd: 31, budget_limit: 30, duration_s: 2, p0: 0, p1: 0, z3_passed: 12, z3_total: 12 };
vm.runInContext('BUDGET_LIMIT = 30', sandbox);
sandbox.trendCache = [run];
sandbox.showTrendTip(0, { clientX: 10, clientY: 10 });
assert(tip.innerHTML.includes('tt-over'), 'showTrendTip must mark over-budget row');
assert(tip.innerHTML.includes('limit $30'), 'showTrendTip must show the run limit');
sandbox.refsTrendCache = [run];
sandbox.showRefsTrendTip(0, { clientX: 10, clientY: 10 });
assert(tip.innerHTML.includes('tt-over'), 'showRefsTrendTip must mark over-budget row');
assert(tip.innerHTML.includes('limit $30'), 'showRefsTrendTip must show the run limit');
const safe = Object.assign({}, run, { budget_usd: 29 });
sandbox.trendCache = [safe];
sandbox.showTrendTip(0, { clientX: 10, clientY: 10 });
assert(tip.innerHTML.includes('tt-under'), 'showTrendTip must mark under-budget row');
sandbox.refsTrendCache = [safe];
sandbox.showRefsTrendTip(0, { clientX: 10, clientY: 10 });
assert(tip.innerHTML.includes('tt-under'), 'showRefsTrendTip must mark under-budget row');
console.log('trend tooltip DOM: PASS — showTrendTip/showRefsTrendTip over/under colors verified');
