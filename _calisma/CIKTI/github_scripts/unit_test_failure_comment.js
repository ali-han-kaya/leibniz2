// unit_test_failure_comment.js — unit_tests.log'dan FAIL/ERROR satırlarını ayrıştırıp PR yorumu üretir.
// verify.yml'deki inline github-script adımının yerine kullanılır (async eval wraptest).
const fs = require('fs');

const marker = '<!-- unit-test-failures -->';

module.exports = async ({ github, context }) => {
  let log = '';
  try { log = fs.readFileSync('unit_tests.log', 'utf8'); } catch {}
  if (!log) return;

  const lines = log.split('\n');
  const failures = [];
  for (let i = 0; i < lines.length; i++) {
    const m = lines[i].match(/^(\S+) \(\S+\) \.\.\. (FAIL|ERROR)$/);
    if (m) {
      const detail = [];
      for (let j = i + 1; j < lines.length; j++) {
        if (/^=/.test(lines[j]) || /^\S+ \(\S+\) \.\.\./.test(lines[j])) break;
        detail.push(lines[j]);
      }
      failures.push({
        test: m[1], status: m[2],
        detail: detail.join('\n').trim().slice(0, 300)
      });
    }
  }
  if (!failures.length) return;

  const p0 = failures.filter(f => f.status === 'ERROR');
  const p1 = failures.filter(f => f.status === 'FAIL');
  let body = `## 🧪 Unit Test Düşenler\n\n`;
  body += `**${failures.length}** düşen test (ERROR: ${p0.length}, FAIL: ${p1.length})\n\n`;
  body += `| Durum | Test | Detay |\n|-------|------|-------|\n`;
  for (const f of failures) {
    const icon = f.status === 'ERROR' ? '🔴' : '🟡';
    const det = (f.detail.split('\n')[0] || '—').slice(0, 80).replace(/\|/g, '\\|');
    body += `| ${icon} ${f.status} | \`${f.test}\` | ${det} |\n`;
  }
  body += `\n<details><summary>Log excerpt</summary>\n\n\`\`\`\n${log.slice(-2000)}\n\`\`\`\n</details>`;

  // Upsert: mevcut yorumu bul veya yeni aç
  const { data: comments } = await github.rest.issues.listComments({
    owner: context.repo.owner, repo: context.repo.repo,
    issue_number: context.issue.number, per_page: 100
  });
  const existing = comments.find(c => c.body.includes(marker));
  if (existing) {
    await github.rest.issues.updateComment({
      owner: context.repo.owner, repo: context.repo.repo,
      comment_id: existing.id, body: marker + '\n' + body
    });
  } else {
    await github.rest.issues.createComment({
      owner: context.repo.owner, repo: context.repo.repo,
      issue_number: context.issue.number, body: marker + '\n' + body
    });
  }
};
