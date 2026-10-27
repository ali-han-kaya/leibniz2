// trivy_sarif_pr_comment.js — Trivy SARIF → PR-diff yorumu (docker-security PR koşumu).
//
// Kaynak: trivy.sarif (trivy-action format: sarif, scan-type: fs).
// Sözleşme (github_scripts_battery K16 senaryolarıyla sabit):
//   • results: [] (temiz)   → temiz-yorum UPSERT, setFailed YOK
//   • kapı setinde bulgu    → bulgu-tablosu + diff-içi/diff-dışı damgası + setFailed
//   • bozuk SARIF (runs:[]) → setFailed, yanıltıcı yorum YOK (fail-closed)
//   • seviye-yok            → açık "bilinmiyor" işareti + fail-closed setFailed
//     (SESSIZ HIGH YOK: kapı eşiği artık girdiden gelir, uydurma HIGH değil)
// Kapı girdileri docker-security.yml'nin workflow-env'inden gelir:
//   TRIVY_GATE_SEVERITY        → zorlayıcı tabela/SARIF adımının `severity` girdisi
//   TRIVY_GATE_IGNORE_UNFIXED  → aynı adımın `ignore-unfixed` girdisi
// Varsayılanlar workflow'daki değerlerle birebir (harness/lokal koşum);
// workflow bunları değiştirirse yorum da eşlik eder — iki ayrı eşik KAYMAZ.
// Upsert marker: <!-- trivy-sarif-pr-comment --> (pr_status_comment.js deseni).
// Çağrım: github-script adımı gövdeyi fs.readFileSync + eval(async-wrap) ile
// koşar (manifest_comment.js ile aynı desen) — module.exports YOKTUR.
'use strict';

const fs = require('fs');

const MARKER = '<!-- trivy-sarif-pr-comment -->';
const SARIF_PATH = 'trivy.sarif';
const CHANGED_PATH = 'changed_files.txt';
const SEVERITIES = new Set(['CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'UNKNOWN']);
// Seviye okunamadığının işareti (kaynakta 'UNKNOWN', yorumda 'bilinmiyor').
const UNKNOWN = 'UNKNOWN';

// Kapı eşiği — zorlayıcı adımla AYNI girdi (docker-security.yml env).
// Tek kaynak oradadır; buradaki varsayılan yalnız harness/lojal koşum içindir
// ve workflow env'iyle birebir tutulur (sözleşme testi pin'ler).
const GATE_SEVERITY = String(
  (process.env && process.env.TRIVY_GATE_SEVERITY) || 'CRITICAL,HIGH'
)
  .split(',')
  .map((s) => s.trim().toUpperCase())
  .filter(Boolean);
const GATE_IGNORE_UNFIXED = /^(1|true|yes)$/i.test(
  String(
    process.env && process.env.TRIVY_GATE_IGNORE_UNFIXED !== undefined
      ? process.env.TRIVY_GATE_IGNORE_UNFIXED
      : 'true'
  )
);
const GATE_LABEL = GATE_SEVERITY.join('/');
const UNFIXED_LABEL = GATE_IGNORE_UNFIXED ? ', ignore-unfixed' : '';

function severityOf(result) {
  // Önce properties.severity (fixture/test sözleşmesi); yoksa mesajdaki
  // "Severity: MEDIUM" (GERÇEK Trivy SARIF'i — canlı PR koşumunda ölçüldü:
  // properties.severity taşınmıyor, tüm sonuçlar HIGH sanılıyordu).
  // İkisi de yoksa seviye BİLİNMEYEN ('UNKNOWN' → yorumda 'bilinmiyor').
  // Eski davranış sessiz 'HIGH' döndürüyordu: kapı seti TRIVY_GATE_SEVERITY'den
  // geldiği için bu ya sahte-blokaj ya da sahte-geçiş üretirdi (kapı CRITICAL
  // iken HIGH bulgusu 'HIGH' diye bloklanır, kapı HIGH'ya daralınca da
  // seviyesiz sonuç sessizce HIGH sanılırdı). Artık uydurma yok: eksik seviye
  // açıkça 'bilinmiyor' diye etiketlenir ve fail-closed kapıya girer.
  const direct = String((result.properties && result.properties.severity) || '')
    .trim()
    .toUpperCase();
  if (SEVERITIES.has(direct)) return direct;
  const text = String((result.message && result.message.text) || '');
  const m = /Severity:\s*([A-Za-z]+)/.exec(text);
  const parsed = m ? m[1].toUpperCase() : '';
  if (SEVERITIES.has(parsed)) return parsed;
  return UNKNOWN;
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
  // Bloklama eşiği kapı setinden: set üyesi YA DA seviye bilinmiyor
  // (fail-closed — eksik veri "geçti" anlamına gelemez), ama asla
  // uydurulan 'HIGH' üzerinden değil; bilinmiyor ayrı işaretlenir.
  const blocking = findings.filter(
    (f) => f.severity === UNKNOWN || GATE_SEVERITY.includes(f.severity)
  );
  const unknown = blocking.filter((f) => f.severity === UNKNOWN);
  const inDiff = blocking.filter((f) => f.inDiff);

  let body = MARKER + '\n## 🛡️ Trivy tarama raporu (docker-security)\n\n';
  if (!blocking.length) {
    body +=
      '✅ **' +
      GATE_LABEL +
      ' bulgu yok** — Trivy temiz ' +
      '(' +
      GATE_LABEL +
      UNFIXED_LABEL +
      ').\n';
  } else {
    body +=
      '**' +
      blocking.length +
      '** ' +
      GATE_LABEL +
      ' bulgu ' +
      '(diff-içi: ' +
      inDiff.length +
      ')\n\n';
    if (unknown.length) {
      body +=
        '> ⚠️ **' +
        unknown.length +
        ' bulgu için seviye okunamadı** — `bilinmiyor` olarak işaretlendi ve ' +
        'fail-closed kapıya dahil edildi (HIGH varsayılmıyor). ' +
        'SARIF girdisine bakın: ' +
        '`severity=' +
        GATE_LABEL +
        '` (zorlayıcı adımla aynı).\n\n';
    }
    body +=
      '| Seviye | Kural | Bulgu | Dosya | Kapsam |\n' +
      '|--------|-------|-------|-------|--------|\n';
    for (const f of blocking) {
      body +=
        '| ' +
        (f.severity === UNKNOWN ? 'bilinmiyor' : f.severity) +
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
    body +=
      '\nKapı: ' +
      GATE_LABEL +
      (GATE_IGNORE_UNFIXED ? ' (ignore-unfixed)' : '') +
      ' → gate kırmızı. ' +
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
        ' ' +
        GATE_LABEL +
        ' bulgu ' +
        '(diff-içi: ' +
        inDiff.length +
        ')' +
        (unknown.length
          ? ' — seviye bilinmeyen: ' +
            unknown.length +
            ' (fail-closed, HIGH varsayılmadı)'
          : '') +
        ' — gate kırmızı'
    );
  } else {
    console.log('Trivy temiz — ' + GATE_LABEL + ' bulgu yok');
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
