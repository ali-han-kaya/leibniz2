#!/usr/bin/env node
const fs = require('fs');
const vm = require('vm');
const assert = require('assert');

const html = fs.readFileSync(__dirname + '/preview.html', 'utf8');
const script = html.match(/<script>\n"use strict";([\s\S]*?)<\/script>/);
assert(script, 'inline dashboard script not found');

const sandbox = {
  console,
  Date,
  isFinite,
  encodeURIComponent,
  decodeURIComponent,
  setTimeout,
  setInterval: () => {},
  fetch: () => Promise.resolve({ json: () => Promise.resolve([]) }),
  EventSource: function() { this.addEventListener = () => {}; this.close = () => {}; },
  document: { getElementById: () => ({ addEventListener: () => {}, classList: {toggle(){}, add(){}, remove(){}} }), querySelectorAll: () => [] },
  window: {},
  navigator: {},
};
vm.createContext(sandbox);
vm.runInContext('"use strict";\n' + script[1], sandbox);

const rows = Array.from({length: 35}, (_, i) => ({
  ts: `2026-08-01T00:${String(i).padStart(2, '0')}:00Z`,
  budget_usd: i + 1,
}));
sandbox.BUDGET_LIMIT = 10;
const output = sandbox.budgetOverDetailRows(rows);
const lines = output.split('\n');
assert.strictEqual(lines.length, 31, 'must render 30 rows plus overflow marker');
assert(lines[0].includes('$35.00'), 'newest run must be first');
assert(lines[29].includes('$6.00'), '30th newest run must be last');
assert(lines[30].includes('… +5 run daha'), 'overflow count must be accurate');
assert(!lines.some(line => line.includes('$5.00')), '31st row must be omitted');
console.log('budgetOverDetailRows: PASS — 30-row cap, newest-first, overflow count');
