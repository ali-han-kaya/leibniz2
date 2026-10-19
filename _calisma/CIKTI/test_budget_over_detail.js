#!/usr/bin/env node
// test_budget_over_detail.js — preview.js budgetOverDetailRows() Node testi.
//
// Mimari not: dashboard script'i inline'dan preview.js'e taşındı (IIFE +
// üst-seviye `let` state). Test, preview.js'i ortak vm-sandbox yardımcısı
//yla yükler; BUDGET_LIMIT/trendCache sandbox İÇİNDE koşan vm-koduyla
// yazılır (lexical `let`'e dışarıdan sandbox.X = ataması etki etmez).
//
// Kullanım: node test_budget_over_detail.js
"use strict";
const vm = require("vm");
const assert = require("assert");

const { loadPreview } = require("./preview_vm_sandbox.js");
const sandbox = loadPreview();

const rows = Array.from({ length: 35 }, (_, i) => ({
  ts: `2026-08-01T00:${String(i).padStart(2, "0")}:00Z`,
  budget_usd: i + 1,
}));
sandbox.rows = rows; // sandbox-icinden gorunur kilsin (vm-lexikal state yazimi)
vm.runInContext("BUDGET_LIMIT = 10; trendCache = rows", sandbox);
const output = vm.runInContext("budgetOverDetailRows(trendCache)", sandbox);
const lines = output.split("\n");
assert.strictEqual(
  lines.length,
  31,
  "must render 30 rows plus overflow marker"
);
assert(lines[0].includes("$35.00"), "newest run must be first");
assert(lines[29].includes("$6.00"), "30th newest run must be last");
assert(lines[30].includes("… +5 run daha"), "overflow count must be accurate");
assert(
  !lines.some((line) => line.includes("$5.00")),
  "31st row must be omitted"
);
console.log(
  "budgetOverDetailRows: PASS — 30-row cap, newest-first, overflow count"
);
