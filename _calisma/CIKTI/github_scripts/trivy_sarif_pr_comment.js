// trivy_sarif_pr_comment.js — Trivy SARIF → PR-diff yorumu (docker-security PR koşumu).
//
// Kaynak: trivy.sarif (trivy-action format: sarif, scan-type: fs).
// Sözleşme (github_scripts_battery K16 senaryolarıyla sabit):
//   • results: [] (temiz)   → temiz-yorum UPSERT, setFailed YOK
//   • kapı-seviyesi bulgu   → bulgu-tablosu + diff-içi/diff-dışı damgası + setFailed
//   • bozuk SARIF (runs:[]) → setFailed, yanıltıcı yorum YOK (fail-closed)
//   • seviye mesajda yok    → SARIF `level` eşlemesi (warning→MEDIUM, note→LOW;
//                             ölçüldü: trivy 0.74.0, 82 bulgu) → MEDIUM/LOW bloklamaz
//   • seviye-okunamadı      → UNKNOWN etiketi + fail-closed (seviye UYDURULMAZ)
//   • kapı girdileri yok    → setFailed (varsayılan severity YOK)
//
// KAPI GİRDİLERİ TEK KAYNAKTAN GELİR: .github/workflows/docker-security.yml
// `image-scan` job env'i (TRIVY_SEVERITY / TRIVY_IGNORE_UNFIXED) hem Trivy
// tarama adımlarının `severity`/`ignore-unfixed` girdilerine hem de bu
// script'in adımına verilir. Script bu değerleri VARSAYMAZ, okur: bloklayan
// seviye kümesi ve yorum metni aynı girdilerden türer, böylece "eşik neyse
// rapor o" garantisi makineseldir (test_gate_scripts_meta_guard pin'ler).
// Upsert marker: <!-- trivy-sarif-pr-comment --> (pr_status_comment.js deseni).
// Çağrım: github-script adımı gövdeyi fs.readFileSync + eval(async-wrap) ile
// koşar (manifest_comment.js ile aynı desen) — module.exports YOKTUR.
'use strict';

const fs = require('fs');

const MARKER = '<!-- trivy-sarif-pr-comment -->';
const SARIF_PATH = 'trivy.sarif';
const CHANGED_PATH = 'changed_files.txt';

const SEVERITIES = new Set(['CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'UNKNOWN']);

// Kapı girdileri (workflow job env'inden). Eksik/geçersizse null — çağıran
// fail-closed davranır: eşiği bilinmeyen bir taramanın "temiz" ya da "bloklu"
// kararı varsayımla verilemez.
function gateSeverities() {
  const raw = String(process.env.TRIVY_SEVERITY || '').trim();
  const list = raw
    .split(',')
    .map((s) => s.trim().toUpperCase())
    .filter(Boolean);
  if (!list.length) return null;
  if (list.some((s) => !SEVERITIES.has(s))) return null;
  return list;
}

function gateIgnoreUnfixed() {
  const raw = String(process.env.TRIVY_IGNORE_UNFIXED || '')
    .trim()
    .toLowerCase();
  if (raw === 'true') return true;
  if (raw === 'false') return false;
  return null;
}

// SARIF `level` → seviye bandı. Trivy'nin gerçek çıktısı üzerinde ölçüldü
// (trivy 0.74.0 fs-scan, 82 bulgu: 0/82 properties.severity; error↔9 CRITICAL
// + 30 HIGH, warning↔37 MEDIUM, note↔6 LOW). `error` CRITICAL/HIGH'ı
// ayıramaz → eşlenmez, UNKNOWN kalır (fail-closed).
const LEVEL_SEVERITY = { warning: 'MEDIUM', note: 'LOW' };

function severityOf(result) {
  // 1) properties.severity (fixture sözleşmesi; gerçek Trivy taşımıyor)
  // 2) mesajdaki "Severity: MEDIUM" satırı (gerçek Trivy çıktısı)
  // 3) SARIF `level` bandı → warning=MEDIUM, note=LOW
  // Hiçbiri yoksa '' (BİLİNMİYOR) döner. Seviye UYDURULMAZ: buradaki eski
  // 'HIGH' default'u, seviyesi okunamayan her bulguyu (gerçekte MEDIUM/LOW
  // olanlar dahil) rapora "HIGH" yazıyor ve blokluyordu. `level` fallback'i
  // o sınıfı kapatır; yalnız gerçekten bandı okunamayan (error/level-yok)
  // sonuç UNKNOWN olarak fail-closed bloklar.
  const direct = String((result.properties && result.properties.severity) || '')
    .trim()
    .toUpperCase();
  if (SEVERITIES.has(direct)) return direct;
  const text = String((result.message && result.message.text) || '');
  const m = /Severity:\s*([A-Za-z]+)/.exec(text);
  const parsed = m ? m[1].toUpperCase() : '';
  if (SEVERITIES.has(parsed)) return parsed;
  const level = String(result.level || '')
    .trim()
    .toLowerCase();
  return LEVEL_SEVERITY[level] || '';
}

function cell(text) {
  return String(text).slice(0, 120).replace(/\|/g, '\\|').replace(/\n/g, ' ');
}

async function upsertCommentQuiet(body) {
  // Yan fayda adımı: API/ kota arızası gate kararını ETKİLEMEZ (karar
  // yerel SARIF'ten verilir) ama sessizce yutulmaz — uyarı + hata metni.
  try {
    const { data: comments } = await github.rest.issues.listComments({
      owner: context.repo.owner,
      repo: context.repo.repo,
      issue_number: context.issue.number,
      per_page: 100,
    });
    const existing = comments.find((c) => c.body && c.body.includes(MARKER));
    if (existing) {
      await github.rest.issues.updateComment({
        owner: context.repo.owner,
        repo: context.repo.repo,
        comment_id: existing.id,
        body,
      });
    } else {
      await github.rest.issues.createComment({
        owner: context.repo.owner,
        repo: context.repo.repo,
        issue_number: context.issue.number,
        body,
      });
    }
    return null;
  } catch (err) {
    const msg = err && err.message ? err.message : String(err);
    core.warning('Trivy PR yorumu düşülemedi (yan fayda atlandı): ' + msg);
    return msg;
  }
}

try {
  // Kapı girdileri: yoksa yorum da karar da üretilmez (fail-closed).
  const severityList = gateSeverities();
  const ignoreUnfixed = gateIgnoreUnfixed();
  if (!severityList || ignoreUnfixed === null) {
    core.setFailed(
      'Trivy kapı girdileri eksik/geçersiz — TRIVY_SEVERITY=' +
        JSON.stringify(process.env.TRIVY_SEVERITY || '') +
        ' TRIVY_IGNORE_UNFIXED=' +
        JSON.stringify(process.env.TRIVY_IGNORE_UNFIXED || '') +
        ' (docker-security image-scan job env bunları bu adıma geçirmeli);' +
        ' varsayılan eşik YOK — fail-closed'
    );
    return;
  }
  const blockingSeverities = new Set(severityList);
  const sevLabel = severityList.join('/');
  const gateDesc =
    severityList.join(',') + (ignoreUnfixed ? ', ignore-unfixed' : '');

  const raw = fs.readFileSync(SARIF_PATH, 'utf8');
  const sarif = JSON.parse(raw);
  const runs = sarif && Array.isArray(sarif.runs) ? sarif.runs : [];
  if (runs.length !== 1) {
    // Fail-closed: SARIF üretimi bozuldu — bulgu-yokluğu İSPAT edilemez;
    // yanıltıcı "temiz" yorumu düşmeden gate'i kırmızıya çevir.
    core.setFailed(
      'SARIF bozuk (runs: ' + runs.length + ') — tarama kanıtı yok, fail-closed'
    );
    return;
  }

  const changed = new Set();
  try {
    for (const line of fs.readFileSync(CHANGED_PATH, 'utf8').split('\n')) {
      const f = line.trim();
      if (f) changed.add(f);
    }
  } catch {} // changed listesi yoksa tüm bulgular diff-dışı sayılır

  const findings = [];
  for (const result of runs[0].results || []) {
    const uri =
      (((result.locations || [])[0] || {}).physicalLocation || {})
        .artifactLocation || {};
    const file = String(uri.uri || 'bilinmeyen-dosya');
    findings.push({
      severity: severityOf(result),
      rule: String(result.ruleId || '?'),
      message: String((result.message && result.message.text) || ''),
      file,
      inDiff: changed.has(file),
    });
  }
  // Seviyesi okunamayan sonuç fail-closed bloklar: SARIF'te sonuç varsa
  // Trivy kapı filtresinden geçmiş bir bulgu VAR (bulgu-yokluğu ispatlanamaz).
  const blocking = findings.filter(
    (f) => blockingSeverities.has(f.severity) || f.severity === ''
  );
  const inDiff = blocking.filter((f) => f.inDiff);
  const unknown = blocking.filter((f) => f.severity === '');

  let body = MARKER + '\n## 🛡️ Trivy tarama raporu (docker-security)\n\n';
  if (!blocking.length) {
    body +=
      '✅ **' + sevLabel + ' bulgu yok** — Trivy temiz ' +
      '(' + gateDesc + ').\n';
  } else {
    body +=
      '**' +
      blocking.length +
      '** ' + sevLabel + ' bulgu ' +
      '(diff-içi: ' +
      inDiff.length +
      ')\n\n';
    body +=
      '| Seviye | Kural | Bulgu | Dosya | Kapsam |\n' +
      '|--------|-------|-------|-------|--------|\n';
    for (const f of blocking) {
      body +=
        '| ' +
        (f.severity || 'UNKNOWN') +
        ' | `' +
        cell(f.rule) +
        '` | ' +
        cell(f.message) +
        ' | `' +
        cell(f.file) +
        '` | ' +
        (f.inDiff ? 'diff-içi' : 'diff-dışı') +
        ' |\n';
    }
    if (unknown.length) {
      body +=
        '\n`UNKNOWN` = SARIF seviyesi okunamadı → fail-closed olarak bloklar (' +
        unknown.length +
        ' sonuç).\n';
    }
    body +=
      '\nKapı: ' + gateDesc + ' → gate kırmızı. ' +
      'Çözüm: yamalı base-image / pkg yükseltmesi (DOCKER_SECURITY_PATCHING.md).\n';
  }

  // PR yorumu YAN FAYDADIR; kapı kararı yerel SARIF'ten verildi.
  // upsertCommentQuiet: API arızasında (403 kota / ağ) yalnız uyarır ve
  // hata metnini DÖNDÜRÜR — hata gizlenmez, ama tarama sonucunu da
  // maskelemez. Gerçek bulgu varsa setFailed aşağıda, yorumdan BAĞIMSIZ.
  const commentError = await upsertCommentQuiet(body);

  if (blocking.length) {
    core.setFailed(
      'Trivy: ' +
        blocking.length +
        ' ' + sevLabel + ' bulgu ' +
        '(diff-içi: ' +
        inDiff.length +
        ') — gate kırmızı' +
        (unknown.length
          ? ' (seviye-okunamadı: ' + unknown.length + ')'
          : '')
    );
  } else {
    console.log('Trivy temiz — ' + sevLabel + ' bulgu yok');
  }
} catch (err) {
  // Okunamaz/çözümlenemez SARIF = yerel arıza: bulgu-yokluğu
  // İSPAT EDİLEMEZ → fail-closed (yanlış "temiz" yorumu da atılmaz).
  // API/yorum hataları buraya DÜŞMEZ (yukarıda yan-fayda olarak
  // ele alınır) — böylece kota, tarama sonucunu maskelemez.
  core.setFailed(
    'SARIF okunamadı/çözümlenemedi: ' + (err && err.message ? err.message : err)
  );
}
