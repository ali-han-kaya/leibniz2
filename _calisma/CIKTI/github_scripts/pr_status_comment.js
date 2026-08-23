  const fs = require('fs');
  const BUDGET_PATH = 'budget/index.json';
  const PC_PATH = 'precommit_findings/PRECOMMIT_RAPORU.json';
  const K0_PATH = 'k0_findings.json';
  const LINEAGE_PATH = 'lineage_findings.json';
  const KLAYERS_PATH = 'klayers.json';
  const K10_VERDICT_PATH = 'k10_verdict.txt';
  const REPRO_MANIFEST_PATH = 'reproducibility/manifest.json';
  const MARKER = '<!-- stoic-hume-v5-pr-status -->';

  const budget = fs.existsSync(BUDGET_PATH)
    ? JSON.parse(fs.readFileSync(BUDGET_PATH, 'utf8'))
    : null;
  const pc = fs.existsSync(PC_PATH)
    ? JSON.parse(fs.readFileSync(PC_PATH, 'utf8'))
    : null;
  const k0 = fs.existsSync(K0_PATH)
    ? JSON.parse(fs.readFileSync(K0_PATH, 'utf8'))
    : null;
  const lineage = fs.existsSync(LINEAGE_PATH)
    ? JSON.parse(fs.readFileSync(LINEAGE_PATH, 'utf8'))
    : null;
  const klayers = fs.existsSync(KLAYERS_PATH)
    ? JSON.parse(fs.readFileSync(KLAYERS_PATH, 'utf8'))
    : null;
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

  // ── Commit-msg bölümü ──
  const cmLines = [];
  let cmBadge;
  const cm = pc && pc.commit_msg ? pc.commit_msg : null;
  if (cm) {
    const violations = cm.violations || [];
    const checked = cm.checked || 0;
    if (violations.length) {
      cmBadge = `🟠 **Commit-msg: ${violations.length} ihlal** (${checked} commit denetlendi)`;
      for (const v of violations) {
        const sha = (v.commit || '?').slice(0, 12);
        const subj = (v.subject || '?').replace(/\|/g, '\\|');
        cmLines.push(`- \`${sha}\` ${subj}`);
        if (v.detail) cmLines.push(`  - ${v.detail}`);
      }
    } else {
      cmBadge = `✅ **Commit-msg: temiz** (${checked} commit denetlendi)`;
    }
  } else {
    cmBadge = '⏭️ **Commit-msg: denetim çalışmadı**';
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
  // k10_verdict.txt (reproducibility job'ının K10 manifest.sha256 doğrulama
  // sonucu: PASS/FAIL) + reproducibility/manifest.json varlığı. K10 PASS iken
  // manifest bundle'ı SHA-256 ile doğrulanmıştır; FAIL ise bütünlük ihlali.
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

  // ── Etiket senkronu (precommit-p0 / precommit-p1) ──
  const LABELS = [
    { label: 'precommit-p0', has: p0.length > 0 },
    { label: 'precommit-p1', has: p1.length > 0 },
  ];
  const labels = await github.rest.issues.listLabelsOnIssue({
    issue_number: context.issue.number,
    owner: context.repo.owner,
    repo: context.repo.repo,
  });
  for (const L of LABELS) {
    const hasLabel = labels.data.some(l => l.name === L.label);
    if (L.has && !hasLabel) {
      await github.rest.issues.addLabels({
        issue_number: context.issue.number,
        owner: context.repo.owner,
        repo: context.repo.repo,
        labels: [L.label],
      });
      console.log(`Etiket eklendi: ${L.label}`);
    } else if (!L.has && hasLabel) {
      await github.rest.issues.removeLabel({
        issue_number: context.issue.number,
        owner: context.repo.owner,
        repo: context.repo.repo,
        name: L.label,
      });
      console.log(`Etiket kaldırıldı: ${L.label}`);
    }
  }

  // ── State-sync: bulgu yoksa bayat yorumu sil ──
  // Tüm bulgular çözüldüyse (bütçe aşımsız, P0/P1 yok, K0 temiz,
  // soy hattı başarılı, K katmanları FAIL yok) bayat uyarı yorumu
  // yanıltıcı kalmasın — config_diff_comment.js aynı deseni kullanır.
  const hasBudgetOverflow = budget && (budget.failures || []).length > 0;
  const hasP0P1 = p0.length > 0 || p1.length > 0;
  const hasK0Findings = k0 && (k0.count || 0) > 0;
  const hasLineageFail = lineage && !lineage.ok;
  let hasKlayersFail = false;
  if (klayers && klayers.layers) {
    for (const key of ['K1','K2','K3','K4','K5','K6','K7','K8','K9','K10','K11','K12','K13','K14','K16','K17']) {
      const lyr = klayers.layers[key];
      if (lyr && lyr.status === 'FAIL') { hasKlayersFail = true; break; }
    }
  }
  const hasCommitMsgViolations = cm && (cm.violations || []).length > 0;
  const hasReproFindings = !hasReproManifest || !k10Verdict
    || k10Verdict !== 'PASS';
  const hasMissingSidecars = !budget || !pc || !k0 || !lineage || !klayers;
  const hasAnyFindings = hasBudgetOverflow || hasP0P1 || hasK0Findings
    || hasLineageFail || hasKlayersFail || hasMissingSidecars || hasCliOverride
    || hasCommitMsgViolations || hasReproFindings;

  const { data: comments } = await github.rest.issues.listComments({
    issue_number: context.issue.number,
    owner: context.repo.owner,
    repo: context.repo.repo,
    per_page: 100,
  });

  // ── Geçiş temizliği: eski precommit-p0-bot / precommit-p1-bot marker'lı ──
  const LEGACY_MARKERS = [
    '<!-- precommit-p0-bot -->',
    '<!-- precommit-p1-bot -->',
  ];
  for (const c of comments) {
    if (!c.body) continue;
    const isLegacy = LEGACY_MARKERS.some(m => c.body.includes(m));
    const isCurrent = c.body.includes(MARKER);
    if (isLegacy && !isCurrent) {
      await github.rest.issues.deleteComment({
        comment_id: c.id,
        owner: context.repo.owner,
        repo: context.repo.repo,
      });
      console.log(`Eski bot yorumu silindi: comment_id=${c.id}`);
    }
  }

  const existing = comments.find(c => c.body && c.body.includes(MARKER));

  if (!hasAnyFindings) {
    // Tüm bulgular çözüldü: mevcut yorum varsa sil (state-sync).
    if (existing) {
      await github.rest.issues.deleteComment({
        comment_id: existing.id,
        owner: context.repo.owner,
        repo: context.repo.repo,
      });
      console.log(`Bulgular çözüldü — bayat yorum kaldırıldı: comment_id=${existing.id}`);
    } else {
      console.log('Bulgular çözüldü — yorum yok (temiz)');
    }
    return;
  }

  // Bulgu var: yorumu oluştur veya güncelle.
  const runUrl = `${context.payload.repository.html_url}/actions/runs/${context.runId}`;
  const body = [
    '## 📊 PR doğrulama durumu (advisory)',
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
    '',
    MARKER,
  ].join('\n');

  if (existing) {
    await github.rest.issues.updateComment({
      comment_id: existing.id,
      owner: context.repo.owner,
      repo: context.repo.repo,
      body,
    });
    console.log(`Mevcut durum yorumu güncellendi: comment_id=${existing.id}`);
  } else {
    await github.rest.issues.createComment({
      issue_number: context.issue.number,
      owner: context.repo.owner,
      repo: context.repo.repo,
      body,
    });
    console.log('Durum yorumu oluşturuldu');
  }
