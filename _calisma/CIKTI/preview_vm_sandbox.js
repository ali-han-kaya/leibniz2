// preview_vm_sandbox.js — preview.js'i Node vm sandbox'ında yükleyen ortak yardımcı.
//
// Dashboard script'i inline'dan preview.js'e taşındı (IIFE + üst-seviye
// state). Üç Node testi (test_refs_trend_badge_node, test_budget_over_detail,
// test_trend_tooltip_dom) bu yardımcıyla TAM preview.js'i çalıştırır:
// üst-seviye state'ler `let` (lexical) olduğundan testler state'e yalnız
// sandbox İÇİNDE koşan vm-koduyla yazabilir (sandbox.X = ataması etki etmez).
//
// Kullanım:
//   const { loadPreview } = require('./preview_vm_sandbox.js');
//   const sandbox = loadPreview({ tipElement: myTip });
//   sandbox.showTrendTip(0, { clientX: 10, clientY: 10 });
"use strict";

const fs = require("fs");
const path = require("path");
const vm = require("vm");

function makeElementStub(overrides) {
  const el = Object.assign(
    {
      addEventListener: () => {},
      removeEventListener: () => {},
      classList: { toggle() {}, add() {}, remove() {}, contains: () => false },
      style: {},
      dataset: {},
      setAttribute: () => {},
      getAttribute: () => null,
      focus: () => {},
      appendChild: () => {},
      querySelector: () => null,
      querySelectorAll: () => [],
      textContent: "",
      innerHTML: "",
      hidden: false,
      offsetWidth: 100,
      offsetHeight: 50,
    },
    overrides || {}
  );
  return el;
}

/**
 * preview.js'i tam dosya olarak vm sandbox'ında çalıştırır ve sandbox'ı döner.
 * options.tipElement: getElementById('tip') çağrısına dönen element
 * (innerHTML/style test tarafından okunur).
 */
function loadPreview(options) {
  const opts = options || {};
  const src = fs.readFileSync(path.join(__dirname, "preview.js"), "utf8");
  const tip = opts.tipElement || makeElementStub();
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
    fetch: () => Promise.resolve({ json: () => Promise.resolve([]), ok: true }),
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
    document: {
      getElementById: (id) => (id === "tip" ? tip : makeElementStub()),
      querySelectorAll: () => [],
      querySelector: () => null,
      addEventListener: () => {},
      body: makeElementStub(),
      documentElement: makeElementStub(),
      activeElement: null,
    },
    localStorage: {
      getItem: () => null,
      setItem: () => {},
      removeItem: () => {},
    },
    history: { pushState: () => {}, replaceState: () => {} },
    location: { hash: "", search: "", pathname: "/preview.html" },
  };
  sandbox.window.document = sandbox.document;
  sandbox.globalThis = sandbox;
  vm.createContext(sandbox);
  vm.runInContext('"use strict";\n' + src, sandbox, { filename: "preview.js" });
  return sandbox;
}

module.exports = { loadPreview, makeElementStub };
