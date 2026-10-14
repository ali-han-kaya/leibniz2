#!/usr/bin/env node
// test_preview_interaction_dom.js — preview.js etkileşim katmanı (tarayıcısız).
//
// Üç kullanıcı akışı, Node vm sandbox'ta GERÇEK preview.js çalıştırılarak:
//   1. trend hover hedefi → tooltip: inline onmousemove/onmouseleave wire'ı
//      sandbox'ta fiilen koşturulur (string aramak yetmez), tooltip görünürlüğü
//      + verdict/bütçe renk sınıfı + konum okunur;
//   2. run-history filtresi (all/PASS/FAIL/P0): aktif buton, sayaç metni ve
//      listelenen satır sayısı /api/run-history stub'ıyla doğrulanır;
//   3. Z3 lightbox: aç/kapat, ←/→ (fare ve klavye), Escape ve Tab odak tuzağı
//      (WCAG 2.4.3).
//
// Neden bu katman: swap-baskısı altında ağır tek-süreç tarayıcı koşumu yerine
// her ortamda koşan (node yeter, tarayıcı gerekmez) statik taban. Gerçek
// hover/click koşumu ayrı katmandadır: test_preview_interaction_cdp.py —
// o katman tarayıcı yoksa SKIP eder; BU katman ETMEZ (fail-closed statik taban:
// tarayıcısız ortamda da kırmızıya dönebilir).
//
// Kullanım: node test_preview_interaction_dom.js
'use strict';

const assert = require('assert');
const vm = require('vm');
const { loadPreview, makeElementStub } = require('./preview_vm_sandbox.js');

const tick = () => new Promise((r) => setImmediate(r));
const flush = async () => {
  for (let i = 0; i < 6; i++) await tick();
};

const TREND_ROWS = [
  {
    ts: '2026-10-08T10:00:00Z',
    p0: 0,
    p1: 0,
    duration_s: 9,
    budget_usd: 1.5,
    lean_ok: true,
    z3_passed: 12,
    z3_total: 12,
  },
  {
    ts: '2026-10-08T10:05:00Z',
    p0: 2,
    p1: 1,
    duration_s: 12,
    budget_usd: 31,
    lean_ok: false,
    z3_passed: 10,
    z3_total: 12,
  },
  {
    ts: '2026-10-08T10:10:00Z',
    p0: 0,
    p1: 3,
    duration_s: 30,
    budget_usd: 2,
    lean_ok: null,
    z3_passed: 12,
    z3_total: 12,
  },
];

const HISTORY_ROWS = [
  {
    ts: '2026-10-08T10:00:00Z',
    verdict: 'PASS',
    p0: 0,
    p1: 0,
    duration_s: 9,
    budget_usd: 1.5,
    refs_verified: 20,
    refs_total: 20,
    pdf_pages: 12,
    lean_ok: true,
  },
  {
    ts: '2026-10-08T10:05:00Z',
    verdict: 'FAIL',
    p0: 2,
    p1: 1,
    duration_s: 12,
    budget_usd: 31,
    refs_verified: 18,
    refs_total: 20,
    pdf_pages: 12,
    lean_ok: false,
  },
  {
    ts: '2026-10-08T10:10:00Z',
    verdict: 'ERROR',
    p0: 0,
    p1: 0,
    duration_s: 3,
    budget_usd: 0.5,
    refs_verified: 0,
    refs_total: 0,
    pdf_pages: 0,
    lean_ok: null,
  },
  {
    ts: '2026-10-08T10:15:00Z',
    verdict: 'PASS',
    p0: 0,
    p1: 3,
    duration_s: 20,
    budget_usd: 40,
    refs_verified: 20,
    refs_total: 20,
    pdf_pages: 11,
    lean_ok: true,
  },
  {
    ts: '2026-10-08T10:20:00Z',
    verdict: 'PASS',
    p0: 0,
    p1: 0,
    duration_s: 8,
    budget_usd: 2,
    refs_verified: 20,
    refs_total: 20,
    pdf_pages: 12,
    lean_ok: true,
  },
];

const jsonOnce = (payload) => () =>
  Promise.resolve({ json: () => Promise.resolve(payload) });
const urlFetch = (prefix, payload) => (url) =>
  Promise.resolve({
    json: () => Promise.resolve(url.indexOf(prefix) === 0 ? payload : []),
  });

// ── 1) trend hover → tooltip ────────────────────────────────────────────────
async function trendHoverFlow() {
  const trend = makeElementStub();
  const tip = makeElementStub({
    style: { display: 'none', left: '', top: '' },
  });
  const sandbox = loadPreview({
    elements: {
      trend: trend,
      tip: tip,
      'trend-legend': makeElementStub(),
      'trend-count': makeElementStub(),
    },
    fetch: urlFetch('/api/trend', { history: TREND_ROWS }),
  });
  await flush();

  // Kablolama sözleşmesi: inline handler YOK (CSP script-src 'self' + nonce
  // inline event handler'ları bloklar) — hedefler data-tip-i taşır ve
  // listener SVG üzerinde DELEGE edilir.
  const hits = trend.innerHTML.match(/data-tip-i="(\d+)"/g) || [];
  assert.strictEqual(
    hits.length,
    TREND_ROWS.length,
    "her trend run'ı için bir hover hedefi olmalı (beklenen " +
      TREND_ROWS.length +
      ', bulunan ' +
      hits.length +
      ')'
  );
  assert.ok(
    trend.innerHTML.indexOf('onmousemove=') < 0 &&
      trend.innerHTML.indexOf('onmouseleave=') < 0,
    'hover hedefleri inline handler taşımamalı (CSP bloklar)'
  );
  assert.strictEqual(
    (trend.__listeners.mousemove || []).length,
    1,
    "mousemove listener'ı SVG'ye tam bir kez bağlanmalı (yeniden render çiftlemez)"
  );
  assert.strictEqual(
    (trend.__listeners.mouseleave || []).length,
    1,
    "mouseleave listener'ı SVG'ye tam bir kez bağlanmalı"
  );

  // Delegasyonu fiilen koştur: hedef sütun + sahte olay.
  const hoverAt = (i) =>
    trend.dispatch('mousemove', {
      target: makeElementStub({
        getAttribute: (k) => (k === 'data-tip-i' ? String(i) : null),
      }),
      clientX: 40,
      clientY: 40,
    });

  hoverAt(0);
  assert.strictEqual(
    tip.style.display,
    'block',
    'hover tooltip görünür olmalı'
  );
  assert.ok(
    tip.innerHTML.indexOf('verdict : PASS') >= 0,
    "0. run hover'ında verdict PASS olmalı"
  );
  assert.strictEqual(
    tip.style.left,
    '54px',
    'tooltip hover noktasına konumlanmalı (x)'
  );
  assert.strictEqual(
    tip.style.top,
    '54px',
    'tooltip hover noktasına konumlanmalı (y)'
  );

  hoverAt(1);
  assert.ok(
    tip.innerHTML.indexOf('verdict : FAIL (P0)') >= 0,
    "1. run hover'ında P0 verdict'i olmalı"
  );
  assert.ok(
    tip.innerHTML.indexOf('tt-over') >= 0,
    'limit üstü bütçe satırı tt-over sınıfını almalı'
  );

  // Grafiğin dışına çıkma (SVG mouseleave) tooltip'i kapatır.
  trend.dispatch('mouseleave');
  assert.strictEqual(
    tip.style.display,
    'none',
    "grafikten çıkış tooltip'i gizlemeli"
  );
}

// ── 2) run-history filtresi ────────────────────────────────────────────────
async function filterHarness(rows) {
  const list = makeElementStub();
  const count = makeElementStub();
  const buttons = ['all', 'PASS', 'FAIL', 'P0'].map((f) =>
    makeElementStub({ dataset: { f: f } })
  );
  const fetched = [];
  const sandbox = loadPreview({
    elements: { 'run-history': list, 'run-history-count': count },
    selectors: { '.rh-filter button': buttons },
    fetch: (url) => {
      fetched.push(url);
      return urlFetch('/api/run-history', rows)(url);
    },
  });
  await flush(); // açılıştaki setRhFilter("all") çözülsün
  return { sandbox, list, count, buttons, fetched };
}

const rowStub = (ts) =>
  makeElementStub({ getAttribute: (k) => (k === 'data-ts' ? ts : null) });

const activeFilters = (buttons) =>
  buttons.filter((b) => b.classList.contains('active')).map((b) => b.dataset.f);
const rowCount = (list) =>
  (list.innerHTML.match(/class="rh-row"/g) || []).length;

async function filterFlow() {
  const h = await filterHarness(HISTORY_ROWS);
  assert.strictEqual(h.count.textContent, '(5)', 'all filtresi 5 run saymalı');
  assert.deepStrictEqual(
    activeFilters(h.buttons),
    ['all'],
    'açılışta all aktif'
  );
  assert.strictEqual(rowCount(h.list), 5, 'all filtresi 5 satır listelemeli');
  // Buton kablolaması: CSP inline onclick'i blokladığı için filtreler
  // addEventListener ile bağlanmalı — her butonda tam bir click listener.
  h.buttons.forEach((b) =>
    assert.strictEqual(
      (b.__listeners.click || []).length,
      1,
      `filtre butonu (${b.dataset.f}) addEventListener ile bağlanmalı`
    )
  );

  // Filtreler KULLANICI yolundan (buton tıklaması) sürülür — doğrudan
  // setRhFilter çağrısı kablolamayı atlardı ve mutasyon dişi olmazdı.
  const byName = (name) => h.buttons.find((b) => b.dataset.f === name);

  byName('PASS').dispatch('click');
  await flush();
  assert.strictEqual(
    h.count.textContent,
    '(3 / 5)',
    'PASS filtresi 3/5 saymalı'
  );
  assert.deepStrictEqual(
    activeFilters(h.buttons),
    ['PASS'],
    'aktif buton PASS olmalı'
  );
  assert.strictEqual(rowCount(h.list), 3, 'PASS filtresi 3 satır listelemeli');

  byName('FAIL').dispatch('click');
  await flush();
  assert.strictEqual(
    h.count.textContent,
    '(2 / 5)',
    'FAIL filtresi 2/5 saymalı'
  );
  assert.ok(
    h.list.innerHTML.indexOf('>ERROR<') >= 0,
    "FAIL filtresi ERROR verdict'ini de kapsamalı"
  );

  byName('P0').dispatch('click');
  await flush();
  assert.strictEqual(h.count.textContent, '(1 / 5)', 'P0 filtresi 1/5 saymalı');
  assert.ok(
    h.list.innerHTML.indexOf('>ERROR<') < 0,
    "P0 filtresi P0'sız ERROR satırını dışlamalı"
  );

  // Satır tıklaması da inline onclick değil delege ile bağlanmalı: bir satıra
  // tıklamak /api/run-stdout isteği tetikler.
  h.list.dispatch('click', {
    target: makeElementStub({
      closest: (sel) =>
        sel === '.rh-row' ? rowStub('2026-10-08T10:05:00Z') : null,
    }),
  });
  assert.strictEqual(
    h.fetched.filter((u) => u.indexOf('/api/run-stdout?ts=') === 0).length,
    1,
    'satır tıklaması tek bir /api/run-stdout isteği açmalı'
  );
  assert.ok(
    h.list.innerHTML.indexOf('onclick=') < 0,
    'run satırları inline onclick taşımamalı (CSP bloklar)'
  );

  // boş sonuç dalı ayrı mesaj basmalı (sayaç yine doğru)
  const empty = await filterHarness([HISTORY_ROWS[0]]);
  empty.buttons.find((b) => b.dataset.f === 'P0').dispatch('click');
  await flush();
  assert.strictEqual(
    empty.count.textContent,
    '(0 / 1)',
    'eşleşme yokken sayaç 0/1'
  );
  assert.ok(
    empty.list.innerHTML.indexOf('filtreyle eşleşen run yok') >= 0,
    'eşleşme yokken boş-dal mesajı gösterilmeli'
  );
}

// ── 3) Z3 lightbox ─────────────────────────────────────────────────────────
function lightboxHarness() {
  const slides = [0, 1, 2, 3].map(() => makeElementStub());
  const box = makeElementStub({ hidden: true });
  const image = makeElementStub({ src: '', alt: '' });
  const closeButton = makeElementStub();
  const prev = makeElementStub();
  const next = makeElementStub();
  const root = makeElementStub({ querySelector: () => null });
  const sandbox = loadPreview({
    elements: {
      'z3-slides': root,
      'z3-lightbox': box,
      'z3-lightbox-image': image,
      'z3-close': closeButton,
      'z3-prev': prev,
      'z3-next': next,
    },
    selectors: { '#z3-slide-gallery .z3-slide': slides },
  });
  return { sandbox, slides, box, image, closeButton, prev, next };
}

function lightboxFlow() {
  const h = lightboxHarness();
  assert.strictEqual(h.box.hidden, true, 'lightbox açılışta kapalı olmalı');

  // Kapalıyken klavye kısayolları etkisiz olmalı (guard).
  h.sandbox.__dispatchDocument('keydown', { key: 'ArrowRight' });
  assert.strictEqual(
    h.image.src,
    '',
    'kapalı lightbox ok tuşuna tepki vermemeli'
  );

  h.slides[1].dispatch('click');
  assert.strictEqual(h.box.hidden, false, "slayt tıklaması lightbox'ı açmalı");
  assert.strictEqual(
    h.image.src,
    '/slides_z3/P1-b.png',
    'açılan slayt doğru dosya olmalı'
  );
  assert.strictEqual(
    h.image.alt,
    'P1-b Z3 slaytı',
    'alt metni slayt adını taşımalı'
  );
  assert.strictEqual(
    h.sandbox.document.activeElement,
    h.closeButton,
    'açılışta odak kapat butonuna gitmeli (WCAG 2.4.3)'
  );

  h.next.dispatch('click');
  assert.strictEqual(
    h.image.src,
    '/slides_z3/P2.png',
    '→ sonraki slayta geçmeli'
  );
  h.prev.dispatch('click');
  assert.strictEqual(
    h.image.src,
    '/slides_z3/P1-b.png',
    '← önceki slayta dönmeli'
  );

  h.sandbox.__dispatchDocument('keydown', { key: 'ArrowRight' });
  assert.strictEqual(
    h.image.src,
    '/slides_z3/P2.png',
    'ArrowRight klavyeyle ilerletmeli'
  );
  h.sandbox.__dispatchDocument('keydown', { key: 'ArrowLeft' });
  assert.strictEqual(
    h.image.src,
    '/slides_z3/P1-b.png',
    'ArrowLeft klavyeyle geri almalı'
  );

  // Tab odak tuzağı: son öğeden sonra başa, ilk öğeden Shift+Tab ile sona.
  h.sandbox.document.activeElement = h.closeButton;
  h.box.dispatch('keydown', {
    key: 'Tab',
    shiftKey: false,
    preventDefault() {},
  });
  assert.strictEqual(
    h.sandbox.document.activeElement,
    h.prev,
    'Tab son öğeden ilk öğeye dönmeli'
  );
  h.sandbox.document.activeElement = h.next;
  h.box.dispatch('keydown', {
    key: 'Tab',
    shiftKey: false,
    preventDefault() {},
  });
  assert.strictEqual(
    h.sandbox.document.activeElement,
    h.next,
    'ortadaki öğe odakta serbest kalmalı'
  );
  h.sandbox.document.activeElement = h.prev;
  h.box.dispatch('keydown', {
    key: 'Tab',
    shiftKey: true,
    preventDefault() {},
  });
  assert.strictEqual(
    h.sandbox.document.activeElement,
    h.closeButton,
    'Shift+Tab ilk öğeden son öğeye atlamalı'
  );

  // Escape: kapatır + odağı açan slayda döndürür.
  h.sandbox.__dispatchDocument('keydown', { key: 'Escape' });
  assert.strictEqual(h.box.hidden, true, "Escape lightbox'ı kapatmalı");
  assert.strictEqual(
    h.sandbox.document.activeElement,
    h.slides[1],
    'kapanışta odak açan slayda dönmeli (WCAG 2.4.3)'
  );

  // Kapat butonu da aynı sözleşmeyi taşımalı.
  h.slides[3].dispatch('click');
  h.closeButton.dispatch('click');
  assert.strictEqual(h.box.hidden, true, "kapat butonu lightbox'ı kapatmalı");
  assert.strictEqual(
    h.sandbox.document.activeElement,
    h.slides[3],
    'odak açan slayda dönmeli'
  );
}

(async () => {
  await trendHoverFlow();
  await filterFlow();
  lightboxFlow();
  console.log(
    'preview interaction DOM: PASS — hover tooltip wire + run-history ' +
      'filtreleri (all/PASS/FAIL/P0 + boş dal) + lightbox (aç/←→/Escape/Tab tuzağı)'
  );
})().catch((err) => {
  console.error(
    'preview interaction DOM: FAIL — ' +
      (err && err.message ? err.message : err)
  );
  process.exit(1);
});
