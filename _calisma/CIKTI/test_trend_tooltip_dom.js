#!/usr/bin/env node
// test_trend_tooltip_dom.js — preview.js showTrendTip/showRefsTrendTip DOM testi.
//
// Mimari not: dashboard script'i inline'dan preview.js'e taşındı (IIFE +
// üst-seviye `let` state). Test, preview.js'i ortak vm-sandbox yardımcısı
//yla yükler; tip element'ini sandbox'a enjekte eder, trend/refs cache ve
// BUDGET_LIMIT sandbox içinde koşan vm-koduyla yazılır (lexical `let`'e
// dışarıdan sandbox.X = ataması etki etmez).
//
// Kullanım: node test_trend_tooltip_dom.js
"use strict";
const vm = require("vm");
const assert = require("assert");

const { loadPreview, makeElementStub } = require("./preview_vm_sandbox.js");

const tip = makeElementStub({
  innerHTML: "",
  style: { display: "none", left: "", top: "" },
});
const sandbox = loadPreview({ tipElement: tip });

const run = {
  ts: "2026-08-28T12:00:00Z",
  budget_usd: 31,
  budget_limit: 30,
  duration_s: 2,
  p0: 0,
  p1: 0,
  z3_passed: 12,
  z3_total: 12,
};
sandbox.run = run;
vm.runInContext(
  "BUDGET_LIMIT = 30; trendCache = [run]; refsTrendCache = [run]",
  sandbox
);
sandbox.showTrendTip(0, { clientX: 10, clientY: 10 });
assert(
  tip.innerHTML.includes("tt-over"),
  "showTrendTip must mark over-budget row"
);
assert(
  tip.innerHTML.includes("limit $30"),
  "showTrendTip must show the run limit"
);
sandbox.showRefsTrendTip(0, { clientX: 10, clientY: 10 });
assert(
  tip.innerHTML.includes("tt-over"),
  "showRefsTrendTip must mark over-budget row"
);
assert(
  tip.innerHTML.includes("limit $30"),
  "showRefsTrendTip must show the run limit"
);

const safe = Object.assign({}, run, { budget_usd: 29 });
sandbox.safe = safe;
vm.runInContext("trendCache = [safe]; refsTrendCache = [safe]", sandbox);
sandbox.showTrendTip(0, { clientX: 10, clientY: 10 });
assert(
  tip.innerHTML.includes("tt-under"),
  "showTrendTip must mark under-budget row"
);
sandbox.showRefsTrendTip(0, { clientX: 10, clientY: 10 });
assert(
  tip.innerHTML.includes("tt-under"),
  "showRefsTrendTip must mark under-budget row"
);
console.log(
  "trend tooltip DOM: PASS — showTrendTip/showRefsTrendTip over/under colors verified"
);
