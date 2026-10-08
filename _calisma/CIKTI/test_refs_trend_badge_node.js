#!/usr/bin/env node
// test_refs_trend_badge_node.js — preview.js refsTrendBadge() Node testi.
//
// preview.js'teki refsTrendBadge() fonksiyonunu Node ortamında çalıştırır
// ve test_refs_trend_badge.py ile aynı senaryoları doğrular.
// Çıktı: JSON {ok, passed, failed, results: [{name, input, expected, actual, pass}]}
//
// Mimari not: script inline'dan preview.js'e taşındı (IIFE). Test, ortak
// vm-sandbox yardımcısıyla TAM preview.js'i yükleyip sandbox içinden
// fonksiyonu çağırır — regex ile fonksiyon koparmak yerine.
//
// Kullanım: node test_refs_trend_badge_node.js
"use strict";

const { loadPreview } = require("./preview_vm_sandbox.js");
const sandbox = loadPreview();
const refsTrendBadge = sandbox.refsTrendBadge;
if (typeof refsTrendBadge !== "function") {
  process.stdout.write(
    JSON.stringify({ ok: false, error: "refsTrendBadge bulunamadı" })
  );
  process.exit(1);
}

// ── Test senaryoları ──────────────────────────────────────────────────────
function row(v, t) {
  return { refs_verified: v, refs_total: t };
}

const tests = [
  {
    name: "no_data_unknown",
    input: null,
    expected: { cls: "unknown", text: "tam kapsam: veri yok" },
  },
  {
    name: "empty_array_unknown",
    input: [],
    expected: { cls: "unknown", text: "tam kapsam: veri yok" },
  },
  {
    name: "none_fields_filtered",
    input: [{ refs_verified: null, refs_total: null }, row(61, 61)],
    expected: { cls: "ok", text: "✓ TAM KAPSAM 61/61" },
  },
  {
    name: "single_full_run",
    input: [row(61, 61)],
    expected: { cls: "ok", text: "✓ TAM KAPSAM 61/61" },
  },
  {
    name: "consecutive_full_streak_2",
    input: [row(60, 61), row(61, 61), row(61, 61)],
    expected: { cls: "ok", text: "✓ TAM KAPSAM 61/61 · 2 run" },
  },
  {
    name: "consecutive_full_streak_3",
    input: [row(60, 61), row(61, 61), row(61, 61), row(61, 61)],
    expected: { cls: "ok", text: "✓ TAM KAPSAM 61/61 · 3 run" },
  },
  {
    name: "last_partial_warn",
    input: [row(61, 61), row(60, 61)],
    expected: { cls: "warn", text: "kapsam eksik 60/61" },
  },
  {
    name: "streak_resets_on_partial",
    input: [row(61, 61), row(60, 61), row(61, 61), row(61, 61)],
    expected: { cls: "ok", text: "✓ TAM KAPSAM 61/61 · 2 run" },
  },
  {
    name: "all_partial",
    input: [row(58, 61), row(59, 61), row(60, 61)],
    expected: { cls: "warn", text: "kapsam eksik 60/61" },
  },
  {
    name: "mixed_none_and_valid",
    input: [
      { refs_verified: null, refs_total: null },
      { refs_verified: null, refs_total: 61 },
      row(61, 61),
    ],
    expected: { cls: "ok", text: "✓ TAM KAPSAM 61/61" },
  },
];

// ── Çalıştır ──────────────────────────────────────────────────────────────
let passed = 0,
  failed = 0;
const results = [];

for (const t of tests) {
  const actual = sandbox.refsTrendBadge(t.input);
  const ok = actual.cls === t.expected.cls && actual.text === t.expected.text;
  if (ok) passed++;
  else failed++;
  results.push({
    name: t.name,
    expected: t.expected,
    actual,
    pass: ok,
  });
}

process.stdout.write(
  JSON.stringify({
    ok: failed === 0,
    passed,
    failed,
    total: tests.length,
    results,
  })
);
