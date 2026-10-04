#!/usr/bin/env node
// preview_vm_sandbox.js — dashboard testleri için ORTAK node sandbox.
//
// preview.js 3000 satırlık bir dashboard. Node'da yüklemek, yükleme anındaki
// DOM çağrılarını (setTheme, z3-slide listesi, klavye kısayolları) taklit
// etmeyi gerektiriyor — ve o çağrılar hiçbir testin konusu değil.
//
// Elle yazılan stub bu yüzden iki kez öldürdü: her yeni panel eklendiğinde
// kırıldı ve HİÇBİR YERDE koşulmadığı için fark edilmedi. Buradaki stub
// özyinelemeli: okunabilen her özellik, çağrılabilen her yol geçerli bir
// nesne gibi davranır. Test yalnızca gerçekten incelediği elemana (ör.
// tooltip) somut bir stub verir.
//
// KULLANIM:
//   const { loadPreview } = require('./preview_vm_sandbox.js');
//   const { sandbox, setInScript } = loadPreview({ elements: { tip } });
//   setInScript('trendCache', [run]);   // `let` binding — sandbox.trendCache DEĞİL
'use strict';

const fs = require('fs');
const path = require('path');
const vm = require('vm');

const PREVIEW_JS = path.join(__dirname, 'preview.js');

/** Özyinelemeli stub: her yol okunabilir/çağrılabilir, atama saklanır. */
function stub(name) {
  const fn = function () {
    return stub(name + '()');
  };
  return new Proxy(fn, {
    get(target, prop) {
      if (prop === Symbol.toPrimitive || prop === 'toString') {
        return () => name;
      }
      if (prop === Symbol.iterator) return function* () {};
      if (!(prop in target)) target[prop] = stub(name + '.' + String(prop));
      return target[prop];
    },
    set(target, prop, value) {
      target[prop] = value;
      return true;
    },
  });
}

/**
 * preview.js'i permissive bir sandbox'ta yükler.
 *
 * @param {object} [opts]
 * @param {Record<string, any>} [opts.elements] getElementById için somut
 *   elemanlar — testin gerçekten incelediği düğümler.
 * @returns {{sandbox: object, setInScript: (name: string, value: any) => void}}
 */
function loadPreview(opts = {}) {
  const script = fs.readFileSync(PREVIEW_JS, 'utf8');
  if (!script.length) throw new Error('preview.js okunamadı: ' + PREVIEW_JS);

  const elements = opts.elements || {};
  const documentStub = stub('document');
  documentStub.getElementById = (id) =>
    Object.prototype.hasOwnProperty.call(elements, id)
      ? elements[id]
      : stub('el#' + id);

  const sandbox = {
    console,
    Date,
    isFinite,
    encodeURIComponent,
    decodeURIComponent,
    setTimeout,
    setInterval: () => {},
    fetch: () => Promise.resolve({ json: () => Promise.resolve([]) }),
    EventSource: stub('EventSource'),
    navigator: stub('navigator'),
    window: stub('window'),
    document: documentStub,
  };
  sandbox.document.documentElement.dataset = {};
  sandbox.window.innerWidth = 1200;
  sandbox.window.innerHeight = 800;

  vm.createContext(sandbox);
  vm.runInContext(script, sandbox);

  // preview.js `let trendCache` / `let refsTrendCache` / `let BUDGET_LIMIT`
  // ile DEKLARE ediyor; bunlar lexical binding'dir, sandbox NESNESİ üzerinde
  // yaşamaz. `sandbox.trendCache = […]` ayrı bir global property yazar ve
  // script onu hiç okumaz — fonksiyon boş veri görüp sessizce dönüyordu.
  const setInScript = (name, value) =>
    vm.runInContext(`${name} = ${JSON.stringify(value)}`, sandbox);

  return { sandbox, setInScript };
}

module.exports = { stub, loadPreview };
