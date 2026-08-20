  const fs = require('fs');
  const BUDGET_PATH = 'budget/index.json';
  const PC_PATH = 'precommit_findings/PRECOMMIT_RAPORU.json';
  const MARKER = '<!-- stoic-hume-v5-pr-status -->';

  const budget = fs.existsSync(BUDGET_PATH)
    ? JSON.parse(fs.readFileSync(BUDGET_PATH, 'utf8'))
    : null;
  const pc = fs.existsSync(PC_PATH)
    ? JSON.parse(fs.readFileSync(PC_PATH, 'utf8'))
    : null;

  // ── Bütçe bölümü ──
  // CLI override + aşım BİRLİKTEYSE tek uyarı bloğunda gösterilir:
  // aşımın olası nedeni (bütçe kalkanı dosya config yerine CLI değeriyle
  // koşmuş) görünür olur — override bilgisi budget/index.json'un
  // cli_overrides alanından gelir (check_cli_overrides.py yazar).
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
      // Aşım + CLI override → aynı blokta neden-görünürlüğü (tek uyarı).
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
      // Aşım YOK ama override var → override yine görünür (bilgilendirme),
      // tek blok değil ama aynı bütçe bölümünde.
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

  // ── Tek yorum (upsert) ──
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
    `> Detay: [run #${context.runId}](${runUrl})`,
    '',
    MARKER,
  ].join('\n');

  const { data: comments } = await github.rest.issues.listComments({
    issue_number: context.issue.number,
    owner: context.repo.owner,
    repo: context.repo.repo,
    per_page: 100,
  });
  const existing = comments.find(c => c.body && c.body.includes(MARKER));
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
