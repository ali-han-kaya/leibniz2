#!/usr/bin/env node
// github_scripts_selftest.js — github-script self-test runner'ı (K16 katmanı).
//
// Kullanım: node github_scripts_selftest.js <script.js> <fixtureDir>
//
// github-script adımlarını K12/K13 tarzında MOCK girdiyle çalıştırır ve
// çıktı eşleşmesini (hangi REST çağrısı, hangi body, hangi comment_id,
// core.setFailed var/yok) JSON olarak döker — github_scripts_battery.py
// bu kaydı beklenen davranışla karşılaştırır.
//
// fixtureDir'den opsiyonel mock dosyaları okur:
//   mock_context.json   — context nesnesi (issue/repo/runId/payload...)
//   mock_labels.json    — issues.listLabelsOnIssue yanıtı (array)
//   mock_comments.json  — issues.listComments yanıtı (array: [{id, body}])
//
// Stdout'a TEK JSON satırı yazar: {script, ok, error, setFailed, calls,
// console}. Harness hatası yoksa exit 0 — gerçek PASS/FAIL kararını
// battery (Python) verir; script throw ederse ok=false + error dolar.
'use strict';

const fs = require('fs');
const path = require('path');
const vm = require('vm');

const [scriptPath, fixtureDir] = process.argv.slice(2);
if (!scriptPath || !fixtureDir) {
  process.stderr.write('kullanım: node github_scripts_selftest.js <script> <fixtureDir>\n');
  process.exit(2);
}
process.chdir(fixtureDir);

function loadJson(name, fallback) {
  const p = path.join(fixtureDir, name);
  if (!fs.existsSync(p)) return fallback;
  try {
    return JSON.parse(fs.readFileSync(p, 'utf8'));
  } catch (e) {
    process.stderr.write(`mock dosya bozuk (${name}): ${e}\n`);
    process.exit(2);
  }
}

const labels = loadJson('mock_labels.json', []);
const comments = loadJson('mock_comments.json', []);
const ctx = loadJson('mock_context.json', null);

const calls = [];          // her REST çağrısı: {fn, args}
const setFailed = [];      // core.setFailed mesajları
const consoleLines = [];   // yakalanan console çıktısı

const record = (fn) => async (args) => {
  calls.push({ fn, args: args || {} });
  return { data: undefined };
};

const github = {
  rest: {
    issues: {
      listLabelsOnIssue: async (a) => {
        calls.push({ fn: 'issues.listLabelsOnIssue', args: a || {} });
        return { data: labels };
      },
      listComments: async (a) => {
        calls.push({ fn: 'issues.listComments', args: a || {} });
        return { data: comments };
      },
      addLabels: record('issues.addLabels'),
      removeLabel: record('issues.removeLabel'),
      createComment: record('issues.createComment'),
      updateComment: record('issues.updateComment'),
      deleteComment: record('issues.deleteComment'),
    },
  },
};

const core = {
  setFailed: (m) => setFailed.push(String(m)),
  info: () => {},
  warning: () => {},
  error: () => {},
  notice: () => {},
};

const context = Object.assign(
  {
    issue: { number: 1 },
    repo: { owner: 'mock-owner', repo: 'mock-repo' },
    runId: 42,
    payload: {
      repository: { html_url: 'https://github.com/mock-owner/mock-repo' },
    },
  },
  ctx || {},
);

const scriptBody = fs.readFileSync(scriptPath, 'utf8');
const wrapped = `(async () => {\n${scriptBody}\n})();`;

const sandbox = {
  require: (m) => require(m),
  console: {
    log: (...a) => consoleLines.push(a.map(String).join(' ')),
    error: (...a) => consoleLines.push('ERR ' + a.map(String).join(' ')),
    warn: (...a) => consoleLines.push('WARN ' + a.map(String).join(' ')),
  },
  github,
  core,
  context,
  process,
  Buffer,
  setTimeout,
  clearTimeout,
};
vm.createContext(sandbox);

const base = {
  script: path.basename(scriptPath),
  ok: true,
  error: null,
  setFailed,
  calls,
  console: consoleLines,
};

let settled = false;
function finish(res) {
  if (settled) return;
  settled = true;
  clearTimeout(timer);
  process.stdout.write(JSON.stringify(res));
}
const timer = setTimeout(() => {
  finish(Object.assign({}, base, { ok: false, error: 'timeout 15s' }));
}, 15000);

try {
  vm.runInContext(wrapped, sandbox, { filename: path.basename(scriptPath) })
    .then(() => finish(base))
    .catch((e) => finish(Object.assign({}, base, {
      ok: false,
      error: String((e && e.stack) || e),
    })));
} catch (e) {
  // Senkron hata (ör. söz dizimi) — promise üretilemeden patladı.
  finish(Object.assign({}, base, { ok: false, error: String((e && e.stack) || e) }));
}
