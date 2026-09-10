// z3_scan.js — Z3 progress bar compute (preview.html scanZ3/updateZ3Bar pure logic).
//
// Preview.html'deki K8 Z3 ilerleme çubuğu: stream satırı ayrıştırma +
// bar durumu hesaplaması, DOM'dan arındırılmış saf fonksiyonlar olarak.
// Node ile doğrudan test edilebilir (preview.html window objesi yok).
// budget_scan.js ile aynı desen: browser'da fonksiyonlar/Z3_TOTAL global,
// Node'da module.exports.
'use strict';

// Toplam Z3 kontrol sayısı (K8: 12 sembolik ispat kontrolü).
const Z3_TOTAL = 12;

// Özet tablo satırı: "  [PASS] P1-a ..." / "  [FAIL] P4-b ..."
const _SUMMARY_RE = /\[\s*(PASS|FAIL)\s*\]\s*(P[1-5](?:-(?:[a-e]|note))?)\b/;
// Bireysel kontrol satırı: "[P1-a] ... : UNSAT ..." (canlı ilerleme)
const _CTRL_RE = /^\[(P[1-5](?:-(?:[a-e]|note))?)\]/;
// Yeni K8 Z3 koşusu başladığını belirten satır ("SEMBOLİK İSPAT ...")
const _RESET_RE = /SEMBOLİK İSPAT/;

// ── 1) Ayrıştırma: stream satırı → eylem tanımlayıcısı | null ──
// Döndürür:
//   { type: 'reset' }                          — yeni koşu başladı (sayaç sıfırlanır)
//   { type: 'summary', status, id }            — özet tablo satırı (PASS/FAIL)
//   { type: 'control', id }                    — bireysel kontrol satırı (canlı)
//   null                                       — eşleşmeyen satır (yok sayılır)
function parseZ3Line(line) {
  if (_RESET_RE.test(line)) return { type: 'reset' };
  let m = line.match(_SUMMARY_RE);
  if (m) return { type: 'summary', status: m[1], id: m[2] };
  m = line.match(_CTRL_RE);
  if (m) return { type: 'control', id: m[1] };
  return null;
}

// ── 2) Durum hesaplaması (updateZ3Bar saf karşılığı) ──
// seen/passed/failed: sayaç boyutları (Set.size — tam sayı), total: toplam
// kontrol. Döndürür {pct, barClass, cntClass, text}:
//   failed > 0        → 'z3fill err' + 'N FAIL' eki
//   passed == total   → 'z3fill ok' + 'z3count ok'
//   aksi halde        → nötr sınıflar
// total <= 0          → pct 0 (sıfır-bölme koruması; text yine geçerli).
function computeZ3Status(seen, passed, failed, total) {
  const pct = total > 0 ? Math.round(seen / total * 100) : 0;
  let barClass = 'z3fill', cntClass = 'z3count';
  if (failed > 0) barClass = 'z3fill err';
  else if (passed === total) { barClass = 'z3fill ok'; cntClass = 'z3count ok'; }
  const text = passed + '/' + total + (failed > 0 ? ' · ' + failed + ' FAIL' : '');
  return { pct, barClass, cntClass, text };
}

// ── Dışa aktarım (Node/browser uyumlu) ─────────────────────────────────────
if (typeof module !== 'undefined' && module.exports) {
  module.exports = { Z3_TOTAL, parseZ3Line, computeZ3Status };
}
