// budget_scan.js — Budget bar compute (preview.html scanBudget/updateBudgetBar pure logic).
//
// Preview.html'deki [BÜTÇE] satır ayrıştırma + progress bar hesaplaması
// DOM'dan arındırılmış saf fonksiyonlar olarak. Node ile doğrudan test
// edilebilir (preview.html window objesi yok).
'use strict';

// ── Yardımcı ────────────────────────────────────────────────────────────────
function fmtLimit(v) {
  if (v >= 10) return v.toFixed(0);
  if (v >= 1) return v.toFixed(1);
  return v.toFixed(2);
}

// ── 1) Ayrıştırma: "[BÜTÇE] ~175990 token → $1.08 (limit $30.0, …)" ──
// Döndürür {est, limit} | null (satır eşleşmezse).
function parseBudgetLine(line) {
  const m = line.match(/\[BÜTÇE\][^→]*→\s*\$([0-9.]+)\s*\(limit\s*\$([0-9.]+)/);
  if (!m) return null;
  const est = parseFloat(m[1]);
  const limit = parseFloat(m[2]);
  if (!isFinite(est) || !isFinite(limit)) return null;
  return { est, limit };
}

// ── 2) Durum hesaplaması (updateBudgetBar saf karşılığı) ──
// Döndürür {pct, over, barClass, cntClass, text}
// est/limit yoksa veya geçersizse → sıfır durumu.
function computeBudgetStatus(est, limit) {
  if (est == null || limit == null || !isFinite(est) || !isFinite(limit) || limit <= 0) {
    return { pct: 0, over: false, barClass: 'z3fill budget', cntClass: 'z3count', text: '—' };
  }
  const pct = Math.min(100, Math.round(est / limit * 100));
  const over = est > limit;
  const barClass = over ? 'z3fill err' : 'z3fill budget';
  const cntClass = over ? 'z3count' : 'z3count ok';
  const text = '$' + est.toFixed(2) + ' / $' + limit.toFixed(2)
    + ' (' + pct + '%)' + (over ? ' · AŞIM' : '');
  return { pct, over, barClass, cntClass, text };
}

// ── 3) Tooltip notu (budgetLimitNote saf karşılığı) ──
// v: değer (null/NaN olabilir), limit: bütçe sınırı
function budgetLimitNote(v, limit) {
  if (v == null || !isFinite(v) || limit == null || !isFinite(limit)) return '';
  const lim = '$' + fmtLimit(limit);
  return v > limit ? ' (limit ' + lim + ' üstünde — AŞIM)' : ' (limit ' + lim + ' altında)';
}

// ── Dışa aktarım (Node/browser uyumlu) ─────────────────────────────────────
if (typeof module !== 'undefined' && module.exports) {
  module.exports = { parseBudgetLine, computeBudgetStatus, budgetLimitNote, fmtLimit };
}