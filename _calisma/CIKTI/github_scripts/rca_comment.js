// rca_comment.js — kırmızı koşum için RCA tablosunu PR yorumuna düşürür.
//
// Girdi: rca_report.py'nin yazdığı JSON (varsayılan `rca_failures.json`,
// RCA_INPUT env'iyle değiştirilebilir):
//   {run_id, workflow, verdict, required_failures, advisory_failures,
//    rows: [{job, severity, pattern, pattern_detail, root_cause, rca_doc,
//            action, evidence}]}
//
// Neden ayrı script: sınıflandırma Python'da (ci_failure_pattern ile TEK
// kural), render + upsert burada. github_scripts deseninin tamamı:
//   · tek marker → idempotent upsert (aynı koşum ikinci yorum üretmez)
//   · düşen job yok → bayat marker yorumu SİLİNİR (state-sync)
//   · PR yoksa (push/schedule koşumu) hiçbir şey yapılmaz, hata da atılmaz
//   · yorum hatası run'ı düşürmez (setFailed yok — kanıt yorumu, kapı değil)
//
// Stil: globals (github / context / EXISTING_COMMENTS) — github-script@v8
// scriptPath DESTEKLEMEZ, bu yüzden gövde eval ile çalıştırılır; batarya
// (github_scripts_selftest.js) de aynı stili çalıştırır.
const fs = require('fs');

const MARKER = '<!-- ci-rca -->';
const INPUT = (typeof RCA_INPUT !== 'undefined' && RCA_INPUT) || 'rca_failures.json';

const esc = (s) =>
  String(s == null ? '' : s).replace(/\|/g, '\\|').replace(/\n/g, ' ');

// Hedef PR: workflow_run payload'ı (PR koşumu) → PR yorumu; yoksa push/schedule.
const targetPr = () => {
  const prs = context.payload && context.payload.workflow_run &&
              context.payload.workflow_run.pull_requests;
  if (prs && prs.length && prs[0].number) return prs[0].number;
  if (context.issue && context.issue.number) return context.issue.number;
  if (typeof PR_NUMBER !== 'undefined' && PR_NUMBER) return PR_NUMBER;
  return null;
};

const readReport = () => {
  try {
    if (!fs.existsSync(INPUT)) return null;
    return JSON.parse(fs.readFileSync(INPUT, 'utf8'));
  } catch (e) {
    console.log(`RCA girdisi okunamadı (${INPUT}): ${e.message}`);
    return null;
  }
};

const report = readReport();
  const pr = targetPr();

  if (!pr) {
    console.log('NOT: koşum bir PR\'a ait değil — yorum düşülmez');
    return;
  }

  const { data: comments } = await github.rest.issues.listComments({
    issue_number: pr,
    owner: context.repo.owner,
    repo: context.repo.repo,
    per_page: 100,
  });
  const all = (typeof EXISTING_COMMENTS !== 'undefined' && EXISTING_COMMENTS)
    ? EXISTING_COMMENTS : comments;

  // Girdi yok ya da düşen job yok → bayat tablo kalmasın (state-sync).
  if (!report || !report.rows || report.rows.length === 0) {
    let deleted = 0;
    for (const c of all) {
      if (c.body && c.body.includes(MARKER)) {
        await github.rest.issues.deleteComment({
          comment_id: c.id,
          owner: context.repo.owner,
          repo: context.repo.repo,
        });
        deleted++;
      }
    }
    console.log(`RCA yorumu yok — ${deleted} bayat yorum temizlendi`);
    return;
  }

  const blocking = report.verdict === 'blocking';
  const lines = [
    blocking
      ? `## 🔴 RCA — merge'i **bloklayan** kırmızı (run [#${report.run_id}](${report.rows[0].evidence}))`
      : `## 🟡 RCA — yalnız **advisory** kırmızı (run [#${report.run_id}](${report.rows[0].evidence}))`,
    '',
    blocking
      ? `**${report.required_failures}** zorunlu kontrol kırmızı → bu koşum merge'i durdurur.`
      : `Zorunlu kontrol kırmızısı yok (${report.advisory_failures} advisory) → merge'i durdurmaz; yine de kayda geçer.`,
    '',
    '| Job | Önem | Desen | Kök neden (RCA) | Belge | Önerilen adım |',
    '|---|---|---|---|---|---|',
  ];
  for (const r of report.rows) {
    const sev =
      r.severity === 'required' ? '🔴 required' :
      r.severity === 'advisory' ? '🟡 advisory' : '⚪ unknown';
    lines.push(
      `| ${esc(r.job)} | ${sev} | \`${esc(r.pattern)}\` | ${esc(r.root_cause)} | ` +
        `${r.rca_doc ? '`' + esc(r.rca_doc) + '`' : '—'} | ${esc(r.action)} |`
    );
  }
  const body = lines.join('\n') + '\n\n' + MARKER;

  const existing = all.find((c) => c.body && c.body.includes(MARKER));
  if (existing) {
    await github.rest.issues.updateComment({
      comment_id: existing.id,
      owner: context.repo.owner,
      repo: context.repo.repo,
      body,
    });
    console.log(`RCA yorumu güncellendi: comment_id=${existing.id}`);
  } else {
    await github.rest.issues.createComment({
      issue_number: pr,
      owner: context.repo.owner,
      repo: context.repo.repo,
      body,
    });
    console.log('RCA yorumu oluşturuldu');
  }
