// preview_vm_sandbox.js — preview.js'i Node vm sandbox'ında yükleyen ortak yardımcı.
//
// Dashboard script'i inline'dan preview.js'e taşındı (IIFE + üst-seviye
// state). Node testleri bu yardımcıyla TAM preview.js'i çalıştırır: üst-seviye
// state'ler `let` (lexical) olduğundan testler state'e yalnız sandbox İÇİNDE
// koşan vm-koduyla yazabilir (sandbox.X = ataması etki etmez).
//
// Kullanım:
//   const { loadPreview, makeElementStub } = require('./preview_vm_sandbox.js');
//   const sandbox = loadPreview({ tipElement: myTip });
//   sandbox.showTrendTip(0, { clientX: 10, clientY: 10 });
//
// Etkileşim testleri (hover/filtre/lightbox) için üç opsiyonel genişletme:
//   elements   : { "id": stub } — getElementById bu map'i kullanır (kalan
//                id'ler için tembel stub üretilir). Stub'lar focus() çağrısını
//                document.activeElement'e yazar; bu yüzden odak
//                doğrulamaları (WCAG 2.4.3) sandbox içinde okunabilir.
//   selectors  : { ".rh-filter button": [stub, ...] } — querySelectorAll map'i.
//   fetch      : (url) => Promise — URL'e göre veri dönen stub (varsayılan: []).
// Stub'lar ayrıca `dispatch(type, ev)` ile kayıtlı listener'ları senkron
// tetikler; document listener'ları `sandbox.__dispatchDocument(type, ev)`.
'use strict';

const fs = require('fs');
const path = require('path');
const vm = require('vm');

// Canvas 2D bağlamı: DOM'da <canvas> varsa getContext("2d") çalışır ve
// çizim metotları no-op'tur. renderBudgetSparkline() gibi çizim kodunun
// sandbox'ta yarıda patlamasını önler (patlarsa tooltip/hover üretimi de
// düşer, çünkü aynı render zincirindedir).
function makeCanvasContextStub() {
  const noop = () => {};
  return {
    canvas: null,
    clearRect: noop,
    fillRect: noop,
    strokeRect: noop,
    beginPath: noop,
    closePath: noop,
    moveTo: noop,
    lineTo: noop,
    arc: noop,
    rect: noop,
    fill: noop,
    stroke: noop,
    save: noop,
    restore: noop,
    scale: noop,
    translate: noop,
    setLineDash: noop,
    fillText: noop,
    strokeText: noop,
    measureText: () => ({ width: 0 }),
    createLinearGradient: () => ({ addColorStop: noop }),
  };
}

function makeElementStub(overrides, docRef) {
  const listeners = Object.create(null);
  const classes = new Set();
  const el = {
    addEventListener: (type, fn) => {
      (listeners[type] || (listeners[type] = [])).push(fn);
    },
    removeEventListener: (type, fn) => {
      if (listeners[type])
        listeners[type] = listeners[type].filter((f) => f !== fn);
    },
    // Test yardımcıları (production kodunda karşılığı yok):
    dispatch: (type, ev) => {
      (listeners[type] || []).slice().forEach((fn) => fn(ev || {}));
    },
    __listeners: listeners,
    classList: {
      toggle(name, force) {
        const on = force === undefined ? !classes.has(name) : !!force;
        if (on) classes.add(name);
        else classes.delete(name);
        return on;
      },
      add: (name) => classes.add(name),
      remove: (name) => classes.delete(name),
      contains: (name) => classes.has(name),
    },
    style: {},
    dataset: {},
    setAttribute: () => {},
    getAttribute: () => null,
    focus() {
      if (docRef) docRef.activeElement = el;
    },
    appendChild: () => {},
    querySelector: () => null,
    querySelectorAll: () => [],
    // <canvas> yüzeyi: genişlik/yükseklik sayı olmalı (çizim kodu üzerlerinde
    // aritmetik yapar) + getContext("2d") no-op bağlam döner.
    getContext: () => makeCanvasContextStub(),
    width: 300,
    height: 150,
    textContent: '',
    innerHTML: '',
    hidden: false,
    offsetWidth: 100,
    offsetHeight: 50,
    // Görünürlük filtresi (lightbox odak tuzağı `offsetParent !== null`
    // arar): varsayılan görünür.
    offsetParent: {},
  };
  return Object.assign(el, overrides || {});
}

/**
 * preview.js'i tam dosya olarak vm sandbox'ında çalıştırır ve sandbox'ı döner.
 * options.tipElement: getElementById('tip') çağrısına dönen element
 * (innerHTML/style test tarafından okunur).
 * options.elements / options.selectors / options.fetch: yukarıdaki başlık.
 */
function loadPreview(options) {
  const opts = options || {};
  const src = fs.readFileSync(path.join(__dirname, 'preview.js'), 'utf8');
  const elements = Object.assign({}, opts.elements || {});
  const selectors = Object.assign({}, opts.selectors || {});
  const docListeners = Object.create(null);

  const documentStub = {
    getElementById: (id) => {
      if (!elements[id]) {
        elements[id] =
          id === 'tip' && opts.tipElement
            ? opts.tipElement
            : makeElementStub({}, documentStub);
      }
      return elements[id];
    },
    querySelectorAll: (sel) => selectors[sel] || [],
    querySelector: (sel) => (selectors[sel] && selectors[sel][0]) || null,
    addEventListener: (type, fn) => {
      (docListeners[type] || (docListeners[type] = [])).push(fn);
    },
    removeEventListener: () => {},
    body: makeElementStub(),
    documentElement: makeElementStub(),
    activeElement: null,
  };
  // Odak kitabı: dışarıdan verilen stub'lar dokümandan önce yaratıldığı için
  // focus() burada bağlanır (aksi halde document.activeElement hiç yazılmaz).
  // elements map'i kadar selectors listeleri de bağlanır: lightbox odak
  // dönüşü (WCAG 2.4.3) açan slayt düğmesini — yani selectors içindeki bir
  // stub'ı — focus'lar.
  const wireFocus = (el) => {
    if (el && typeof el === 'object') {
      el.focus = () => {
        documentStub.activeElement = el;
      };
    }
    return el;
  };
  Object.keys(elements).forEach((id) => wireFocus(elements[id]));
  Object.keys(selectors).forEach((sel) => {
    const value = selectors[sel];
    if (Array.isArray(value)) value.forEach(wireFocus);
    else wireFocus(value);
  });

  const sandbox = {
    console,
    Date,
    isFinite,
    encodeURIComponent,
    decodeURIComponent,
    setTimeout,
    setInterval: () => {},
    clearInterval: () => {},
    clearTimeout: () => {},
    fetch:
      opts.fetch ||
      (() => Promise.resolve({ json: () => Promise.resolve([]), ok: true })),
    EventSource: function () {
      this.addEventListener = () => {};
      this.close = () => {};
    },
    matchMedia: () => ({
      matches: false,
      addEventListener() {},
      addListener() {},
    }),
    alert: () => {},
    navigator: {},
    window: {
      innerWidth: 1200,
      innerHeight: 800,
      addEventListener: () => {},
      matchMedia: () => ({
        matches: false,
        addEventListener() {},
        addListener() {},
      }),
    },
    document: documentStub,
    localStorage: {
      getItem: () => null,
      setItem: () => {},
      removeItem: () => {},
    },
    history: { pushState: () => {}, replaceState: () => {} },
    location: { hash: '', search: '', pathname: '/preview.html' },
  };
  sandbox.__elements = elements;
  sandbox.__dispatchDocument = (type, ev) => {
    (docListeners[type] || []).slice().forEach((fn) => fn(ev || {}));
  };
  sandbox.window.document = sandbox.document;
  sandbox.globalThis = sandbox;
  vm.createContext(sandbox);
  vm.runInContext('"use strict";\n' + src, sandbox, { filename: 'preview.js' });
  return sandbox;
}

module.exports = { loadPreview, makeElementStub, makeCanvasContextStub };
