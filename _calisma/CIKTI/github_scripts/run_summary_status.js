// run_summary_status.js — push-safe run-summary varyantı (pr_status_comment.js
// ile aynı girdi sözleşmesi, farklı çıktı hedefi).
//
// pr_status_comment.js pull_request'te koşar ve bulguları PR yorumuna yazar.
// Push build'lerde issue/PR numarası tanımsızdır — orada yorum atlanır ve
// durum yalnızca run sayfasında görünür. Bu script AYNI 7 girdiyi okur
// (budget/index.json, precommit_findings/PRECOMMIT_RAPORU.json,
// k0_findings.json, lineage_findings.json, klayers.json, k10_verdict.txt,
// reproducibility/manifest.json) ve bölüm rozetlerini GitHub Job Summary'ye
// (core.summary) yazar. REST'e hiç gitmez: issues.* çağrısı yapılmaması
// battery'de `no_rest_calls` kontratıyla sabitlenmiştir — yanlış job'a
// yazılmış yorum yerine sessiz koruma.
//
// Bölüm metinleri pr_status_comment.js ile birebir aynıdır (tek kaynak
// DEĞİL, bilinçli kopya: PR yorumu REST tabanlı state-sync yapar —
// yorum oluştur/güncelle/sil — run summary ise her koşuda yeniden yazılır;
// ortaklaştırma iki farklı çıktı yaşam döngüsünü tek soyutlamaya sıkıştırır.
// Sürüklenirse battery senaryoları `summary_contains` ile yakalar).
'use strict';

  const fs = require('fs');
  const BUDGET_PATH = 'budget/index.json';
  const PC_PATH = 'precommit_findings/PRECOMMIT_RAPORU.json';
  const K0_PATH = 'k0_findings.json';
  const LINEAGE_PATH = 'lineage_findings.json';
  const KLAYERS_PATH = 'klayers.json';
  const K10_VERDICT_PATH = 'k10_verdict.txt';
  const REPRO_MANIFEST_PATH = 'reproducibility/manifest.json';

  let budget = null;
  if (fs.existsSync(BUDGET_PATH)) {
    try { budget = JSON.parse(fs.readFileSync(BUDGET_PATH, 'utf8')); } catch (e) { console.log(`budget/index.json okunamadı: ${e.message} — degrade null`); }
  }
  let pc = null;
  if (fs.existsSync(PC_PATH)) {
    try { pc = JSON.parse(fs.readFileSync(PC_PATH, 'utf8')); } catch (e) { console.log(`precommit_findings/PRECOMMIT_RAPORU.json okunamadı: ${e.message} — degrade null`); }
  }
  let k0 = null;
  if (fs.existsSync(K0_PATH)) {
    try { k0 = JSON.parse(fs.readFileSync(K0_PATH, 'utf8')); } catch (e) { console.log(`k0_findings.json okunamadı: ${e.message} — degrade null`); }
  }
  let lineage = null;
  if (fs.existsSync(LINEAGE_PATH)) {
    try { lineage = JSON.parse(fs.readFileSync(LINEAGE_PATH, 'utf8')); } catch (e) { console.log(`lineage_findings.json okunamadı: ${e.message} — degrade null`); }
  }
  let klayers = null;
  if (fs.existsSync(KLAYERS_PATH)) {
    try { klayers = JSON.parse(fs.readFileSync(KLAYERS_PATH, 'utf8')); } catch (e) { console.log(`klayers.json okunamadı: ${e.message} — degrade null`); }
  }
  const hasReproManifest = fs.existsSync(REPRO_MANIFEST_PATH);
  const k10Verdict = fs.existsSync(K10_VERDICT_PATH)
    ? fs.readFileSync(K10_VERDICT_PATH, 'utf8').trim() : null;

  // ── Bütçe bölümü ──
  const budgetLines = [];
  let budgetBadge;
  const cliOverrides = budget && budget.cli_overrides
    ? (budget.cli_overrides.overrides || []) : [];
  const hasCliOverride = budget && budget.cli_overrides
    && budget.cli_overrides.warning && cliOverrides.length;
  if (budget) {
    const failures = budget.failures || [];
    const runs = budget.runs || [];
    if (failures.length) {
      budgetBadge = '⚠️ **Bütçe: limit aşıldı**';
      for (const f of failures) {
        budgetLines.push(
          `- **${f.source || 'bilinmeyen'}**: $${f.estimated_usd} / $${f.limit} limiti ` +
          `(+$${(f.estimated_usd - f.limit).toFixed(2)} aşım, ~${f.tokens_est} token)`);
      }
      if (hasCliOverride) {
        budgetLines.push('');
        budgetLines.push('🔧 **CLI override tespit edildi — bütçe kalkanı dosya '
          + 'config değeriyle DEĞİL CLI değeriyle koştu (tekrarlanabilirlik '
          + 'sapması, aşımın olası nedeni):**');
        for (const o of cliOverrides) {
          budgetLines.push(
            `- \`${o.key}\`: ${JSON.stringify(o.file_value)} → ` +
            `${JSON.stringify(o.effective)} (CLI verildi)`);
        }
      }
    } else {
      budgetBadge = '✅ **Bütçe: limit içinde**';
      for (const r of runs) {
        budgetLines.push(`- **${r.source || 'verify'}**: $${r.estimated_usd} / $${r.limit} (~${r.tokens_est} token)`);
      }
      if (hasCliOverride) {
        budgetLines.push('');
        budgetLines.push('🔧 **CLI override aktif** (tekrarlanabilirlik sapması):');
        for (const o of cliOverrides) {
          budgetLines.push(
            `- \`${o.key}\`: ${JSON.stringify(o.file_value)} → ` +
            `${JSON.stringify(o.effective)} (CLI verildi)`);
        }
      }
    }
    if (budget.method) budgetLines.push(`> Yöntem: \`${budget.method}\``);
  } else {
    budgetBadge = '⚠️ **Bütçe: sidecar bulunamadı**';
  }

  // ── Pre-commit bölümü ──
  const pcLines = [];
  let pcBadge;
  const pcFindings = pc ? (pc.findings || []) : [];
  const p0 = pcFindings.filter(f => f.priority === 'P0');
  const p1 = pcFindings.filter(f => f.priority === 'P1');
  if (pc) {
    if (p0.length || p1.length) {
      pcBadge = '🔴 **Pre-commit: bulgu var**';
      if (p0.length) {
        pcLines.push(`- 🔴 P0 (${p0.length})`);
        for (const f of p0) pcLines.push(`  - ${f.message}`);
      }
      if (p1.length) {
        pcLines.push(`- 🟠 P1 (${p1.length})`);
        for (const f of p1) pcLines.push(`  - ${f.message}`);
      }
    } else {
      pcBadge = '✅ **Pre-commit: bulgu yok**';
      const c = pc.counts || {};
      if (c.hooks != null && c.passed != null) {
        pcLines.push(`- ${c.passed}/${c.hooks} hook geçti`);
      }
    }
  } else {
    pcBadge = '⚠️ **Pre-commit: rapor bulunamadı**';
  }

  // ── K0 bayat zip bölümü ──
  const k0Lines = [];
  let k0Badge;
  if (k0) {
    const k0Count = k0.count || 0;
    if (k0Count > 0) {
      k0Badge = `🔴 **K0 bayat zip: ${k0Count} bulgu**`;
      for (const f of (k0.findings || [])) {
        k0Lines.push(`- \`${f.rel}\`  (\`${(f.sha256 || '?').slice(0, 16)}…\`)`);
      }
    } else {
      k0Badge = '✅ **K0 bayat zip: temiz**';
      k0Lines.push('- CIKTI dışında bayat zip bulunamadı');
    }
  } else {
    k0Badge = '⚠️ **K0 bayat zip: sidecar bulunamadı**';
  }

  // ── Soy hattı bölümü ──
  const lineageLines = [];
  let lineageBadge;
  if (lineage) {
    const gens = lineage.generations || [];
    const ok = !!lineage.ok;
    if (ok) {
      lineageBadge = `✅ **Soy hattı: ${gens.length} nesil doğrulandı**`;
    } else {
      lineageBadge = `🔴 **Soy hattı: doğrulama başarısız (${gens.length} nesil)**`;
    }
    const recent = gens.slice(-3);
    for (const g of recent) {
      const h = (g.hash || '?').slice(0, 16);
      const note = (g.note || '?').replace(/\|/g, '\\|');
      const icon = (g.status || '').startsWith('PASS') ? '✅' : '❌';
      lineageLines.push(`- ${icon} ${note} (\`${h}…\`)`);
    }
    if (gens.length > 3) {
      lineageLines.unshift(`- _…ve ${gens.length - 3} önceki nesil_`);
    }
  } else {
    lineageBadge = '⚠️ **Soy hattı: sidecar bulunamadı**';
  }

  // ── K katmanları bölümü ──
  const kLayerLines = [];
  let kLayerBadge;
  if (klayers && klayers.layers) {
    const layers = klayers.layers;
    const layerKeys = ['K1','K2','K3','K4','K5','K6','K7','K8','K9','K10','K11','K12','K13','K14','K16','K17'];
    let passCount = 0, failCount = 0, skipCount = 0;
    const failedLayers = [];
    for (const key of layerKeys) {
      const lyr = layers[key];
      if (!lyr) continue;
      const s = lyr.status || 'SKIP';
      if (s === 'PASS') passCount++;
      else if (s === 'FAIL') { failCount++; failedLayers.push(`${key}: ${lyr.label || '?'}`); }
      else skipCount++;
    }
    if (failCount > 0) {
      kLayerBadge = `🔴 **K katmanları: ${failCount} FAIL**`;
      for (const fl of failedLayers) kLayerLines.push(`- ❌ ${fl}`);
    } else {
      kLayerBadge = `✅ **K katmanları: ${passCount} PASS**` +
        (skipCount > 0 ? `, ${skipCount} SKIP` : '');
    }
  } else {
    kLayerBadge = '⚠️ **K katmanları: sidecar bulunamadı**';
  }

  // ── Reproducibility manifest bölümü (K10 digest + bundle varlığı) ──
  const reproLines = [];
  let reproBadge;
  if (!hasReproManifest || !k10Verdict) {
    reproBadge = '⚠️ **Reproducibility manifest: denetim çalışmadı**';
  } else if (k10Verdict === 'PASS') {
    reproBadge = '✅ **Reproducibility manifest: PASS**';
    reproLines.push('- manifest.json + manifest.sha256 bundle bütünlüğü K10 ile doğrulandı');
  } else if (k10Verdict === 'FAIL') {
    reproBadge = '❌ **Reproducibility manifest: FAIL**';
    reproLines.push("- K10 manifest digest FAIL — bundle hash'i doğrulanamadı");
  } else {
    reproBadge = `⚠️ **Reproducibility manifest: ${k10Verdict}**`;
    reproLines.push('- k10_verdict.txt beklenmeyen değer taşıyor');
  }

  // ── Commit-msg bölümü (bilgi amaçlı — precommit raporundan) ──
  const cmLines = [];
  let cmBadge;
  const cm = pc && pc.commit_msg ? pc.commit_msg : null;
  if (cm) {
    const violations = cm.violations || [];
    const checked = cm.checked || 0;
    cmBadge = violations.length
      ? `🟠 **Commit-msg: ${violations.length} ihlal** (${checked} commit denetlendi)`
      : `✅ **Commit-msg: temiz** (${checked} commit denetlendi)`;
    for (const v of violations) {
      const sha = (v.commit || '?').slice(0, 12);
      const subj = (v.subject || '?').replace(/\|/g, '\\|');
      cmLines.push(`- \`${sha}\` ${subj}`);
    }
  } else {
    cmBadge = '⏭️ **Commit-msg: denetim çalışmadı**';
  }

  // ── Job Summary'ye yaz (REST çağrısı YOK — push-safe kontrat) ──
  const runUrl = `${context.payload.repository.html_url}/actions/runs/${context.runId}`;
  const body = [
    '## 📊 Doğrulama durumu (run summary — push-safe varyant)',
    '',
    '### 💰 Bütçe',
    budgetBadge,
    ...budgetLines,
    '',
    '### 🛡️ Pre-commit',
    pcBadge,
    ...pcLines,
    '',
    '### 📝 Commit-msg',
    cmBadge,
    ...cmLines,
    '',
    '### 🔍 K0 bayat zip',
    k0Badge,
    ...k0Lines,
    '',
    '### 🧬 Soy hattı',
    lineageBadge,
    ...lineageLines,
    '',
    '### 📦 K katmanları',
    kLayerBadge,
    ...kLayerLines,
    '',
    '### 📦 Reproducibility manifest',
    reproBadge,
    ...reproLines,
    '',
    `> Detay: [run #${context.runId}](${runUrl})`,
  ].join('\n');

  await core.summary.addRaw(body).write();
  console.log("Doğrulama durumu Job Summary'ye yazıldı (REST çağrısı yok)");
