#!/usr/bin/env node
// test_refs_trend_badge_node.js — refsTrendBadge() Node birim testi.
//
// preview.html'deki refsTrendBadge() fonksiyonunu Node ortamında
// çalıştırır ve test_refs_trend_badge.py ile aynı senaryoları doğrular.
// Çıktı: JSON {ok, passed, failed, results: [{name, input, expected, actual, pass}]}
//
// Kullanım: node test_refs_trend_badge_node.js
'use strict';

const fs = require('fs');
const path = require('path');

// preview.html'den refsTrendBadge fonksiyonunu çıkar
const previewPath = path.join(__dirname, 'preview.html');
const html = fs.readFileSync(previewPath, 'utf8');
const fnMatch = html.match(/function refsTrendBadge\(rows\)\s*\{[\s\S]*?\n\}/);
if (!fnMatch) {
  process.stdout.write(JSON.stringify({ok: false, error: 'refsTrendBadge bulunamadı'}));
  process.exit(1);
}
// Fonksiyonu eval ile tanımla (global scope'a)
const fnBody = fnMatch[0];
const fn = new Function('rows', fnBody.replace('function refsTrendBadge(rows)', ''));
// Global olarak tanımla
globalThis.refsTrendBadge = fn;

// ── Test senaryoları ──────────────────────────────────────────────────────
function row(v, t) { return { refs_verified: v, refs_total: t }; }

const tests = [
  {
    name: 'no_data_unknown',
    input: null,
    expected: { cls: 'unknown', text: 'tam kapsam: veri yok' },
  },
  {
    name: 'empty_array_unknown',
    input: [],
    expected: { cls: 'unknown', text: 'tam kapsam: veri yok' },
  },
  {
    name: 'none_fields_filtered',
    input: [{ refs_verified: null, refs_total: null }, row(61, 61)],
    expected: { cls: 'ok', text: '✓ TAM KAPSAM 61/61' },
  },
  {
    name: 'single_full_run',
    input: [row(61, 61)],
    expected: { cls: 'ok', text: '✓ TAM KAPSAM 61/61' },
  },
  {
    name: 'consecutive_full_streak_2',
    input: [row(60, 61), row(61, 61), row(61, 61)],
    expected: { cls: 'ok', text: '✓ TAM KAPSAM 61/61 · 2 run' },
  },
  {
    name: 'consecutive_full_streak_3',
    input: [row(60, 61), row(61, 61), row(61, 61), row(61, 61)],
    expected: { cls: 'ok', text: '✓ TAM KAPSAM 61/61 · 3 run' },
  },
  {
    name: 'last_partial_warn',
    input: [row(61, 61), row(60, 61)],
    expected: { cls: 'warn', text: 'kapsam eksik 60/61' },
  },
  {
    name: 'streak_resets_on_partial',
    input: [row(61, 61), row(60, 61), row(61, 61), row(61, 61)],
    expected: { cls: 'ok', text: '✓ TAM KAPSAM 61/61 · 2 run' },
  },
  {
    name: 'all_partial',
    input: [row(58, 61), row(59, 61), row(60, 61)],
    expected: { cls: 'warn', text: 'kapsam eksik 60/61' },
  },
  {
    name: 'mixed_none_and_valid',
    input: [
      { refs_verified: null, refs_total: null },
      { refs_verified: null, refs_total: 61 },
      row(61, 61),
    ],
    expected: { cls: 'ok', text: '✓ TAM KAPSAM 61/61' },
  },
];

// ── Çalıştır ──────────────────────────────────────────────────────────────
let passed = 0, failed = 0;
const results = [];

for (const t of tests) {
  const actual = refsTrendBadge(t.input);
  const ok = actual.cls === t.expected.cls && actual.text === t.expected.text;
  if (ok) passed++; else failed++;
  results.push({
    name: t.name,
    expected: t.expected,
    actual,
    pass: ok,
  });
}

process.stdout.write(JSON.stringify({
  ok: failed === 0,
  passed,
  failed,
  total: tests.length,
  results,
}));
